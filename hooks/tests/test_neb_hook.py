#!/usr/bin/env python3
"""test_neb_hook.py — dispatcher de los hooks opcionales registrados por el plugin (6.15.0).

Cubre hooks/neb-hook.py y hooks/lib/approved_plan.py:
  • gate: unión de NEB_HOOKS y NEB_PROJECT_HOOKS; valores inválidos (desconocidos, con espacios)
  • main(): gate apagado, subsesión interna y stdin inválido no despachan
  • dispatch(): argumentos de cada hook (logbook-sync, usage-tracker, notify-*, ops-capture,
    preprocess-prompt), PYTHONIOENCODING en los hijos, ops-capture desacoplado
  • save-approved-plan: slug ASCII completo, ruta y encabezado, proyecto de un cwd de Windows
  • extremo a extremo: neb-hook.py como proceso con un HOME temporal

Framework: unittest (stdlib). HOME temporal; nunca toca ~/.claude.
  py -m unittest discover -s hooks/tests -p test_neb_hook.py
"""
import contextlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS_DIR = os.path.dirname(HERE)
LIB = os.path.join(HOOKS_DIR, "lib")
sys.path.insert(0, LIB)

import approved_plan  # noqa: E402

SCRIPT = os.path.join(HOOKS_DIR, "neb-hook.py")
_spec = importlib.util.spec_from_file_location("neb_hook", SCRIPT)
nh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nh)


class TestGate(unittest.TestCase):

    def test_union_de_las_dos_variables(self):
        env = {"NEB_HOOKS": "notify-on-stop,logbook-sync", "NEB_PROJECT_HOOKS": "usage-tracker"}
        self.assertEqual(nh.enabled_hooks(env), {"notify-on-stop", "logbook-sync", "usage-tracker"})

    def test_proyecto_solo(self):
        self.assertEqual(nh.enabled_hooks({"NEB_PROJECT_HOOKS": "save-approved-plan"}), {"save-approved-plan"})

    def test_vacias_o_ausentes(self):
        self.assertEqual(nh.enabled_hooks({}), set())
        self.assertEqual(nh.enabled_hooks({"NEB_HOOKS": "", "NEB_PROJECT_HOOKS": ","}), set())

    def test_invalidos_no_activan(self):
        env = {"NEB_HOOKS": "logbook-sync, usage-tracker,Notify,logbook", "NEB_PROJECT_HOOKS": "x"}
        self.assertEqual(nh.enabled_hooks(env), {"logbook-sync"})
        self.assertEqual(nh.invalid_tokens(env), [("NEB_HOOKS", " usage-tracker"), ("NEB_HOOKS", "Notify"),
                                                  ("NEB_HOOKS", "logbook"), ("NEB_PROJECT_HOOKS", "x")])

    def test_sin_invalidos(self):
        self.assertEqual(nh.invalid_tokens({"NEB_HOOKS": "ops-capture,,preprocess-prompt"}), [])


class TestMain(unittest.TestCase):

    def _main(self, env, stdin=b'{"session_id": "s", "cwd": "/p"}', hook="logbook-sync"):
        fake_stdin = mock.Mock()
        fake_stdin.buffer.read.return_value = stdin
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(nh, "dispatch") as dispatch, \
                mock.patch.object(nh.sys, "stdin", fake_stdin):
            nh.main(["neb-hook.py", hook])
        return dispatch

    def test_activado_despacha(self):
        d = self._main({"NEB_HOOKS": "logbook-sync"})
        d.assert_called_once()
        self.assertEqual(d.call_args[0][0], "logbook-sync")
        self.assertEqual(d.call_args[0][2], {"session_id": "s", "cwd": "/p"})

    def test_apagado_no_despacha(self):
        self._main({"NEB_HOOKS": "usage-tracker"}).assert_not_called()

    def test_subsesion_interna_no_despacha(self):
        self._main({"NEB_HOOKS": "logbook-sync", "NEB_INTERNAL_SUBSESSION": "1"}).assert_not_called()

    def test_stdin_invalido_no_despacha(self):
        self._main({"NEB_HOOKS": "logbook-sync"}, stdin=b"no es json").assert_not_called()
        self._main({"NEB_HOOKS": "logbook-sync"}, stdin=b'["lista"]').assert_not_called()


class TestDispatch(unittest.TestCase):

    EVENT = {"session_id": "sid-1", "cwd": "C:\\Users\\x\\mi.proyecto",
             "transcript_path": "C:\\Users\\x\\.claude\\projects\\C--Users-x-mi-proyecto\\sid-1.jsonl",
             "hook_event_name": "Stop"}

    def _dispatch(self, hook, event=None, windows=None):
        event = self.EVENT if event is None else event
        payload = json.dumps(event).encode("utf-8")
        with contextlib.ExitStack() as stack:
            run = stack.enter_context(mock.patch.object(nh.subprocess, "run"))
            popen = stack.enter_context(mock.patch.object(nh.subprocess, "Popen"))
            if windows is not None:
                stack.enter_context(mock.patch.object(nh, "IS_WINDOWS", windows))
            nh.dispatch(hook, payload, event, "HOME")
        return run, popen, payload

    def test_logbook_sync_argumentos(self):
        run, _, payload = self._dispatch("logbook-sync")
        argv = run.call_args[0][0]
        self.assertEqual(argv[1:], [os.path.join(nh.LIB, "logbook.py"), "sid-1", self.EVENT["cwd"],
                                    self.EVENT["transcript_path"], "Stop", nh.ROOT, "HOME"])
        self.assertEqual(run.call_args[1]["input"], payload)
        self.assertEqual(run.call_args[1]["env"]["PYTHONIOENCODING"], "utf-8")

    def test_logbook_sync_sin_sesion_no_corre(self):
        run, _, _ = self._dispatch("logbook-sync", event={"cwd": "/p"})
        run.assert_not_called()

    def test_usage_tracker_proyecto_desde_transcript(self):
        # El cwd tiene '.', que Claude Code convierte a '-' y encode_cwd no.
        run, _, _ = self._dispatch("usage-tracker")
        argv = run.call_args[0][0]
        self.assertEqual(argv[1:], [os.path.join(nh.LIB, "usage-tracker.py"), "sid-1",
                                    "C--Users-x-mi-proyecto", nh.ROOT, "HOME"])

    def test_usage_tracker_transcript_posix(self):
        ev = {"session_id": "s", "cwd": "/Users/x/mi.proyecto",
              "transcript_path": "/Users/x/.claude/projects/-Users-x-mi-proyecto/s.jsonl"}
        run, _, _ = self._dispatch("usage-tracker", event=ev)
        self.assertEqual(run.call_args[0][0][3], "-Users-x-mi-proyecto")

    def test_usage_tracker_fallback_encode_cwd(self):
        ev = {"session_id": "s", "cwd": "C:\\Users\\x\\proj"}
        run, _, _ = self._dispatch("usage-tracker", event=ev)
        self.assertEqual(run.call_args[0][0][3], "C--Users-x-proj")

    def test_notify_windows_ps1(self):
        run, _, _ = self._dispatch("notify-on-stop", windows=True)
        argv = run.call_args[0][0]
        self.assertEqual(argv[:5], ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"])
        self.assertEqual(argv[5], os.path.join(nh.HERE, "notify-on-stop.ps1"))
        self.assertEqual(run.call_args[1]["stdout"], subprocess.DEVNULL)
        self.assertEqual(run.call_args[1]["stderr"], subprocess.DEVNULL)

    def test_notify_posix_sh(self):
        run, _, _ = self._dispatch("notify-on-permission", windows=False)
        self.assertEqual(run.call_args[0][0], ["bash", os.path.join(nh.HERE, "notify-on-permission.sh")])

    def test_preprocess_hereda_stdout(self):
        run, _, payload = self._dispatch("preprocess-prompt")
        self.assertEqual(run.call_args[0][0][1], os.path.join(nh.HERE, "preprocess-prompt.py"))
        self.assertIsNone(run.call_args[1]["stdout"])
        self.assertEqual(run.call_args[1]["timeout"], 33)
        self.assertEqual(run.call_args[1]["env"]["PYTHONIOENCODING"], "utf-8")

    def test_ops_capture_desacoplado_windows(self):
        run, popen, payload = self._dispatch("ops-capture", windows=True)
        run.assert_not_called()
        kwargs = popen.call_args[1]
        self.assertEqual(popen.call_args[0][0][1], os.path.join(nh.HERE, "ops-capture.py"))
        self.assertTrue(kwargs["creationflags"] & nh._CREATE_BREAKAWAY_FROM_JOB)
        self.assertTrue(kwargs["creationflags"] & nh._CREATE_NO_WINDOW)
        self.assertEqual(kwargs["stdout"], subprocess.DEVNULL)
        popen.return_value.stdin.write.assert_called_once_with(payload)
        popen.return_value.stdin.close.assert_called_once()
        popen.return_value.wait.assert_not_called()

    def test_ops_capture_sin_breakaway_si_el_job_no_lo_permite(self):
        event = self.EVENT
        payload = json.dumps(event).encode("utf-8")
        ok = mock.Mock()
        with mock.patch.object(nh, "IS_WINDOWS", True), \
                mock.patch.object(nh.subprocess, "Popen", side_effect=[OSError("access denied"), ok]) as popen:
            nh.dispatch("ops-capture", payload, event, "HOME")
        self.assertEqual(popen.call_count, 2)
        self.assertFalse(popen.call_args_list[1][1]["creationflags"] & nh._CREATE_BREAKAWAY_FROM_JOB)
        ok.stdin.write.assert_called_once_with(payload)

    def test_ops_capture_desacoplado_posix(self):
        _, popen, _ = self._dispatch("ops-capture", windows=False)
        self.assertTrue(popen.call_args[1]["start_new_session"])
        self.assertNotIn("creationflags", popen.call_args[1])


class TestApprovedPlan(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="neb-test-")
        self.addCleanup(shutil.rmtree, self.home, True)

    def test_slug_ascii_completo(self):
        self.assertEqual(approved_plan.slugify("# Plan: Instalación de módulos — fase 2"),
                         "plan-instalacion-de-modulos-fase-2")
        self.assertEqual(approved_plan.slugify("  ## Migrar PHP 7.0→7.2.34 en la tienda!"),
                         "migrar-php-7-0-7-2-34-en-la-tienda")
        self.assertEqual(approved_plan.slugify("Corrección del niño (ñ)"), "correccion-del-nino-n")

    def test_slug_vacio_y_limite(self):
        self.assertEqual(approved_plan.slugify("### ¿¿??"), "plan")
        slug = approved_plan.slugify("a-" * 40)
        self.assertLessEqual(len(slug), 50)
        self.assertFalse(slug.endswith("-"))

    def test_save_ruta_y_encabezado(self):
        ev = {"session_id": "sid-9", "cwd": "C:\\Users\\x\\tienda",
              "tool_input": {"plan": "# Reorden de pedidos\n\nPaso 1"}}
        path = approved_plan.save(ev, self.home, now=datetime(2026, 10, 23, 14, 5, 9))
        self.assertEqual(path, os.path.join(self.home, ".claude", "approved-plans",
                                            "20261023-140509-tienda-reorden-de-pedidos.md"))
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "# Plan aprobado — 2026-10-23 14:05:09\n\n**Proyecto:** tienda\n"
                                       "**Sesión:** sid-9\n**CWD:** C:\\Users\\x\\tienda\n\n"
                                       "# Reorden de pedidos\n\nPaso 1\n")

    def test_save_cwd_en_raiz_de_unidad(self):
        # `C:` en el nombre abriría un flujo alternativo de NTFS en vez de un archivo.
        path = approved_plan.save({"cwd": "C:\\", "tool_input": {"plan": "Plan"}}, self.home,
                                  now=datetime(2026, 10, 23, 14, 5, 9))
        self.assertEqual(os.path.basename(path), "20261023-140509-C-plan.md")

    def test_save_sin_plan(self):
        self.assertIsNone(approved_plan.save({"tool_input": {}}, self.home))
        self.assertFalse(os.path.exists(os.path.join(self.home, ".claude", "approved-plans")))


class TestExtremoAExtremo(unittest.TestCase):
    """neb-hook.py como lo lanza el gate del shell: proceso aparte, JSON por stdin, HOME temporal."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="neb-test-")
        self.addCleanup(shutil.rmtree, self.home, True)
        self.env = {k: v for k, v in os.environ.items()
                    if k not in ("NEB_HOOKS", "NEB_PROJECT_HOOKS", "NEB_HOME", "NEB_INTERNAL_SUBSESSION",
                                 "CLAUDE_PREPROCESS_RECURSION")}
        self.env.update(HOME=self.home, USERPROFILE=self.home)

    def _run(self, hook, event, **env):
        e = dict(self.env, **env)
        return subprocess.run([sys.executable, SCRIPT, hook], input=json.dumps(event).encode("utf-8"),
                              env=e, capture_output=True, timeout=60)

    def test_save_approved_plan_activado_por_proyecto(self):
        ev = {"session_id": "s", "cwd": "/w/demo", "tool_input": {"plan": "Plan de prueba"}}
        r = self._run("save-approved-plan", ev, NEB_PROJECT_HOOKS="save-approved-plan")
        self.assertEqual(r.returncode, 0)
        files = os.listdir(os.path.join(self.home, ".claude", "approved-plans"))
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].endswith("-demo-plan-de-prueba.md"))

    def test_apagado_sale_0_sin_efectos(self):
        ev = {"session_id": "s", "cwd": "/w/demo", "tool_input": {"plan": "Plan"}}
        r = self._run("save-approved-plan", ev, NEB_HOOKS="logbook-sync")
        self.assertEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".claude", "approved-plans")))

    def test_falla_sale_0_con_rastro_en_stderr(self):
        # ~/.claude es un archivo: approved_plan.save no puede crear approved-plans/.
        open(os.path.join(self.home, ".claude"), "w").close()
        ev = {"session_id": "s", "cwd": "/w/demo", "tool_input": {"plan": "Plan"}}
        r = self._run("save-approved-plan", ev, NEB_HOOKS="save-approved-plan")
        self.assertEqual(r.returncode, 0)
        self.assertIn(b"[neb-hook]", r.stderr)

    def test_hook_desconocido_sale_0(self):
        self.assertEqual(self._run("no-existe", {}, NEB_HOOKS="no-existe").returncode, 0)


if __name__ == "__main__":
    unittest.main()
