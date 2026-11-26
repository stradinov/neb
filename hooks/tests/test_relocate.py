#!/usr/bin/env python3
"""
test_relocate.py — la mecánica de la mudanza a la carpeta de datos (hooks/lib/_relocate.py, 8.0.0).

Cubre, con carpetas temporales:
  • la base testigo: una base con solo schema_step y la fila de la mudanza, en un solo archivo; no pisa un archivo
    que existe; is_witness la reconoce también en WAL y quita los -wal/-shm que deja una lectura de solo lectura
    (lo que hace el código 6.48–7.6 al abrirla), y no reconoce una base usable, otra fila, un archivo que no es
    base, uno de 0 bytes ni uno que falta;
  • move_db en el mismo volumen: integra el -wal, respaldo nuevo en un solo archivo (journal_mode=DELETE, íntegro,
    con los datos), la base llega usable y en WAL, y la testigo ocupa su lugar; sin testigo, el origen desaparece;
  • move_db se niega sin tocar nada: destino con datos o con sus -wal/-shm, origen que no es base, enlace u
    ocupado por otra conexión (la base vuelve a WAL y no queda respaldo); sin origen o de 0 bytes, nada;
  • move_db entre volúmenes (EXDEV simulado): copia verificada, la testigo reemplaza al origen y no quedan
    temporales; si el origen cambia mientras se copia, se queda donde estaba y la copia se borra;
  • plan_moves / apply_moves: mover, iguales (quita el origen), conflictos (nada se toca), con newer_wins queda el
    más nuevo; manifiesto nuevo con origen, destino y tamaño, «hecho» al terminar; carpetas intermedias creadas;
    poda de las carpetas vacías salvo las protegidas; un destino que aparece entre el plan y el movimiento no se
    pisa; EXDEV copia y borra el origen; sin poder escribir el manifiesto no se mueve nada; los enlaces se omiten;
  • write_json_atomic: reemplaza de un paso y no escribe a través de un enlace.

Nunca toca ~/.claude ni ~/.neb reales (sin NEB_DATA: _entorno).
  py -m unittest discover -s hooks/tests -p test_relocate.py
"""

import errno
import json
import os
import pathlib
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lib"))

import _entorno  # noqa: E402,F401 — quita NEB_DATA del entorno heredado
import _db_shared  # noqa: E402
import _migrations  # noqa: E402
import _relocate  # noqa: E402

SCHEMA = os.path.join(HERE, "..", "logbook-schema.sql")


def _make_db(path, rows=3, wal_pending=True):
    """Base de la bitácora con `rows` filas en work; con wal_pending, la última queda en el -wal (sin checkpoint)."""
    _db_shared._connect(path, SCHEMA).close()
    con = sqlite3.connect(path)
    con.execute("PRAGMA wal_autocheckpoint=0")
    for i in range(rows):
        con.execute("INSERT INTO work (mode, created_at, updated_at) VALUES ('exploratory', ?, ?)",
                    (f"2026-01-0{i + 1}", f"2026-01-0{i + 1}"))
        con.commit()
    if not wal_pending:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()


def _count(path):
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT count(*) FROM work").fetchone()[0]
    finally:
        con.close()


def _journal_mode(path):
    con = sqlite3.connect(path)
    try:
        return con.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        con.close()


def _header_mode(path):
    """Bytes 18 y 19 del encabezado: (1, 1) en rollback journal (DELETE), (2, 2) en WAL."""
    with open(path, "rb") as fh:
        head = fh.read(20)
    return head[18], head[19]


def _junction(target, link):
    """Junction en Windows (sin privilegios), symlink de carpeta en los demás; False si no se pudo."""
    try:
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(target, link)
        else:
            os.symlink(target, link, target_is_directory=True)
        return True
    except (OSError, AttributeError, ImportError):
        return False


def _remove_link(link):
    if os.path.lexists(link):
        if os.name == "nt":
            os.rmdir(link)
        else:
            os.unlink(link)


class Base(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="neb-test-relocate-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.old = os.path.join(self.root, "claude")
        self.new = os.path.join(self.root, "datos")
        os.makedirs(self.old)
        os.makedirs(os.path.join(self.new, "backups"))
        self.src = os.path.join(self.old, "neb.db")
        self.dst = os.path.join(self.new, "neb.db")
        self.bak = os.path.join(self.new, "backups", "neb.pre-8.0.0.prueba.db")
        self.wit = os.path.join(self.old, ".neb.db.testigo-prueba")

    def write(self, path, data=b"x"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def read(self, path):
        with open(path, "rb") as fh:
            return fh.read()


# --------------------------------------------------------------------------- base testigo

class TestTestigo(Base):

    def test_critico_la_testigo_es_solo_schema_step_con_la_fila_de_la_mudanza(self):
        _relocate.write_witness(self.src, "8.0.0")
        con = sqlite3.connect(self.src)
        try:
            self.assertEqual([r[0] for r in con.execute("SELECT name FROM sqlite_master")], ["schema_step"])
            self.assertEqual(con.execute("SELECT step, min_code, title, neb_version FROM schema_step").fetchall(),
                             [(1000, 1000, _relocate.WITNESS_TITLE, "8.0.0")])
            # El mecanismo de versiones la lee como más nueva e incompatible para todo código con C < 1000.
            self.assertEqual(_migrations.read_version(con), (1000, 1000))
        finally:
            con.close()
        self.assertEqual(_header_mode(self.src), (1, 1), "un solo archivo (journal_mode=DELETE)")
        self.assertEqual(sorted(os.listdir(self.old)), ["neb.db"])
        self.assertTrue(_relocate.is_witness(self.src))
        self.assertEqual(_db_shared._probe_db(self.src), "sin-work", "no es usable: no dispara la guarda")

    def test_no_pisa_un_archivo_que_existe(self):
        self.write(self.src, b"datos del dev")
        with self.assertRaises(FileExistsError):
            _relocate.write_witness(self.src, "8.0.0")
        self.assertEqual(self.read(self.src), b"datos del dev")

    def test_critico_is_witness_en_wal_quita_los_auxiliares_de_una_lectura_de_solo_lectura(self):
        _relocate.write_witness(self.src, "8.0.0")
        con = sqlite3.connect(self.src)                     # lo que hace el código viejo al abrirla
        con.execute("PRAGMA journal_mode=WAL")
        con.close()
        ro = sqlite3.connect(pathlib.Path(self.src).as_uri() + "?mode=ro", uri=True)
        ro.execute("SELECT count(*) FROM schema_step").fetchone()
        ro.close()
        self.assertTrue(_relocate.sidecars(self.src), "la prueba necesita los -wal/-shm de la lectura ro")
        self.assertTrue(_relocate.is_witness(self.src))
        self.assertEqual(_relocate.sidecars(self.src), [])

    def test_no_es_testigo(self):
        self.assertFalse(_relocate.is_witness(self.src), "no existe")
        self.assertFalse(os.path.exists(self.src), "no lo crea")
        self.write(self.src, b"")
        self.assertFalse(_relocate.is_witness(self.src), "0 bytes")
        self.write(self.src, b"no es una base " * 10)
        self.assertFalse(_relocate.is_witness(self.src), "no es base")
        os.remove(self.src)
        _make_db(self.src, wal_pending=False)
        self.assertFalse(_relocate.is_witness(self.src), "una base usable")
        os.remove(self.src)
        con = sqlite3.connect(self.src)
        con.execute(_migrations._BOOKKEEPING_DDL[0])
        con.execute("INSERT INTO schema_step (step, min_code, title, neb_version, applied_at) "
                    "VALUES (1000, 1, 'otra', '8.0.0', 'a')")
        con.commit()
        con.close()
        self.assertFalse(_relocate.is_witness(self.src), "otra fila")

    def test_un_enlace_no_es_testigo(self):
        real = os.path.join(self.root, "real")
        os.makedirs(real)
        _relocate.write_witness(os.path.join(real, "neb.db"), "8.0.0")
        link = os.path.join(self.root, "enlace")
        if not _junction(real, link):
            self.skipTest("no se pudo crear el enlace")
        self.addCleanup(_remove_link, link)
        self.assertTrue(_relocate.is_link(link))
        self.assertFalse(_relocate.is_witness(link))


# --------------------------------------------------------------------------- move_db

class TestMoverBase(Base):

    def test_critico_mismo_volumen_respaldo_base_en_wal_y_testigo_en_su_lugar(self):
        _make_db(self.src, rows=3, wal_pending=True)
        self.assertTrue(os.path.exists(self.src + "-wal") or _count(self.src) == 3)
        _relocate.write_witness(self.wit, "8.0.0")
        r = _relocate.move_db(self.src, self.dst, self.bak, witness=self.wit)
        self.assertEqual((r["codigo"], r["modo"]), ("ok", "replace"), r)
        self.assertIsNone(r["aviso"], r)
        self.assertEqual(r["respaldo"], self.bak)
        # destino: usable, con todo (también lo que estaba en el -wal), en WAL
        self.assertEqual(_db_shared._probe_db(self.dst), "usable")
        self.assertEqual(_count(self.dst), 3)
        self.assertEqual(_journal_mode(self.dst), "wal")
        # respaldo: un solo archivo, íntegro, con los datos
        self.assertEqual(_header_mode(self.bak), (1, 1))
        self.assertEqual(_count(self.bak), 3)
        self.assertFalse(_relocate.sidecars(self.bak))
        # origen: la testigo ocupa su lugar; el temporal de la testigo ya no existe con su nombre
        self.assertTrue(_relocate.is_witness(self.src))
        self.assertFalse(os.path.exists(self.wit))
        self.assertEqual(_relocate.sidecars(self.src), [])

    def test_sin_testigo_el_origen_desaparece(self):
        _make_db(self.src)
        r = _relocate.move_db(self.src, self.dst, self.bak)
        self.assertEqual(r["codigo"], "ok", r)
        self.assertFalse(os.path.exists(self.src))
        self.assertEqual(_count(self.dst), 3)

    def test_destino_de_cero_bytes_se_reemplaza(self):
        _make_db(self.src)
        self.write(self.dst, b"")
        r = _relocate.move_db(self.src, self.dst, self.bak)
        self.assertEqual(r["codigo"], "ok", r)
        self.assertEqual(_count(self.dst), 3)

    def _intact(self, before_rows=3):
        self.assertEqual(_count(self.src), before_rows)
        self.assertFalse(os.path.exists(self.bak), "sin respaldo huérfano")

    def test_critico_no_pisa_un_destino_con_datos(self):
        _make_db(self.src)
        self.write(self.dst, b"la base de la carpeta de datos")
        r = _relocate.move_db(self.src, self.dst, self.bak)
        self.assertEqual(r["codigo"], "aborto", r)
        self.assertIn("no lo pisa", r["mensaje"])
        self.assertEqual(self.read(self.dst), b"la base de la carpeta de datos")
        self._intact()

    def test_no_mueve_con_auxiliares_del_destino(self):
        _make_db(self.src)
        self.write(self.dst + "-wal", b"w")
        r = _relocate.move_db(self.src, self.dst, self.bak)
        self.assertEqual(r["codigo"], "aborto", r)
        self.assertIn(self.dst + "-wal", r["mensaje"])
        self.assertFalse(os.path.exists(self.dst))
        self._intact()

    def test_origen_que_no_es_base(self):
        self.write(self.src, b"no es una base " * 100)
        r = _relocate.move_db(self.src, self.dst, self.bak)
        self.assertEqual(r["codigo"], "aborto", r)
        self.assertIn("no es una base usable", r["mensaje"])
        self.assertEqual(self.read(self.src), b"no es una base " * 100)
        self.assertFalse(os.path.exists(self.dst))
        self.assertFalse(os.path.exists(self.bak))

    def test_sin_origen_o_de_cero_bytes_no_hay_nada(self):
        self.assertEqual(_relocate.move_db(self.src, self.dst, self.bak)["codigo"], "nada")
        self.write(self.src, b"")
        self.assertEqual(_relocate.move_db(self.src, self.dst, self.bak)["codigo"], "nada")
        self.assertFalse(os.path.exists(self.dst))

    def test_origen_enlace_no_se_sigue(self):
        real = os.path.join(self.root, "real")
        os.makedirs(real)
        link = os.path.join(self.old, "carpeta-enlace")
        if not _junction(real, link):
            self.skipTest("no se pudo crear el enlace")
        self.addCleanup(_remove_link, link)
        r = _relocate.move_db(link, self.dst, self.bak)
        self.assertEqual(r["codigo"], "aborto", r)
        self.assertFalse(os.path.exists(self.dst))

    def test_ocupada_por_otra_conexion_queda_en_su_lugar_y_en_wal(self):
        _make_db(self.src, wal_pending=False)
        other = sqlite3.connect(self.src)                   # otra sesión con la base abierta (WAL)
        other.execute("SELECT count(*) FROM work").fetchone()
        try:
            r = _relocate.move_db(self.src, self.dst, self.bak)
        finally:
            other.close()
        self.assertEqual(r["codigo"], "ocupada", r)
        self.assertFalse(os.path.exists(self.dst))
        self._intact()
        self.assertEqual(_journal_mode(self.src), "wal")

    def test_entre_volumenes_copia_verificada_y_testigo(self):
        _make_db(self.src, rows=4)
        _relocate.write_witness(self.wit, "8.0.0")
        real_replace = os.replace

        def replace(a, b):
            if _relocate.same_path(a, self.src) and _relocate.same_path(b, self.dst):
                raise OSError(errno.EXDEV, "Invalid cross-device link")
            return real_replace(a, b)
        with mock.patch.object(_relocate.os, "replace", replace):
            r = _relocate.move_db(self.src, self.dst, self.bak, witness=self.wit)
        self.assertEqual((r["codigo"], r["modo"]), ("ok", "copia"), r)
        self.assertIn("entre volúmenes", r["mensaje"])
        self.assertEqual(_count(self.dst), 4)
        self.assertEqual(_journal_mode(self.dst), "wal")
        self.assertTrue(_relocate.is_witness(self.src))
        self.assertEqual(sorted(f for f in os.listdir(self.new) if ".tmp-" in f), [], "sin temporales")
        self.assertEqual(_count(self.bak), 4)

    def test_entre_volumenes_si_el_origen_cambia_mientras_se_copia_no_se_muda(self):
        _make_db(self.src, rows=2)
        real_replace, real_fp = os.replace, _relocate._fingerprint
        calls = []

        def replace(a, b):
            if _relocate.same_path(a, self.src) and _relocate.same_path(b, self.dst):
                raise OSError(errno.EXDEV, "Invalid cross-device link")
            return real_replace(a, b)

        def fingerprint(path):
            calls.append(path)
            fp = real_fp(path)
            return fp if len(calls) < 4 else (fp[0], fp[1] + 1, fp[2])   # la 4.a: tras la copia, «cambió»
        with mock.patch.object(_relocate.os, "replace", replace), \
                mock.patch.object(_relocate, "_fingerprint", fingerprint):
            r = _relocate.move_db(self.src, self.dst, self.bak)
        self.assertEqual(r["codigo"], "ocupada", r)
        self.assertIn("cambió mientras se copiaba", r["mensaje"])
        self.assertFalse(os.path.exists(self.dst), "la copia se borra")
        self.assertEqual(_count(self.src), 2)
        self.assertFalse(os.path.exists(self.bak))


# --------------------------------------------------------------------------- mover archivos

class TestMoverArchivos(Base):

    def setUp(self):
        super().setUp()
        self.a = os.path.join(self.old, "arbol")
        self.b = os.path.join(self.new, "arbol")
        self.manifest = os.path.join(self.new, "backups", "manifest-prueba.json")

    def test_plan(self):
        self.write(os.path.join(self.a, "nuevo.md"), b"1")
        self.write(os.path.join(self.a, "igual.md"), b"2")
        self.write(os.path.join(self.b, "igual.md"), b"2")
        self.write(os.path.join(self.a, "distinto.md"), b"3")
        self.write(os.path.join(self.b, "distinto.md"), b"otro")
        p = _relocate.plan_moves(_relocate.tree_pairs(self.a, self.b))
        names = {k: sorted(os.path.basename(r["origen"]) for r in v) for k, v in p.items()}
        self.assertEqual(names, {"mover": ["nuevo.md"], "iguales": ["igual.md"], "conflictos": ["distinto.md"],
                                 "reemplazar": [], "descartar": []})
        self.assertEqual([r["bytes"] for r in p["mover"]], [1])

    def test_critico_apply_mueve_quita_iguales_deja_conflictos_y_escribe_el_manifiesto(self):
        self.write(os.path.join(self.a, "sub", "profundo", "plan.txt"), b"plan")
        self.write(os.path.join(self.a, "igual.md"), b"2")
        self.write(os.path.join(self.b, "igual.md"), b"2")
        self.write(os.path.join(self.a, "distinto.md"), b"3")
        self.write(os.path.join(self.b, "distinto.md"), b"otro")
        res = _relocate.apply_moves(_relocate.tree_pairs(self.a, self.b), self.manifest, "8.0.0:prueba", self.new,
                                    prune=(self.a,), keep=(self.old,))
        self.assertEqual(self.read(os.path.join(self.b, "sub", "profundo", "plan.txt")), b"plan")
        self.assertFalse(os.path.exists(os.path.join(self.a, "sub")), "poda las carpetas vacías")
        self.assertFalse(os.path.exists(os.path.join(self.a, "igual.md")))
        self.assertEqual(self.read(os.path.join(self.a, "distinto.md")), b"3", "el conflicto queda en su lugar")
        self.assertEqual(self.read(os.path.join(self.b, "distinto.md")), b"otro", "y no se pisa")
        self.assertTrue(os.path.isdir(self.a), "con un conflicto adentro, la raíz se queda")
        self.assertTrue(os.path.isdir(self.old), "la carpeta protegida nunca se poda")
        self.assertEqual((len(res["movidos"]), len(res["iguales"]), len(res["conflictos"]), res["fallos"]),
                         (1, 1, 1, []))
        with open(self.manifest, encoding="utf-8") as fh:
            m = json.load(fh)
        self.assertEqual((m["paso"], m["estado"]), ("8.0.0:prueba", "hecho"))
        moved = [e for e in m["entradas"] if e["accion"] == "mover"][0]
        self.assertEqual((moved["origen"], moved["destino"], moved["bytes"]),
                         (os.path.join(self.a, "sub", "profundo", "plan.txt"),
                          os.path.join(self.b, "sub", "profundo", "plan.txt"), 4))
        self.assertIn("deshacer", m)
        self.assertEqual([c["origen"] for c in m["conflictos"]], [os.path.join(self.a, "distinto.md")])

    def test_sin_nada_que_mover_no_hay_manifiesto(self):
        self.write(os.path.join(self.a, "distinto.md"), b"3")
        self.write(os.path.join(self.b, "distinto.md"), b"otro")
        res = _relocate.apply_moves(_relocate.tree_pairs(self.a, self.b), self.manifest, "8.0.0:prueba", self.new)
        self.assertIsNone(res["manifiesto"])
        self.assertFalse(os.path.exists(self.manifest))
        self.assertEqual(len(res["conflictos"]), 1)

    def test_newer_wins_queda_el_mas_nuevo(self):
        viejo_src = self.write(os.path.join(self.a, "viejo-en-origen"), b"origen viejo")
        self.write(os.path.join(self.b, "viejo-en-origen"), b"destino nuevo")
        nuevo_src = self.write(os.path.join(self.a, "nuevo-en-origen"), b"origen nuevo")
        self.write(os.path.join(self.b, "nuevo-en-origen"), b"destino viejo")
        os.utime(viejo_src, (1_000_000_000, 1_000_000_000))
        os.utime(os.path.join(self.b, "nuevo-en-origen"), (1_000_000_000, 1_000_000_000))
        res = _relocate.apply_moves(_relocate.tree_pairs(self.a, self.b), self.manifest, "8.0.0:prueba", self.new,
                                    newer_wins=True)
        self.assertEqual(self.read(os.path.join(self.b, "viejo-en-origen")), b"destino nuevo")
        self.assertEqual(self.read(os.path.join(self.b, "nuevo-en-origen")), b"origen nuevo")
        self.assertFalse(os.path.exists(viejo_src))
        self.assertFalse(os.path.exists(nuevo_src))
        self.assertEqual((len(res["reemplazados"]), len(res["descartados"]), res["conflictos"]), (1, 1, []))

    def test_critico_un_destino_que_aparece_entre_el_plan_y_el_movimiento_no_se_pisa(self):
        src = self.write(os.path.join(self.a, "plan.md"), b"del origen")
        dst = os.path.join(self.b, "plan.md")
        real_plan = _relocate.plan_moves

        def plan(pairs, newer_wins=False):
            out = real_plan(pairs, newer_wins)
            self.write(dst, b"apareci\xc3\xb3 despu\xc3\xa9s")       # otra sesión lo escribió justo ahora
            return out
        with mock.patch.object(_relocate, "plan_moves", plan):
            res = _relocate.apply_moves([(src, dst)], self.manifest, "8.0.0:prueba", self.new)
        self.assertEqual(self.read(dst), "apareció después".encode("utf-8"))
        self.assertEqual(self.read(src), b"del origen")
        self.assertEqual([r["origen"] for r in res["conflictos"]], [src])
        self.assertEqual(res["movidos"], [])

    def test_entre_volumenes_copia_y_borra_el_origen(self):
        src = self.write(os.path.join(self.a, "plan.md"), b"contenido")
        dst = os.path.join(self.b, "plan.md")
        real = _relocate._move_no_clobber
        calls = []

        def no_clobber(a, b):
            calls.append(a)
            if len(calls) == 1:
                raise OSError(errno.EXDEV, "Invalid cross-device link")
            return real(a, b)                   # el temporal ya está en el volumen del destino
        with mock.patch.object(_relocate, "_move_no_clobber", no_clobber):
            res = _relocate.apply_moves([(src, dst)], self.manifest, "8.0.0:prueba", self.new)
        self.assertEqual(self.read(dst), b"contenido")
        self.assertFalse(os.path.exists(src))
        self.assertEqual(len(res["movidos"]), 1)
        self.assertEqual([f for f in os.listdir(self.b) if ".tmp-" in f], [])

    def test_sin_poder_escribir_el_manifiesto_no_mueve_nada(self):
        src = self.write(os.path.join(self.a, "plan.md"), b"contenido")
        self.write(self.manifest, b"ya existe")
        with self.assertRaises(OSError):
            _relocate.apply_moves([(src, os.path.join(self.b, "plan.md"))], self.manifest, "8.0.0:prueba", self.new)
        self.assertTrue(os.path.exists(src))
        self.assertFalse(os.path.exists(os.path.join(self.b, "plan.md")))
        self.assertEqual(self.read(self.manifest), b"ya existe")

    def test_los_enlaces_se_omiten(self):
        fuera = os.path.join(self.root, "fuera")
        self.write(os.path.join(fuera, "ajeno.md"), b"no es de neb")
        self.write(os.path.join(self.a, "plan.md"), b"1")
        link = os.path.join(self.a, "enlace")
        if not _junction(fuera, link):
            self.skipTest("no se pudo crear el enlace")
        self.addCleanup(_remove_link, link)
        self.assertEqual(_relocate.walk_files(self.a), ["plan.md"])
        self.assertEqual(_relocate.walk_files(link), [], "una raíz que es enlace no se recorre")
        _relocate.apply_moves(_relocate.tree_pairs(self.a, self.b), self.manifest, "8.0.0:prueba", self.new,
                              prune=(self.a,))
        self.assertTrue(os.path.isfile(os.path.join(fuera, "ajeno.md")))
        self.assertFalse(os.path.exists(os.path.join(self.b, "enlace")))

    def test_un_nivel_intermedio_que_es_enlace_se_rechaza(self):
        fuera = os.path.join(self.root, "fuera")
        os.makedirs(fuera)
        link = os.path.join(self.new, "arbol")
        if not _junction(fuera, link):
            self.skipTest("no se pudo crear el enlace")
        self.addCleanup(_remove_link, link)
        src = self.write(os.path.join(self.a, "sub", "plan.md"), b"1")
        res = _relocate.apply_moves([(src, os.path.join(link, "sub", "plan.md"))], self.manifest, "8.0.0:prueba",
                                    self.new)
        self.assertEqual(len(res["fallos"]), 1, res)
        self.assertTrue(os.path.exists(src))
        self.assertEqual(os.listdir(fuera), [], "no escribe a través del enlace")


class TestJsonAtomico(Base):

    def test_reemplaza_de_un_paso(self):
        path = os.path.join(self.new, "config.json")
        _relocate.write_json_atomic(path, {"a": 1})
        _relocate.write_json_atomic(path, {"a": 2})
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {"a": 2})
        self.assertEqual([f for f in os.listdir(self.new) if ".tmp-" in f], [])

    def test_no_escribe_a_traves_de_un_enlace(self):
        fuera = os.path.join(self.root, "fuera")
        os.makedirs(fuera)
        link = os.path.join(self.new, "enlace.json")
        if not _junction(fuera, link):
            self.skipTest("no se pudo crear el enlace")
        self.addCleanup(_remove_link, link)
        with self.assertRaises(ValueError):
            _relocate.write_json_atomic(link, {"a": 1})
        self.assertEqual(os.listdir(fuera), [])


if __name__ == "__main__":
    unittest.main()
