#!/usr/bin/env python3
"""
test_migration_7_3_0.py — la migración guiada de neb 7.3.0 (migrations/7.3.0.py).

Cubre, con el árbol real y homes temporales:
  • la migración carga con sus dos pasos (compas-proyectos y vacuum-neb-db) y sus atributos;
  • compas-proyectos de punta a punta con `apply --guiados`: `Clientes:` -> `Proyectos:` con el mismo
    contenido (bonos idénticos), sin `Roadmap:`, `version: 3`, respaldo nuevo en la carpeta de respaldos con los bytes
    originales; la segunda corrida no lo marca; sin compas, sin-cambio; un compas solo con `version: 2` se
    marca; los fines de línea CRLF y el BOM se conservan;
  • compas.md de solo lectura (desde 7.4.0 se migra y conserva la protección) y de más de 1 MB (se migra);
    falla sembrada: error al reemplazarlo (también siendo de solo lectura) -> fallo con el original intacto, con
    su protección y sin respaldo ni temporal sobrante;
  • vacuum-neb-db sobre una base con muchas páginas libres: freelist 0, integridad, la base vuelve a WAL, el
    respaldo es una copia válida (journal_mode=DELETE, íntegra, con los datos) y después ya no se marca; una base
    compacta no se marca; con otra conexión abierta no corre y queda pendiente con su motivo, sin respaldo; si la
    segunda comprobación falla, no compacta y no deja la copia;
  • mantenimiento recurrente: la base vuelve a acumular páginas libres, el paso se ofrece otra vez y la segunda
    compactación borra la copia anterior y deja solo la suya, sin tocar otros respaldos;
  • espacio en disco: sin espacio (shutil.disk_usage parcheado) queda pendiente con lo que hace falta, sin copia
    ni cambios; copia y VACUUM en el mismo volumen se suman; el temporal de SQLite en otro volumen se revisa;
  • falla sembrada en el VACUUM (SQLITE_FULL) y en integrity_check: ninguna copia queda sin reportar, y el
    detalle no pide un restore que no existe para ese respaldo;
  • los bonos del compas migrado, leídos con pendings.parse_compas de 7.3.0, son los de 7.2.x; con BOM y el
    frontmatter en la primera línea, detectar y aplicar ven lo mismo;
  • de punta a punta: una base de neb en esquema 2 (raíz 'cliente') y fragmentada; un solo `apply --guiados`
    corre el paso de base 3 y después vacuum-neb-db, sin dejar el exclusivo en pendiente.

Disposición de 8.0.0: la base, compas.md y los respaldos en la carpeta de datos del home temporal (<home>/.neb,
sin NEB_DATA: _entorno); con la de 7.x (en ~/.claude), la cubre test_migration_8_0_0.py. Nunca toca ~/.claude,
~/.neb, neb.db ni compas.md reales.
  py -m unittest hooks.tests.test_migration_7_3_0
"""

import collections
import contextlib
import glob
import importlib.util
import io
import json
import os
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sin_registro  # noqa: E402,F401 — sin el registro real de Windows
import _entorno  # noqa: E402,F401 — quita NEB_DATA: la carpeta de datos es la del home temporal
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
NEB = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(NEB, "hooks", "lib"))

import _guided  # noqa: E402
import _machine  # noqa: E402

V = "7.3.0"

# compas.md como lo escribía write_compas de 7.2.x (v2), con un objetivo con bonos y otro sin ellos.
COMPAS_V2 = """# compas.md — Brújula de priorización personal

<!-- Artefacto LOCAL, NO versionado, mantenido por Claude (REQ neb-pendings-sqlite).
     Fuente ÚNICA del peso de cada tema: los `topic` de la DB no llevan peso.
     El recomendador parsea este archivo en CADA pase de /pendings-review.
     Jerarquía de fuentes de prioridad (mayor a menor):
       1. Criterio explícito del prompt (efímero, no se escribe aquí)
       2. Banda curada del pendiente (pase del dev / curate) — este archivo no la pisa
       3. Este compas.md (peso por tópico vía objetivos + bonus por cliente)
       4. Señales intrínsecas del pending (work/fase, bloqueo, urgencia, recencia)
       5. Si insuficiente: Claude infiere objetivos, pregunta y ESCRIBE aquí.
     `Temas:` = slugs del eje tópico; `Clientes:` = slug=+bonus del eje cliente (opcional).
     Editar a mano es válido; Claude respeta lo que encuentre y solo propone deltas. -->

---
version: 2
updated_at: 2026-11-01
owner: dev
---

## Objetivo: Seguridad del parque
- **Peso:** 90
- **Temas:** seguridad, incidente
- **Roadmap:** —
- **Clientes:** alpha=+15, beta=+10, gamma=+5

## Objetivo: Deuda técnica
- **Peso:** 40
- **Temas:** deuda, rendimiento
- **Roadmap:** INIT-018
"""


class FakeUserEnv:
    kind = "windows"

    def present_user(self, name):
        return False

    def present_machine(self, name):
        return False

    def delete_user(self, name):
        raise AssertionError("esta migración no toca variables de usuario")

    def broadcast(self):
        pass


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


nm = _load("neb_migrate_730_test", os.path.join(NEB, "bootstrap", "neb-migrate.py"))


def _migration():
    migrations, errors = _guided.load(NEB)
    bad = [e for e in errors if e[0] == V + ".py"]
    if bad:
        raise AssertionError(f"7.3.0.py no carga: {bad}")
    for m in migrations:
        if m.version == V:
            return m
    raise AssertionError("no se encontró la migración 7.3.0")


def _step(step_id):
    return {s.id: s for s in _migration().steps}[step_id]


def _field(text, label):
    """Valores de las líneas '- **Label:** valor' (misma forma que parse_compas), en orden."""
    pat = re.compile(r"^[ \t\-*]*" + re.escape(label) + r"[ \t]*:[ \t]*\**[ \t]*(.*?)[ \t]*$", re.MULTILINE)
    return [m.group(1).strip() for m in pat.finditer(text)]


def _bonus(text, label):
    out = {}
    for raw in _field(text, label):
        for cell in raw.split(","):
            if "=" in cell:
                slug, val = cell.split("=", 1)
                out[slug.strip()] = int(re.search(r"-?\d+", val).group(0))
    return out


class Base(unittest.TestCase):

    def setUp(self):
        p = mock.patch.dict(os.environ)
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop("CLAUDE_CONFIG_DIR", None)
        self.home = tempfile.mkdtemp(prefix="neb-test-730-")
        self.addCleanup(self._rmtree)
        self.claude = os.path.join(self.home, ".claude")
        os.makedirs(self.claude)
        self.data = os.path.join(self.home, ".neb")      # carpeta de datos (8.0.0)
        os.makedirs(self.data)
        self.db = os.path.join(self.data, "neb.db")
        self.compas = os.path.join(self.data, "compas.md")
        self.backups = os.path.join(self.data, "backups")
        self.env = FakeUserEnv()
        p = mock.patch.object(_machine, "default_user_env", lambda: self.env)
        p.start()
        self.addCleanup(p.stop)

    def _rmtree(self):
        for root, _dirs, files in os.walk(self.home):
            for f in files:
                try:
                    os.chmod(os.path.join(root, f), stat.S_IWRITE | stat.S_IREAD)
                except OSError:
                    pass
        shutil.rmtree(self.home, True)

    def ctx(self):
        return _machine.Ctx(self.home, db_path=self.db, user_env=self.env)

    def write_compas(self, data):
        mode = "wb" if isinstance(data, bytes) else "w"
        kw = {} if isinstance(data, bytes) else {"encoding": "utf-8", "newline": ""}
        with open(self.compas, mode, **kw) as fh:
            fh.write(data)

    def read_bytes(self, path):
        with open(path, "rb") as fh:
            return fh.read()

    def backups_like(self, pattern):
        return sorted(glob.glob(os.path.join(self.backups, pattern)))


# --------------------------------------------------------------------------- carga

class TestCarga(unittest.TestCase):

    def test_carga_con_sus_dos_pasos(self):
        steps = {s.id: s for s in _migration().steps}
        self.assertEqual(set(steps), {"compas-proyectos", "vacuum-neb-db"})
        self.assertTrue(steps["compas-proyectos"].respaldo)
        self.assertFalse(steps["compas-proyectos"].exclusivo)
        v = steps["vacuum-neb-db"]
        self.assertTrue(v.respaldo and v.exclusivo)
        self.assertTrue(callable(v.condicion), "vacuum-neb-db declara su propia condición")
        self.assertTrue(os.path.isfile(_migration().prompt or ""), "falta migrations/7.3.0.md")


# --------------------------------------------------------------------------- compas-proyectos

class TestCompasProyectos(Base):

    def apply(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = nm.apply(self.home, (), False, True)
        return rc, json.loads(out.getvalue())

    @staticmethod
    def ids(rows):
        return {r["id"] for r in rows}

    def test_reescribe_con_proyectos_sin_roadmap_y_version_3(self):
        self.write_compas(COMPAS_V2)
        original = self.read_bytes(self.compas)
        self.assertTrue(_step("compas-proyectos").detectar(self.ctx()))

        rc, out = self.apply()
        g = out["guiados"]
        self.assertIn(f"{V}:compas-proyectos", self.ids(g["aplicados"]), out)
        row = [r for r in g["aplicados"] if r["id"] == f"{V}:compas-proyectos"][0]

        new = self.read_bytes(self.compas).decode("utf-8")
        self.assertNotIn("Roadmap", new)
        self.assertEqual(_field(new, "Clientes"), [])
        self.assertEqual(_field(new, "Proyectos"), ["alpha=+15, beta=+10, gamma=+5"])
        self.assertEqual(_bonus(new, "Proyectos"), _bonus(COMPAS_V2, "Clientes"))
        self.assertEqual(_bonus(new, "Proyectos"), {"alpha": 15, "beta": 10, "gamma": 5})
        self.assertIn("\nversion: 3\n", new)
        self.assertNotIn("version: 2", new)
        # lo demás queda igual: pesos, temas, títulos y frontmatter
        self.assertEqual(_field(new, "Peso"), ["90", "40"])
        self.assertEqual(_field(new, "Temas"), ["seguridad, incidente", "deuda, rendimiento"])
        self.assertIn("updated_at: 2026-11-01\nowner: dev\n", new)
        self.assertIn("`Proyectos:` = slug=+bonus del eje proyecto (opcional).", new)
        self.assertIn("bonus por proyecto)", new)
        expected = COMPAS_V2.replace("- **Clientes:**", "- **Proyectos:**").replace("version: 2", "version: 3")
        expected = "".join(l for l in expected.splitlines(keepends=True) if "**Roadmap:**" not in l)
        expected = expected.replace("`Clientes:` = slug=+bonus del eje cliente", "`Proyectos:` = slug=+bonus del eje proyecto")
        expected = expected.replace("bonus por cliente)", "bonus por proyecto)")
        self.assertEqual(new, expected)

        # con el parse_compas de 7.3.0, los bonos por proyecto son los client_bonus que daba 7.2.x y los pesos
        # por tema no cambian
        import pendings
        parsed = pendings.parse_compas(self.home)
        self.assertEqual(parsed["project_bonus"], {"alpha": 15, "beta": 10, "gamma": 5})
        self.assertEqual(parsed["topic_weight"],
                         {"seguridad": 90, "incidente": 90, "deuda": 40, "rendimiento": 40})

        # respaldo: archivo nuevo en la carpeta de respaldos con los bytes originales
        backups = self.backups_like("compas.pre-7.3.0.*.md")
        self.assertEqual(len(backups), 1)
        self.assertEqual(os.path.normcase(row["respaldo"]), os.path.normcase(backups[0]))
        self.assertEqual(self.read_bytes(backups[0]), original)
        self.assertEqual([f for f in os.listdir(self.data) if ".tmp-" in f], [])

        # segunda corrida: ya no se marca
        self.assertFalse(_step("compas-proyectos").detectar(self.ctx()))
        rc2, out2 = self.apply()
        self.assertNotIn(f"{V}:compas-proyectos", self.ids(out2["guiados"]["aplicados"]))
        self.assertNotIn(f"{V}:compas-proyectos", self.ids(out2["guiados"]["pendientes"]))
        r = _guided.run(self.ctx(), _step("compas-proyectos"))
        self.assertEqual(r["estado"], "sin-cambio")
        self.assertEqual(len(self.backups_like("compas.pre-7.3.0.*.md")), 1)

    def test_sin_compas_sin_cambio(self):
        self.assertFalse(_step("compas-proyectos").detectar(self.ctx()))
        r = _guided.run(self.ctx(), _step("compas-proyectos"))
        self.assertEqual(r["estado"], "sin-cambio")
        self.assertFalse(os.path.exists(self.compas))
        self.assertFalse(os.path.isdir(self.backups) and os.listdir(self.backups))

    def test_compas_v3_no_se_marca(self):
        self.write_compas("---\nversion: 3\n---\n\n## Objetivo: X\n- **Peso:** 10\n- **Temas:** a\n"
                          "- **Proyectos:** beta=+5\n")
        self.assertFalse(_step("compas-proyectos").detectar(self.ctx()))

    def test_clientes_en_un_comentario_no_cuenta(self):
        self.write_compas("---\nversion: 3\n---\n<!-- `Clientes:` era el nombre viejo -->\n")
        self.assertFalse(_step("compas-proyectos").detectar(self.ctx()))

    def test_solo_version_2_se_marca_y_sube_a_3(self):
        self.write_compas("---\nversion: 2\n---\n\n## Objetivo: X\n- **Peso:** 10\n- **Temas:** a\n")
        self.assertTrue(_step("compas-proyectos").detectar(self.ctx()))
        r = _guided.run(self.ctx(), _step("compas-proyectos"))
        self.assertEqual(r["estado"], "aplicado", r)
        self.assertEqual(self.read_bytes(self.compas).decode("utf-8"),
                         "---\nversion: 3\n---\n\n## Objetivo: X\n- **Peso:** 10\n- **Temas:** a\n")

    def test_bom_con_frontmatter_en_la_primera_linea_se_marca(self):
        """Detectar y aplicar ven el mismo texto: con BOM, un frontmatter en la primera línea con solo
        `version: 2` también se marca."""
        self.write_compas(b"\xef\xbb\xbf---\nversion: 2\n---\n\n## Objetivo: X\n- **Peso:** 10\n- **Temas:** a\n")
        self.assertTrue(_step("compas-proyectos").detectar(self.ctx()))
        r = _guided.run(self.ctx(), _step("compas-proyectos"))
        self.assertEqual(r["estado"], "aplicado", r)
        self.assertEqual(self.read_bytes(self.compas),
                         b"\xef\xbb\xbf---\nversion: 3\n---\n\n## Objetivo: X\n- **Peso:** 10\n- **Temas:** a\n")
        self.assertFalse(_step("compas-proyectos").detectar(self.ctx()))

    def test_crlf_y_bom_se_conservan(self):
        data = b"\xef\xbb\xbf" + COMPAS_V2.replace("\n", "\r\n").encode("utf-8")
        self.write_compas(data)
        r = _guided.run(self.ctx(), _step("compas-proyectos"))
        self.assertEqual(r["estado"], "aplicado", r)
        new = self.read_bytes(self.compas)
        self.assertTrue(new.startswith(b"\xef\xbb\xbf"))
        text = new[3:].decode("utf-8")
        self.assertNotIn("Roadmap", text)
        self.assertIn("- **Proyectos:** alpha=+15, beta=+10, gamma=+5\r\n", text)
        self.assertIn("\r\nversion: 3\r\n", text)
        self.assertNotIn("\n", text.replace("\r\n", ""))

    def test_solo_lectura_se_migra_y_conserva_la_proteccion(self):
        """Desde 7.4.0 el paso no pide al dev quitar la protección: la quita, reemplaza y el archivo nuevo la
        conserva."""
        self.write_compas(COMPAS_V2)
        original = self.read_bytes(self.compas)
        os.chmod(self.compas, stat.S_IREAD)
        r = _guided.run(self.ctx(), _step("compas-proyectos"))
        self.assertNotIn(r.get("estado"), ("fallo", "manual", "pendiente"), r)
        self.assertIn("conserva esa protección", r["detalle"])
        self.assertEqual(_field(self.read_bytes(self.compas).decode("utf-8"), "Proyectos"),
                         ["alpha=+15, beta=+10, gamma=+5"])
        self.assertFalse(os.access(self.compas, os.W_OK), "sigue de solo lectura")
        self.assertEqual([self.read_bytes(p) for p in self.backups_like("compas.pre-7.3.0.*.md")], [original])
        self.assertEqual([f for f in os.listdir(self.data) if ".tmp-" in f], [])
        self.assertFalse(_step("compas-proyectos").detectar(self.ctx()))

    def test_falla_sembrada_solo_lectura_y_error_al_reemplazar_deja_el_original_protegido(self):
        self.write_compas(COMPAS_V2)
        original = self.read_bytes(self.compas)
        os.chmod(self.compas, stat.S_IREAD)
        with mock.patch("os.replace", side_effect=PermissionError(13, "valor-que-no-sale")):
            r = _guided.run(self.ctx(), _step("compas-proyectos"))
        self.assertEqual(r["estado"], "fallo", r)
        self.assertEqual(self.read_bytes(self.compas), original)
        self.assertFalse(os.access(self.compas, os.W_OK), "el original vuelve a su protección")
        self.assertEqual(self.backups_like("compas.pre-7.3.0.*.md"), [])
        self.assertEqual([f for f in os.listdir(self.data) if ".tmp-" in f], [])
        self.assertTrue(_step("compas-proyectos").detectar(self.ctx()), "sigue pendiente")

    def test_compas_de_mas_de_1_mb_se_migra(self):
        """En 7.3.0 un compas.md de más de 1 MB quedaba en «manual»; desde 7.4.0 lo migra el paso."""
        relleno = "<!-- " + "x" * (1024 * 1024 + 10) + " -->" + chr(10)
        self.write_compas(COMPAS_V2 + relleno)
        self.assertTrue(_step("compas-proyectos").detectar(self.ctx()))
        r = _guided.run(self.ctx(), _step("compas-proyectos"))
        self.assertNotIn(r.get("estado"), ("fallo", "manual", "pendiente"), r)
        new = self.read_bytes(self.compas).decode("utf-8")
        self.assertEqual(_field(new, "Proyectos"), ["alpha=+15, beta=+10, gamma=+5"])
        self.assertTrue(new.endswith(relleno))
        self.assertFalse(_step("compas-proyectos").detectar(self.ctx()))

    def test_falla_sembrada_error_al_reemplazar_deja_el_original(self):
        self.write_compas(COMPAS_V2)
        original = self.read_bytes(self.compas)
        with mock.patch("os.replace", side_effect=PermissionError(13, "valor-que-no-sale")):
            r = _guided.run(self.ctx(), _step("compas-proyectos"))
        self.assertEqual(r["estado"], "fallo", r)
        self.assertNotIn("valor-que-no-sale", r["detalle"])
        self.assertIn("PermissionError", r["detalle"])
        self.assertEqual(self.read_bytes(self.compas), original)
        self.assertEqual(self.backups_like("compas.pre-7.3.0.*.md"), [])
        self.assertEqual([f for f in os.listdir(self.data) if ".tmp-" in f], [])

    def test_compas_que_cambia_durante_la_migracion_no_se_pisa(self):
        self.write_compas(COMPAS_V2)
        real_open = open
        state = {"n": 0}
        otra = COMPAS_V2.replace("90", "95").encode("utf-8")

        def racing_fsync(fd):
            # otra sesión reescribe compas.md justo antes de la relectura
            if state["n"] == 0:
                state["n"] = 1
                with real_open(self.compas, "wb") as fh:
                    fh.write(otra)
        with mock.patch("os.fsync", side_effect=racing_fsync):
            r = _guided.run(self.ctx(), _step("compas-proyectos"))
        self.assertEqual(r["estado"], "pendiente", r)
        self.assertEqual(self.read_bytes(self.compas), otra)
        self.assertEqual(self.backups_like("compas.pre-7.3.0.*.md"), [])


# --------------------------------------------------------------------------- vacuum-neb-db

class TestVacuum(Base):

    def make_db(self, rows=1200, delete_ratio=0.8, wal=True):
        """Base con una tabla de filas de ~4 KB; borra una parte para dejar páginas libres."""
        con = sqlite3.connect(self.db)
        if wal:
            con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, body BLOB)")
        con.executemany("INSERT INTO t (body) VALUES (?)", [(os.urandom(4000),) for _ in range(rows)])
        con.commit()
        con.execute("DELETE FROM t WHERE id <= ?", (int(rows * delete_ratio),))
        con.commit()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.close()

    def stats(self, path=None):
        con = sqlite3.connect(path or self.db)
        try:
            return {k: con.execute(f"PRAGMA {k}").fetchone()[0]
                    for k in ("page_count", "freelist_count", "page_size", "journal_mode", "integrity_check",
                              "auto_vacuum")} | {"rows": con.execute("SELECT count(*) FROM t").fetchone()[0],
                                                 "sum": con.execute("SELECT sum(id) FROM t").fetchone()[0]}
        finally:
            con.close()

    def test_compacta_con_respaldo_valido(self):
        self.make_db()
        before = self.stats()
        self.assertGreater(before["freelist_count"] * before["page_size"], 1024 * 1024)
        self.assertTrue(_step("vacuum-neb-db").detectar(self.ctx()))

        r = _guided.run(self.ctx(), _step("vacuum-neb-db"))
        self.assertEqual(r["estado"], "aplicado", r)

        after = self.stats()
        self.assertEqual(after["freelist_count"], 0)
        self.assertEqual(after["integrity_check"], "ok")
        self.assertEqual(after["journal_mode"], "wal", "la base vuelve a su modo de journal")
        self.assertEqual(after["auto_vacuum"], before["auto_vacuum"], "no cambia auto_vacuum")
        self.assertEqual((after["rows"], after["sum"]), (before["rows"], before["sum"]))
        self.assertLess(after["page_count"], before["page_count"])

        backups = self.backups_like("neb.pre-vacuum.*.db")
        self.assertEqual(len(backups), 1)
        self.assertEqual(os.path.normcase(r["respaldo"]), os.path.normcase(backups[0]))
        self.assertFalse(os.path.exists(backups[0] + "-wal") or os.path.exists(backups[0] + "-journal"))
        b = self.stats(backups[0])
        self.assertEqual(b["journal_mode"], "delete")
        self.assertEqual(b["integrity_check"], "ok")
        self.assertEqual((b["rows"], b["sum"]), (before["rows"], before["sum"]))
        self.assertEqual(b["freelist_count"], before["freelist_count"], "el respaldo es el estado previo")

        self.assertFalse(_step("vacuum-neb-db").detectar(self.ctx()), "tras compactar ya no se marca")
        r2 = _guided.run(self.ctx(), _step("vacuum-neb-db"))
        self.assertEqual(r2["estado"], "sin-cambio")

    def refragmentar(self, rows=1200, delete_ratio=0.8):
        """Vuelve a dejar páginas libres en una base ya compactada: inserta filas y borra las más viejas."""
        con = sqlite3.connect(self.db)
        try:
            con.executemany("INSERT INTO t (body) VALUES (?)", [(os.urandom(4000),) for _ in range(rows)])
            con.commit()
            con.execute("DELETE FROM t WHERE id IN (SELECT id FROM t ORDER BY id LIMIT ?)",
                        (int(rows * delete_ratio),))
            con.commit()
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            con.close()

    def test_patron_de_borrado_no_acepta_salto_de_linea_final(self):
        """Solo se borran nombres que casan completos: con re.match y `$`, un nombre con \\n final casaría."""
        step = _step("vacuum-neb-db")
        g = step.aplicar.__globals__
        bueno = "neb.pre-vacuum.20261124T000000123456Z.db"
        self.assertIsNotNone(g["_VACUUM_BACKUP_RE"].fullmatch(bueno))
        with tempfile.TemporaryDirectory() as d:
            ctx = mock.Mock(backups_dir=d)
            keep = os.path.join(d, "neb.pre-vacuum.20261125T000000000000Z.db")
            otros = [bueno, bueno + ".txt", "neb.pre-paso-3.20261124T000000000000Z.db"]
            for n in otros + [os.path.basename(keep)]:
                open(os.path.join(d, n), "wb").close()
            if os.name != "nt":  # Windows no admite \n en un nombre de archivo
                open(os.path.join(d, bueno + "\n"), "wb").close()
            g["_borrar_copias_anteriores"](ctx, keep)
            quedan = set(os.listdir(d))
        self.assertNotIn(bueno, quedan)
        self.assertTrue({bueno + ".txt", "neb.pre-paso-3.20261124T000000000000Z.db",
                         os.path.basename(keep)} <= quedan)
        if os.name != "nt":
            self.assertIn(bueno + "\n", quedan)

    def test_segunda_compactacion_borra_la_copia_anterior(self):
        """Mantenimiento recurrente: la base vuelve a acumular páginas libres, el paso se marca otra vez y, tras
        compactar, deja solo la copia de esta corrida; los demás respaldos de la carpeta no se tocan."""
        self.make_db()
        r1 = _guided.run(self.ctx(), _step("vacuum-neb-db"))
        self.assertEqual(r1["estado"], "aplicado", r1)
        first = self.backups_like("neb.pre-vacuum.*.db")
        self.assertEqual(len(first), 1)

        otros = {
            "neb.pre-paso-3.20261124T000000000000Z.db": b"paso-3",
            "compas.pre-7.3.0.20261124T000000000000Z.md": b"compas",
            "neb.pre-vacuum.notas.db": b"no casa con el patron",
            "neb.pre-vacuum.20261124T000000000000Z.db.txt": b"tampoco",
        }
        for name, data in otros.items():
            with open(os.path.join(self.backups, name), "wb") as fh:
                fh.write(data)

        self.refragmentar()
        self.assertTrue(_step("vacuum-neb-db").detectar(self.ctx()), "se vuelve a ofrecer")
        r2 = _guided.run(self.ctx(), _step("vacuum-neb-db"))
        self.assertEqual(r2["estado"], "aplicado", r2)
        self.assertIn("copia anterior", r2["detalle"])

        self.assertFalse(os.path.exists(first[0]), "la copia anterior se borró")
        copias = [p for p in self.backups_like("neb.pre-vacuum.*.db")
                  if re.match(r"^neb\.pre-vacuum\.\d{8}T\d+Z\.db$", os.path.basename(p))]
        self.assertEqual([os.path.normcase(p) for p in copias], [os.path.normcase(r2["respaldo"])],
                         "queda solo la copia de esta corrida")
        self.assertEqual(self.stats(r2["respaldo"])["integrity_check"], "ok")
        for name, data in otros.items():
            self.assertEqual(self.read_bytes(os.path.join(self.backups, name)), data, name)
        self.assertEqual(self.stats()["freelist_count"], 0)

    def test_espacio_insuficiente_queda_pendiente_sin_copia(self):
        """Sin espacio para la copia y el VACUUM: pendiente con el espacio que hace falta, sin crear nada."""
        self.make_db()
        before = self.stats()
        du = collections.namedtuple("usage", "total used free")
        with mock.patch.object(shutil, "disk_usage", return_value=du(10 ** 12, 10 ** 12 - 1024, 1024)) as m:
            r = _guided.run(self.ctx(), _step("vacuum-neb-db"))
        self.assertTrue(m.called, "aplicar mide el espacio libre")
        self.assertEqual(r["estado"], "pendiente", r)
        self.assertIn("falta espacio", r["detalle"])
        self.assertRegex(r["detalle"], r"piden \d+\.\d MB libres")
        self.assertIsNone(r["respaldo"])
        self.assertFalse(os.path.exists(self.backups), "no se creó la carpeta de respaldos ni la copia")
        after = self.stats()
        self.assertEqual((after["page_count"], after["freelist_count"]),
                         (before["page_count"], before["freelist_count"]))
        self.assertEqual(after["journal_mode"], "wal")
        self.assertTrue(_step("vacuum-neb-db").detectar(self.ctx()), "sigue pendiente")

    def test_espacio_se_suma_cuando_copia_y_base_comparten_volumen(self):
        """Mismo volumen para la carpeta de respaldos y la base (y el temporal): hace falta 1 vez la base para la
        copia más 2 para el VACUUM; con 2.5 veces no alcanza."""
        self.make_db()
        size = os.path.getsize(self.db)
        du = collections.namedtuple("usage", "total used free")
        step = _step("vacuum-neb-db")
        with mock.patch.dict(step.aplicar.__globals__, {"_volumen": lambda p: "uno"}), \
                mock.patch.object(shutil, "disk_usage", return_value=du(10 ** 13, 0, int(size * 2.5))):
            r = _guided.run(self.ctx(), step)
        self.assertEqual(r["estado"], "pendiente", r)
        self.assertIn("falta espacio", r["detalle"])
        self.assertFalse(os.path.exists(self.backups))

    def test_temporal_en_otro_volumen_sin_espacio_queda_pendiente(self):
        """El temporal de SQLite en otro volumen pide 1 vez la base ahí; sin eso, pendiente. Con espacio, corre."""
        self.make_db()
        tmp = os.path.join(self.home, "tmp-sqlite")
        os.makedirs(tmp)
        size = os.path.getsize(self.db)
        du = collections.namedtuple("usage", "total used free")
        step = _step("vacuum-neb-db")
        real_vol = step.aplicar.__globals__["_volumen"]

        def en_tmp(path):
            return os.path.normcase(os.path.abspath(path)).startswith(os.path.normcase(tmp))

        def volumen(path):
            return "tmp" if en_tmp(path) else real_vol(path)

        def correr(free_tmp):
            def disk_usage(path):
                return du(10 ** 13, 0, free_tmp if en_tmp(path) else 10 ** 13)
            with mock.patch.dict(step.aplicar.__globals__, {"_volumen": volumen, "_sqlite_temp_dir": lambda: tmp}), \
                    mock.patch.object(shutil, "disk_usage", side_effect=disk_usage):
                return _guided.run(self.ctx(), step)

        r = correr(size // 2)
        self.assertEqual(r["estado"], "pendiente", r)
        self.assertIn(tmp, r["detalle"])
        self.assertFalse(os.path.exists(self.backups))

        r = correr(size * 2)
        self.assertEqual(r["estado"], "aplicado", r)

    def test_base_compacta_no_se_marca(self):
        self.make_db(rows=600, delete_ratio=0.1)            # ~240 KB libres: menos de 1 MB
        self.assertFalse(_step("vacuum-neb-db").detectar(self.ctx()))
        self.make_db_ratio_bajo()
        self.assertFalse(_step("vacuum-neb-db").detectar(self.ctx()))

    def make_db_ratio_bajo(self):
        """Más de 1 MB libre pero menos de una cuarta parte de las páginas."""
        os.remove(self.db)
        self.make_db(rows=2000, delete_ratio=0.15)
        s = self.stats()
        assert s["freelist_count"] * s["page_size"] > 1024 * 1024
        assert s["freelist_count"] < 0.25 * s["page_count"]

    def test_sin_base_no_se_marca(self):
        self.assertFalse(_step("vacuum-neb-db").detectar(self.ctx()))
        self.assertFalse(os.path.exists(self.db), "detectar no crea la base")

    def test_detectar_no_escribe(self):
        self.make_db()
        before = self.read_bytes(self.db)
        self.assertTrue(_step("vacuum-neb-db").detectar(self.ctx()))
        self.assertEqual(self.read_bytes(self.db), before)

    def test_con_otra_conexion_abierta_no_corre(self):
        self.make_db()
        before = self.stats()
        other = sqlite3.connect(self.db)
        other.execute("SELECT count(*) FROM t").fetchone()
        try:
            r = _guided.run(self.ctx(), _step("vacuum-neb-db"))
        finally:
            other.close()
        self.assertEqual(r["estado"], "pendiente", r)
        self.assertIn("otra sesión", r["detalle"])
        self.assertEqual(self.backups_like("neb.pre-vacuum.*.db"), [])
        after = self.stats()
        self.assertEqual(after["freelist_count"], before["freelist_count"])
        self.assertEqual(after["journal_mode"], "wal")

    def test_otra_conexion_entre_la_condicion_y_aplicar(self):
        """La condición se cumple al revisarla, pero otra sesión abre la base antes de aplicar: el cambio de
        journal_mode de aplicar lo detecta y no compacta."""
        self.make_db()
        before = self.stats()
        step = _step("vacuum-neb-db")
        holder = {}

        def condicion(ctx):
            if getattr(ctx, "_vacuum_con", None) is None and "con" not in holder:
                motivo = step.condicion(ctx)
                holder["con"] = sqlite3.connect(self.db)
                holder["con"].execute("SELECT count(*) FROM t").fetchone()
                return motivo
            return step.condicion(ctx)

        s = _guided.GuidedStep(step.id, step.titulo, detectar=step.detectar, aplicar=step.aplicar,
                               respaldo=True, exclusivo=True, condicion=condicion)
        try:
            r = _guided.run(self.ctx(), s)
        finally:
            holder["con"].close()
        self.assertEqual(r["estado"], "pendiente", r)
        self.assertEqual(self.backups_like("neb.pre-vacuum.*.db"), [])
        self.assertEqual(self.stats()["freelist_count"], before["freelist_count"])

    def test_segunda_comprobacion_fallida_no_compacta_ni_deja_copia(self):
        self.make_db()
        before = self.stats()
        step = _step("vacuum-neb-db")
        calls = {"n": 0}

        def condicion(ctx):
            calls["n"] += 1
            return None if calls["n"] == 1 else "sembrada: el candado se perdió"

        s = _guided.GuidedStep(step.id, step.titulo, detectar=step.detectar, aplicar=step.aplicar,
                               respaldo=True, exclusivo=True, condicion=condicion)
        r = _guided.run(self.ctx(), s)
        self.assertEqual(r["estado"], "pendiente", r)
        self.assertEqual(calls["n"], 2, "aplicar vuelve a comprobar con ctx.exclusivo_ok()")
        self.assertEqual(self.backups_like("neb.pre-vacuum.*.db"), [])
        after = self.stats()
        self.assertEqual(after["freelist_count"], before["freelist_count"])
        self.assertEqual(after["journal_mode"], "wal")

    def test_candado_retenido_durante_el_vacuum(self):
        """Mientras aplicar retiene el candado, otra conexión no puede leer la base (la condición propia lo
        comprueba en la segunda llamada)."""
        self.make_db()
        step = _step("vacuum-neb-db")
        seen = []

        def condicion(ctx):
            motivo = step.condicion(ctx)
            if getattr(ctx, "_vacuum_con", None) is not None:
                probe = sqlite3.connect(self.db, timeout=0)
                try:
                    probe.execute("SELECT count(*) FROM t").fetchone()
                    seen.append("leyó")
                except sqlite3.OperationalError:
                    seen.append("bloqueada")
                finally:
                    probe.close()
            return motivo

        s = _guided.GuidedStep(step.id, step.titulo, detectar=step.detectar, aplicar=step.aplicar,
                               respaldo=True, exclusivo=True, condicion=condicion)
        r = _guided.run(self.ctx(), s)
        self.assertEqual(r["estado"], "aplicado", r)
        self.assertEqual(seen, ["bloqueada"])
        # al terminar suelta el candado
        con = sqlite3.connect(self.db, timeout=0)
        try:
            con.execute("BEGIN IMMEDIATE")
            con.execute("ROLLBACK")
        finally:
            con.close()

    def test_falla_sembrada_respaldo_no_compacta(self):
        self.make_db()
        before = self.stats()
        real_connect = sqlite3.connect

        def connect(path, *a, **kw):
            if "neb.pre-vacuum." in str(path):
                raise sqlite3.OperationalError("valor-que-no-sale")
            return real_connect(path, *a, **kw)
        with mock.patch("sqlite3.connect", side_effect=connect):
            r = _guided.run(self.ctx(), _step("vacuum-neb-db"))
        self.assertEqual(r["estado"], "fallo", r)
        self.assertNotIn("valor-que-no-sale", r["detalle"])
        self.assertEqual(self.backups_like("neb.pre-vacuum.*"), [])
        after = self.stats()
        self.assertEqual(after["freelist_count"], before["freelist_count"])
        self.assertEqual(after["journal_mode"], "wal")

    # -- falla sembrada en el VACUUM y en la integridad: la conexión de aplicar pasa por un proxy

    def run_with_proxy(self, fail_vacuum=False, corrupt=False):
        """Corre vacuum-neb-db con la conexión de aplicar (la de isolation_level=None del módulo) envuelta:
        fail_vacuum hace que `VACUUM` lance SQLITE_FULL; corrupt, que integrity_check de la base responda mal
        después del VACUUM (el del respaldo es otra conexión y no se toca)."""
        step = _step("vacuum-neb-db")
        real = sqlite3
        state = {"vacuum": False}

        class ProxyCon:
            def __init__(self, con):
                self._con = con

            def execute(self, sql, *a):
                s = sql.strip().upper()
                if s == "VACUUM":
                    state["vacuum"] = True
                    if fail_vacuum:
                        raise real.OperationalError("database or disk is full")
                if s == "PRAGMA INTEGRITY_CHECK" and corrupt and state["vacuum"]:
                    return mock.Mock(fetchone=lambda: ("*** in database main ***",))
                return self._con.execute(sql, *a)

            def __getattr__(self, name):
                return getattr(self._con, name)

        class FakeSqlite:
            def __getattr__(self, name):
                return getattr(real, name)

            @staticmethod
            def connect(path, *a, **kw):
                con = real.connect(path, *a, **kw)
                if "isolation_level" in kw and kw["isolation_level"] is None:
                    return ProxyCon(con)
                return con

        with mock.patch.dict(step.aplicar.__globals__, {"sqlite3": FakeSqlite()}):
            r = _guided.run(self.ctx(), step)
        self.assertTrue(state["vacuum"], "aplicar llegó al VACUUM")
        return r

    def test_falla_sembrada_vacuum_no_deja_copia_huerfana(self):
        """VACUUM lanza SQLITE_FULL con la base íntegra: fallo, la base quedó como estaba y la copia se borró."""
        self.make_db()
        before = self.stats()
        r = self.run_with_proxy(fail_vacuum=True)
        self.assertEqual(r["estado"], "fallo", r)
        self.assertIsNone(r["respaldo"])
        self.assertIn("OperationalError", r["detalle"])
        self.assertIn("quedó como estaba", r["detalle"])
        self.assertNotIn("disk is full", r["detalle"])
        self.assertEqual(self.backups_like("neb.pre-vacuum.*"), [], "sin copia huérfana")
        after = self.stats()
        self.assertEqual(after["freelist_count"], before["freelist_count"])
        self.assertEqual(after["journal_mode"], "wal")
        self.assertTrue(_step("vacuum-neb-db").detectar(self.ctx()), "sigue pendiente")

    def test_falla_sembrada_vacuum_con_base_no_integra_reporta_la_copia(self):
        self.make_db()
        r = self.run_with_proxy(fail_vacuum=True, corrupt=True)
        self.assertEqual(r["estado"], "fallo", r)
        backups = self.backups_like("neb.pre-vacuum.*.db")
        self.assertEqual(len(backups), 1)
        self.assertEqual(os.path.normcase(r["respaldo"]), os.path.normcase(backups[0]))
        self.assertIn("no corras nada más", r["detalle"])
        self.assertIn("restore no lo acepta", r["detalle"])
        self.assertEqual(self.stats(backups[0])["integrity_check"], "ok")

    def test_falla_sembrada_integridad_tras_el_vacuum(self):
        """La base no pasa integrity_check tras el VACUUM: fallo con la copia reportada y sin pedir un restore
        que no existe para este respaldo."""
        self.make_db()
        before = self.stats()
        r = self.run_with_proxy(corrupt=True)
        self.assertEqual(r["estado"], "fallo", r)
        backups = self.backups_like("neb.pre-vacuum.*.db")
        self.assertEqual(len(backups), 1)
        self.assertEqual(os.path.normcase(r["respaldo"]), os.path.normcase(backups[0]))
        self.assertIn("no corras nada más", r["detalle"])
        self.assertIn("restore no lo acepta", r["detalle"])
        self.assertNotIn("restaura", r["detalle"])
        b = self.stats(backups[0])
        self.assertEqual(b["integrity_check"], "ok")
        self.assertEqual(b["freelist_count"], before["freelist_count"], "la copia es el estado previo")


# --------------------------------------------------------------------------- apply de punta a punta

class TestApplyPuntaAPunta(Base):

    def test_un_apply_guiados_corre_el_paso_3_y_compacta(self):
        """Una base de neb en esquema 2 (raíz 'cliente') y fragmentada: un solo `apply --guiados` corre el paso
        de base 3 (renombre de la raíz, con su respaldo) y después vacuum-neb-db; ninguna conexión de apply deja
        el exclusivo en pendiente."""
        import _db_shared
        import _migrations
        con = _db_shared._connect(self.db, steps=_migrations.STEPS[:2])
        self.assertIsNotNone(con)
        try:
            con.execute("INSERT INTO topic (slug, name) VALUES ('cliente', 'Cliente')")
            con.execute("INSERT INTO topic (slug, name, parent_id) "
                        "VALUES ('beta', 'Beta', (SELECT id FROM topic WHERE slug = 'cliente'))")
            con.execute("CREATE TABLE relleno (id INTEGER PRIMARY KEY, body BLOB)")
            con.executemany("INSERT INTO relleno (body) VALUES (?)", [(os.urandom(4000),) for _ in range(1000)])
            con.commit()
            con.execute("DROP TABLE relleno")
            con.commit()
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self.assertEqual(_migrations.read_version(con)[0], 2)
        finally:
            con.close()
        self.assertTrue(_step("vacuum-neb-db").detectar(self.ctx()))

        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = nm.apply(self.home, (), False, True)
        res = json.loads(out.getvalue())
        g = res["guiados"]
        self.assertEqual(res["schema_version_db"], 3, res)
        self.assertEqual(res["pasos_detenidos"], [], res)
        self.assertIn(f"{V}:vacuum-neb-db", {r["id"] for r in g["aplicados"]}, res)
        self.assertEqual(g["pendientes"], [], res)
        self.assertEqual(g["fallos"], [], res)
        self.assertTrue(res["ok"], res)
        self.assertEqual(rc, 0)

        self.assertEqual(len(glob.glob(os.path.join(self.backups, "neb.pre-paso-3.*.db"))), 1)
        self.assertEqual(len(self.backups_like("neb.pre-vacuum.*.db")), 1)
        chk = sqlite3.connect(self.db)
        try:
            self.assertEqual(chk.execute("PRAGMA freelist_count").fetchone()[0], 0)
            self.assertEqual(chk.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            self.assertEqual(chk.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            roots = chk.execute("SELECT slug, name FROM topic WHERE parent_id IS NULL "
                                "AND slug IN ('cliente', 'proyecto')").fetchall()
            self.assertEqual(roots, [("proyecto", "Proyecto")])
            self.assertEqual(chk.execute("SELECT p.slug FROM topic t JOIN topic p ON p.id = t.parent_id "
                                         "WHERE t.slug = 'beta'").fetchone()[0], "proyecto")
        finally:
            chk.close()


if __name__ == "__main__":
    unittest.main()
