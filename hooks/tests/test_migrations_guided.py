#!/usr/bin/env python3
"""
test_migrations_guided.py — migración guiada (hooks/lib/_guided.py y bootstrap/neb-migrate.py, 6.49.0).

Con una migración de prueba en un árbol temporal (fixture):
  • registro por versión semántica; un nombre que no es versión se ignora; un archivo roto se reporta;
  • `status` lista lo pendiente con su clase y lo omitido;
  • `apply` corre solo lo que deja con qué deshacerlo (de catálogo y libres) y deja hasta `--include` el paso
    que quita un secreto y el libre sin respaldo;
  • un paso libre que declara respaldo y no lo deja es fallo;
  • un paso `exclusivo` con otra conexión abierta no hace nada y queda pendiente con su motivo;
  • `skip` y su efecto; `--include` de un omitido lo corre y borra el «no»; un paso aplicado cuyo estado
    vuelve se detecta otra vez;
  • `al-iniciar` (7.5.0): corre lo que deja respaldo y lo reporta; encarga el menú en la sesión para lo que
    pide al dev (también sin el candado), no con lo omitido ni sin pendientes; candado entre corridas (dos a la
    vez: una sola aplica; un proceso muerto lo libera); ventana de exclusivos; presupuesto; sale con 0 ante una
    excepción; `neb: skip`; tope de la salida; apply/skip/restore con el candado tomado: migracion-en-curso.

Homes temporales; nunca ~/.claude ni el registro real.
  py -m unittest discover -s hooks/tests -p test_migrations_guided.py
"""

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sin_registro  # noqa: E402,F401 — sin el registro real de Windows
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
NEB = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(NEB, "hooks", "lib"))

import _db_shared
import _guided
import _machine


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


nm = _load("neb_migrate_guided_test", os.path.join(NEB, "bootstrap", "neb-migrate.py"))
nb = _load("neb_bootstrap_context_guided", os.path.join(NEB, "bootstrap", "neb-bootstrap-context.py"))

MIGRATION = textwrap.dedent('''
    import os
    import shutil
    from _guided import GuidedStep

    def _f(ctx, name):
        return os.path.join(ctx.claude_dir, name)

    def _hay(name):
        return lambda ctx: os.path.exists(_f(ctx, name))

    def _con_respaldo(name):
        def aplicar(ctx):
            bak = _f(ctx, name + ".bak")
            shutil.copyfile(_f(ctx, name), bak)
            os.remove(_f(ctx, name))
            return {"respaldo": bak, "detalle": "movido"}
        return aplicar

    def _sin_respaldo(name):
        def aplicar(ctx):
            os.remove(_f(ctx, name))
            return {"detalle": "borrado"}
        return aplicar

    def _respaldo_falso(ctx):
        os.remove(_f(ctx, "falso.txt"))
        return {"respaldo": _f(ctx, "no-existe.bak")}

    def _exclusivo(ctx):
        motivo = ctx.exclusivo_ok()
        if motivo:
            return {"estado": "pendiente", "detalle": motivo}
        return _con_respaldo("excl.txt")(ctx)

    STEPS = [
        GuidedStep("settings-solo", "Quitar NEB_PRUEBA_A", op="settings_env_remove",
                   args={"claves": ["NEB_PRUEBA_A"]}),
        GuidedStep("settings-secreto", "Quitar NEB_PRUEBA_TOKEN", op="settings_env_remove",
                   args={"claves": ["NEB_PRUEBA_TOKEN"], "secretas": ["NEB_PRUEBA_TOKEN"]}),
        GuidedStep("entorno", "Quitar la variable NEB_PRUEBA_X", op="user_env_remove",
                   args={"nombre": "NEB_PRUEBA_X"}),
        GuidedStep("libre-respaldo", "Libre con respaldo", detectar=_hay("libre.txt"),
                   aplicar=_con_respaldo("libre.txt"), respaldo=True),
        GuidedStep("libre-falso", "Libre que no deja su respaldo", detectar=_hay("falso.txt"),
                   aplicar=_respaldo_falso, respaldo=True),
        GuidedStep("libre-dev", "Libre sin respaldo", detectar=_hay("dev.txt"), aplicar=_sin_respaldo("dev.txt")),
        GuidedStep("exclusivo", "Libre exclusivo", detectar=_hay("excl.txt"), aplicar=_exclusivo,
                   respaldo=True, exclusivo=True),
    ]
''')

V = "9.9.9"


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


class Base(unittest.TestCase):

    def setUp(self):
        p = mock.patch.dict(os.environ)
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop("CLAUDE_CONFIG_DIR", None)
        self.home = tempfile.mkdtemp(prefix="neb-test-guided-")
        self.addCleanup(shutil.rmtree, self.home, True)
        self.claude = os.path.join(self.home, ".claude")
        os.makedirs(self.claude)
        self.db = os.path.join(self.claude, "neb.db")
        self.tree = tempfile.mkdtemp(prefix="neb-test-arbol-")
        self.addCleanup(shutil.rmtree, self.tree, True)
        os.makedirs(os.path.join(self.tree, "migrations"))
        self.write_migration(V, MIGRATION)
        self.env = FakeUserEnv()
        for target, value in ((nm, "ROOT"),):
            p = mock.patch.object(target, value, self.tree)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(_machine, "default_user_env", lambda: self.env)
        p.start()
        self.addCleanup(p.stop)
        with contextlib.redirect_stderr(io.StringIO()):
            _db_shared._connect(self.db).close()

    def write_migration(self, version, text):
        with open(os.path.join(self.tree, "migrations", version + ".py"), "w", encoding="utf-8") as fh:
            fh.write(text)

    def touch(self, name):
        with open(os.path.join(self.claude, name), "w", encoding="utf-8") as fh:
            fh.write("contenido")

    def settings(self, env):
        with open(os.path.join(self.claude, "settings.json"), "w", encoding="utf-8") as fh:
            json.dump({"env": env, "model": "x"}, fh)

    def settings_env(self):
        with open(os.path.join(self.claude, "settings.json"), encoding="utf-8") as fh:
            return json.load(fh)["env"]

    def apply(self, include=(), sin_exclusivos=False, guiados=True):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = nm.apply(self.home, include, sin_exclusivos, guiados)
        return rc, json.loads(out.getvalue())

    def skip(self, key):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = nm.skip(self.home, key)
        return rc, json.loads(out.getvalue())

    def pending(self):
        g = nm.status(self.home)["guiados"]
        return ({r["id"]: r["clase"] for r in g["pendientes"]}, {r["id"] for r in g["omitidos"]})

    @staticmethod
    def ids(rows):
        return sorted(r["id"].split(":")[1] for r in rows)


class TestRegistro(Base):

    def test_orden_por_version_semantica_y_nombres_ignorados(self):
        empty = "from _guided import GuidedStep\nSTEPS = []\n"
        for name in ("10.0.0", "9.10.0", "1.2", "notas", "9.9.9a"):
            self.write_migration(name, empty)
        migrations, errors = _guided.load(self.tree)
        self.assertEqual([m.version for m in migrations], ["9.9.9", "9.10.0", "10.0.0"])
        self.assertEqual(errors, [])

    def test_archivo_roto_se_reporta_y_no_detiene_a_los_demas(self):
        self.write_migration("9.9.8", "raise RuntimeError('rota')\n")
        self.write_migration("9.9.7", "from _guided import GuidedStep\nSTEPS = [GuidedStep('x', 'x', op='nada')]\n")
        migrations, errors = _guided.load(self.tree)
        self.assertEqual([m.version for m in migrations], [V])
        self.assertEqual(sorted(a for a, _m in errors), ["9.9.7.py", "9.9.8.py"])
        self.assertIn("errores_de_carga", nm.status(self.home)["guiados"])
        self.assertEqual(len(nm.status(self.home)["guiados"]["errores_de_carga"]), 2)

    def test_ids_repetidos_o_invalidos_no_cargan(self):
        for text in ("STEPS = [GuidedStep('a', 'a', op='user_env_remove', args={'nombre': 'NEB_A'})] * 2\n",
                     "STEPS = [GuidedStep('Mal Id', 'a', op='user_env_remove', args={'nombre': 'NEB_A'})]\n",
                     "STEPS = [GuidedStep('a', 'a', detectar=lambda c: True)]\n",
                     "STEPS = ['no es paso']\n"):
            self.write_migration("1.0.0", "from _guided import GuidedStep\n" + text)
            _migrations, errors = _guided.load(self.tree)
            self.assertEqual([a for a, _m in errors], ["1.0.0.py"], text)
            self.assertIn("migración inválida: ", errors[0][1], text)  # forma de la migración: el mensaje se conserva

    def test_carga_aunque_el_modulo_tenga_otro_nombre(self):
        # El arranque carga _guided por ruta con otro nombre: los pasos siguen siendo GuidedStep de ese módulo.
        other = _load("guided_por_ruta", os.path.join(NEB, "hooks", "lib", "_guided.py"))
        migrations, errors = other.load(self.tree)
        self.assertEqual(errors, [])
        self.assertEqual(len(migrations[0].steps), 7)

    def test_arbol_con_corchetes_carga_sus_migraciones_y_no_las_de_otra_carpeta(self):
        # x[1] es ruta, no patrón de glob: leerla como patrón miraría x1.
        base = tempfile.mkdtemp(prefix="neb-test-arbol-")
        self.addCleanup(shutil.rmtree, base, True)
        own, decoy = os.path.join(base, "x[1]"), os.path.join(base, "x1")
        empty = "from _guided import GuidedStep\nSTEPS = []\n"
        for root, version in ((own, "9.9.1"), (decoy, "9.9.2")):
            os.makedirs(os.path.join(root, "migrations"))
            with open(os.path.join(root, "migrations", version + ".py"), "w", encoding="utf-8") as fh:
                fh.write(empty)
        with mock.patch.dict(os.environ, {"HOME": own, "USERPROFILE": own}):
            migrations, errors = _guided.load(own)
        self.assertEqual([m.version for m in migrations], ["9.9.1"])
        self.assertEqual(errors, [])


class TestApply(Base):

    def test_status_lista_lo_pendiente_con_su_clase(self):
        self.settings({"NEB_PRUEBA_A": "x", "NEB_PRUEBA_TOKEN": "s3cr3t-v4l0r", "OTRA": "y"})
        self.env.user["NEB_PRUEBA_X"] = "valor"
        for f in ("libre.txt", "dev.txt"):
            self.touch(f)
        pend, omit = self.pending()
        self.assertEqual(pend, {V + ":settings-solo": "solo", V + ":settings-secreto": "dev",
                                V + ":entorno": "dev", V + ":libre-respaldo": "solo", V + ":libre-dev": "dev"})
        self.assertEqual(omit, set())

    def db_state(self):
        def digest(p):
            if not os.path.exists(p):
                return None
            with open(p, "rb") as fh:
                return hashlib.sha256(fh.read()).hexdigest()
        wal = self.db + "-wal"            # un lector en WAL puede crear un -wal vacío: sin datos no es escritura
        return [digest(self.db), os.path.getsize(wal) if os.path.exists(wal) else 0]

    def test_status_no_escribe(self):
        self.touch("libre.txt")
        self.settings({"NEB_PRUEBA_TOKEN": "s3cr3t-v4l0r"})
        before = self.db_state()
        out = json.dumps(nm.status(self.home))
        self.assertTrue(os.path.exists(os.path.join(self.claude, "libre.txt")))
        self.assertEqual(self.db_state(), before)
        self.assertNotIn("s3cr3t-v4l0r", out)
        con = sqlite3.connect(self.db)
        try:
            self.assertIsNone(con.execute("SELECT name FROM sqlite_master WHERE name = 'migration_skip'").fetchone())
        finally:
            con.close()

    def test_apply_sin_base_no_la_crea(self):
        for s in ("", "-wal", "-shm"):
            if os.path.exists(self.db + s):
                os.remove(self.db + s)
        self.touch("libre.txt")
        rc, out = self.apply()
        self.assertEqual(rc, 0)
        self.assertIsNone(out["base"])
        self.assertEqual(self.ids(out["guiados"]["aplicados"]), ["libre-respaldo"])
        self.assertEqual([n for n in os.listdir(self.claude) if n.startswith("neb")], [])

    def test_sin_exclusivos_deja_los_exclusivos_pendientes(self):
        self.touch("excl.txt")
        self.touch("libre.txt")
        rc, out = self.apply(sin_exclusivos=True)
        self.assertEqual(self.ids(out["guiados"]["aplicados"]), ["libre-respaldo"])
        self.assertEqual(self.ids(out["guiados"]["pendientes"]), ["exclusivo"])
        self.assertTrue(os.path.exists(os.path.join(self.claude, "excl.txt")))

    def test_paso_libre_sin_cambio_no_pasa_por_la_comprobacion_del_respaldo(self):
        step = _guided.GuidedStep("nada", "Nada", detectar=lambda c: True,
                                  aplicar=lambda c: {"estado": "sin-cambio", "detalle": "ya estaba"}, respaldo=True)
        r = _guided.run(_machine.Ctx(self.home, db_path=self.db, user_env=self.env), step)
        self.assertEqual((r["estado"], r["respaldo"], r["detalle"]), ("sin-cambio", None, "ya estaba"))

    def test_error_de_un_paso_libre_no_filtra_su_mensaje(self):
        def aplicar(ctx):
            raise RuntimeError("comando con --token s3cr3t-v4l0r")
        step = _guided.GuidedStep("raro", "raro", detectar=lambda c: True, aplicar=aplicar, respaldo=True)
        r = _guided.run(_machine.Ctx(self.home, db_path=self.db, user_env=self.env), step)
        self.assertEqual(r["estado"], "fallo")
        self.assertIn("RuntimeError", r["detalle"])
        self.assertNotIn("s3cr3t-v4l0r", r["detalle"])

        def detectar(ctx):
            raise SystemExit("s3cr3t-v4l0r")
        step = _guided.GuidedStep("sale", "sale", detectar=detectar, aplicar=lambda c: {})
        rows = _guided.survey(_machine.Ctx(self.home, db_path=self.db, user_env=self.env),
                              [_guided.Migration("1.0.0", [step], None)], set())
        self.assertIn("SystemExit", rows[0]["error"])
        self.assertNotIn("s3cr3t-v4l0r", rows[0]["error"])

    def test_apply_corre_solo_lo_que_deja_con_que_deshacerlo(self):
        self.settings({"NEB_PRUEBA_A": "x", "NEB_PRUEBA_TOKEN": "s3cr3t-v4l0r", "OTRA": "y"})
        self.env.user["NEB_PRUEBA_X"] = "valor"
        for f in ("libre.txt", "dev.txt"):
            self.touch(f)
        rc, out = self.apply()
        g = out["guiados"]
        self.assertEqual(self.ids(g["aplicados"]), ["libre-respaldo", "settings-solo"])
        self.assertEqual(self.ids(g["pendientes"]), ["entorno", "libre-dev", "settings-secreto"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.settings_env(), {"NEB_PRUEBA_TOKEN": "s3cr3t-v4l0r", "OTRA": "y"})
        self.assertIn("NEB_PRUEBA_X", self.env.user)
        self.assertTrue(os.path.exists(os.path.join(self.claude, "dev.txt")))
        self.assertTrue(os.path.exists(os.path.join(self.claude, "libre.txt.bak")))
        self.assertNotIn("s3cr3t-v4l0r", json.dumps(out))
        self.assertNotIn("valor", json.dumps(out))

    def test_include_corre_los_que_piden_al_dev(self):
        self.settings({"NEB_PRUEBA_TOKEN": "s3cr3t-v4l0r", "OTRA": "y"})
        self.env.user["NEB_PRUEBA_X"] = "valor"
        self.touch("dev.txt")
        rc, out = self.apply([V + ":settings-secreto", V + ":entorno", V + ":libre-dev"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.ids(out["guiados"]["aplicados"]), ["entorno", "libre-dev", "settings-secreto"])
        self.assertEqual(self.settings_env(), {"OTRA": "y"})
        self.assertEqual(self.env.user, {})
        self.assertEqual(self.pending()[0], {})

    def test_include_desconocido_es_error(self):
        rc, out = self.apply([V + ":no-existe"])
        self.assertEqual(rc, 1)
        self.assertEqual(out["guiados"]["no_encontrados"], [V + ":no-existe"])

    def test_paso_libre_que_no_deja_su_respaldo_es_fallo(self):
        self.touch("falso.txt")
        rc, out = self.apply()
        self.assertEqual(rc, 1)
        self.assertEqual(self.ids(out["guiados"]["fallos"]), ["libre-falso"])
        self.assertIn("no existe", out["guiados"]["fallos"][0]["detalle"])

    def run_declaring(self, aplicar):
        step = _guided.GuidedStep("r", "r", detectar=lambda c: True, aplicar=aplicar, respaldo=True)
        return _guided.run(_machine.Ctx(self.home, db_path=self.db, user_env=self.env), step)

    def test_respaldo_viejo_no_cuenta(self):
        def aplicar(c):
            bak = os.path.join(c.claude_dir, "viejo.bak")
            with open(bak, "w", encoding="utf-8") as fh:
                fh.write("x")
            past = os.path.getmtime(bak) - 3600
            os.utime(bak, (past, past))
            return {"respaldo": bak}
        r = self.run_declaring(aplicar)
        self.assertEqual(r["estado"], "fallo")
        self.assertIn("no se creó en esta corrida", r["detalle"])

    def test_respaldo_que_ya_existia_no_cuenta(self):
        self.touch("previo.bak")

        def aplicar(c):
            bak = os.path.join(c.claude_dir, "previo.bak")
            with open(bak, "w", encoding="utf-8") as fh:
                fh.write("reescrito")
            return {"respaldo": bak}
        r = self.run_declaring(aplicar)
        self.assertEqual(r["estado"], "fallo")
        self.assertIn("ya existía", r["detalle"])

    def test_archivo_vivo_no_es_respaldo(self):
        # Archivos vivos que nacen en el paso, con contenido: solo la regla de archivo vivo los rechaza.
        for name in ("neb-logbook.db", "settings.local.json", "neb.db-journal"):
            def aplicar(c, name=name):
                p = os.path.join(c.claude_dir, name)
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write("contenido")
                return {"respaldo": p}
            r = self.run_declaring(aplicar)
            self.assertEqual(r["estado"], "fallo", name)
            self.assertIn("archivo vivo", r["detalle"], name)
            os.remove(os.path.join(self.claude, name))

    def test_respaldo_en_carpeta_vecina_no_cuenta(self):
        vecina = self.claude + "-otro"
        os.makedirs(vecina)

        def aplicar(c):
            bak = os.path.join(vecina, "x.bak")
            with open(bak, "w", encoding="utf-8") as fh:
                fh.write("x")
            return {"respaldo": bak}
        r = self.run_declaring(aplicar)
        self.assertEqual(r["estado"], "fallo")
        self.assertIn("no está directamente", r["detalle"])

    def test_respaldo_sqlite_sano_cuenta(self):
        def aplicar(c):
            bak = os.path.join(c.claude_dir, "neb.pre-prueba.db")
            src = sqlite3.connect(self.db)
            dst = sqlite3.connect(bak)
            try:
                src.backup(dst)
                self.assertEqual(dst.execute("PRAGMA journal_mode=DELETE").fetchone()[0], "delete")
            finally:
                dst.close()
                src.close()
            return {"respaldo": bak}
        r = self.run_declaring(aplicar)
        self.assertEqual((r["estado"], r["detalle"]), ("aplicado", ""))
        self.assertFalse(os.path.exists(os.path.join(self.claude, "neb.pre-prueba.db-shm")))

    def test_respaldo_sqlite_en_wal_no_cuenta(self):
        def aplicar(c):
            bak = os.path.join(c.claude_dir, "neb.pre-wal.db")
            src = sqlite3.connect(self.db)
            dst = sqlite3.connect(bak)
            try:
                src.backup(dst)
                dst.execute("PRAGMA journal_mode=WAL").fetchone()
            finally:
                dst.close()
                src.close()
            return {"respaldo": bak}
        r = self.run_declaring(aplicar)
        self.assertEqual(r["estado"], "fallo")
        self.assertIn("WAL", r["detalle"])

    def test_respaldo_fuera_de_claude_no_cuenta(self):
        outside = tempfile.mkdtemp(prefix="neb-test-fuera-")
        self.addCleanup(shutil.rmtree, outside, True)
        bak = os.path.join(outside, "x.bak")

        def aplicar(ctx):
            with open(bak, "w", encoding="utf-8") as fh:
                fh.write("x")
            return {"respaldo": bak}
        step = _guided.GuidedStep("fuera", "fuera", detectar=lambda c: True, aplicar=aplicar, respaldo=True)
        r = _guided.run(_machine.Ctx(self.home, db_path=self.db, user_env=self.env), step)
        self.assertEqual(r["estado"], "fallo")
        self.assertIn("no está directamente", r["detalle"])

    def test_respaldo_sqlite_danado_no_cuenta(self):
        def aplicar(ctx):
            bak = os.path.join(ctx.claude_dir, "base.bak")
            with open(bak, "wb") as fh:
                fh.write(b"SQLite format 3\x00" + b"\x00" * 200)
            return {"respaldo": bak}
        step = _guided.GuidedStep("sqlite", "sqlite", detectar=lambda c: True, aplicar=aplicar, respaldo=True)
        r = _guided.run(_machine.Ctx(self.home, db_path=self.db, user_env=self.env), step)
        self.assertEqual(r["estado"], "fallo")

    def test_exclusivo_con_otra_conexion_queda_pendiente(self):
        self.touch("excl.txt")
        other = sqlite3.connect(self.db)
        other.execute("SELECT count(*) FROM work").fetchone()
        try:
            rc, out = self.apply()
        finally:
            other.close()
        self.assertEqual(self.ids(out["guiados"]["pendientes"]), ["exclusivo"])
        self.assertIn("se reintenta en el siguiente inicio de sesión", out["guiados"]["pendientes"][0]["detalle"])
        self.assertNotIn("cierra", out["guiados"]["pendientes"][0]["detalle"], "nunca pide cerrar sesiones")
        self.assertTrue(os.path.exists(os.path.join(self.claude, "excl.txt")))
        self.assertFalse(os.path.exists(os.path.join(self.claude, "excl.txt.bak")))
        rc, out = self.apply()                                       # ya sin la otra conexión
        self.assertEqual(self.ids(out["guiados"]["aplicados"]), ["exclusivo"])
        self.assertFalse(os.path.exists(os.path.join(self.claude, "excl.txt")))

    def journal_mode(self):
        con = sqlite3.connect(self.db)
        try:
            return con.execute("PRAGMA journal_mode").fetchone()[0]
        finally:
            con.close()

    def test_exclusividad_con_lector_de_solo_lectura_y_vuelta_a_wal(self):
        ctx = _machine.Ctx(self.home, db_path=self.db, user_env=self.env)
        self.assertEqual(self.journal_mode(), "wal")
        self.assertIsNone(_guided.base_sin_otras_conexiones(ctx))
        self.assertEqual(self.journal_mode(), "wal")                 # la prueba la deja en WAL
        from pathlib import Path
        ro = sqlite3.connect(Path(self.db).as_uri() + "?mode=ro", uri=True)
        cur = ro.execute("SELECT count(*) FROM work")
        cur.fetchall()
        cur.close()                                                  # cursor agotado y cerrado: conexión ociosa
        try:
            self.assertIsNotNone(_guided.base_sin_otras_conexiones(ctx))
        finally:
            ro.close()
        self.assertEqual(self.journal_mode(), "wal")

    def test_exclusividad_fuera_de_wal(self):
        con = sqlite3.connect(self.db)
        con.execute("PRAGMA journal_mode=DELETE").fetchone()
        con.close()
        ctx = _machine.Ctx(self.home, db_path=self.db, user_env=self.env)
        self.assertIsNone(_guided.base_sin_otras_conexiones(ctx))
        other = sqlite3.connect(self.db, isolation_level=None)
        other.execute("BEGIN IMMEDIATE")
        try:
            self.assertIsNotNone(_guided.base_sin_otras_conexiones(ctx))
        finally:
            other.execute("ROLLBACK")
            other.close()

    def test_exclusivo_comprueba_otra_vez_antes_de_actuar(self):
        calls = []

        def cond(ctx):
            calls.append(1)
            return None if len(calls) == 1 else "otra sesión abrió la base"

        def aplicar(ctx):
            motivo = ctx.exclusivo_ok()
            return {"estado": "pendiente", "detalle": motivo} if motivo else {"respaldo": None}
        step = _guided.GuidedStep("e", "e", detectar=lambda c: True, aplicar=aplicar, respaldo=True,
                                  exclusivo=True, condicion=cond)
        ctx = _machine.Ctx(self.home, db_path=self.db, user_env=self.env)
        r = _guided.run(ctx, step)
        self.assertEqual(r["estado"], "pendiente")
        self.assertEqual(len(calls), 2)
        self.assertIsNone(ctx.exclusivo_ok())                        # se restablece tras el paso

    def test_skip_saca_de_lo_pendiente_y_include_lo_corre(self):
        self.touch("dev.txt")
        rc, out = self.skip(V + ":libre-dev")
        self.assertEqual((rc, out["ok"]), (0, True))
        pend, omit = self.pending()
        self.assertNotIn(V + ":libre-dev", pend)
        self.assertEqual(omit, {V + ":libre-dev"})
        rc, out = self.apply()
        self.assertEqual(out["guiados"]["pendientes"], [])
        rc, out = self.apply([V + ":libre-dev"])
        self.assertEqual(self.ids(out["guiados"]["aplicados"]), ["libre-dev"])
        self.assertEqual(self.pending(), ({}, set()))                # el «no» se borró
        con = sqlite3.connect(self.db)
        try:
            self.assertEqual(con.execute("SELECT count(*) FROM migration_skip").fetchone()[0], 0)
        finally:
            con.close()

    def test_omitidos_ilegibles_no_corren_pasos_guiados(self):
        con = sqlite3.connect(self.db)
        try:
            con.execute("CREATE TABLE migration_skip (x TEXT)")          # «no such column: id», no «no such table»
            con.commit()
        finally:
            con.close()
        self.touch("libre.txt")
        rc, out = self.apply()
        self.assertEqual(rc, 1)
        self.assertIn("migration_skip", out["guiados"]["error"])
        self.assertEqual(out["guiados"]["aplicados"], [])
        self.assertTrue(os.path.exists(os.path.join(self.claude, "libre.txt")))

    def test_skip_de_un_paso_desconocido_se_niega(self):
        rc, out = self.skip(V + ":no-existe")
        self.assertEqual(rc, 1)
        self.assertEqual(out["motivo"], "paso-desconocido")

    def test_skip_no_guarda_el_valor(self):
        self.env.user["NEB_PRUEBA_X"] = "valor-que-no-sale"
        self.skip(V + ":entorno")
        con = sqlite3.connect(self.db)
        try:
            rows = con.execute("SELECT * FROM migration_skip").fetchall()
        finally:
            con.close()
        self.assertEqual(len(rows), 1)
        self.assertNotIn("valor-que-no-sale", repr(rows))

    def test_paso_aplicado_cuyo_estado_vuelve_se_detecta_otra_vez(self):
        self.touch("libre.txt")
        self.apply()
        self.assertEqual(self.pending()[0], {})
        self.touch("libre.txt")
        self.assertEqual(self.pending()[0], {V + ":libre-respaldo": "solo"})

    def test_error_al_detectar_se_reporta_en_su_fila(self):
        self.write_migration("9.9.10", "from _guided import GuidedStep\n"
                             "def d(ctx):\n    raise OSError('sin acceso')\n"
                             "STEPS = [GuidedStep('d', 'd', detectar=d, aplicar=lambda c: {})]\n")
        g = nm.status(self.home)["guiados"]
        rows = [r for r in g["pendientes"] if r["id"] == "9.9.10:d"]
        self.assertEqual(len(rows), 1)
        self.assertIn("OSError", rows[0]["error"])
        self.assertNotIn("sin acceso", rows[0]["error"])            # mensaje de un paso libre: omitido
        rc, out = self.apply()
        self.assertEqual(self.ids(out["guiados"]["fallos"]), ["d"])

    def test_apply_a_secas_no_corre_pasos_guiados(self):
        # Reintentar un paso de base (lo que sugiere el aviso de un paso detenido) no corre la migración guiada.
        self.settings({"NEB_PRUEBA_A": "x"})
        self.touch("libre.txt")
        rc, out = self.apply(guiados=False)
        self.assertEqual(rc, 0)
        self.assertIsNone(out["guiados"])
        self.assertTrue(os.path.exists(os.path.join(self.claude, "libre.txt")))
        self.assertEqual(self.settings_env(), {"NEB_PRUEBA_A": "x"})
        rc, out = self.apply(sin_exclusivos=True, guiados=False)     # --sin-exclusivos implica --guiados
        self.assertEqual(self.ids(out["guiados"]["aplicados"]), ["libre-respaldo", "settings-solo"])

    def test_migracion_que_no_carga_deja_apply_sin_ok_y_sin_su_mensaje(self):
        self.write_migration("9.9.8", "raise RuntimeError('s3cr3t-v4l0r')\n")
        self.write_migration("9.9.6", "def f(:\n")
        rc, out = self.apply()
        self.assertEqual(rc, 1)
        errores = {e["archivo"]: e["motivo"] for e in out["guiados"]["errores_de_carga"]}
        self.assertEqual(sorted(errores), ["9.9.6.py", "9.9.8.py"])
        self.assertIn("RuntimeError", errores["9.9.8.py"])
        self.assertIn("SyntaxError en la línea 1", errores["9.9.6.py"])
        self.assertNotIn("s3cr3t-v4l0r", json.dumps(out))
        self.assertNotIn("s3cr3t-v4l0r", json.dumps(nm.status(self.home)))

    def remove_db(self):
        for s in ("", "-wal", "-shm"):
            if os.path.exists(self.db + s):
                os.remove(self.db + s)

    def test_skip_sin_base_se_niega_y_no_la_crea(self):
        self.remove_db()
        self.touch("dev.txt")
        rc, out = self.skip(V + ":libre-dev")
        self.assertEqual((rc, out["motivo"]), (1, "sin-base"))
        self.assertEqual([n for n in os.listdir(self.claude) if n.startswith("neb")], [])
        self.assertIn(V + ":libre-dev", self.pending()[0])

    def test_skip_en_base_mas_nueva_sin_la_tabla_se_niega(self):
        import _migrations
        c = _migrations.code_version()
        con = sqlite3.connect(self.db)
        try:
            con.execute("INSERT INTO schema_step (step, min_code, title, neb_version, applied_at, backup) "
                        "VALUES (?, 1, 'futuro', '99.0.0', '2099-01-01', NULL)", (c + 1,))
            con.commit()
        finally:
            con.close()
        rc, out = self.skip(V + ":libre-dev")
        self.assertEqual((rc, out["motivo"]), (1, "base-mas-nueva"))
        con = sqlite3.connect(self.db)
        try:
            self.assertIsNone(con.execute("SELECT name FROM sqlite_master WHERE name = 'migration_skip'").fetchone())
            con.execute(_guided.SKIP_DDL)                            # con la tabla, la base más nueva sí lo guarda
            con.commit()
        finally:
            con.close()
        rc, out = self.skip(V + ":libre-dev")
        self.assertEqual((rc, out["ok"]), (0, True))

    def test_respaldo_oculto_que_ya_existia_no_cuenta(self):
        self.touch(".credentials.json")

        def aplicar(c):
            p = os.path.join(c.claude_dir, ".credentials.json")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("reescrito")
            return {"respaldo": p}
        r = self.run_declaring(aplicar)
        self.assertEqual(r["estado"], "fallo")
        self.assertIn("ya existía", r["detalle"])

    def sqlite_copy(self, name):
        bak = os.path.join(self.claude, name)
        src, dst = sqlite3.connect(self.db), sqlite3.connect(bak)
        try:
            src.backup(dst)
            dst.execute("PRAGMA journal_mode=DELETE").fetchone()
        finally:
            dst.close()
            src.close()
        return bak

    def test_respaldo_sqlite_con_journal_no_cuenta(self):
        def aplicar(c):
            bak = self.sqlite_copy("neb.pre-journal.db")
            with open(bak + "-journal", "wb") as fh:
                fh.write(b"\x00" * 512)
            return {"respaldo": bak}
        r = self.run_declaring(aplicar)
        self.assertEqual(r["estado"], "fallo")
        self.assertIn("-journal", r["detalle"])

    def test_respaldo_que_sirve_queda_solo_para_el_usuario(self):
        calls = []
        real_chmod = os.chmod
        with mock.patch.object(_guided.os, "chmod", lambda p, m: (calls.append((p, m)), real_chmod(p, m))):
            r = self.run_declaring(lambda c: {"respaldo": self.sqlite_copy("neb.pre-chmod.db")})
        self.assertEqual(r["estado"], "aplicado")
        self.assertEqual([(_guided._norm(p), m) for p, m in calls],
                         [(_guided._norm(os.path.join(self.claude, "neb.pre-chmod.db")), 0o600)])

    def test_exclusividad_con_un_archivo_que_no_es_base_reporta_su_tipo(self):
        bad = os.path.join(self.claude, "no-es-base.db")
        with open(bad, "wb") as fh:
            fh.write(b"esto no es sqlite" * 100)
        motivo = _guided.base_sin_otras_conexiones(_machine.Ctx(self.home, db_path=bad, user_env=self.env))
        self.assertIn("DatabaseError", motivo)
        self.assertNotIn("otra sesión", motivo)

    def test_exclusividad_que_no_vuelve_a_wal_la_regresa(self):
        real_connect = sqlite3.connect

        class Con:
            def __init__(self, con):
                self.con, self.fooled = con, False

            def execute(self, sql, *a):
                if sql == "PRAGMA journal_mode=WAL" and not self.fooled:   # la primera vuelta «falla»
                    self.fooled = True
                    return real_connect(":memory:").execute("SELECT 'delete'")
                return self.con.execute(sql, *a)

            def close(self):
                self.con.close()
        with mock.patch.object(_guided.sqlite3, "connect", lambda *a, **k: Con(real_connect(*a, **k))):
            motivo = _guided.base_sin_otras_conexiones(_machine.Ctx(self.home, db_path=self.db, user_env=self.env))
        self.assertIn("no volvió a WAL", motivo)
        self.assertEqual(self.journal_mode(), "wal")


class TestAlIniciar(Base):
    """`neb-migrate.py al-iniciar`, la entrada de migración de SessionStart (7.5.0)."""

    def setUp(self):
        super().setUp()
        # Árbol de prueba con su bootstrap/ y su hooks/: al-iniciar carga el arranque y las migraciones de su árbol.
        os.makedirs(os.path.join(self.tree, "bootstrap"))
        shutil.copyfile(os.path.join(NEB, "bootstrap", "neb-bootstrap-context.py"),
                        os.path.join(self.tree, "bootstrap", "neb-bootstrap-context.py"))
        shutil.copytree(os.path.join(NEB, "hooks", "lib"), os.path.join(self.tree, "hooks", "lib"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copyfile(os.path.join(NEB, "hooks", "logbook-schema.sql"),
                        os.path.join(self.tree, "hooks", "logbook-schema.sql"))
        for k in ("CLAUDE_PROJECT_DIR", "NEB_HOME", "NEB_INTERNAL_SUBSESSION", "CLAUDE_PREPROCESS_RECURSION"):
            os.environ.pop(k, None)

    def run_al_iniciar(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = nm.al_iniciar(self.home)
        self.assertEqual(rc, 0)
        return out.getvalue()

    def lock(self):
        fd = _guided.try_lock(_guided.lock_path(_machine.Ctx(self.home, db_path=self.db)))
        self.assertIsNotNone(fd)
        self.addCleanup(_guided.unlock, fd)
        return fd

    def exists(self, name):
        return os.path.exists(os.path.join(self.claude, name))

    def test_sin_pendientes_no_dice_nada(self):
        self.assertEqual(self.run_al_iniciar(), "")

    def test_critico_corre_lo_que_tiene_respaldo_y_encarga_el_menu(self):
        self.touch("libre.txt")
        self.touch("dev.txt")
        self.settings({"NEB_PRUEBA_A": "1"})
        text = self.run_al_iniciar()
        self.assertFalse(self.exists("libre.txt"))                   # corrió solo, con su respaldo
        self.assertTrue(self.exists("libre.txt.bak"))
        self.assertNotIn("NEB_PRUEBA_A", self.settings_env())
        self.assertTrue(self.exists("dev.txt"), "lo que pide al dev no corre solo")
        self.assertIn("aplicó al iniciar la sesión", text)
        self.assertIn("`%s:libre-respaldo`" % V, text)
        self.assertIn("`%s:settings-solo`" % V, text)
        self.assertIn("`%s:libre-dev`" % V, text)                    # el encargo del menú
        self.assertIn("pasos 1, 2, 4 y 5 (el 3 ya lo corrió el inicio de sesión) de `", text)
        self.assertIn("/commands/migrate.md`", text)
        self.assertIn("No ofrezcas abrir otra sesión", text)
        self.assertNotIn("\r", text)
        self.assertIn("no es una parte del arranque", text)
        self.assertLessEqual(nm._u16(text), nm.AL_INICIAR_MAX)

    def test_lo_omitido_no_se_encarga(self):
        self.touch("dev.txt")
        self.skip(V + ":libre-dev")
        self.assertEqual(self.run_al_iniciar(), "")

    def test_critico_sin_candado_no_corre_pero_encarga_el_menu(self):
        self.touch("libre.txt")
        self.touch("dev.txt")
        self.lock()                                                  # otra corrida lo tiene
        text = self.run_al_iniciar()
        self.assertTrue(self.exists("libre.txt"), "sin el candado no corre nada")
        self.assertNotIn("aplicó", text)
        self.assertIn("`%s:libre-dev`" % V, text, "el encargo sale aunque no tome el candado: solo lee")

    def test_critico_apply_skip_y_restore_con_el_candado_tomado(self):
        self.touch("libre.txt")
        self.lock()
        rc, out = self.apply()
        self.assertEqual((rc, out["motivo"]), (1, "migracion-en-curso"))
        self.assertTrue(self.exists("libre.txt"))
        rc, out = self.skip(V + ":libre-dev")
        self.assertEqual((rc, out["motivo"]), (1, "migracion-en-curso"))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            rc = nm.restore(self.home, os.path.join(self.claude, "neb-backups", "neb.pre-paso-1.20260101T000000Z.db"))
        self.assertEqual((rc, json.loads(buf.getvalue())["motivo"]), (1, "migracion-en-curso"))

    def test_critico_un_proceso_muerto_libera_el_candado(self):
        import subprocess
        import time as _t
        path = _guided.lock_path(_machine.Ctx(self.home, db_path=self.db))
        code = ("import sys, time; sys.path.insert(0, %r); import _guided\n"
                "fd = _guided.try_lock(%r); print('tomado' if fd is not None else 'ocupado', flush=True)\n"
                "time.sleep(60)\n") % (os.path.join(NEB, "hooks", "lib"), path)
        p = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(p.stdout.readline().strip(), "tomado")
            self.assertIsNone(_guided.try_lock(path), "lo tiene el otro proceso")
            p.kill()                                                 # TerminateProcess en Windows, SIGKILL fuera
            p.wait(30)
        finally:
            if p.poll() is None:
                p.kill()
            p.stdout.close()
        fd = None
        for _ in range(20):
            fd = _guided.try_lock(path)
            if fd is not None:
                break
            _t.sleep(0.1)
        self.assertIsNotNone(fd, "el sistema libera el candado al morir el proceso")
        _guided.unlock(fd)

    def test_critico_dos_al_iniciar_a_la_vez_aplican_una_sola_vez(self):
        import subprocess
        import threading
        self.write_migration("9.9.11", textwrap.dedent('''
            import os, shutil, time
            from _guided import GuidedStep

            def _det(ctx):
                return os.path.exists(os.path.join(ctx.claude_dir, "lento.txt"))

            def _apl(ctx):
                with open(os.path.join(ctx.claude_dir, "cuenta.txt"), "a") as fh:
                    fh.write("x")
                time.sleep(1.5)
                bak = os.path.join(ctx.claude_dir, "lento.txt.bak-%d" % os.getpid())
                shutil.move(os.path.join(ctx.claude_dir, "lento.txt"), bak)
                return {"respaldo": bak}

            STEPS = [GuidedStep("lento", "Paso lento", detectar=_det, aplicar=_apl, respaldo=True)]
        '''))
        # Como lo correría la plataforma: el script del árbol de prueba en dos procesos a la vez.
        shutil.copyfile(os.path.join(NEB, "bootstrap", "neb-migrate.py"),
                        os.path.join(self.tree, "bootstrap", "neb-migrate.py"))
        shutil.copyfile(os.path.join(NEB, "VERSION"), os.path.join(self.tree, "VERSION"))
        self.touch("lento.txt")
        env = dict(os.environ, HOME=self.home, USERPROFILE=self.home)
        script = os.path.join(self.tree, "bootstrap", "neb-migrate.py")
        results = []

        def correr():
            r = subprocess.run([sys.executable, script, "al-iniciar"], env=env, capture_output=True, timeout=120)
            results.append(r)
        hilos = [threading.Thread(target=correr) for _ in range(2)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        self.assertEqual([r.returncode for r in results], [0, 0], [r.stderr for r in results])
        with open(os.path.join(self.claude, "cuenta.txt"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "x", "un solo proceso corrió el paso")
        self.assertFalse(self.exists("lento.txt"))

    def test_critico_exclusivo_reintenta_dentro_de_la_ventana(self):
        import threading
        self.touch("excl.txt")
        other = sqlite3.connect(self.db, check_same_thread=False)
        other.execute("SELECT count(*) FROM work").fetchone()
        t = threading.Timer(1.0, other.close)                        # la otra conexión se va a 1 s
        t.start()
        try:
            text = self.run_al_iniciar()
        finally:
            t.cancel()
            try:
                other.close()
            except sqlite3.Error:
                pass
        self.assertFalse(self.exists("excl.txt"), text)
        self.assertIn("`%s:exclusivo`" % V, text)

    def test_critico_exclusivo_sin_ventana_queda_pendiente_sin_pedir_nada(self):
        import time as _t
        self.touch("excl.txt")
        other = sqlite3.connect(self.db)
        other.execute("SELECT count(*) FROM work").fetchone()
        try:
            t0 = _t.monotonic()
            text = self.run_al_iniciar()
            elapsed = _t.monotonic() - t0
        finally:
            other.close()
        self.assertTrue(self.exists("excl.txt"))
        self.assertIn("Quedan para el siguiente inicio de sesión", text)
        self.assertIn("`%s:exclusivo`" % V, text)
        self.assertNotIn("cierra", text, "nunca pide cerrar sesiones")
        self.assertLess(elapsed, nm.AL_INICIAR_WINDOW + 2.5, "la ventana acota la espera")
        self.run_al_iniciar()                                        # sin la otra conexión: se aplica
        self.assertFalse(self.exists("excl.txt"))

    def test_presupuesto_vencido_no_empieza_pasos(self):
        self.touch("libre.txt")
        with mock.patch.object(nm, "AL_INICIAR_BUDGET", 0.0):
            text = self.run_al_iniciar()
        self.assertTrue(self.exists("libre.txt"))
        self.assertIn("sin tiempo en este inicio de sesión", text)
        self.run_al_iniciar()
        self.assertFalse(self.exists("libre.txt"))

    def test_critico_sale_con_0_ante_una_excepcion(self):
        with mock.patch.object(nm, "_al_iniciar_run", side_effect=RuntimeError("x")):
            text = self.run_al_iniciar()
        self.assertIn("falló al iniciar la sesión (RuntimeError)", text)
        with mock.patch.object(nm, "_load_bootstrap", side_effect=ImportError("x")):
            self.assertEqual(self.run_al_iniciar(), "")

    def test_main_al_iniciar_sale_con_0(self):
        with mock.patch.object(nm, "al_iniciar", return_value=0) as m, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(nm.main(["al-iniciar"]), 0)
        m.assert_called_once()

    def test_neb_skip_no_hace_nada(self):
        proj = tempfile.mkdtemp(prefix="neb-test-proj-")
        self.addCleanup(shutil.rmtree, proj, True)
        with open(os.path.join(proj, "CLAUDE.md"), "w", encoding="utf-8") as fh:
            fh.write("<!-- neb: skip -->\n")
        self.touch("libre.txt")
        self.touch("dev.txt")
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": proj}):
            self.assertEqual(self.run_al_iniciar(), "")
        self.assertTrue(self.exists("libre.txt"))

    def test_omitidos_ilegibles_no_ofrecen_menu(self):
        self.touch("dev.txt")
        with mock.patch.object(_guided, "read_skips", side_effect=sqlite3.OperationalError("disk I/O error")):
            text = self.run_al_iniciar()
        self.assertIn("no se pudieron leer los pasos que el dev omitió", text)
        self.assertNotIn("pasos 1, 2, 4 y 5", text)
        self.assertTrue(self.exists("dev.txt"))

    def test_deteccion_que_falla_entra_al_encargo(self):
        self.write_migration("9.9.10", "from _guided import GuidedStep\n"
                             "def d(ctx):\n    raise OSError('sin acceso')\n"
                             "STEPS = [GuidedStep('d', 'd', detectar=d, aplicar=lambda c: {})]\n")
        text = self.run_al_iniciar()
        self.assertIn("`9.9.10:d`", text)
        self.assertIn("su detección falla", text)
        self.assertNotIn("sin acceso", text)
        self.skip("9.9.10:d")
        self.assertNotIn("9.9.10:d", self.run_al_iniciar())

    def test_lo_que_no_carga_se_reporta(self):
        self.write_migration("9.9.8", "def f(:\n")
        text = self.run_al_iniciar()
        self.assertIn("la migración `9.9.8.py` no carga", text)
        self.assertIn("SyntaxError", text)

    def test_tope_de_la_salida(self):
        for i in range(60):
            self.write_migration("8.%d.0" % i, "from _guided import GuidedStep\n"
                                 "STEPS = [GuidedStep('p', 'paso de prueba con un título largo para llenar', "
                                 "detectar=lambda c: True, aplicar=lambda c: {})]\n")
        text = self.run_al_iniciar()
        self.assertLessEqual(nm._u16(text), nm.AL_INICIAR_MAX)
        self.assertIn("`neb-migrate.py status` da el detalle", text)
        self.assertIn("piden al dev", text, "el encargo tiene la mayor prioridad")
        # El recorte acorta la lista de pasos, nunca la instrucción del encargo (va antes de la lista).
        for frase in ("pasos 1, 2, 4 y 5 (el 3 ya lo corrió el inicio de sesión) de `", "/commands/migrate.md`", "NEB_SRC=", "No ofrezcas abrir otra sesión",
                      "«Aplicarlo», «No aplicarlo» y «Después»"):
            self.assertIn(frase, text)
        self.assertRegex(text, r"y \d+ más")

    def test_critico_el_recorte_conserva_fallos_y_encargo_completos(self):
        fallos = {"prio": 1, "ord": 1, "pre": "Problemas de la migración de Neb al iniciar la sesión: ",
                  "items": ["`8.%d.0:p` (paso) falló: %s" % (i, "x" * 120) for i in range(40)], "post": ".",
                  "tell": True}
        encargo = {"prio": 1, "ord": 0, "pre": nm.AL_INICIAR_ASK % (nm.AL_INICIAR_PASO3["corrio"],
                                                                 "C:/plug/commands/migrate.md", nm._sh_quote("C:/plug")),
                   "items": ["`8.%d.0:d` (paso dev)" % i for i in range(40)], "post": ".", "tell": False}
        aplicado = {"prio": 4, "pre": "La migración guiada de Neb aplicó al iniciar la sesión: ",
                    "items": ["`7.0.0:a` (a)"], "post": ".", "tell": True}
        text = nm._fit([aplicado, fallos, encargo])
        self.assertLessEqual(nm._u16(text), nm.AL_INICIAR_MAX)
        self.assertIn("Problemas de la migración", text)
        self.assertIn("No ofrezcas abrir otra sesión", text)
        self.assertIn("NEB_SRC='C:/plug'", text)
        self.assertNotIn("aplicó al iniciar la sesión", text, "la prioridad 4 sale antes de acortar la 1")
        self.assertEqual(text.count("Dile al dev"), 1)
        self.assertLess(text.index("No ofrezcas abrir otra sesión"), text.index("Problemas de la migración"),
                        "el encargo va antes que los fallos: el corte final cae en los fallos")

    def test_critico_un_fallo_enorme_no_se_lleva_el_encargo(self):
        fallos = {"prio": 1, "ord": 1, "pre": "Problemas de la migración de Neb al iniciar la sesión: ",
                  "items": ["`8.0.0:p` (paso) falló: " + "x" * 6000], "post": ".", "tell": True}
        encargo = {"prio": 1, "ord": 0, "pre": nm.AL_INICIAR_ASK % (nm.AL_INICIAR_PASO3["corrio"],
                                                                 "C:/plug/commands/migrate.md", nm._sh_quote("C:/plug")),
                   "items": ["`8.0.0:d` (paso dev)"], "post": ".", "tell": False}
        text = nm._fit([fallos, encargo])
        self.assertLessEqual(nm._u16(text), nm.AL_INICIAR_MAX)
        for frase in ("No ofrezcas abrir otra sesión", "NEB_SRC='C:/plug'", "`8.0.0:d`", "`8.0.0:p` (paso) falló: xxx",
                      "Dile al dev"):
            self.assertIn(frase, text)
        self.assertIn("x….", text, "se acorta la entrada (con su cierre), no el texto por el final")

    def test_critico_en_el_aviso_el_encargo_va_antes_que_los_fallos(self):
        report = {"guiados": {"fallos": [{"id": "8.0.0:p", "titulo": "paso", "detalle": "x" * 100}],
                              "aplicados": [], "pendientes": [], "manual": [], "errores_de_carga": [], "error": None}}
        guided = {"pendientes": [{"id": "8.0.0:d", "titulo": "paso dev", "clase": "dev"}], "error_omitidos": None}
        text = nm._al_iniciar_text(report, "", guided)
        self.assertLess(text.index("No ofrezcas abrir otra sesión"), text.index("Problemas de la migración"))

    def test_la_orden_de_decirlo_va_una_sola_vez(self):
        self.touch("libre.txt")
        self.write_migration("9.9.7", "def f(:\n")
        text = self.run_al_iniciar()
        self.assertIn("aplicó al iniciar la sesión", text)
        self.assertIn("no carga", text)
        self.assertEqual(text.count("Dile al dev"), 1, text)

    def test_lo_pendiente_no_se_le_pide_decir_al_dev(self):
        self.touch("excl.txt")
        other = sqlite3.connect(self.db)
        other.execute("SELECT count(*) FROM work").fetchone()
        try:
            with mock.patch.object(nm, "AL_INICIAR_WINDOW", 0.0):
                text = self.run_al_iniciar()
        finally:
            other.close()
        self.assertIn("Quedan para el siguiente inicio de sesión", text)
        self.assertIn("se reintentan solos", text)
        self.assertNotIn("Dile al dev", text)

    def test_con_un_fallo_y_lo_pendiente_la_orden_no_queda_junto_a_lo_pendiente(self):
        self.touch("excl.txt")
        self.write_migration("9.9.7", "def f(:\n")
        other = sqlite3.connect(self.db)
        other.execute("SELECT count(*) FROM work").fetchone()
        try:
            with mock.patch.object(nm, "AL_INICIAR_WINDOW", 0.0):
                text = self.run_al_iniciar()
        finally:
            other.close()
        self.assertEqual(text.count("Dile al dev"), 1, text)
        self.assertLess(text.index("Dile al dev"), text.index("Quedan para el siguiente inicio"))
        self.assertIn("lo que se reintenta solo, únicamente si pregunta", text)

    def test_lo_aplicado_lleva_su_detalle(self):
        self.touch("libre.txt")
        text = self.run_al_iniciar()
        self.assertIn("`%s:libre-respaldo` (Libre con respaldo): movido, respaldo `" % V, text)

    def test_neb_src_va_entre_comillas(self):
        self.assertEqual(nm._sh_quote("C:/Users/Ana María/x"), "'C:/Users/Ana María/x'")
        self.assertEqual(nm._sh_quote("a'b"), "'a'\"'\"'b'")
        self.touch("dev.txt")
        text = self.run_al_iniciar()
        self.assertIn("NEB_SRC='", text)

    def test_critico_sin_la_carpeta_de_la_base_no_corre_pasos(self):
        # Sin ~/.claude de verdad (no un sustituto de _take_lock): los settings viven en CLAUDE_CONFIG_DIR.
        cfg = os.path.join(self.home, "cfg")
        os.makedirs(cfg)
        os.environ["CLAUDE_CONFIG_DIR"] = cfg
        with open(os.path.join(cfg, "settings.json"), "w", encoding="utf-8") as fh:
            json.dump({"env": {"NEB_PRUEBA_A": "1"}}, fh)
        shutil.rmtree(self.claude)
        text = self.run_al_iniciar()
        with open(os.path.join(cfg, "settings.json"), encoding="utf-8") as fh:
            self.assertIn("NEB_PRUEBA_A", json.load(fh)["env"], "sin candado no corre nada solo")
        self.assertFalse(os.path.isdir(self.claude), "no crea la carpeta de la base")
        self.assertIn("`/neb:migrate` corre estos pasos: `%s:settings-solo`" % V, text)
        self.assertIn("Dile al dev", text)
        self.assertNotIn("se reintentan solos", text)

    def test_sin_correr_la_migracion_el_encargo_incluye_el_paso_3(self):
        self.touch("dev.txt")
        with mock.patch.object(nm, "_take_lock", lambda home: -1):
            text = self.run_al_iniciar()
        self.assertIn("pasos 1 a 5 (este inicio de sesión no corrió la migración", text)
        self.assertNotIn("el 3 ya lo corrió", text)
        self.assertIn("no se pudo tomar el candado", text)

    def test_al_iniciar_respeta_la_espera_tras_un_fallo_de_base(self):
        # Se espía la frontera real (_db_shared._connect), no el envoltorio: retry=False es lo que hace esperar.
        seen = []
        real = nm._db_shared._connect

        def spy(db, *a, **k):
            seen.append(k.get("retry", False))
            return real(db, *a, **k)
        with mock.patch.object(nm._db_shared, "_connect", spy):
            self.run_al_iniciar()
        self.assertTrue(seen)
        self.assertEqual(set(seen), {False})

    def test_un_enlace_puesto_al_abrir_el_candado_se_rechaza(self):
        path = _guided.lock_path(_machine.Ctx(self.home, db_path=self.db))
        with mock.patch.object(_guided._machine, "is_link", side_effect=[False, True]):
            with self.assertRaises(OSError):
                _guided.try_lock(path)
        self.touch("libre.txt")
        calls = iter([False, True])
        with mock.patch.object(_guided._machine, "is_link", side_effect=lambda p: next(calls, False)):
            text = self.run_al_iniciar()
        self.assertTrue(self.exists("libre.txt"))
        self.assertIn("no se pudo tomar el candado", text)

    def test_un_error_del_candado_que_no_es_contencion_no_se_calla(self):
        import errno as _errno
        target = "msvcrt" if os.name == "nt" else "fcntl"
        mod = __import__(target)
        fn = "locking" if os.name == "nt" else "flock"
        self.touch("libre.txt")
        with mock.patch.object(mod, fn, side_effect=OSError(_errno.EINVAL, "sin candados")):
            text = self.run_al_iniciar()
        self.assertTrue(self.exists("libre.txt"))
        self.assertIn("no se pudo tomar el candado", text)

    def test_partes_no_cambian_con_lo_pendiente(self):
        # Flujo 2: lo que las partes agregan al arranque no cambia con lo guiado pendiente.
        bc = nm._load_bootstrap()
        with mock.patch.object(os.path, "expanduser", lambda p: self.home if p == "~" else p):
            antes = bc._env_notices(os.path.join(self.tree, "bootstrap"))
            self.touch("libre.txt")
            self.touch("dev.txt")
            despues = bc._env_notices(os.path.join(self.tree, "bootstrap"))
        self.assertEqual(antes, despues)
        self.assertFalse(any("migración guiada" in n for n in despues), despues)


if __name__ == "__main__":
    unittest.main()
