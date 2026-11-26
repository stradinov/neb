#!/usr/bin/env python3
"""
test_migration_8_0_0.py — la migración guiada de neb 8.0.0 (migrations/8.0.0.py): la mudanza de lo que Neb
guardaba en ~/.claude a su carpeta de datos, con el árbol real y homes temporales.

Cubre:
  • la migración carga con sus ocho pasos, en orden, todos con respaldo; solo mover-base es exclusivo;
  • de punta a punta con `apply --guiados` y con `al-iniciar`: la base (con la testigo en su lugar), los respaldos
    (neb-backups/ y los sueltos con sus patrones exactos), compas.md, approved-plans/ (cualquier archivo),
    research/, el estado de preprocess y la caché de sonidos, .neb-requisitos.json y los tres JSON de configuración
    (en config.json) quedan en la carpeta de datos; lo de Claude Code (settings.json, projects/, backups/,
    plugins/) y lo que no es de Neb se quedan; cada manifiesto queda «hecho»; la segunda corrida no hace nada; la
    captura de este código escribe en la base mudada;
  • desde 7.2: un solo `apply --guiados` corre el compas de 7.3.0, muda, corre el paso de base 3 sobre la base
    mudada y, en la segunda pasada, la compactación de 7.3.0 y el tema de 7.4.0;
  • la base vieja con otra conexión: mover-base queda pendiente (sin respaldo ni testigo) y la guarda sigue; una
    base usable además de la mudada, o un archivo que no es base en ~/.claude/neb.db: manual, sin pisar nada;
  • homónimos distintos en el destino: no se pisan y el paso pide al dev; idénticos: se quita el origen;
  • fusionar-config: crea o completa config.json sin pisar una llave con otro valor (manual, nada escrito ni
    borrado), JSON ilegible (manual, nada tocado), BOM (utf-8-sig), respaldo con los textos originales;
  • el candado doble: con el candado viejo de ~/.claude tomado (una sesión 7.5–7.6) no corre nada; sin él no se
    crea; los dos se sueltan;
  • NEB_DATA en ~/.claude: no hay mudanza; los respaldos van a ~/.claude/neb-backups/, nunca a ~/.claude/backups/
    (de Claude Code);
  • el «no» del dev guardado en la base vieja se respeta mientras se muda, y sigue en la base mudada;
  • status con la base sin mudar; la siembra de la taxonomía con la base sin mudar responde su motivo sin crear
    nada.

Nunca toca ~/.claude ni ~/.neb reales (HOME/USERPROFILE temporales, sin NEB_DATA: _entorno) ni el registro real.
  py -m unittest discover -s hooks/tests -p test_migration_8_0_0.py
"""

import codecs
import contextlib
import glob
import importlib.util
import io
import json
import os
import shutil
import tempfile
import sqlite3
import subprocess
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _sin_registro  # noqa: E402,F401 — sin el registro real de Windows
import _entorno  # noqa: E402 — quita NEB_DATA: la carpeta de datos es la del home temporal

NEB = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(NEB, "hooks", "lib"))

import _db_shared  # noqa: E402
import _guided  # noqa: E402
import _machine  # noqa: E402
import _migrations  # noqa: E402
import _relocate  # noqa: E402

V = "8.0.0"
SCHEMA = os.path.join(NEB, "hooks", "logbook-schema.sql")
STEP_IDS = ["mover-base", "mover-respaldos", "mover-compas", "mover-planes", "mover-research", "mover-estado",
            "mover-requisitos", "fusionar-config"]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


nm = _load("neb_migrate_800_test", os.path.join(NEB, "bootstrap", "neb-migrate.py"))


def _migration():
    migrations, errors = _guided.load(NEB)
    assert not errors, errors
    return [m for m in migrations if m.version == V][0]


def _tree(root):
    """Rutas relativas (con /) de los archivos bajo root."""
    out = []
    for cur, _dirs, files in os.walk(root):
        for f in files:
            out.append(os.path.relpath(os.path.join(cur, f), root).replace(os.sep, "/"))
    return sorted(out)


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


COMPAS_V3 = ("---\nversion: 3\n---\n\n## Objetivo: Seguridad\n- **Peso:** 70\n- **Temas:** seguridad\n"
             "- **Proyectos:** alpha=+10\n")


class Base(unittest.TestCase):

    def setUp(self):
        p = mock.patch.dict(os.environ)
        p.start()
        self.addCleanup(p.stop)
        for k in ("CLAUDE_CONFIG_DIR", "CLAUDE_PROJECT_DIR", "NEB_HOME", "NEB_INTERNAL_SUBSESSION",
                  "CLAUDE_PREPROCESS_RECURSION", _entorno.DATA_ENV):
            os.environ.pop(k, None)
        self.home = _entorno.home_temporal(self, claude=True)
        os.environ.update(HOME=self.home, USERPROFILE=self.home)
        self.claude = os.path.join(self.home, ".claude")
        self.data = os.path.join(self.home, ".neb")
        self.old_db = os.path.join(self.claude, "neb.db")
        self.db = os.path.join(self.data, "neb.db")
        self.backups = os.path.join(self.data, "backups")
        self.env = FakeUserEnv()
        p = mock.patch.object(_machine, "default_user_env", lambda: self.env)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(nm, "_requisitos", lambda **kw: None)      # sin la oferta de instalar Python
        p.start()
        self.addCleanup(p.stop)

    # ------------------------------------------------------------------ armado

    def write(self, path, data=b"x"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if isinstance(data, str):
            data = data.encode("utf-8")
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def read(self, path):
        with open(path, "rb") as fh:
            return fh.read()

    def c(self, *parts):
        return os.path.join(self.claude, *parts)

    def d(self, *parts):
        return os.path.join(self.data, *parts)

    def make_old_db(self, rows=2):
        with contextlib.redirect_stderr(io.StringIO()):
            _db_shared._connect(self.old_db, SCHEMA).close()
        con = sqlite3.connect(self.old_db)
        for i in range(rows):
            con.execute("INSERT INTO work (mode, created_at, updated_at) VALUES ('exploratory', ?, ?)",
                        (f"2026-11-0{i + 1}", f"2026-11-0{i + 1}"))
        con.commit()
        con.close()

    def claude_code_files(self):
        """Lo de Claude Code, que la mudanza no toca: {ruta relativa a ~/.claude: bytes}."""
        files = {"settings.json": b'{"model": "x"}', "projects/p/s.jsonl": b"{}\n",
                 "backups/.claude.json.backup.1": b"de claude code", "plugins/installed.json": b"{}",
                 "neb-logbook.db": b"base de 6.x (sin soporte: se queda)", "notas.txt": b"del dev",
                 "neb.db.backup": b"no es un respaldo de neb con su patron"}
        for rel, data in files.items():
            self.write(self.c(*rel.split("/")), data)
        return files

    def legacy_layout(self):
        """Todo lo que 7.x dejaba en ~/.claude. Devuelve lo de Claude Code (que se queda)."""
        self.make_old_db()
        self.write(self.c("neb-backups", "neb.pre-paso-2.20260101T000000Z.db"), b"respaldo de paso")
        self.write(self.c("neb-backups", "compas.pre-7.4.0.20260101T000000Z.md"), b"compas viejo")
        for name in ("neb-logbook.db.bak-20251001", "neb-logbook.db.bak-20251001-wal",
                     "neb.pre-paso-1.20251001T000000Z.db", "neb.db.bak-pre-taxonomy-20251002T000000-1Z",
                     "neb-logbook.pre-paso-2.20251001T000000Z.db", "compas.md.bak-20251003"):
            self.write(self.c(name), name.encode("ascii"))
        self.write(self.c("compas.md"), COMPAS_V3)
        self.write(self.c("approved-plans", "2026-01-01-plan.md"), "# plan")
        self.write(self.c("approved-plans", "sub", "anexo.pdf"), b"%PDF")
        self.write(self.c("research", "tema", "notas.md"), "notas")
        self.write(self.c("preprocess-state", "sesion.json"), "{}")
        self.write(self.c("neb-sounds", "stop.wav"), b"RIFF")
        self.write(self.c(".neb-requisitos.json"), '{"no_ofrecer": []}')
        self.write(self.c("notify-on-stop.json"), codecs.BOM_UTF8 + b'{"enabled": true, "wav": "C:/a.wav"}')
        self.write(self.c("notify-on-permission.json"), '{"enabled": false}')
        self.write(self.c("preprocess.json"), '{"mode": "off"}')
        return self.claude_code_files()

    # ------------------------------------------------------------------ corridas

    def apply(self, include=(), sin_exclusivos=False, guiados=True):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = nm.apply(self.home, include, sin_exclusivos, guiados)
        return rc, json.loads(out.getvalue())

    def al_iniciar(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = nm.al_iniciar(self.home)
        self.assertEqual(rc, 0)
        return out.getvalue()

    @staticmethod
    def ids(rows):
        return sorted(r["id"] for r in rows)

    def count(self, path, table="work"):
        con = sqlite3.connect(path)
        try:
            return con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        finally:
            con.close()

    def assert_moved(self, claude_code):
        """La disposición tras la mudanza completa."""
        self.assertEqual(_db_shared._probe_db(self.db), "usable")
        self.assertEqual(self.count(self.db), 2)
        self.assertTrue(_relocate.is_witness(self.old_db), "la testigo ocupa el lugar de la base")
        backups = _tree(self.backups)
        for name in ("neb.pre-paso-2.20260101T000000Z.db", "compas.pre-7.4.0.20260101T000000Z.md",
                     "neb-logbook.db.bak-20251001", "neb-logbook.db.bak-20251001-wal",
                     "neb.pre-paso-1.20251001T000000Z.db", "neb.db.bak-pre-taxonomy-20251002T000000-1Z",
                     "neb-logbook.pre-paso-2.20251001T000000Z.db", "compas.md.bak-20251003"):
            self.assertIn(name, backups)
        self.assertEqual(len(glob.glob(os.path.join(self.backups, "neb.pre-8.0.0.*.db"))), 1)
        self.assertEqual(len(glob.glob(os.path.join(self.backups, "config-sources.pre-8.0.0.*.json"))), 1)
        manifests = sorted(glob.glob(os.path.join(self.backups, "manifest-8.0.0.*.json")))
        self.assertEqual(sorted(os.path.basename(m).split(".")[3] for m in manifests),
                         sorted(["mover-respaldos", "mover-compas", "mover-planes", "mover-research",
                                 "mover-estado", "mover-requisitos"]))
        for m in manifests:
            with open(m, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh)["estado"], "hecho", m)
        self.assertEqual(self.read(self.d("compas.md")).decode("utf-8"), COMPAS_V3)
        self.assertEqual(_tree(self.d("approved-plans")), ["2026-01-01-plan.md", "sub/anexo.pdf"])
        self.assertEqual(_tree(self.d("research")), ["tema/notas.md"])
        self.assertEqual(_tree(self.d("state", "preprocess")), ["sesion.json"])
        self.assertEqual(_tree(self.d("cache", "sounds")), ["stop.wav"])
        self.assertTrue(os.path.isfile(self.d(".neb-requisitos.json")))
        with open(self.d("config.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {"schema": 1, "notify": {"stop": {"enabled": True, "wav": "C:/a.wav"},
                                                                     "permission": {"enabled": False}},
                                             "preprocess": {"mode": "off"}})
        # En ~/.claude queda solo lo de Claude Code, lo que no es de Neb y la testigo.
        self.assertEqual(_tree(self.claude), sorted(list(claude_code) + ["neb.db"]))
        for rel, data in claude_code.items():
            self.assertEqual(self.read(self.c(*rel.split("/"))), data, rel)


# --------------------------------------------------------------------------- carga

class TestCarga(unittest.TestCase):

    def test_carga_con_sus_ocho_pasos_en_orden(self):
        m = _migration()
        self.assertEqual([s.id for s in m.steps], STEP_IDS)
        self.assertTrue(all(s.respaldo for s in m.steps))
        self.assertEqual([s.id for s in m.steps if s.exclusivo], ["mover-base"])
        self.assertTrue(callable(m.steps[0].condicion), "mover-base mira la base vieja, no la de ctx.db_path")
        self.assertTrue(os.path.isfile(m.prompt or ""), "falta migrations/8.0.0.md")


# --------------------------------------------------------------------------- de punta a punta

class TestMudanzaCompleta(Base):

    def test_critico_apply_guiados_muda_todo_y_deja_la_testigo(self):
        claude_code = self.legacy_layout()
        rc, res = self.apply()
        g = res["guiados"]
        self.assertEqual(self.ids(g["aplicados"]), sorted(f"{V}:{s}" for s in STEP_IDS), res)
        self.assertEqual((g["pendientes"], g["manual"], g["fallos"]), ([], [], []), res)
        self.assertTrue(res["ok"], res)
        self.assertEqual(rc, 0)
        self.assertEqual(os.path.normcase(res["base"]), os.path.normcase(self.db))
        self.assert_moved(claude_code)
        base_row = [r for r in g["aplicados"] if r["id"] == f"{V}:mover-base"][0]
        self.assertIn("base testigo", base_row["detalle"])
        self.assertIn(os.path.join(self.backups, "neb.pre-8.0.0."), base_row["respaldo"])
        # La segunda corrida no encuentra nada que hacer.
        rc, res = self.apply()
        self.assertEqual((res["guiados"]["aplicados"], res["guiados"]["pendientes"]), ([], []), res)
        self.assertEqual(rc, 0)
        self.assertEqual(nm.status(self.home)["estado"], "al-dia")

    def test_critico_al_iniciar_muda_todo(self):
        claude_code = self.legacy_layout()
        text = self.al_iniciar()
        self.assertIn("La migración guiada de Neb aplicó al iniciar la sesión", text)
        self.assertIn(f"`{V}:mover-base`", text)
        self.assertNotIn("La base de Neb sigue en", text)
        self.assert_moved(claude_code)
        self.assertTrue(os.path.isfile(self.d(".neb-migrate.lock")))
        self.assertFalse(os.path.exists(self.c(".neb-migrate.lock")), "el candado viejo no se crea")

    def test_critico_tras_mudar_la_captura_va_a_la_carpeta_de_datos(self):
        self.legacy_layout()
        self.assertEqual(self.apply()[0], 0)
        witness = self.read(self.old_db)
        cwd = os.path.join(self.home, "repo")
        os.makedirs(cwd)
        t = self.write(os.path.join(self.home, "S8.jsonl"),
                       json.dumps({"type": "user", "message": {"content": "tema tras la mudanza"}}) + "\n")
        r = subprocess.run([sys.executable, os.path.join(NEB, "hooks", "lib", "logbook.py"), "S8", cwd, t, "Stop",
                            NEB, self.home], env=_entorno.env_con_home(self.home, NEB_HOME=None),
                           capture_output=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        con = sqlite3.connect(self.db)
        try:
            self.assertIsNotNone(con.execute("SELECT 1 FROM work WHERE claude_session_id = 'S8'").fetchone())
        finally:
            con.close()
        self.assertTrue(_relocate.is_witness(self.old_db))
        self.assertEqual(len(self.read(self.old_db)), len(witness))

    def test_sin_nada_de_7x_no_hay_pasos(self):
        self.claude_code_files()
        rc, res = self.apply()
        self.assertEqual((res["guiados"]["aplicados"], res["guiados"]["pendientes"]), ([], []), res)
        self.assertEqual(rc, 0)
        self.assertEqual(nm.status(self.home)["estado"], "sin-base")


class TestDesde72(Base):
    """Una máquina que pasa de 7.2.x a 8.0.0 de un salto: base en la versión 2 (raíz 'cliente', un tema
    'proyecto' citado en compas.md v2) y fragmentada, todo en ~/.claude."""

    def setUp(self):
        super().setUp()
        with contextlib.redirect_stderr(io.StringIO()):
            _db_shared._connect(self.old_db, SCHEMA, steps=_migrations.STEPS[:2]).close()
        con = sqlite3.connect(self.old_db)
        con.execute("INSERT INTO topic (id, slug, name) VALUES (33, 'cliente', 'Cliente')")
        con.execute("INSERT INTO topic (id, slug, name, parent_id) VALUES (40, 'alpha', 'Alpha', 33)")
        con.execute("INSERT INTO topic (id, slug, name) VALUES (34, 'topico', 'Tópico')")
        con.execute("INSERT INTO topic (id, slug, name, parent_id) VALUES (51, 'proyecto', 'Proyecto', 34)")
        con.execute("CREATE TABLE relleno (id INTEGER PRIMARY KEY, body BLOB)")
        con.executemany("INSERT INTO relleno (body) VALUES (?)", [(os.urandom(4000),) for _ in range(500)])
        con.commit()
        con.execute("DROP TABLE relleno")
        con.commit()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.close()
        self.write(self.c("compas.md"), "---\nversion: 2\n---\n\n## Objetivo: Estrella\n- **Peso:** 80\n"
                                        "- **Temas:** seguridad, proyecto\n- **Clientes:** alpha=+10\n")

    def test_critico_un_solo_apply_corre_7_3_muda_paso_3_y_la_segunda_pasada(self):
        rc, res = self.apply()
        g = res["guiados"]
        applied = self.ids(g["aplicados"])
        for key in ("7.3.0:compas-proyectos", f"{V}:mover-base", f"{V}:mover-compas", "7.3.0:vacuum-neb-db",
                    "7.4.0:compas-tema-proyecto"):
            self.assertIn(key, applied, res)
        self.assertEqual((g["pendientes"], g["manual"], g["fallos"]), ([], [], []), res)
        self.assertEqual(res["schema_version_db"], 3, res)
        self.assertTrue(res["ok"], res)
        self.assertEqual(rc, 0)
        self.assertTrue(_relocate.is_witness(self.old_db))
        con = sqlite3.connect(self.db)
        try:
            self.assertEqual(con.execute("PRAGMA freelist_count").fetchone()[0], 0, "compactada en la segunda pasada")
            self.assertEqual(con.execute("SELECT slug FROM topic WHERE id = 51").fetchone()[0], "proyecto-51")
            self.assertEqual(con.execute("SELECT slug FROM topic WHERE id = 33").fetchone()[0], "proyecto")
        finally:
            con.close()
        compas = self.read(self.d("compas.md")).decode("utf-8")
        self.assertIn("version: 3", compas)
        self.assertIn("- **Proyectos:** alpha=+10", compas)
        self.assertIn("- **Temas:** seguridad, proyecto-51", compas)
        self.assertFalse(os.path.exists(self.c("compas.md")))
        for pattern in ("neb.pre-8.0.0.*.db", "neb.pre-paso-3.*.db", "neb.pre-vacuum.*.db"):
            self.assertEqual(len(glob.glob(os.path.join(self.backups, pattern))), 1, pattern)


# --------------------------------------------------------------------------- la base

class TestBase(Base):

    def test_con_otra_conexion_queda_pendiente_sin_respaldo_y_la_guarda_sigue(self):
        self.make_old_db()
        con = sqlite3.connect(self.old_db)          # una sesión con la base vieja abierta (WAL)
        con.execute("SELECT count(*) FROM work").fetchone()
        try:
            rc, res = self.apply(include=(f"{V}:mover-base",))
        finally:
            con.close()
        g = res["guiados"]
        self.assertIn(f"{V}:mover-base", self.ids(g["pendientes"]), res)
        self.assertNotEqual(rc, 0)
        self.assertFalse(os.path.exists(self.db))
        self.assertEqual(glob.glob(os.path.join(self.backups, "neb.pre-8.0.0.*")), [])
        self.assertEqual(self.count(self.old_db), 2)
        self.assertEqual([f for f in os.listdir(self.claude) if ".testigo-" in f], [])
        self.assertIsNotNone(_db_shared.unmoved_legacy(self.home))
        self.assertEqual(nm.status(self.home)["estado"], "sin-mudar")

    def test_una_base_usable_ademas_de_la_mudada_es_manual(self):
        self.make_old_db()
        self.assertEqual(self.apply()[0], 0)
        os.remove(self.old_db)                      # alguien pone otra base en el lugar de la testigo
        self.make_old_db(rows=5)
        rc, res = self.apply()
        manual = res["guiados"]["manual"]
        self.assertEqual(self.ids(manual), [f"{V}:mover-base"], res)
        self.assertIn("además de la de la carpeta de datos", manual[0]["detalle"])
        self.assertEqual((self.count(self.old_db), self.count(self.db)), (5, 2), "ninguna se pisa")
        self.assertIsNone(_db_shared.unmoved_legacy(self.home), "con la mudada usable, la guarda no aplica")

    def test_un_archivo_que_no_es_base_es_manual_y_se_queda(self):
        self.write(self.old_db, b"no es una base " * 50)
        rc, res = self.apply()
        manual = res["guiados"]["manual"]
        self.assertEqual(self.ids(manual), [f"{V}:mover-base"], res)
        self.assertIn("no es una base usable", manual[0]["detalle"])
        self.assertEqual(self.read(self.old_db), b"no es una base " * 50)
        self.assertFalse(os.path.exists(self.db))

    def test_la_testigo_no_dispara_nada(self):
        os.makedirs(self.data)
        _relocate.write_witness(self.old_db, V)
        self.assertIsNone(_db_shared.unmoved_legacy(self.home))
        rc, res = self.apply()
        self.assertEqual(res["guiados"]["aplicados"], [], res)
        self.assertEqual(rc, 0)
        self.assertTrue(_relocate.is_witness(self.old_db))


# --------------------------------------------------------------------------- homónimos

class TestHomonimos(Base):

    def test_critico_un_homonimo_distinto_no_se_pisa_y_pide_al_dev(self):
        self.write(self.c("compas.md"), "el de ~/.claude")
        self.write(self.d("compas.md"), "el de la carpeta de datos")
        self.write(self.c("approved-plans", "nuevo.md"), "nuevo")
        self.write(self.c("approved-plans", "choque.md"), "viejo")
        self.write(self.d("approved-plans", "choque.md"), "otro")
        self.write(self.c("approved-plans", "igual.md"), "igual")
        self.write(self.d("approved-plans", "igual.md"), "igual")
        rc, res = self.apply()
        manual = {r["id"]: r for r in res["guiados"]["manual"]}
        self.assertEqual(sorted(manual), [f"{V}:mover-compas", f"{V}:mover-planes"], res)
        self.assertIn(self.c("approved-plans", "choque.md"), manual[f"{V}:mover-planes"]["detalle"])
        self.assertEqual((rc, res["ok"]), (0, True), "lo manual se le dice al dev; no es un fallo de apply")
        self.assertEqual(self.read(self.c("compas.md")), b"el de ~/.claude")
        self.assertEqual(self.read(self.d("compas.md")), b"el de la carpeta de datos")
        self.assertEqual(self.read(self.c("approved-plans", "choque.md")), b"viejo")
        self.assertEqual(self.read(self.d("approved-plans", "choque.md")), b"otro")
        self.assertEqual(self.read(self.d("approved-plans", "nuevo.md")), b"nuevo")
        self.assertFalse(os.path.exists(self.c("approved-plans", "nuevo.md")))
        self.assertFalse(os.path.exists(self.c("approved-plans", "igual.md")), "idéntico: se quita el origen")
        self.assertIsNotNone(manual[f"{V}:mover-planes"]["respaldo"], "lo movido tiene su manifiesto")

    def test_estado_y_cache_con_homonimo_queda_el_mas_nuevo(self):
        viejo = self.write(self.c("preprocess-state", "s.json"), "viejo")
        os.utime(viejo, (1_000_000_000, 1_000_000_000))
        self.write(self.d("state", "preprocess", "s.json"), "nuevo")
        rc, res = self.apply()
        self.assertIn(f"{V}:mover-estado", self.ids(res["guiados"]["aplicados"]), res)
        self.assertEqual(self.read(self.d("state", "preprocess", "s.json")), b"nuevo")
        self.assertFalse(os.path.exists(self.c("preprocess-state")))


# --------------------------------------------------------------------------- fusionar-config

class TestFusionarConfig(Base):

    def run_step(self):
        step = [s for s in _migration().steps if s.id == "fusionar-config"][0]
        return _guided.run(_machine.Ctx(self.home, user_env=self.env), step)

    def test_critico_una_llave_con_otro_valor_no_escribe_ni_borra(self):
        cfg = self.write(self.d("config.json"), json.dumps({"schema": 1, "notify": {"stop": {"enabled": False}}}))
        before = self.read(cfg)
        self.write(self.c("notify-on-stop.json"), '{"enabled": true}')
        self.write(self.c("preprocess.json"), '{"mode": "off"}')
        r = self.run_step()
        self.assertEqual(r["estado"], "manual", r)
        self.assertIn("notify.stop.enabled", r["detalle"])
        self.assertEqual(self.read(cfg), before)
        self.assertTrue(os.path.isfile(self.c("notify-on-stop.json")))
        self.assertTrue(os.path.isfile(self.c("preprocess.json")))
        self.assertEqual(glob.glob(os.path.join(self.backups, "config-sources.*")), [])

    def test_json_ilegible_no_toca_nada(self):
        self.write(self.c("notify-on-stop.json"), '{"enabled": true}')
        self.write(self.c("preprocess.json"), "{no es json")
        r = self.run_step()
        self.assertEqual(r["estado"], "manual", r)
        self.assertIn("preprocess.json", r["detalle"])
        self.assertFalse(os.path.exists(self.d("config.json")))
        self.assertTrue(os.path.isfile(self.c("notify-on-stop.json")))
        self.assertTrue(os.path.isfile(self.c("preprocess.json")))

    def test_completa_un_config_existente_y_respalda_los_textos(self):
        cfg = self.write(self.d("config.json"), json.dumps({"schema": 1, "language": {"variedad": "mexico"},
                                                            "notify": {"stop": {"wav": "C:/a.wav"}}}))
        previo = self.read(cfg).decode("utf-8")
        texto = '{"enabled": true, "wav": "C:/a.wav"}'
        self.write(self.c("notify-on-stop.json"), codecs.BOM_UTF8 + texto.encode("utf-8"))
        r = self.run_step()
        self.assertEqual(r["estado"], "aplicado", r)
        with open(cfg, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {"schema": 1, "language": {"variedad": "mexico"},
                                             "notify": {"stop": {"wav": "C:/a.wav", "enabled": True}}})
        self.assertFalse(os.path.exists(self.c("notify-on-stop.json")))
        with open(r["respaldo"], encoding="utf-8") as fh:
            bak = json.load(fh)
        self.assertEqual(bak["archivos"], {self.c("notify-on-stop.json"): texto})
        self.assertEqual(bak["config_json_previo"], previo)
        self.assertEqual(os.path.dirname(r["respaldo"]), self.backups)


# --------------------------------------------------------------------------- candado doble

class TestCandadoDoble(Base):

    def test_critico_con_el_candado_viejo_tomado_no_corre_nada(self):
        self.legacy_layout()
        fd = _guided.try_lock(self.c(".neb-migrate.lock"))     # una sesión 7.5–7.6 en su migración
        self.assertIsNotNone(fd)
        self.addCleanup(_guided.unlock, fd)
        rc, res = self.apply()
        self.assertEqual((rc, res["motivo"]), (1, "migracion-en-curso"), res)
        self.assertIn("7.5 o 7.6", res["detalle"])
        self.al_iniciar()
        self.assertFalse(os.path.exists(self.db))
        self.assertTrue(os.path.isfile(self.c("compas.md")))
        self.assertEqual(self.count(self.old_db), 2)

    def test_sin_candado_viejo_no_se_crea_y_los_dos_se_sueltan(self):
        self.legacy_layout()
        self.assertEqual(self.apply()[0], 0)
        self.assertFalse(os.path.exists(self.c(".neb-migrate.lock")))
        self.write(self.c(".neb-migrate.lock"), b"")               # lo dejó una corrida de 7.5–7.6
        self.assertEqual(self.apply()[0], 0)
        for path in (self.c(".neb-migrate.lock"), self.d(".neb-migrate.lock")):
            fd = _guided.try_lock(path, create=False)
            self.assertIsNotNone(fd, f"{path} quedó tomado")
            _guided.unlock(fd)


# --------------------------------------------------------------------------- NEB_DATA en ~/.claude

def _quitar_enlace(path):
    """Quita un symlink o una junction sin tocar su destino."""
    try:
        os.unlink(path)
    except OSError:
        try:
            os.rmdir(path)               # junction en Windows
        except OSError:
            pass


class TestNebDataEnClaude(Base):

    def test_critico_sin_mudanza_y_sin_tocar_los_respaldos_de_claude_code(self):
        os.environ[_entorno.DATA_ENV] = self.claude
        self.make_old_db()
        self.write(self.c("compas.md"), COMPAS_V3)
        self.write(self.c("neb.pre-paso-1.20251001T000000Z.db"), b"suelto")
        self.write(self.c("backups", ".claude.json.backup.1"), b"de claude code")
        self.write(self.c("preprocess.json"), '{"mode": "off"}')
        rc, res = self.apply()
        g = res["guiados"]
        self.assertEqual(self.ids(g["aplicados"]), [f"{V}:fusionar-config"], res)
        self.assertEqual((g["manual"], g["fallos"]), ([], []), res)
        self.assertEqual(rc, 0)
        self.assertEqual(_db_shared._probe_db(self.old_db), "usable", "la base sigue donde está")
        self.assertFalse(os.path.exists(self.data))
        self.assertTrue(os.path.isfile(self.c("compas.md")))
        self.assertTrue(os.path.isfile(self.c("neb.pre-paso-1.20251001T000000Z.db")))
        self.assertTrue(os.path.isfile(self.c("config.json")))
        self.assertEqual(_tree(self.c("backups")), [".claude.json.backup.1"], "la carpeta de Claude Code no se toca")
        self.assertEqual(len(glob.glob(self.c("neb-backups", "config-sources.pre-8.0.0.*.json"))), 1)

    def test_critico_neb_data_en_claude_por_otra_ruta_no_borra_nada(self):
        """NEB_DATA nombra ~/.claude por otra ruta (aquí, a través de un enlace al home: como un nombre 8.3, una
        unidad subst o un home POSIX detrás de un symlink). Cada archivo se emparejaría consigo mismo y caería en
        «iguales»: sin comparar en disco, la mudanza borraría el único ejemplar."""
        alias_root = tempfile.mkdtemp(prefix="neb-alias-")
        self.addCleanup(shutil.rmtree, alias_root, True)
        alias = os.path.join(alias_root, "home")
        try:
            os.symlink(self.home, alias, target_is_directory=True)
        except (OSError, NotImplementedError):
            try:
                import _winapi
                _winapi.CreateJunction(self.home, alias)
            except (ImportError, AttributeError, OSError):
                self.skipTest("sin permiso para crear enlaces")
        self.addCleanup(_quitar_enlace, alias)   # corre antes que el rmtree de alias_root (LIFO): no se sigue
        os.environ[_entorno.DATA_ENV] = os.path.join(alias, ".claude")
        self.make_old_db()
        files = {self.c("compas.md"): COMPAS_V3.encode("utf-8"),
                 self.c("approved-plans", "20261101-000000-demo-plan.md"): b"plan",
                 self.c("research", "2026-11-01-tema.md"): b"research",
                 self.c("neb-backups", "neb.pre-paso-1.20251001T000000Z.db"): b"respaldo",
                 self.c(".neb-requisitos.json"): b"{}"}
        for path, data in files.items():
            self.write(path, data)
        rc, res = self.apply()
        self.assertEqual(rc, 0, res)
        for path, data in files.items():
            self.assertTrue(os.path.isfile(path), f"se borró {path}")
            self.assertEqual(self.read(path), data)
        self.assertEqual(_db_shared._probe_db(self.old_db), "usable", "la base sigue donde está")
        self.assertFalse(os.path.exists(self.data))


# --------------------------------------------------------------------------- omisiones

class TestOmisiones(Base):

    def test_critico_el_no_guardado_en_la_base_vieja_se_respeta_y_sigue_tras_mudar(self):
        self.make_old_db()
        self.write(self.c("compas.md"), COMPAS_V3)
        con = _db_shared._connect(self.old_db)
        try:
            _guided.add_skip(con, f"{V}:mover-compas", "8.0.0")
            con.commit()
        finally:
            con.close()
        rc, res = self.apply()
        applied = self.ids(res["guiados"]["aplicados"])
        self.assertIn(f"{V}:mover-base", applied, res)
        self.assertNotIn(f"{V}:mover-compas", applied, res)
        self.assertTrue(os.path.isfile(self.c("compas.md")))
        st = nm.status(self.home)
        self.assertEqual(st["estado"], "al-dia")
        self.assertIn(f"{V}:mover-compas", {r["id"] for r in st["guiados"]["omitidos"]})

    def test_omitir_mover_base_deja_la_base_sin_mudar(self):
        self.make_old_db()
        con = _db_shared._connect(self.old_db)
        try:
            _guided.add_skip(con, f"{V}:mover-base", "8.0.0")
            con.commit()
        finally:
            con.close()
        rc, res = self.apply()
        self.assertNotIn(f"{V}:mover-base", self.ids(res["guiados"]["aplicados"]), res)
        self.assertNotEqual(rc, 0, "con la base sin mudar, apply no es ok")
        st = nm.status(self.home)
        self.assertEqual(st["estado"], "sin-mudar")
        self.assertIn(f"{V}:mover-base", {r["id"] for r in st["guiados"]["omitidos"]})


# --------------------------------------------------------------------------- status y siembra

class TestSinMudar(Base):

    def test_status_sin_mudar_no_escribe(self):
        self.make_old_db()
        before = self.read(self.old_db)
        st = nm.status(self.home)
        self.assertEqual(st["estado"], "sin-mudar")
        self.assertIn(self.old_db, st["detalle"])
        self.assertIn(f"{V}:mover-base", {r["id"] for r in st["guiados"]["pendientes"]})
        self.assertEqual(self.read(self.old_db), before)
        self.assertFalse(os.path.exists(self.data))

    def test_critico_la_siembra_con_la_base_sin_mudar_responde_su_motivo_sin_crear_nada(self):
        seed = _load("seed_taxonomy_800_test", os.path.join(NEB, "bootstrap", "seed-pendings-taxonomy.py"))
        self.make_old_db()
        err = _db_shared.unmoved_legacy(self.home)
        self.assertIsNotNone(err)
        expected = f"{err.detalle} Cómo: {err.accion}."
        db = _db_shared.resolve_db_path(self.home)
        for call in (lambda: seed.run(db, "catalogo.json", "dataset.json", apply=False),
                     lambda: seed.run(db, "catalogo.json", "dataset.json", apply=True, backup_dir=self.home),
                     lambda: seed.rollback(db, "respaldo.db")):
            with self.assertRaises(RuntimeError) as cm:
                call()
            self.assertEqual(str(cm.exception), expected)
            self.assertFalse(os.path.exists(self.data))

    def test_critico_base_vieja_ilegible_falla_cerrada_sin_crear_la_nueva(self):
        """Un error que la guarda no reconoce al leer la base vieja (E/S, antivirus, archivo dañado) no deja abrir:
        crear <datos>/neb.db escondería el historial para siempre (la guarda ya no se activaría)."""
        self.make_old_db()
        real = _db_shared._probe_db

        def probe(path):                                # la vieja da un error que la guarda no reconoce
            return "otro" if os.path.normcase(path) == os.path.normcase(self.old_db) else real(path)

        with mock.patch.object(_db_shared, "_probe_db", probe), \
                self.assertRaises(_db_shared.UnmovedDb) as cm:
            _db_shared.prepare_default_db(self.home)
        self.assertIn("No se pudo leer", cm.exception.detalle)
        self.assertFalse(os.path.exists(self.db))


if __name__ == "__main__":
    unittest.main()
