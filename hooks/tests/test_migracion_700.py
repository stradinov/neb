#!/usr/bin/env python3
"""
test_migracion_700.py — la migración guiada de neb 7.0.0 (migrations/7.0.0.py) por bootstrap/neb-migrate.py.

Cubre, con el árbol real y homes temporales:
  • 7.0.0:renombrar-base de punta a punta con `apply --guiados`: cambia el nombre, su respaldo pasa la
    comprobación del respaldo declarado y después corren los pasos de base (el 2, con su respaldo);
  • su condición propia sobre neb-logbook.db: con otra conexión abierta queda pendiente sin llamar al
    migrador; un os.replace fallido lo deja pendiente; la base vieja que reaparece con escrituras lo deja
    en manual (con la base ya renombrada y migrada);
  • con la base sin migrar, `apply` sin --guiados, `skip` y el borrado de omisiones no crean neb.db, y
    `status` responde sin-migrar sin abrir la base vieja;
  • quitar-logbook-settings: solo el endpoint corre solo y su respaldo guarda ese par; con el token va al
    menú y corre sin respaldo con --include, sin que el valor salga en la salida;
  • quitar-endpoint-entorno y quitar-token-entorno van al menú;
  • borrar-respaldos-settings: encuentra los settings.json.bak-neb-* que traen el nombre del token, con sus
    topes de archivos y de bytes, sin sacar su contenido; va al menú y borra solo esos.

Nunca toca ~/.claude ni el registro real: el entorno de usuario es un doble en memoria.
  py -m unittest discover -s hooks/tests -p test_migracion_700.py
"""

import contextlib
import glob
import hashlib
import importlib.util
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sin_registro  # noqa: E402,F401 — sin el registro real de Windows
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
NEB = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(NEB, "hooks", "lib"))

import _db_shared  # noqa: E402
import _guided  # noqa: E402
import _machine  # noqa: E402
import _migrations  # noqa: E402

SCHEMA = os.path.join(NEB, "hooks", "logbook-schema.sql")
V = "7.0.0"
TOKEN_VALUE = "tok-7f3a-valor-que-no-sale"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


nm = _load("neb_migrate_700_test", os.path.join(NEB, "bootstrap", "neb-migrate.py"))


class FakeUserEnv:
    kind = "windows"

    def __init__(self):
        self.user = {}

    def present_user(self, name):
        return name in self.user

    def present_machine(self, name):
        return False

    def delete_user(self, name):
        del self.user[name]

    def broadcast(self):
        pass


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


class Base(unittest.TestCase):

    def setUp(self):
        p = mock.patch.dict(os.environ)
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop("CLAUDE_CONFIG_DIR", None)
        self.home = tempfile.mkdtemp(prefix="neb-test-700-")
        self.addCleanup(shutil.rmtree, self.home, True)
        self.claude = os.path.join(self.home, ".claude")
        os.makedirs(self.claude)
        self.legacy = os.path.join(self.claude, "neb-logbook.db")
        self.db = os.path.join(self.claude, "neb.db")
        self.env = FakeUserEnv()
        p = mock.patch.object(_machine, "default_user_env", lambda: self.env)
        p.start()
        self.addCleanup(p.stop)

    def legacy_645(self, rows=2):
        """neb-logbook.db como la deja 6.45.0: el esquema inicial (en WAL), sin tabla de versión."""
        c = sqlite3.connect(self.legacy)
        with open(SCHEMA, encoding="utf-8") as fh:
            c.executescript(fh.read())
        for i in range(rows):
            c.execute("INSERT INTO work (mode, project, req_slug, owner, created_at, updated_at) "
                      "VALUES ('req', 'p', ?, 'dev', 't', 't')", (f"r{i}",))
        c.commit()
        c.close()

    def neb_db(self):
        with contextlib.redirect_stderr(io.StringIO()):
            _db_shared._connect(self.db).close()

    def run_nm(self, fn, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = fn(self.home, *args)
        return rc, out.getvalue()

    def apply(self, include=(), guiados=True):
        rc, out = self.run_nm(nm.apply, include, False, guiados)
        return rc, json.loads(out), out

    def by_id(self, guided):
        return {bucket: {r["id"].split(":", 1)[1]: r for r in guided[bucket]}
                for bucket in ("aplicados", "pendientes", "manual", "fallos")}

    def settings(self, env):
        with open(os.path.join(self.claude, "settings.json"), "w", encoding="utf-8") as fh:
            json.dump({"env": env, "model": "x"}, fh)

    def settings_env(self):
        with open(os.path.join(self.claude, "settings.json"), encoding="utf-8") as fh:
            return json.load(fh)["env"]

    def files(self):
        return sorted(os.listdir(self.claude))

    def pending(self):
        g = nm.status(self.home)["guiados"]
        return {r["id"].split(":", 1)[1]: r for r in g["pendientes"] if r["version"] == V}


# =========================================================================== renombrar-base

class TestRenombrarBase(Base):

    def test_base_vieja_que_no_es_sqlite_queda_en_manual(self):
        with open(self.legacy, "wb") as fh:
            fh.write(b"x" * 4096)
        rc, out, _raw = self.apply()
        self.assertIn("no es una base usable", self.by_id(out["guiados"])["manual"]["renombrar-base"]["detalle"])
        self.assertEqual(self.files(), ["neb-logbook.db"])

    def test_si_la_base_renombrada_no_abre_el_reporte_conserva_los_guiados(self):
        self.legacy_645(rows=2)
        err = {"ok": False, "motivo": "sin-conexion", "detalle": "x", "accion": "y"}
        with mock.patch.object(nm, "_open_for_apply", lambda db: (None, err)):
            rc, out, _raw = self.apply()
        self.assertEqual(rc, 1)
        self.assertEqual(out["motivo"], "sin-conexion")
        r = self.by_id(out["guiados"])["aplicados"]["renombrar-base"]
        self.assertTrue(r["respaldo"])

    def test_critico_apply_guiados_cambia_el_nombre_y_corren_los_pasos_de_base(self):
        self.legacy_645(rows=2)
        rc, out, _raw = self.apply()
        self.assertEqual(rc, 0, out)
        self.assertTrue(out["ok"])
        b = self.by_id(out["guiados"])
        self.assertIn("renombrar-base", b["aplicados"], out)
        bak = b["aplicados"]["renombrar-base"]["respaldo"]
        self.assertEqual(os.path.dirname(bak), self.claude)
        self.assertTrue(os.path.basename(bak).startswith("neb-logbook.db.bak-"))
        self.assertFalse(os.path.exists(self.legacy))
        self.assertEqual(out["schema_version_db"], _migrations.SCHEMA_VERSION)
        c = sqlite3.connect(self.db)
        try:
            cols = {r[1] for r in c.execute("PRAGMA table_info(work)")}
            self.assertEqual(c.execute("SELECT count(*) FROM work").fetchone()[0], 2)
            self.assertIsNone(c.execute("SELECT 1 FROM sqlite_master WHERE name='event'").fetchone())
        finally:
            c.close()
        self.assertNotIn("owner", cols)
        # La poda es por paso: queda el último respaldo de cada paso destructivo (el 2 de 7.0.0 y el 3 de 7.3.0).
        baks = sorted(os.path.basename(p) for p in
                      glob.glob(os.path.join(glob.escape(self.claude), "neb-backups", "neb.pre-paso-*.db")))
        self.assertEqual([b.split(".")[1] for b in baks], ["pre-paso-2", "pre-paso-3"], baks)
        self.assertNotIn("renombrar-base", self.pending())

    def test_critico_condicion_propia_con_la_base_vieja_abierta(self):
        self.legacy_645()
        other = sqlite3.connect(self.legacy)
        try:
            other.execute("SELECT count(*) FROM work").fetchone()
            rc, out, _raw = self.apply()
        finally:
            other.close()
        self.assertEqual(rc, 1)
        r = self.by_id(out["guiados"])["pendientes"]["renombrar-base"]
        self.assertTrue(r["detalle"].startswith("otra sesión tiene la base abierta: queda pendiente y se reintenta"),
                        r["detalle"])
        self.assertIsNone(r["respaldo"])
        self.assertEqual(self.files(), ["neb-logbook.db"])

    def test_os_replace_que_falla_lo_deja_pendiente(self):
        self.legacy_645()
        real = os.replace
        legacy = self.legacy

        def falla(src, dst):
            if os.path.abspath(src) == os.path.abspath(legacy):
                raise PermissionError(13, "El proceso no tiene acceso al archivo")
            return real(src, dst)
        with mock.patch.object(os, "replace", falla):
            rc, out, _raw = self.apply()
        self.assertEqual(rc, 1)
        r = self.by_id(out["guiados"])["pendientes"]["renombrar-base"]
        self.assertIn("no se pudo cambiar el nombre", r["detalle"])
        self.assertEqual(self.files(), ["neb-logbook.db"])

    def test_base_vieja_que_reaparece_con_escrituras_queda_en_manual(self):
        self.legacy_645()
        legacy = self.legacy
        real = _db_shared._probe_db

        def sonda(path):                # la verificación del migrador, justo después del cambio de nombre
            if os.path.isfile(path) and not os.path.exists(legacy):
                with open(legacy, "wb") as fh:
                    fh.write(b"x" * 4096)
            return real(path)
        with mock.patch.object(_db_shared, "_probe_db", sonda):
            rc, out, _raw = self.apply()
        r = self.by_id(out["guiados"])["manual"]["renombrar-base"]
        self.assertIn("esas capturas no están en neb.db", r["detalle"])
        self.assertTrue(r["respaldo"])
        self.assertEqual(out["schema_version_db"], _migrations.SCHEMA_VERSION, "neb.db ya renombrado y migrado")

    def test_status_sin_migrar_no_abre_la_base_vieja(self):
        self.legacy_645()
        before = (self.files(), _sha(self.legacy))
        s = nm.status(self.home)
        self.assertEqual(s["estado"], "sin-migrar")
        self.assertIn("nombre anterior a neb 7.0.0", s["detalle"])
        self.assertIn("/neb:migrate", s["accion"])
        r = self.pending()["renombrar-base"]
        self.assertEqual((r["clase"], r["exclusivo"]), ("solo", True))
        self.assertEqual((self.files(), _sha(self.legacy)), before)

    def test_critico_apply_sin_guiados_no_crea_neb_db(self):
        self.legacy_645()
        before = _sha(self.legacy)
        rc, raw = self.run_nm(nm.apply, (), False, False)
        out = json.loads(raw)
        self.assertEqual(rc, 1)
        self.assertEqual((out["ok"], out["motivo"]), (False, "base-sin-migrar"))
        self.assertIn("/neb:migrate", out["accion"])
        self.assertIn("migrate-neb-db.py", out["comando"])
        self.assertEqual(self.files(), ["neb-logbook.db"])
        self.assertEqual(_sha(self.legacy), before)

    def test_critico_skip_no_crea_neb_db(self):
        self.legacy_645()
        rc, raw = self.run_nm(nm.skip, V + ":quitar-token-entorno")
        out = json.loads(raw)
        self.assertEqual(rc, 1)
        self.assertEqual(out["motivo"], "base-sin-migrar")
        self.assertEqual(self.files(), ["neb-logbook.db"])

    def test_borrar_omisiones_sin_migrar_no_crea_neb_db(self):
        self.legacy_645()
        other = sqlite3.connect(self.legacy)       # renombrar-base queda pendiente: la base sigue sin migrar
        try:
            other.execute("SELECT count(*) FROM work").fetchone()
            key = V + ":borrar-respaldos-settings"
            out = nm._apply_guided(self.home, self.db, {key}, {key}, False)
        finally:
            other.close()
        self.assertEqual(out["omision_sin_borrar"], [key])
        self.assertEqual(self.files(), ["neb-logbook.db"])

    def test_sin_base_vieja_no_hay_nada_que_cambiar(self):
        self.neb_db()
        self.assertNotIn("renombrar-base", self.pending())


# =========================================================================== settings y entorno

class TestConfiguracionDelBackend(Base):

    def setUp(self):
        super().setUp()
        self.neb_db()

    def test_critico_solo_el_endpoint_corre_solo_y_su_respaldo_guarda_ese_par(self):
        self.settings({"NEB_LOGBOOK_ENDPOINT": "https://central.invalid", "OTRA": "y"})
        self.assertEqual(self.pending()["quitar-logbook-settings"]["clase"], "solo")
        rc, out, _raw = self.apply()
        self.assertEqual(rc, 0, out)
        r = self.by_id(out["guiados"])["aplicados"]["quitar-logbook-settings"]
        with open(r["respaldo"], encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["env"], {"NEB_LOGBOOK_ENDPOINT": "https://central.invalid"})
        self.assertEqual(self.settings_env(), {"OTRA": "y"})

    def test_critico_con_el_token_va_al_menu_y_corre_sin_respaldo(self):
        self.settings({"NEB_LOGBOOK_ENDPOINT": "https://central.invalid", "NEB_LOGBOOK_TOKEN": TOKEN_VALUE})
        self.assertEqual(self.pending()["quitar-logbook-settings"]["clase"], "dev")
        rc, out, raw = self.apply()
        self.assertEqual(rc, 0, out)
        self.assertIn("quitar-logbook-settings", self.by_id(out["guiados"])["pendientes"])
        self.assertEqual(set(self.settings_env()), {"NEB_LOGBOOK_ENDPOINT", "NEB_LOGBOOK_TOKEN"})
        rc, out, raw2 = self.apply(include=[V + ":quitar-logbook-settings"])
        self.assertEqual(rc, 0, out)
        r = self.by_id(out["guiados"])["aplicados"]["quitar-logbook-settings"]
        self.assertIsNone(r["respaldo"])
        self.assertEqual(self.settings_env(), {})
        for p in glob.glob(os.path.join(glob.escape(self.claude), "neb-backups", "*")):
            with open(p, "rb") as fh:
                self.assertNotIn(TOKEN_VALUE.encode(), fh.read(), p)
        for text in (raw, raw2, json.dumps(nm.status(self.home))):
            self.assertNotIn(TOKEN_VALUE, text)

    def test_variables_de_usuario_van_al_menu(self):
        self.env.user.update({"NEB_LOGBOOK_ENDPOINT": "x", "NEB_LOGBOOK_TOKEN": TOKEN_VALUE})
        p = self.pending()
        self.assertEqual((p["quitar-endpoint-entorno"]["clase"], p["quitar-token-entorno"]["clase"]),
                         ("dev", "dev"))
        rc, out, _raw = self.apply()
        self.assertEqual(set(self.env.user), {"NEB_LOGBOOK_ENDPOINT", "NEB_LOGBOOK_TOKEN"})
        rc, out, raw = self.apply(include=[V + ":quitar-endpoint-entorno", V + ":quitar-token-entorno"])
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.env.user, {})
        self.assertNotIn(TOKEN_VALUE, raw)


# =========================================================================== respaldos de settings.json

class TestRespaldosDeSettings(Base):

    def setUp(self):
        super().setUp()
        self.neb_db()
        self.step = {s.id: s for m in _guided.load(NEB)[0] if m.version == V for s in m.steps}[
            "borrar-respaldos-settings"]

    def bak(self, suffix, data):
        p = os.path.join(self.claude, "settings.json.bak-neb-" + suffix)
        with open(p, "wb") as fh:
            fh.write(data)
        return p

    def ctx(self):
        return _machine.Ctx(self.home, db_path=self.db, user_env=self.env)

    def test_critico_encuentra_solo_los_que_traen_el_token_y_va_al_menu(self):
        con = self.bak("1", json.dumps({"env": {"NEB_LOGBOOK_TOKEN": TOKEN_VALUE}}).encode())
        sin = self.bak("2", json.dumps({"env": {"OTRA": "y"}}).encode())
        os.makedirs(os.path.join(self.claude, "settings.json.bak-neb-3"))
        self.assertEqual(self.pending()["borrar-respaldos-settings"]["clase"], "dev")
        rc, out, raw = self.apply()
        self.assertIn("borrar-respaldos-settings", self.by_id(out["guiados"])["pendientes"])
        self.assertTrue(os.path.exists(con))
        rc, out, raw2 = self.apply(include=[V + ":borrar-respaldos-settings"])
        self.assertEqual(rc, 0, out)
        r = self.by_id(out["guiados"])["aplicados"]["borrar-respaldos-settings"]
        self.assertIn("borrados 1 respaldos", r["detalle"])
        self.assertFalse(os.path.exists(con))
        self.assertTrue(os.path.exists(sin))
        self.assertTrue(os.path.isdir(os.path.join(self.claude, "settings.json.bak-neb-3")))
        for text in (raw, raw2):
            self.assertNotIn(TOKEN_VALUE, text)

    def test_topes_de_bytes_y_de_archivos(self):
        g = self.step.detectar.__globals__
        self.bak("a", b" " * 64 + b"NEB_LOGBOOK_TOKEN")
        with mock.patch.dict(g, {"BAK_MAX_BYTES": 32}):
            self.assertFalse(self.step.detectar(self.ctx()))
        self.assertTrue(self.step.detectar(self.ctx()))
        self.bak("0", b"{}")                               # ordena antes que «a»
        with mock.patch.dict(g, {"BAK_MAX_FILES": 1}):
            # más respaldos que el tope: el paso no se da por hecho, y aplicarlo lo deja a mano
            self.assertTrue(self.step.detectar(self.ctx()))
            r = self.step.aplicar(self.ctx())
            self.assertEqual(r["estado"], "manual", r)
            self.assertIn("revisa a mano", r["detalle"])
            self.assertIn("borrados 0 respaldos", r["detalle"])
        self.assertTrue(os.path.exists(os.path.join(self.claude, "settings.json.bak-neb-a")))

    def test_corchetes_en_el_dir_de_configuracion_no_son_patron(self):
        raiz = tempfile.mkdtemp(prefix="neb-test-700b-")
        self.addCleanup(shutil.rmtree, raiz, True)
        propio = os.path.join(raiz, "dev[1]", ".claude")
        vecino = os.path.join(raiz, "dev1", ".claude")
        for d in (propio, vecino):
            os.makedirs(d)
        ajeno = os.path.join(vecino, "settings.json.bak-neb-x")
        with open(ajeno, "wb") as fh:
            fh.write(b"NEB_LOGBOOK_TOKEN")
        ctx = _machine.Ctx(os.path.dirname(propio), db_path=self.db, user_env=self.env)
        self.assertFalse(self.step.detectar(ctx))
        with open(os.path.join(propio, "settings.json.bak-neb-y"), "wb") as fh:
            fh.write(b"NEB_LOGBOOK_TOKEN")
        self.assertTrue(self.step.detectar(ctx))
        self.step.aplicar(ctx)
        self.assertTrue(os.path.exists(ajeno))
        self.assertFalse(os.path.exists(os.path.join(propio, "settings.json.bak-neb-y")))

    @unittest.skipUnless(hasattr(os, "symlink"), "sin enlaces simbólicos")
    def test_no_sigue_enlaces(self):
        target = os.path.join(self.home, "fuera.json")
        with open(target, "wb") as fh:
            fh.write(b"NEB_LOGBOOK_TOKEN")
        try:
            os.symlink(target, os.path.join(self.claude, "settings.json.bak-neb-l"))
        except OSError:
            self.skipTest("crear enlaces simbólicos pide permiso en esta máquina")
        self.assertFalse(self.step.detectar(self.ctx()))
        self.assertTrue(os.path.exists(target))


if __name__ == "__main__":
    unittest.main()
