#!/usr/bin/env python3
"""test_neb_hook.py — dispatcher de los hooks opcionales registrados por el plugin (6.15.0).

Cubre hooks/neb-hook.py y hooks/lib/approved_plan.py:
  • gate: unión de NEB_HOOKS y NEB_PROJECT_HOOKS; valores inválidos (desconocidos, con espacios)
  • main(): gate apagado, subsesión interna y stdin inválido no despachan
  • dispatch(): argumentos de cada hook (logbook-sync, notify-*, preprocess-prompt),
    PYTHONIOENCODING en los hijos; notify-* recibe la config efectiva ya resuelta en variables NEB_NOTIFY_*
    (sonido desde 7.2.0; enabled, min_seconds, max_chimes y scaling desde 8.0.0, leídos de config.json),
    no se lanza sin ruta y, si el resolvedor falla, corre sin las variables
  • save-approved-plan: slug ASCII completo, ruta (<datos>/approved-plans/) y encabezado, proyecto de un
    cwd de Windows
  • extremo a extremo: neb-hook.py como proceso con un HOME temporal

Framework: unittest (stdlib). HOME temporal y sin NEB_DATA (_entorno); nunca toca ~/.claude ni ~/.neb reales.
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
sys.path.insert(0, HERE)
sys.path.insert(0, LIB)

import _entorno  # noqa: E402 — quita NEB_DATA del entorno antes de todo
import approved_plan  # noqa: E402
import neb_paths  # noqa: E402
import notify_sound  # noqa: E402 — el mismo módulo que importa dispatch() (sys.modules)

SCRIPT = os.path.join(HOOKS_DIR, "neb-hook.py")
_spec = importlib.util.spec_from_file_location("neb_hook", SCRIPT)
nh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nh)


class TestGate(unittest.TestCase):

    def test_union_de_las_dos_variables(self):
        env = {"NEB_HOOKS": "notify-on-stop,logbook-sync", "NEB_PROJECT_HOOKS": "save-approved-plan"}
        self.assertEqual(nh.enabled_hooks(env), {"notify-on-stop", "logbook-sync", "save-approved-plan"})

    def test_proyecto_solo(self):
        self.assertEqual(nh.enabled_hooks({"NEB_PROJECT_HOOKS": "save-approved-plan"}), {"save-approved-plan"})

    def test_vacias_o_ausentes(self):
        self.assertEqual(nh.enabled_hooks({}), set())
        self.assertEqual(nh.enabled_hooks({"NEB_HOOKS": "", "NEB_PROJECT_HOOKS": ","}), set())

    def test_invalidos_no_activan(self):
        env = {"NEB_HOOKS": "logbook-sync, notify-on-stop,Notify,logbook", "NEB_PROJECT_HOOKS": "x"}
        self.assertEqual(nh.enabled_hooks(env), {"logbook-sync"})
        self.assertEqual(nh.invalid_tokens(env), [("NEB_HOOKS", " notify-on-stop"), ("NEB_HOOKS", "Notify"),
                                                  ("NEB_HOOKS", "logbook"), ("NEB_PROJECT_HOOKS", "x")])

    def test_usage_tracker_retirado(self):
        # 6.29.0: el uso se mide al cerrar con /neb-usage; el nombre ya no activa nada y el arranque avisa.
        self.assertEqual(nh.enabled_hooks({"NEB_HOOKS": "usage-tracker"}), set())
        self.assertEqual(nh.invalid_tokens({"NEB_HOOKS": "usage-tracker"}), [("NEB_HOOKS", "usage-tracker")])

    def test_ops_capture_retirado(self):
        # El nombre ya no activa nada y el arranque avisa (RETIRED).
        self.assertEqual(nh.enabled_hooks({"NEB_HOOKS": "ops-capture"}), set())
        self.assertEqual(nh.invalid_tokens({"NEB_HOOKS": "ops-capture"}), [("NEB_HOOKS", "ops-capture")])
        self.assertIn("ops-capture", nh.RETIRED)

    def test_sin_invalidos(self):
        self.assertEqual(nh.invalid_tokens({"NEB_HOOKS": "notify-on-permission,,preprocess-prompt"}), [])


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
        self._main({"NEB_HOOKS": "notify-on-stop"}).assert_not_called()

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

    def test_logbook_sync_sin_transcript_o_evento_no_corre(self):
        for campo in ("transcript_path", "hook_event_name"):
            for valor in (None, ""):
                with self.subTest(campo=campo, valor=valor):
                    event = dict(self.EVENT)
                    if valor is None:
                        del event[campo]
                    else:
                        event[campo] = valor
                    run, _, _ = self._dispatch("logbook-sync", event=event)
                    run.assert_not_called()

    STOP = {"enabled": True, "wav": "C:\\x\\neb-chime.wav", "reason": None, "min_seconds": 3,
            "max_chimes": 7, "scaling": "fixed"}

    def _notify(self, hook, windows, values=None, error=None):
        kw = {"side_effect": error} if error else {"return_value": self.STOP if values is None else values}
        with mock.patch.object(notify_sound, "effective", **kw) as effective:
            run, popen, payload = self._dispatch(hook, windows=windows)
        return run, effective

    def test_notify_windows_ps1(self):
        run, effective = self._notify("notify-on-stop", windows=True)
        self.assertEqual(effective.call_args[0][0], "notify-on-stop")
        self.assertEqual(effective.call_args[1]["home"], "HOME")
        argv = run.call_args[0][0]
        self.assertEqual(argv[:5], ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"])
        self.assertEqual(argv[5], os.path.join(nh.HERE, "notify-on-stop.ps1"))
        self.assertEqual(run.call_args[1]["stdout"], subprocess.DEVNULL)
        self.assertEqual(run.call_args[1]["stderr"], subprocess.DEVNULL)
        self.assertEqual(run.call_args[1]["env"]["PYTHONIOENCODING"], "utf-8")

    def test_critico_notify_pasa_la_config_efectiva(self):
        run, _ = self._notify("notify-on-stop", windows=True)
        env = run.call_args[1]["env"]
        self.assertEqual({k: env.get(k) for k in notify_sound.ENV_VARS.values()}, {
            "NEB_NOTIFY_ENABLED": "true", "NEB_NOTIFY_WAV": "C:\\x\\neb-chime.wav",
            "NEB_NOTIFY_MIN_SECONDS": "3", "NEB_NOTIFY_MAX_CHIMES": "7", "NEB_NOTIFY_SCALING": "fixed"})

    def test_notify_posix_sh(self):
        run, _ = self._notify("notify-on-permission", windows=False,
                              values={"enabled": True, "wav": "/x/neb-chime.wav", "reason": "motivo"})
        self.assertEqual(run.call_args[0][0], ["bash", os.path.join(nh.HERE, "notify-on-permission.sh")])
        self.assertEqual(run.call_args[1]["env"]["NEB_NOTIFY_WAV"], "/x/neb-chime.wav")
        self.assertEqual(run.call_args[1]["env"]["NEB_NOTIFY_ENABLED"], "true")

    def test_notify_sin_ruta_no_lanza_el_script(self):
        for values in ({"enabled": False, "wav": None, "reason": None},
                       {"enabled": True, "wav": None, "reason": "falta el sonido por defecto"}, {}):
            with self.subTest(values=values):
                run, _ = self._notify("notify-on-stop", windows=True, values=values)
                run.assert_not_called()

    def test_notify_falla_del_resolvedor_corre_el_script_sin_las_variables(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            for var in notify_sound.ENV_VARS.values():
                os.environ.pop(var, None)
            run, _ = self._notify("notify-on-stop", windows=True, error=RuntimeError("roto"))
        run.assert_called_once()
        passed = run.call_args[1]["env"]
        for var in notify_sound.ENV_VARS.values():
            # Sin assertNotIn(var, env): su mensaje de falla imprimiría el entorno completo (llaves incluidas).
            self.assertFalse(var in passed, f"{var} no debía pasar al script")

    def test_critico_notify_lee_config_json_de_la_carpeta_de_datos(self):
        # Sin mock del resolvedor: lo que llega al script sale de <home>/.neb/config.json, normalizado.
        home = _entorno.home_temporal(self, claude=True)
        neb_paths.set_value("notify.stop.max_chimes", 50, home=home, env={})
        neb_paths.set_value("notify.stop.min_seconds", 30, home=home, env={})
        with open(os.path.join(home, ".claude", "notify-on-stop.json"), "w", encoding="utf-8") as f:
            json.dump({"enabled": False}, f)   # el suelto ya no cuenta: hay config.json
        payload = json.dumps(self.EVENT).encode("utf-8")
        with mock.patch.object(nh.subprocess, "run") as run, mock.patch.object(nh, "IS_WINDOWS", True):
            nh.dispatch("notify-on-stop", payload, self.EVENT, home)
        env = run.call_args[1]["env"]
        self.assertEqual((env["NEB_NOTIFY_ENABLED"], env["NEB_NOTIFY_MIN_SECONDS"],
                          env["NEB_NOTIFY_MAX_CHIMES"], env["NEB_NOTIFY_SCALING"]),
                         ("true", "30", "20", "per-minute"))
        self.assertEqual(env["NEB_NOTIFY_WAV"], notify_sound.DEFAULT_WAV)
        neb_paths.set_value("notify.stop.enabled", False, home=home, env={})
        with mock.patch.object(nh.subprocess, "run") as run:
            nh.dispatch("notify-on-stop", payload, self.EVENT, home)
        run.assert_not_called()

    def test_preprocess_hereda_stdout(self):
        run, _, payload = self._dispatch("preprocess-prompt")
        self.assertEqual(run.call_args[0][0][1], os.path.join(nh.HERE, "preprocess-prompt.py"))
        self.assertIsNone(run.call_args[1]["stdout"])
        self.assertEqual(run.call_args[1]["timeout"], 33)
        self.assertEqual(run.call_args[1]["env"]["PYTHONIOENCODING"], "utf-8")


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
        self.assertEqual(path, os.path.join(self.home, ".neb", "approved-plans",
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
        self.assertFalse(os.path.exists(neb_paths.approved_plans_dir(self.home)))


class TestExtremoAExtremo(unittest.TestCase):
    """neb-hook.py como lo lanza el gate del shell: proceso aparte, JSON por stdin, HOME temporal."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="neb-test-")
        self.addCleanup(shutil.rmtree, self.home, True)
        self.env = _entorno.env_con_home(self.home, NEB_HOOKS=None, NEB_PROJECT_HOOKS=None, NEB_HOME=None,
                                         NEB_INTERNAL_SUBSESSION=None, CLAUDE_PREPROCESS_RECURSION=None)

    def _run(self, hook, event, **env):
        e = dict(self.env, **env)
        return subprocess.run([sys.executable, SCRIPT, hook], input=json.dumps(event).encode("utf-8"),
                              env=e, capture_output=True, timeout=60)

    def test_save_approved_plan_activado_por_proyecto(self):
        ev = {"session_id": "s", "cwd": "/w/demo", "tool_input": {"plan": "Plan de prueba"}}
        r = self._run("save-approved-plan", ev, NEB_PROJECT_HOOKS="save-approved-plan")
        self.assertEqual(r.returncode, 0)
        files = os.listdir(os.path.join(self.home, ".neb", "approved-plans"))
        self.assertFalse(os.path.exists(os.path.join(self.home, ".claude", "approved-plans")))
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].endswith("-demo-plan-de-prueba.md"))

    def test_apagado_sale_0_sin_efectos(self):
        ev = {"session_id": "s", "cwd": "/w/demo", "tool_input": {"plan": "Plan"}}
        r = self._run("save-approved-plan", ev, NEB_HOOKS="logbook-sync")
        self.assertEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".neb", "approved-plans")))

    def test_falla_sale_0_con_rastro_en_stderr(self):
        # ~/.neb (la carpeta de datos) es un archivo: approved_plan.save no puede crear approved-plans/.
        open(os.path.join(self.home, ".neb"), "w").close()
        ev = {"session_id": "s", "cwd": "/w/demo", "tool_input": {"plan": "Plan"}}
        r = self._run("save-approved-plan", ev, NEB_HOOKS="save-approved-plan")
        self.assertEqual(r.returncode, 0)
        self.assertIn(b"[neb-hook]", r.stderr)

    def test_hook_desconocido_sale_0(self):
        self.assertEqual(self._run("no-existe", {}, NEB_HOOKS="no-existe").returncode, 0)


if __name__ == "__main__":
    unittest.main()
