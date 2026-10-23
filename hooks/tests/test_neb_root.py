#!/usr/bin/env python3
"""test_neb_root.py — raíz del núcleo y NEB_HOME fijado al caché del plugin (6.15.0).

Un /wakeup anterior a 6.14.3 dejaba `NEB_HOME=<caché versionado>` en ~/.claude/settings.json. Desde 6.15.0
los consumidores que corren fuera del Bash tool lo descartan (hooks/lib/neb_root.py):
  • in_plugin_cache / stale_neb_home / resolve_neb_root
  • esquema del CLI de pendings y logbook con NEB_HOME en un caché que ya no existe
  • el arranque (bootstrap/neb-bootstrap-context.py): sale del árbol propio y avisa; avisa también
    de valores inválidos en NEB_HOOKS / NEB_PROJECT_HOOKS
  • bootstrap/setup-workspace.sh --dry-run: no toma el NEB_HOME del caché

Framework: unittest (stdlib). HOME temporal; nunca toca ~/.claude.
  py -m unittest discover -s hooks/tests -p test_neb_root.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "lib")
NEB = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, LIB)

import logbook  # noqa: E402
import neb_root  # noqa: E402
import pendings  # noqa: E402

CACHE_WIN = "C:\\Users\\x\\.claude\\plugins\\cache\\acme\\neb\\6.13.0"
CACHE_FWD = "C:/Users/x/.claude/plugins/cache/acme/neb/6.13.0"
CACHE_MAC = "/Users/x/.claude/plugins/cache/acme/neb/6.13.0"
CACHE_CFG = "/opt/claude-config/plugins/cache/neb/neb/6.12.1"     # CLAUDE_CONFIG_DIR propio
CLONE = "C:/Users/x/src/neb"


class TestInPluginCache(unittest.TestCase):

    def test_rutas_de_cache(self):
        for p in (CACHE_WIN, CACHE_FWD, CACHE_MAC, CACHE_CFG, "/c/Users/x/.claude/plugins/cache/o/neb/1"):
            self.assertTrue(neb_root.in_plugin_cache(p), p)

    def test_rutas_fuera_de_cache(self):
        for p in (CLONE, "/home/x/neb", "/x/plugins/cache-viejo/neb", "/x/plugins/cache", ""):
            self.assertFalse(neb_root.in_plugin_cache(p), p)

    def test_stale_neb_home(self):
        self.assertEqual(neb_root.stale_neb_home({"NEB_HOME": CACHE_WIN}), CACHE_WIN)
        self.assertEqual(neb_root.stale_neb_home({"NEB_HOME": CLONE}), "")
        self.assertEqual(neb_root.stale_neb_home({}), "")


class TestResolveNebRoot(unittest.TestCase):

    def test_clon_gana(self):
        env = {"NEB_HOME": CLONE, "CLAUDE_PLUGIN_ROOT": "/p"}
        self.assertEqual(neb_root.resolve_neb_root("/own", env), CLONE)

    def test_cache_cae_a_plugin_root(self):
        env = {"NEB_HOME": CACHE_FWD, "CLAUDE_PLUGIN_ROOT": "/p"}
        self.assertEqual(neb_root.resolve_neb_root("/own", env), "/p")

    def test_cache_sin_plugin_root_cae_al_arbol_propio(self):
        self.assertEqual(neb_root.resolve_neb_root("/own", {"NEB_HOME": CACHE_WIN}), "/own")

    def test_sin_nada(self):
        self.assertEqual(neb_root.resolve_neb_root("/own", {}), "/own")


class TestCliConNebHomeEnCache(unittest.TestCase):
    """El caché fijado ya no existe (Claude Code lo borró 14 días después del update)."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="neb-test-")
        self.addCleanup(shutil.rmtree, self.home, True)
        os.makedirs(os.path.join(self.home, ".claude"))
        env = {k: v for k, v in os.environ.items() if k not in ("NEB_HOME", "CLAUDE_PLUGIN_ROOT")}
        env.update(HOME=self.home, USERPROFILE=self.home,
                   NEB_HOME=os.path.join(self.home, ".claude", "plugins", "cache", "acme", "neb", "6.0.0"))
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _assert_table(self, mod, table):
        con = mod._db_for_cli()
        self.assertIsNotNone(con)
        try:
            names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertIn(table, names)
        finally:
            con.close()

    def test_pendings(self):
        self._assert_table(pendings, "pending")

    def test_logbook(self):
        self._assert_table(logbook, "work")


class TestArranque(unittest.TestCase):

    def _bootstrap(self, **env):
        e = {k: v for k, v in os.environ.items()
             if k not in ("NEB_HOME", "CLAUDE_PLUGIN_ROOT", "NEB_HOOKS", "NEB_PROJECT_HOOKS", "NEB_WORKSPACE",
                          "NEB_INTERNAL_SUBSESSION", "CLAUDE_PREPROCESS_RECURSION", "CLAUDE_PROJECT_DIR")}
        e.update(env)
        r = subprocess.run([sys.executable, os.path.join(NEB, "bootstrap", "neb-bootstrap-context.py")],
                           env=e, capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 0)
        return r.stdout.decode("utf-8")

    def _header(self, out):
        return out.split("# Arranque\n", 1)[0]

    def test_neb_home_en_cache_se_ignora_y_avisa(self):
        out = self._bootstrap(NEB_HOME=CACHE_FWD)
        head = self._header(out)
        self.assertIn("(`%s`)" % NEB, head)              # el arranque sale del árbol propio
        self.assertIn("**Aviso de Neb (entorno):** `NEB_HOME` apunta al cache del plugin (`%s`)" % CACHE_FWD, head)
        self.assertIn("# Arranque", out)

    def test_clon_sin_aviso(self):
        head = self._header(self._bootstrap(NEB_HOME=NEB))
        self.assertNotIn("Aviso de Neb", head)

    def test_nombres_invalidos_avisan(self):
        head = self._header(self._bootstrap(NEB_HOOKS="logbook-sync,Notify", NEB_PROJECT_HOOKS="usage-tracker"))
        self.assertIn("`Notify` en `NEB_HOOKS`", head)
        self.assertNotIn("`usage-tracker` en", head)

    def test_nombres_validos_sin_aviso(self):
        head = self._header(self._bootstrap(NEB_HOOKS="logbook-sync", NEB_PROJECT_HOOKS="usage-tracker"))
        self.assertNotIn("Aviso de Neb", head)


def _git_bash():
    """bash como lo resuelve Claude Code en Windows: CLAUDE_CODE_GIT_BASH_PATH, Git for Windows en Program
    Files, o el que se deriva del `git` del PATH (`…\\Git\\cmd\\git.exe` → `…\\Git\\bin\\bash.exe`). Nunca
    `bash` a secas, que en Windows puede ser WSL. Fuera de Windows, el bash del PATH."""
    if os.name != "nt":
        return shutil.which("bash")
    cands = [os.environ.get("CLAUDE_CODE_GIT_BASH_PATH")]
    cands += [os.path.join(os.environ[v], "Git", "bin", "bash.exe")
              for v in ("ProgramFiles", "ProgramFiles(x86)") if os.environ.get(v)]
    git = shutil.which("git")
    if git:
        cands.append(os.path.join(os.path.dirname(os.path.dirname(git)), "bin", "bash.exe"))
    return next((c for c in cands if c and os.path.isfile(c)), None)


BASH = _git_bash()


@unittest.skipUnless(BASH, "requiere bash (Git Bash en Windows)")
class TestSetupWorkspace(unittest.TestCase):

    def test_dry_run_no_toma_el_neb_home_del_cache(self):
        home = tempfile.mkdtemp(prefix="neb-test-")
        self.addCleanup(shutil.rmtree, home, True)
        env = {k: v for k, v in os.environ.items() if k not in ("NEB_HOME", "CLAUDE_PLUGIN_ROOT", "NEB_WORKSPACE")}
        env.update(HOME=home, USERPROFILE=home, NEB_HOME=CACHE_FWD)
        r = subprocess.run([BASH, os.path.join(NEB, "bootstrap", "setup-workspace.sh"), "--dry-run",
                            "--base", os.path.join(home, "ws")],
                           env=env, cwd=home, capture_output=True, timeout=60)
        out = r.stdout.decode("utf-8", "replace")
        line = [l for l in out.splitlines() if "NEB_HOME (nucleo):" in l][0]
        self.assertNotIn("plugins/cache", line)
        self.assertNotIn("6.13.0", out)


if __name__ == "__main__":
    unittest.main()
