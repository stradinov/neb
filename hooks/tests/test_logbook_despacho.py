#!/usr/bin/env python3
"""
test_logbook_despacho.py — despacho de `logbook.py` y verbos retirados (neb 7.0.0).

La captura entra solo con exactamente 6 posicionales, un primer argumento que no es verbo y un cuarto que es
uno de los eventos del hook (Stop, SessionEnd, PreCompact). Un verbo retirado responde su JSON fijo aunque
traiga la aridad del hook; cualquier otro primer argumento responde «subcomando desconocido». Ninguno de
los dos crea works ni la base. Se prueba por subproceso porque el despacho vive en `__main__`.

Invariantes: homes temporales (HOME y USERPROFILE) solo en el entorno del subproceso; nunca ~/.claude.
Framework: unittest (stdlib).
  py -m unittest tests.test_logbook_despacho
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "lib")
NEB_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
LOGBOOK = os.path.join(LIB, "logbook.py")
SCHEMA = os.path.join(HERE, "..", "logbook-schema.sql")
sys.path.insert(0, LIB)

import _db_shared
import logbook

_LOCK = "se retiró en neb 7.0.0 junto con el candado entre devs; "
RETIRED = {
    "sync": {"ok": False, "motivo": "verbo-retirado", "verbo": "sync",
             "detalle": "se retiró en neb 7.0.0 junto con el backend central: la bitácora es solo local y no "
                        "hay nada que sincronizar."},
    "sync-status": {"ok": False, "motivo": "verbo-retirado", "verbo": "sync-status",
                    "detalle": "se retiró en neb 7.0.0 junto con el backend central: la bitácora es solo local "
                               "y no hay estado de sincronización que revisar.",
                    "attention": 0},
    "claim": {"ok": False, "motivo": "verbo-retirado", "verbo": "claim",
              "detalle": _LOCK + "para continuar un REQ usa `retomar <ruta-del-Change-MD>` (## Relevo, plan "
                                 "aprobado y rama)."},
    "release": {"ok": False, "motivo": "verbo-retirado", "verbo": "release",
                "detalle": _LOCK + "para dejar un REQ a otro, deja su ## Relevo en el Change MD y entrega el "
                                   "registro por git."},
    "forced-release": {"ok": False, "motivo": "verbo-retirado", "verbo": "forced-release",
                       "detalle": _LOCK + "para continuar un REQ usa `retomar <ruta-del-Change-MD>`."},
    "request": {"ok": False, "motivo": "verbo-retirado", "verbo": "request",
                "detalle": _LOCK + "para continuar un REQ usa `retomar <ruta-del-Change-MD>`."},
    "search": {"ok": False, "motivo": "verbo-retirado", "verbo": "search",
               "detalle": "se retiró en neb 6.41.0: la bitácora no guarda texto de sesiones. Para retomar un "
                          "REQ usa su Change MD, su ## Relevo, el plan aprobado y la rama."},
}


def _env(home):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("NEB_") and k not in ("PYTHONUTF8", "CLAUDE_PLUGIN_ROOT")}
    env.update(HOME=home, USERPROFILE=home, NEB_HOME=NEB_ROOT, PYTHONIOENCODING="cp1252")
    return env


class _Base(unittest.TestCase):

    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="neb-test-despacho-")
        self.home = os.path.join(self.base, "home")
        os.makedirs(os.path.join(self.home, ".claude"))
        self.cwd = os.path.join(self.base, "repo")
        os.makedirs(self.cwd)
        self.t = os.path.join(self.base, "S.jsonl")
        with open(self.t, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "user", "message": {"content": "hola"}}) + "\n")
        self.db = _db_shared.resolve_db_path(self.home)

    def _hook_args(self, first, event="Stop"):
        """Los 6 posicionales que arma el hook, con `first` en el lugar del session_id."""
        return [first, self.cwd, self.t, event, NEB_ROOT, self.home]

    def _run(self, args):
        r = subprocess.run([sys.executable, LOGBOOK] + args, capture_output=True, env=_env(self.home),
                           cwd=self.base, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.decode("utf-8")

    def _works(self):
        c = sqlite3.connect(self.db)
        try:
            return c.execute("SELECT count(*) FROM work").fetchone()[0]
        finally:
            c.close()

    def _no_new_files(self):
        self.assertEqual(os.listdir(os.path.join(self.home, ".claude")), [])
        self.assertEqual(sorted(os.listdir(self.base)), ["S.jsonl", "home", "repo"])
        self.assertEqual(os.listdir(self.cwd), [])


class TestVerbosRetirados(_Base):

    def test_critico_cada_verbo_retirado_con_la_aridad_del_hook_responde_su_json_y_no_crea_works(self):
        _db_shared._connect(self.db, SCHEMA).close()
        for verb, expected in RETIRED.items():
            for args in ([verb], [verb, "12"], self._hook_args(verb), self._hook_args(verb) + ["x"]):
                with self.subTest(args=args):
                    out = self._run(args)
                    self.assertEqual(out.splitlines(), [json.dumps(expected, ensure_ascii=False)])
                    self.assertEqual(self._works(), 0)

    def test_verbo_retirado_no_crea_la_base(self):
        for verb in RETIRED:
            with self.subTest(verb=verb):
                self._run(self._hook_args(verb))
                self._no_new_files()

    def test_el_diccionario_es_el_de_7_0_0_y_no_se_cruza_con_los_verbos_vivos(self):
        self.assertEqual(set(logbook._RETIRED_VERBS), set(RETIRED))
        self.assertFalse(set(logbook._RETIRED_VERBS) & logbook.CLI_CMDS)
        self.assertEqual(logbook.CLI_CMDS, {"list", "show", "rename", "archive", "link", "trace", "unlink"})
        self.assertEqual(logbook.CAPTURE_EVENTS, {"Stop", "SessionEnd", "PreCompact"})


class TestDesconocido(_Base):

    def test_critico_verbo_desconocido_con_exactamente_6_posicionales_no_captura(self):
        out = self._run(self._hook_args("tomar", event="SubagentStop"))
        self.assertEqual(out.strip(), "subcomando desconocido: tomar")
        self._no_new_files()

    def test_desconocido_con_6_posicionales_y_base_existente_no_crea_works(self):
        _db_shared._connect(self.db, SCHEMA).close()
        for args in (self._hook_args("liberar", event="algo"), self._hook_args("solicitar", event="")):
            with self.subTest(args=args):
                self.assertEqual(self._run(args).strip(), f"subcomando desconocido: {args[0]}")
                self.assertEqual(self._works(), 0)

    def test_desconocido_con_otra_aridad(self):
        for args in (["estado-sync"], ["tomar", "12"], self._hook_args("x")[:5], self._hook_args("y")[:4]):
            with self.subTest(args=args):
                self.assertEqual(self._run(args).strip(), f"subcomando desconocido: {args[0]}")
                self._no_new_files()

    def test_sin_argumentos_no_hace_nada(self):
        self.assertEqual(self._run([]), "")
        self._no_new_files()


class TestCapturaLegitima(_Base):

    def test_critico_seis_posicionales_con_evento_del_hook_crea_el_work(self):
        for i, event in enumerate(("Stop", "PreCompact", "SessionEnd")):
            with self.subTest(event=event):
                self.assertEqual(self._run(self._hook_args(f"S{i}", event=event)), "")
                c = sqlite3.connect(self.db)
                row = c.execute("SELECT mode, repo_path, transcript_path FROM work WHERE claude_session_id=?",
                                (f"S{i}",)).fetchone()
                c.close()
                self.assertEqual(row, ("exploratory", self.cwd, self.t))


if __name__ == "__main__":
    unittest.main()
