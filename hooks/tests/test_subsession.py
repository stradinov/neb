#!/usr/bin/env python3
"""test_subsession.py — guard de subsesión interna del corrector.

Cubre:
  • is_internal_subsession: bandera nueva / alias legacy / ambas / ninguna
  • mark_internal_subsession: setea AMBAS (nueva + legacy) para back-compat
  • neb-bootstrap-context.py: early-return inerte cuando la bandera está presente
    (no inyecta el arranque → el Haiku corrector no recibe instrucciones de asistente)
  • camino feliz: sin bandera SÍ inyecta el arranque

Framework: unittest (stdlib), NO pytest. No toca ~/.claude.
"""
import io
import os
import sys
import unittest
import importlib.util

HOOKS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB_DIR = os.path.join(HOOKS_DIR, "lib")
REPO_ROOT = os.path.dirname(HOOKS_DIR)
BOOTSTRAP = os.path.join(REPO_ROOT, "bootstrap", "neb-bootstrap-context.py")

sys.path.insert(0, LIB_DIR)
import subsession as S  # noqa: E402


def _load_bootstrap():
    spec = importlib.util.spec_from_file_location("neb_bootstrap_context", BOOTSTRAP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestHelper(unittest.TestCase):
    def test_new_flag(self):
        self.assertTrue(S.is_internal_subsession({"NEB_INTERNAL_SUBSESSION": "1"}))

    def test_legacy_alias(self):
        self.assertTrue(S.is_internal_subsession({"CLAUDE_PREPROCESS_RECURSION": "1"}))

    def test_both(self):
        self.assertTrue(S.is_internal_subsession(
            {"NEB_INTERNAL_SUBSESSION": "1", "CLAUDE_PREPROCESS_RECURSION": "1"}))

    def test_neither(self):
        self.assertFalse(S.is_internal_subsession({}))
        self.assertFalse(S.is_internal_subsession({"NEB_INTERNAL_SUBSESSION": "0"}))

    def test_mark_sets_both(self):
        env = S.mark_internal_subsession({})
        self.assertEqual(env["NEB_INTERNAL_SUBSESSION"], "1")
        self.assertEqual(env["CLAUDE_PREPROCESS_RECURSION"], "1")  # alias legacy


class TestBootstrapGuard(unittest.TestCase):
    """El hook SessionStart debe ser inerte dentro de la subsesión del corrector."""

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in
                       ("NEB_INTERNAL_SUBSESSION", "CLAUDE_PREPROCESS_RECURSION",
                        "NEB_HOME", "NEB_WORKSPACE", "CLAUDE_PROJECT_DIR")}
        for k in self._saved:
            os.environ.pop(k, None)
        self.mod = _load_bootstrap()

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _run_main(self):
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            self.mod.main()
        finally:
            sys.stdout = old
        return buf.getvalue()

    def test_inert_with_new_flag(self):
        os.environ["NEB_INTERNAL_SUBSESSION"] = "1"
        self.assertEqual(self._run_main(), "")

    def test_inert_with_legacy_flag(self):
        os.environ["CLAUDE_PREPROCESS_RECURSION"] = "1"
        self.assertEqual(self._run_main(), "")

    def test_injects_without_flag(self):
        # Sin bandera, con NEB_HOME al repo real, inyecta el arranque.
        os.environ["NEB_HOME"] = REPO_ROOT
        out = self._run_main()
        self.assertIn("Arranque de Neb", out)


if __name__ == "__main__":
    unittest.main()
