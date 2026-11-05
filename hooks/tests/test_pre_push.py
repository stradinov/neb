#!/usr/bin/env python3
"""test_pre_push.py — el pre-push valida lo que se publica, no la copia (hooks/pre-push-changelog, PD-753).

El hook toma de la entrada estándar el rango de cada ref y corre las compuertas sobre el árbol del commit
que se empuja, extraído a un temporal. Repo git temporal con un árbol mínimo tipo neb cuyos scripts de
compuerta son stubs: cada uno anota en STUB_LOG que corrió (y sobre qué raíz) y falla si su raíz trae el
marcador FAIL_G<n>; la compuerta 5 falla si VERSION y plugin.json no coinciden. Remoto bare temporal.
  • commit sano con la copia sucia pasa; commit con defecto con la copia «arreglada» bloquea (gates 1, 2, 4, 5, 6)
  • HEAD separado y `git push <remoto> otra-rama` validan la ref empujada (git push real)
  • gate 3 por ref: fragmento ausente, en el commit o solo en la copia; dos refs al mismo SHA
  • ref nueva, borrado, stdin vacío, varias refs, tag anotado, remote sha desconocido, push a una URL
  • higiene: el temporal se borra y la copia y su índice quedan intactos

Framework: unittest (stdlib). Árboles temporales; nunca toca la copia de neb ni ~/.claude.
  py -m unittest discover -s hooks/tests -p test_pre_push.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
NEB = os.path.abspath(os.path.join(HERE, "..", ".."))
HOOK = os.path.join(NEB, "hooks", "pre-push-changelog")
sys.path.insert(0, HERE)
from test_neb_root import BASH  # noqa: E402 — bash como lo resuelve Claude Code (Git Bash en Windows)

ZERO = "0" * 40

# Stub de una compuerta de Python: raíz = --root o la del propio script; falla con FAIL_G<n> en la raíz.
STUB_PY = r'''import os, sys
gate = "%s"
root = sys.argv[sys.argv.index("--root") + 1] if "--root" in sys.argv else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.environ["STUB_LOG"], "a", encoding="utf-8") as f:
    f.write("g%%s %%s\n" %% (gate, os.path.abspath(root).replace("\\", "/")))
if os.path.exists(os.path.join(root, "FAIL_G" + gate)):
    sys.stderr.write("stub g%%s falla\n" %% gate)
    sys.exit(1)
'''

STUB_SCAN = '''#!/usr/bin/env bash
echo "g2 $1" >> "$STUB_LOG"
[ -e "$1/FAIL_G2" ] && { echo "término vetado"; exit 1; }
exit 0
'''


def fwd(p):
    return p.replace("\\", "/")


@unittest.skipUnless(BASH, "requiere bash (Git Bash en Windows)")
class PrePushTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="neb-prepush-")
        self.repo = os.path.join(self.tmp, "repo")
        self.remote = os.path.join(self.tmp, "remote.git")
        self.ws = os.path.join(self.tmp, "ws")
        self.log = os.path.join(self.tmp, "stub.log")
        self.tmpdir = os.path.join(self.tmp, "hooktmp")
        os.makedirs(self.tmpdir)
        os.makedirs(os.path.join(self.ws, "overlay", "scripts"))
        self._write(os.path.join(self.ws, "overlay", "scripts", "scan-forbidden-terms.sh"), STUB_SCAN)
        self.env = dict(os.environ, NEB_WORKSPACE=fwd(self.ws), STUB_LOG=self.log, TMPDIR=fwd(self.tmpdir),
                        GIT_TERMINAL_PROMPT="0")
        for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
            self.env.pop(k, None)

        subprocess.run(["git", "init", "-q", "--bare", self.remote], check=True)
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True)
        for k, v in (("user.name", "t"), ("user.email", "t@t"), ("commit.gpgsign", "false"),
                     ("core.autocrlf", "false"), ("core.hooksPath", fwd(os.path.join(self.repo, ".git", "hooks")))):
            self.git("config", k, v)
        self.git("remote", "add", "origin", self.remote)
        files = {
            "general/startup.md": "# arranque\n",
            "bootstrap/assemble-startup.py": STUB_PY % "1",
            "bootstrap/assemble-changelog.py": STUB_PY % "4",
            "bootstrap/neb-bootstrap-context.py": STUB_PY % "6",
            "VERSION": "1.0.0\n",
            ".claude-plugin/plugin.json": json.dumps({"version": "1.0.0"}) + "\n",
            "changelog.d/1.0.0.md": "## [1.0.0]\n",
            "CHANGELOG.md": "# Changelog\n",
        }
        self.commit(files, "base")
        self.git("push", "-q", "--no-verify", "-u", "origin", "main")
        shutil.copy(HOOK, os.path.join(self.repo, ".git", "hooks", "pre-push"))
        open(self.log, "w").close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── utilidades ────────────────────────────────────────────────────────────
    def _write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def git(self, *args, check=True):
        r = subprocess.run(["git", *args], cwd=self.repo, env=getattr(self, "env", None),
                           capture_output=True, text=True, encoding="utf-8")
        if check and r.returncode:
            raise AssertionError("git %s: %s" % (" ".join(args), r.stderr))
        return r.stdout.strip()

    def wt(self, rel, text=None):
        """Escribe (o borra con text=None) un archivo en la copia, sin commitear."""
        p = os.path.join(self.repo, rel)
        if text is None:
            os.remove(p)
        else:
            self._write(p, text)

    def commit(self, files, msg, fragment=None):
        """Commitea files ({ruta: texto|None para borrar}); fragment agrega changelog.d/<fragment>.md."""
        if fragment:
            files = dict(files, **{"changelog.d/%s.md" % fragment: "## [%s]\n" % fragment})
        for rel, text in files.items():
            if text is None:
                self.git("rm", "-q", rel)
            else:
                self.wt(rel, text)
                self.git("add", rel)
        self.git("commit", "-q", "-m", msg)
        return self.git("rev-parse", "HEAD")

    def run_hook(self, lines, remote="origin", url=None):
        # En bytes: en modo texto, Windows convertiría "\n" en "\r\n" (git manda solo LF).
        stdin = "".join("%s\n" % " ".join(l) for l in lines).encode("utf-8")
        r = subprocess.run([BASH, fwd(HOOK), remote, url or fwd(self.remote)], cwd=self.repo, env=self.env,
                           input=stdin, capture_output=True)
        return subprocess.CompletedProcess(r.args, r.returncode, r.stdout.decode("utf-8", "replace"),
                                           r.stderr.decode("utf-8", "replace"))

    def push(self, *args):
        return subprocess.run(["git", "push", *args], cwd=self.repo, env=self.env,
                              capture_output=True, text=True, encoding="utf-8")

    def line(self, sha=None, rref="refs/heads/main", rsha=None):
        sha = sha or self.git("rev-parse", "HEAD")
        rsha = rsha if rsha is not None else self.git("rev-parse", "origin/main")
        return ("HEAD", sha, rref, rsha)

    def logged(self):
        with open(self.log, encoding="utf-8") as f:
            return [l.split(" ", 1) for l in f.read().splitlines()]

    def assertBlocks(self, r, text=None):
        self.assertNotEqual(r.returncode, 0, r.stderr)
        if text:
            self.assertIn(text, r.stderr)

    def assertPasses(self, r):
        self.assertEqual(r.returncode, 0, r.stderr)

    # ── 1 y 2: se valida el commit, no la copia ───────────────────────────────
    def test_commit_sano_copia_sucia_pasa(self):
        self.commit({"a.md": "x\n"}, "sano", fragment="1.1.0")
        for g in "1246":
            self.wt("FAIL_G%s" % g, "x")
        self.wt("VERSION", "9.9.9\n")
        self.assertPasses(self.run_hook([self.line()]))
        ran = {g for g, _ in self.logged()}
        self.assertEqual(ran, {"g1", "g2", "g4", "g6"})

    def test_commit_con_defecto_copia_arreglada_bloquea(self):
        for g, msg in (("1", "arranque ROTA"), ("2", "Términos vetados"), ("4", "CHANGELOG.md desactualizado"),
                       ("6", "no cabe")):
            with self.subTest(gate=g):
                self.git("reset", "-q", "--hard", "origin/main")
                self.commit({"FAIL_G%s" % g: "x"}, "defecto %s" % g, fragment="1.1.0")
                self.wt("FAIL_G%s" % g, None)  # la copia «lo arregla» sin commitear
                self.assertBlocks(self.run_hook([self.line()]), msg)
        with self.subTest(gate="5"):
            self.git("reset", "-q", "--hard", "origin/main")
            self.commit({"VERSION": "1.1.0\n"}, "desincronizado", fragment="1.1.0")
            self.wt(".claude-plugin/plugin.json", json.dumps({"version": "1.1.0"}) + "\n")
            self.assertBlocks(self.run_hook([self.line()]), "plugin.json.version")

    def test_gate2_y_6_reciben_el_arbol_extraido_no_la_copia(self):
        self.commit({"a.md": "x\n"}, "sano", fragment="1.1.0")
        self.assertPasses(self.run_hook([self.line()]))
        repo = fwd(os.path.abspath(self.repo))
        for g, root in self.logged():
            self.assertNotEqual(fwd(root).rstrip("/"), repo, g)
            self.assertTrue(fwd(root).rstrip("/").endswith("/tree"), (g, root))

    # ── 3: HEAD separado y otra rama, con git push real ───────────────────────
    def test_head_separado_git_push_real(self):
        self.git("checkout", "-q", "--detach")
        self.commit({"FAIL_G1": "x"}, "defecto", fragment="1.1.0")
        self.assertBlocks(self.push("origin", "HEAD:refs/heads/main"), "arranque ROTA")
        self.git("reset", "-q", "--hard", "origin/main")
        self.commit({"a.md": "x\n"}, "sano", fragment="1.1.0")
        self.assertPasses(self.push("origin", "HEAD:refs/heads/main"))

    def test_push_de_otra_rama_valida_esa_rama_no_head(self):
        self.git("checkout", "-q", "-b", "otra")
        self.commit({"FAIL_G6": "x"}, "defecto en otra", fragment="1.1.0")
        self.git("checkout", "-q", "main")
        self.commit({"a.md": "x\n"}, "sano en main", fragment="1.2.0")
        self.assertBlocks(self.push("origin", "otra"), "refs/heads/otra")
        self.assertPasses(self.push("origin", "main"))

    # ── 4: compuerta 3 ────────────────────────────────────────────────────────
    def test_gate3_fragmento(self):
        self.commit({"a.md": "x\n"}, "normativo sin fragmento")
        self.wt("changelog.d/1.1.0.md", "## [1.1.0]\n")  # solo en la copia: no cuenta
        self.assertBlocks(self.run_hook([self.line()]), "sin fragment")
        self.git("reset", "-q", "--hard", "origin/main")
        self.commit({"a.md": "x\n"}, "normativo con fragmento", fragment="1.1.0")
        self.assertPasses(self.run_hook([self.line()]))

    def test_gate3_solo_changelog_no_exige_fragmento(self):
        self.commit({"CHANGELOG.md": "# Changelog\n\nx\n"}, "solo changelog")
        self.assertPasses(self.run_hook([self.line()]))

    # ── 5 a 10b: rangos y refs ────────────────────────────────────────────────
    def test_ref_nueva_usa_commits_que_el_remoto_no_tiene(self):
        self.commit({"a.md": "x\n"}, "normativo sin fragmento")
        self.assertBlocks(self.run_hook([self.line(rref="refs/heads/nueva", rsha=ZERO)]), "sin fragment")
        self.git("reset", "-q", "--hard", "origin/main")
        self.commit({"a.md": "x\n"}, "con fragmento", fragment="1.1.0")
        self.assertPasses(self.run_hook([self.line(rref="refs/heads/nueva", rsha=ZERO)]))

    def test_ref_nueva_sin_commits_nuevos_no_corre_gates(self):
        self.assertPasses(self.run_hook([self.line(rref="refs/heads/copia", rsha=ZERO)]))
        self.assertEqual(self.logged(), [])

    def test_borrado_y_stdin_vacio_no_corren_gates(self):
        sha = self.git("rev-parse", "HEAD")
        self.assertPasses(self.run_hook([("(delete)", ZERO, "refs/heads/vieja", sha)]))
        self.assertPasses(self.run_hook([]))
        self.assertEqual(self.logged(), [])

    def test_varias_refs_una_con_defecto(self):
        sano = self.commit({"a.md": "x\n"}, "sano", fragment="1.1.0")
        malo = self.commit({"FAIL_G4": "x"}, "defecto", fragment="1.2.0")
        r = self.run_hook([self.line(sha=sano), ("refs/heads/x", malo, "refs/heads/x", ZERO)])
        self.assertBlocks(r, "refs/heads/x @ %s" % malo[:7])

    def test_dos_refs_al_mismo_sha_gate3_por_ref_y_arbol_una_vez(self):
        c = self.commit({"a.md": "x\n"}, "normativo sin fragmento")
        # main ya lo tiene en el remoto (no cambia archivos); la ref nueva sí lo publica
        r = self.run_hook([("refs/heads/main", c, "refs/heads/main", c), ("refs/heads/n", c, "refs/heads/n", ZERO)])
        self.assertBlocks(r, "refs/heads/n")
        self.git("reset", "-q", "--hard", "origin/main")
        c = self.commit({"a.md": "x\n"}, "con fragmento", fragment="1.1.0")
        open(self.log, "w").close()
        r = self.run_hook([("refs/heads/a", c, "refs/heads/a", ZERO), ("refs/heads/b", c, "refs/heads/b", ZERO)])
        self.assertPasses(r)
        self.assertEqual([g for g, _ in self.logged()].count("g1"), 1)

    def test_tag_anotado_se_pela_a_su_commit(self):
        self.commit({"FAIL_G1": "x"}, "defecto", fragment="1.1.0")
        self.git("tag", "-a", "v1.1.0", "-m", "t")
        tag = self.git("rev-parse", "v1.1.0")
        self.assertBlocks(self.run_hook([("refs/tags/v1.1.0", tag, "refs/tags/v1.1.0", ZERO)]), "arranque ROTA")

    def test_remote_sha_desconocido(self):
        self.commit({"a.md": "x\n"}, "normativo sin fragmento")
        r = self.run_hook([self.line(rsha="1234567" + "0" * 33)])
        self.assertBlocks(r, "sin fragment")
        self.git("reset", "-q", "--hard", "origin/main")
        self.commit({"a.md": "x\n"}, "con fragmento", fragment="1.1.0")
        self.assertPasses(self.run_hook([self.line(rsha="1234567" + "0" * 33)]))

    def test_push_a_url_no_toma_toda_la_historia(self):
        # La historia ya trae changelog.d/1.0.0.md: con --remotes=<url> la unión la incluiría y pasaría.
        self.commit({"a.md": "x\n"}, "normativo sin fragmento")
        url = fwd(self.remote)
        self.assertBlocks(self.run_hook([self.line(rref="refs/heads/n", rsha=ZERO)], remote=url, url=url),
                          "sin fragment")

    # ── 11: higiene ───────────────────────────────────────────────────────────
    def test_temporal_borrado_y_copia_intacta(self):
        self.wt("sucio.md", "x\n")
        self.git("add", "sucio.md")
        estado = self.git("status", "--porcelain")
        with open(os.path.join(self.repo, ".git", "index"), "rb") as f:
            indice = f.read()
        a = self.commit_tree_only({"a.md": "x\n", "changelog.d/1.1.0.md": "## [1.1.0]\n"})
        b = self.commit_tree_only({"FAIL_G6": "x", "changelog.d/1.2.0.md": "## [1.2.0]\n"})
        self.assertPasses(self.run_hook([("refs/heads/a", a, "refs/heads/a", ZERO)]))
        self.assertBlocks(self.run_hook([("refs/heads/a", a, "refs/heads/a", ZERO),
                                         ("refs/heads/b", b, "refs/heads/b", ZERO)]))
        self.assertEqual(os.listdir(self.tmpdir), [])
        self.assertEqual(self.git("status", "--porcelain"), estado)
        with open(os.path.join(self.repo, ".git", "index"), "rb") as f:
            self.assertEqual(f.read(), indice)

    def commit_tree_only(self, files):
        """Crea un commit hijo de origin/main sin tocar la copia ni el índice (hash-object + mktree)."""
        base = self.git("rev-parse", "origin/main")
        idx = os.path.join(self.tmp, "idx-%d" % len(os.listdir(self.tmp)))
        env = dict(self.env, GIT_INDEX_FILE=idx)
        run = lambda *a, **k: subprocess.run(["git", *a], cwd=self.repo, env=env, capture_output=True, text=True,
                                             check=True, **k).stdout.strip()
        run("read-tree", base)
        for rel, text in files.items():
            blob = run("hash-object", "-w", "--stdin", input=text)
            run("update-index", "--add", "--cacheinfo", "100644,%s,%s" % (blob, rel))
        tree = run("write-tree")
        return run("commit-tree", tree, "-p", base, "-m", "aislado")


if __name__ == "__main__":
    unittest.main()
