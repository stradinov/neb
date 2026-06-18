#!/usr/bin/env python3
"""
test_active_reqs.py — cobertura de los helpers de memoria en _db_shared.py:
  • find_active_reqs   — N REQ activos por proyecto (estructura active_*.md) + compat legacy.
  • resolve_memory_dir — respeta autoMemoryDirectory (precedencia Local > Project > User).

Correr:  py -m unittest discover -s hooks/tests -p "test_*.py" -v
"""

import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LIB  = os.path.join(HERE, "..", "lib")
sys.path.insert(0, LIB)

import _db_shared  # noqa: E402


def _active_md(name, project_path, draft="changes/x.md", state="En progreso"):
    """Contenido de un active_*.md (un REQ por archivo, formato '- **Label:** value')."""
    return (
        f"- **Nombre:** {name}\n"
        f"- **Path del proyecto:** {project_path}\n"
        f"- **Draft changes MD:** {draft}\n"
        f"- **Estado:** {state}\n"
        f"- **Plan resumido:** plan corto\n"
        f"- **Próximos pasos:** seguir\n"
    )


def _legacy_md(name, project_path, draft="changes/x.md", state="En progreso"):
    """Contenido de un project_*.md legacy con la sección '## Requerimiento activo'."""
    return (
        "# Proyecto Foo\n\n## Convenciones\n\ntexto duradero\n\n"
        "## Requerimiento activo\n"
        f"- **Nombre:** {name}\n"
        f"- **Path del proyecto:** {project_path}\n"
        f"- **Draft changes MD:** {draft}\n"
        f"- **Estado:** {state}\n"
    )


class TestFindActiveReqs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="neb-active-")
        self.mem = os.path.join(self.tmp, ".claude", "projects", "C--Users-x", "memory")
        os.makedirs(self.mem)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, fname, content, mtime=None):
        p = os.path.join(self.mem, fname)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(content)
        if mtime is not None:
            os.utime(p, (mtime, mtime))
        return p

    # ----------------------------------------------------------------- issue 1: N REQ
    def test_multiple_active_same_project(self):
        """Dos REQ del MISMO proyecto en archivos active_*.md → ambos capturados."""
        self._write("active_foo_req-a.md", _active_md("req-a", "/repo/foo"))
        self._write("active_foo_req-b.md", _active_md("req-b", "/repo/foo"))
        reqs = _db_shared.find_active_reqs(self.mem)
        self.assertEqual(len(reqs), 2)
        self.assertEqual({r["name"] for r in reqs}, {"req-a", "req-b"})

    def test_legacy_block_still_read(self):
        """Compat: un project_*.md legacy con '## Requerimiento activo' se sigue leyendo."""
        self._write("project_foo.md", _legacy_md("leg-1", "/repo/foo"))
        reqs = _db_shared.find_active_reqs(self.mem)
        self.assertEqual([r["name"] for r in reqs], ["leg-1"])

    def test_dedup_active_wins_over_legacy(self):
        """Mismo (project_path, name) en legacy y active_*: gana active_* (1 sola entrada)."""
        self._write("project_foo.md", _legacy_md("dup", "/repo/foo", draft="changes/old.md", state="Legacy"))
        self._write("active_foo_dup.md", _active_md("dup", "/repo/foo", draft="changes/new.md", state="Nuevo"))
        reqs = _db_shared.find_active_reqs(self.mem)
        self.assertEqual(len(reqs), 1)
        self.assertEqual(reqs[0]["draft"], "changes/new.md")
        self.assertEqual(reqs[0]["state"], "Nuevo")

    def test_malformed_ignored(self):
        """Sin 'Path del proyecto' → mal-formado, se ignora (igual que el comportamiento legacy)."""
        self._write("active_bad.md", "- **Nombre:** sin-path\n- **Estado:** En progreso\n")
        self.assertEqual(_db_shared.find_active_reqs(self.mem), [])

    def test_order_by_mtime_desc(self):
        """La lista viene ordenada por mtime descendente (el más reciente primero)."""
        self._write("active_foo_old.md", _active_md("old", "/repo/foo"), mtime=1_000_000)
        self._write("active_foo_new.md", _active_md("new", "/repo/foo"), mtime=2_000_000)
        reqs = _db_shared.find_active_reqs(self.mem)
        self.assertEqual(reqs[0]["name"], "new")
        self.assertEqual(reqs[-1]["name"], "old")

    def test_missing_dir_returns_empty(self):
        self.assertEqual(_db_shared.find_active_reqs(os.path.join(self.tmp, "nope")), [])

    def test_other_md_files_ignored(self):
        """MEMORY.md u otros .md que no son active_/project_ no se consideran."""
        self._write("MEMORY.md", "# index\n- algo\n")
        self._write("notas.md", "- **Nombre:** x\n- **Path del proyecto:** /y\n")
        self.assertEqual(_db_shared.find_active_reqs(self.mem), [])

    def test_non_utf8_file_skipped(self):
        """Un archivo con bytes no-UTF-8 se salta sin abortar el escaneo (defensivo)."""
        self._write("active_foo_ok.md", _active_md("ok", "/repo/foo"))
        with open(os.path.join(self.mem, "active_foo_bad.md"), "wb") as fh:
            fh.write(b"- **Nombre:** x\n- **Path del proyecto:** \xff\xfe bytes invalidos\n")
        reqs = _db_shared.find_active_reqs(self.mem)
        self.assertIn("ok", {r["name"] for r in reqs})  # el bueno se captura pese al malo


class TestFieldParser(unittest.TestCase):
    def test_field_bold_and_plain(self):
        self.assertEqual(_db_shared._field("- **Nombre:** valor", "Nombre"), "valor")
        self.assertEqual(_db_shared._field("Nombre: valor2", "Nombre"), "valor2")
        self.assertEqual(_db_shared._field("nada aqui", "Nombre"), "")


class TestResolveMemoryDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="neb-resolve-")
        self.home = os.path.join(self.tmp, "home")
        self.cwd = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.home, ".claude"))
        os.makedirs(os.path.join(self.cwd, ".claude"))
        self.encoded = "C--Users-x-repo"
        self.default = os.path.join(self.home, ".claude", "projects", self.encoded, "memory")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _settings(self, scope, value):
        """scope: 'user' | 'project' | 'local'."""
        if scope == "user":
            p = os.path.join(self.home, ".claude", "settings.json")
        elif scope == "project":
            p = os.path.join(self.cwd, ".claude", "settings.json")
        else:
            p = os.path.join(self.cwd, ".claude", "settings.local.json")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write('{"autoMemoryDirectory": "%s"}' % value.replace("\\", "\\\\"))

    def test_default_when_no_setting(self):
        self.assertEqual(_db_shared.resolve_memory_dir(self.home, self.cwd, self.encoded), self.default)

    def test_user_scope(self):
        custom = os.path.join(self.tmp, "unified-mem")
        self._settings("user", custom)
        self.assertEqual(_db_shared.resolve_memory_dir(self.home, "", self.encoded), custom)

    def test_expands_tilde(self):
        self._settings("user", "~/mymem")
        self.assertEqual(
            _db_shared.resolve_memory_dir(self.home, "", self.encoded),
            os.path.join(self.home, "mymem"),
        )

    def test_local_over_project_over_user(self):
        self._settings("user", os.path.join(self.tmp, "u"))
        self._settings("project", os.path.join(self.tmp, "p"))
        self._settings("local", os.path.join(self.tmp, "l"))
        self.assertEqual(
            _db_shared.resolve_memory_dir(self.home, self.cwd, self.encoded),
            os.path.join(self.tmp, "l"),
        )

    def test_project_over_user(self):
        self._settings("user", os.path.join(self.tmp, "u"))
        self._settings("project", os.path.join(self.tmp, "p"))
        self.assertEqual(
            _db_shared.resolve_memory_dir(self.home, self.cwd, self.encoded),
            os.path.join(self.tmp, "p"),
        )

    def test_malformed_settings_falls_back(self):
        with open(os.path.join(self.home, ".claude", "settings.json"), "w", encoding="utf-8") as fh:
            fh.write("{ this is not json ")
        self.assertEqual(_db_shared.resolve_memory_dir(self.home, "", self.encoded), self.default)

    def test_user_scope_ignored_without_cwd_for_project(self):
        """Sin cwd (caso usage-tracker), solo user scope; project/local no se leen."""
        self._settings("project", os.path.join(self.tmp, "p"))
        self._settings("user", os.path.join(self.tmp, "u"))
        # cwd="" → no mira project/local → gana user
        self.assertEqual(
            _db_shared.resolve_memory_dir(self.home, "", self.encoded),
            os.path.join(self.tmp, "u"),
        )


if __name__ == "__main__":
    unittest.main()
