#!/usr/bin/env python3
"""test_preprocess_prompt.py — config y estado por sesión del hook preprocess-prompt.py (8.0.0).

  • load_config: sección `preprocess` de <datos>/config.json (con y sin BOM), JSON sueltos de antes de
    8.0.0 sin config.json, config ilegible, modo desconocido, NEB_DATA
  • resolve_mode: prefijo > sesión > CLAUDE_PREPROCESS_MODE > config > default, uno por nivel
  • estado por sesión: ruta nueva, ruta vieja de ~/.claude solo si falta la nueva, saneo del session_id
  • set_session_mode y la CLI --set-session-mode: escritura atómica, modo y session_id inválidos, purga de
    estados de más de 7 días sin seguir enlaces, enlaces en la ruta
  • main: el modo de la sesión llega al preámbulo (la corrección con `claude -p` va simulada)

Nunca llama al modelo: `correct_with_haiku` se reemplaza en las pruebas de main y ninguna otra la toca.
Framework: unittest (stdlib). HOME temporal y NEB_DATA fuera del entorno; nunca toca ~/.claude ni ~/.neb.
  py -m unittest discover -s hooks/tests -p test_preprocess_prompt.py
"""
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.abspath(os.path.join(HERE, ".."))
SCRIPT = os.path.join(HOOKS, "preprocess-prompt.py")
sys.path.insert(0, os.path.join(HOOKS, "lib"))
import _entorno  # noqa: E402

_spec = importlib.util.spec_from_file_location("preprocess_prompt", SCRIPT)
pp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pp)

DAY = 24 * 3600
SID = "0b4c6a2e-1f3d-4a5b-9c8d-7e6f5a4b3c2d"


class Base(unittest.TestCase):
    def setUp(self):
        self.home = _entorno.home_temporal(self)
        self.env = {}

    def write(self, rel, text, encoding="utf-8"):
        path = os.path.join(self.home, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding=encoding) as f:
            f.write(text)
        return path

    def write_json(self, rel, value, encoding="utf-8"):
        return self.write(rel, json.dumps(value), encoding)

    def state_rel(self, sid=SID):
        return os.path.join(".neb", "state", "preprocess", f"{sid}.json")

    def legacy_state_rel(self, sid=SID):
        return os.path.join(".claude", "preprocess-state", f"{sid}.json")


# --------------------------------------------------------------------------- load_config

class TestLoadConfig(Base):
    def cfg(self):
        return pp.load_config(self.home, self.env)

    def test_sin_nada_son_los_defaults(self):
        self.assertEqual(self.cfg(), pp.DEFAULTS)

    def test_lee_la_seccion_preprocess_de_config_json(self):
        self.write_json(".neb/config.json", {"schema": 1, "preprocess": {"mode": "fast", "model": "m", "prefix": "!!"}})
        self.assertEqual(self.cfg(), {"mode": "fast", "model": "m", "prefix": "!!"})

    def test_config_json_con_bom(self):
        # PowerShell 5.1 (Out-File -Encoding utf8) escribe BOM; antes de 8.0.0 el hook lo leía como ilegible.
        self.write_json(".neb/config.json", {"preprocess": {"mode": "full"}}, encoding="utf-8-sig")
        self.assertEqual(self.cfg()["mode"], "full")

    def test_sin_config_json_lee_el_suelto_de_claude(self):
        self.write_json(".claude/preprocess.json", {"mode": "fast", "prefix": "%%"}, encoding="utf-8-sig")
        cfg = self.cfg()
        self.assertEqual((cfg["mode"], cfg["prefix"], cfg["model"]), ("fast", "%%", pp.DEFAULTS["model"]))

    def test_con_config_json_ignora_el_suelto(self):
        self.write_json(".neb/config.json", {"schema": 1})
        self.write_json(".claude/preprocess.json", {"mode": "fast"})
        self.assertEqual(self.cfg()["mode"], "off")

    def test_config_ilegible_son_los_defaults(self):
        self.write(".neb/config.json", "{ esto no es json")
        self.assertEqual(self.cfg(), pp.DEFAULTS)

    def test_modo_desconocido_cae_a_off(self):
        self.write_json(".neb/config.json", {"preprocess": {"mode": "rapido"}})
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(self.cfg()["mode"], "off")
        self.assertIn("rapido", err.getvalue())

    def test_campo_vacio_o_de_otro_tipo_cae_al_default(self):
        self.write_json(".neb/config.json", {"preprocess": {"mode": 1, "model": "", "prefix": None}})
        self.assertEqual(self.cfg(), pp.DEFAULTS)

    def test_respeta_neb_data(self):
        datos = os.path.join(self.home, "otra")
        self.write_json(os.path.join("otra", "config.json"), {"preprocess": {"mode": "full"}})
        self.env = {"NEB_DATA": datos}
        self.assertEqual(self.cfg()["mode"], "full")

    def test_si_neb_paths_levanta_son_los_defaults(self):
        with mock.patch.object(pp.neb_paths, "section", side_effect=RuntimeError("x")), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.cfg(), pp.DEFAULTS)


# --------------------------------------------------------------------------- resolve_mode

class TestResolveMode(Base):
    def resolve(self, prompt="corrige este texto largo por favor", cfg=None, sid=SID, env=None):
        cfg = dict(pp.DEFAULTS) if cfg is None else cfg
        return pp.resolve_mode(prompt, cfg, self.home, sid, {} if env is None else env)

    def test_default_off(self):
        self.assertEqual(self.resolve()[0], "off")

    def test_config_sobre_default(self):
        self.assertEqual(self.resolve(cfg=dict(pp.DEFAULTS, mode="fast"))[0], "fast")

    def test_config_con_modo_invalido_no_enciende(self):
        self.assertEqual(self.resolve(cfg=dict(pp.DEFAULTS, mode="xyz"))[0], "off")

    def test_env_sobre_config(self):
        mode, _ = self.resolve(cfg=dict(pp.DEFAULTS, mode="fast"), env={"CLAUDE_PREPROCESS_MODE": "full"})
        self.assertEqual(mode, "full")

    def test_env_invalido_se_ignora(self):
        mode, _ = self.resolve(cfg=dict(pp.DEFAULTS, mode="fast"), env={"CLAUDE_PREPROCESS_MODE": "FULL"})
        self.assertEqual(mode, "fast")

    def test_sesion_sobre_env(self):
        self.write_json(self.state_rel(), {"mode": "fast"})
        mode, _ = self.resolve(env={"CLAUDE_PREPROCESS_MODE": "full"})
        self.assertEqual(mode, "fast")

    def test_sesion_off_gana_sobre_env(self):
        self.write_json(self.state_rel(), {"mode": "off"})
        self.assertEqual(self.resolve(env={"CLAUDE_PREPROCESS_MODE": "full"})[0], "off")

    def test_prefijo_sobre_sesion(self):
        self.write_json(self.state_rel(), {"mode": "full"})
        self.assertEqual(self.resolve("$$ explora el repo"), ("off", "explora el repo"))

    def test_prefijo_de_la_config(self):
        self.assertEqual(self.resolve("!!hola", cfg=dict(pp.DEFAULTS, mode="full", prefix="!!")), ("off", "hola"))

    def test_prefijo_seguido_de_simbolo_no_es_bypass(self):
        mode, prompt = self.resolve("$$$ dinero", cfg=dict(pp.DEFAULTS, mode="full"))
        self.assertEqual((mode, prompt), ("full", "$$$ dinero"))

    def test_sesion_respeta_neb_data(self):
        datos = os.path.join(self.home, "datos")
        self.write_json(os.path.join("datos", "state", "preprocess", f"{SID}.json"), {"mode": "full"})
        self.assertEqual(self.resolve(env={"NEB_DATA": datos})[0], "full")
        self.assertEqual(self.resolve(env={})[0], "off")


# --------------------------------------------------------------------------- estado por sesión

class TestEstadoPorSesion(Base):
    def read(self, sid=SID):
        return pp.read_session_mode(self.home, sid, self.env)

    def test_sin_estado(self):
        self.assertIsNone(self.read())

    def test_ruta_nueva(self):
        self.write_json(self.state_rel(), {"mode": "full"})
        self.assertEqual(self.read(), "full")

    def test_ruta_nueva_con_bom(self):
        self.write_json(self.state_rel(), {"mode": "fast"}, encoding="utf-8-sig")
        self.assertEqual(self.read(), "fast")

    def test_ruta_vieja_si_falta_la_nueva(self):
        self.write_json(self.legacy_state_rel(), {"mode": "fast"})
        self.assertEqual(self.read(), "fast")

    def test_la_nueva_gana_sobre_la_vieja(self):
        self.write_json(self.state_rel(), {"mode": "off"})
        self.write_json(self.legacy_state_rel(), {"mode": "full"})
        self.assertEqual(self.read(), "off")

    def test_nueva_ilegible_no_cae_a_la_vieja(self):
        self.write(self.state_rel(), "{ roto")
        self.write_json(self.legacy_state_rel(), {"mode": "full"})
        self.assertIsNone(self.read())

    def test_modo_invalido_o_no_objeto(self):
        for content in ('{"mode": "FULL"}', '["full"]', '"full"', "{}"):
            with self.subTest(content=content):
                self.write(self.state_rel(), content)
                self.assertIsNone(self.read())


class TestSaneoSessionId(Base):
    VALIDOS = (SID, "a", "A_b-9", "x" * 128)
    INVALIDOS = ("", None, 123, "../x", "..", "a/b", "a\\b", "a.b", "con espacio", "x" * 129, "ñ", "a\n")

    def test_valid_session_id(self):
        for sid in self.VALIDOS:
            with self.subTest(sid=sid):
                self.assertTrue(pp.valid_session_id(sid))
        for sid in self.INVALIDOS:
            with self.subTest(sid=sid):
                self.assertFalse(pp.valid_session_id(sid))

    def test_traversal_no_lee_fuera_de_la_carpeta(self):
        # ../x apuntaría a <datos>/state/x.json y a ~/.claude/x.json: ambos existen y no se leen.
        self.write_json(os.path.join(".neb", "state", "x.json"), {"mode": "full"})
        self.write_json(os.path.join(".claude", "x.json"), {"mode": "full"})
        self.assertIsNone(pp.read_session_mode(self.home, "../x", {}))
        self.assertIsNone(pp.session_state_path("../x", self.home, {}))

    def test_invalido_no_tiene_estado(self):
        for sid in ("", None, "x" * 129, "a.b"):
            with self.subTest(sid=sid):
                self.assertIsNone(pp.read_session_mode(self.home, sid, {}))
                with self.assertRaises(ValueError):
                    pp.set_session_mode(sid, "full", self.home, {})
        self.assertFalse(os.path.exists(os.path.join(self.home, ".neb")))


# --------------------------------------------------------------------------- set_session_mode / CLI

def _symlink_o_skip(test, target, link, is_dir=False):
    try:
        os.symlink(target, link, target_is_directory=is_dir)
    except (OSError, NotImplementedError) as e:
        test.skipTest(f"sin permiso para crear symlinks: {e}")


def _enlace_de_carpeta_o_skip(test, target, link):
    """Junction en Windows (no pide privilegios); symlink en lo demás."""
    if sys.platform == "win32":
        try:
            import _winapi
            _winapi.CreateJunction(target, link)
            return
        except (ImportError, OSError) as e:
            test.skipTest(f"sin junction: {e}")
    _symlink_o_skip(test, target, link, is_dir=True)


class TestSetSessionMode(Base):
    def folder(self):
        return os.path.join(self.home, ".neb", "state", "preprocess")

    def set(self, mode, sid=SID, now=None):
        return pp.set_session_mode(sid, mode, self.home, self.env, now=now)

    def test_escribe_y_el_hook_lo_lee(self):
        path = self.set("fast")
        self.assertEqual(path, os.path.join(self.folder(), f"{SID}.json"))
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        self.assertEqual(json.loads(raw), {"mode": "fast"})
        self.assertFalse(raw.startswith("﻿"))
        self.assertEqual(pp.read_session_mode(self.home, SID, self.env), "fast")

    def test_sobrescribe_sin_dejar_temporales(self):
        self.set("full")
        self.set("off")
        self.assertEqual(pp.read_session_mode(self.home, SID, self.env), "off")
        self.assertEqual(os.listdir(self.folder()), [f"{SID}.json"])

    def test_rechaza_modo_invalido(self):
        for mode in ("FULL", "", "on", None):
            with self.subTest(mode=mode):
                with self.assertRaises(ValueError):
                    self.set(mode)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".neb")))

    def test_respeta_neb_data(self):
        datos = os.path.join(self.home, "datos")
        self.env = {"NEB_DATA": datos}
        path = self.set("full")
        self.assertEqual(path, os.path.join(datos, "state", "preprocess", f"{SID}.json"))
        self.assertFalse(os.path.exists(os.path.join(self.home, ".neb")))

    def _viejo(self, name, age_days, now):
        path = os.path.join(self.folder(), name)
        os.makedirs(self.folder(), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"mode": "full"}')
        t = now - age_days * DAY
        os.utime(path, (t, t))
        return path

    def test_limpia_estados_de_mas_de_7_dias(self):
        now = time.time()
        viejo = self._viejo("sesion-vieja.json", 8, now)
        reciente = self._viejo("sesion-reciente.json", 6, now)
        otro_nombre = self._viejo("notas.txt", 30, now)
        nombre_invalido = self._viejo("no.valido.json", 30, now)
        legacy = self.write_json(self.legacy_state_rel("sesion-vieja"), {"mode": "full"})
        os.utime(legacy, (now - 30 * DAY, now - 30 * DAY))
        self.set("fast", now=now)
        self.assertFalse(os.path.exists(viejo))
        for path in (reciente, otro_nombre, nombre_invalido, legacy):
            self.assertTrue(os.path.exists(path), path)

    def test_la_purga_no_borra_el_que_acaba_de_escribir(self):
        # Con un `now` adelantado el recién escrito ya "tiene" más de 7 días: aun así se conserva.
        path = self.set("fast", now=time.time() + 30 * DAY)
        self.assertTrue(os.path.exists(path))

    def test_la_purga_no_sigue_enlaces(self):
        now = time.time()
        fuera = os.path.join(self.home, "fuera")
        os.makedirs(fuera)
        target = os.path.join(fuera, "importante.json")
        with open(target, "w", encoding="utf-8") as f:
            f.write("{}")
        os.utime(target, (now - 30 * DAY, now - 30 * DAY))
        os.makedirs(self.folder())
        link = os.path.join(self.folder(), "enlace.json")
        _symlink_o_skip(self, target, link)
        self.set("fast", now=now)
        self.assertTrue(os.path.lexists(link))
        self.assertTrue(os.path.exists(target))

    def test_rechaza_el_estado_si_es_enlace(self):
        fuera = os.path.join(self.home, "fuera.json")
        with open(fuera, "w", encoding="utf-8") as f:
            f.write("original")
        os.makedirs(self.folder())
        _symlink_o_skip(self, fuera, os.path.join(self.folder(), f"{SID}.json"))
        with self.assertRaises(ValueError):
            self.set("full")
        with open(fuera, encoding="utf-8") as f:
            self.assertEqual(f.read(), "original")

    def test_rechaza_el_estado_si_es_enlace_de_carpeta(self):
        # Variante que corre en Windows sin privilegios (junction): el symlink de archivo de arriba lo pide.
        fuera = os.path.join(self.home, "fuera")
        os.makedirs(fuera)
        os.makedirs(self.folder())
        _enlace_de_carpeta_o_skip(self, fuera, os.path.join(self.folder(), f"{SID}.json"))
        with self.assertRaises(ValueError):
            self.set("full")
        self.assertEqual(os.listdir(fuera), [])

    def test_la_purga_no_sigue_enlaces_de_carpeta(self):
        now = time.time()
        fuera = os.path.join(self.home, "fuera")
        os.makedirs(fuera)
        dentro = os.path.join(fuera, "importante.json")
        with open(dentro, "w", encoding="utf-8") as f:
            f.write("{}")
        os.makedirs(self.folder())
        link = os.path.join(self.folder(), "enlace.json")
        _enlace_de_carpeta_o_skip(self, fuera, link)
        self.set("fast", now=now)
        self.assertTrue(os.path.lexists(link))
        self.assertTrue(os.path.exists(dentro))

    def test_rechaza_la_carpeta_si_es_enlace(self):
        fuera = os.path.join(self.home, "fuera")
        os.makedirs(fuera)
        os.makedirs(os.path.join(self.home, ".neb", "state"))
        _enlace_de_carpeta_o_skip(self, fuera, self.folder())
        with self.assertRaises(ValueError):
            self.set("full")
        self.assertEqual(os.listdir(fuera), [])

    def test_rechaza_state_si_es_enlace(self):
        fuera = os.path.join(self.home, "fuera")
        os.makedirs(fuera)
        os.makedirs(os.path.join(self.home, ".neb"))
        _enlace_de_carpeta_o_skip(self, fuera, os.path.join(self.home, ".neb", "state"))
        with self.assertRaises(ValueError):
            self.set("full")
        self.assertEqual(os.listdir(fuera), [])


class TestCli(Base):
    def run_cli(self, *args, **extra):
        # stderr en UTF-8 aunque la consola de Windows sea cp1252: los mensajes llevan acentos.
        env = _entorno.env_con_home(self.home, PYTHONIOENCODING="utf-8", **extra)
        return subprocess.run([sys.executable, SCRIPT, *args], env=env, capture_output=True, text=True,
                              encoding="utf-8", stdin=subprocess.DEVNULL, timeout=60)

    def test_escribe_e_imprime_la_ruta(self):
        proc = self.run_cli("--set-session-mode", SID, "full")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        path = os.path.join(self.home, ".neb", "state", "preprocess", f"{SID}.json")
        self.assertEqual(os.path.normcase(proc.stdout.strip()), os.path.normcase(path))
        with open(path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"mode": "full"})

    def test_con_neb_data(self):
        datos = os.path.join(self.home, "datos")
        proc = self.run_cli("--set-session-mode", SID, "off", NEB_DATA=datos)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(os.path.isfile(os.path.join(datos, "state", "preprocess", f"{SID}.json")))

    def test_modo_invalido_sale_2(self):
        proc = self.run_cli("--set-session-mode", SID, "turbo")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("modo inválido", proc.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".neb")))

    def test_session_id_invalido_sale_2(self):
        proc = self.run_cli("--set-session-mode", "../x", "full")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("session_id inválido", proc.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".neb")))

    def test_argumentos_de_mas_o_de_menos_sale_2(self):
        for args in (("--set-session-mode",), ("--set-session-mode", SID), ("--set-session-mode", SID, "full", "x")):
            with self.subTest(args=args):
                self.assertEqual(self.run_cli(*args).returncode, 2)


# --------------------------------------------------------------------------- main (sin modelo)

class TestMain(Base):
    def run_main(self, prompt, sid=SID):
        out = io.StringIO()
        payload = json.dumps({"prompt": prompt, "session_id": sid})
        llamada = mock.Mock(return_value="Corregido de prueba")
        with _entorno.home_en_proceso(self.home, CLAUDE_PREPROCESS_MODE=None, NEB_INTERNAL_SUBSESSION=None,
                                      CLAUDE_PREPROCESS_RECURSION=None), \
                mock.patch.object(pp, "correct_with_haiku", llamada), \
                mock.patch.object(sys, "stdin", io.StringIO(payload)), \
                contextlib.redirect_stdout(out):
            pp.main()
        return out.getvalue(), llamada

    def test_modo_de_sesion_llega_al_preambulo(self):
        self.write_json(self.state_rel(), {"mode": "full"})
        out, llamada = self.run_main("agreaga una funcion que valide el correo")
        llamada.assert_called_once()
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("modo full", ctx)
        self.assertIn("Corregido de prueba", ctx)

    def test_modo_de_config_json(self):
        self.write_json(".neb/config.json", {"preprocess": {"mode": "fast", "model": "modelo-x"}})
        out, llamada = self.run_main("agreaga una funcion que valide el correo")
        self.assertEqual(llamada.call_args[0][1], "modelo-x")
        self.assertIn("modo fast", json.loads(out)["hookSpecificOutput"]["additionalContext"])

    def test_sin_estado_ni_config_no_llama_al_modelo(self):
        out, llamada = self.run_main("agreaga una funcion que valide el correo")
        llamada.assert_not_called()
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
