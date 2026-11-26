#!/usr/bin/env python3
"""test_neb_paths.py — carpeta de datos de Neb y config.json (hooks/lib/neb_paths.py, 8.0.0).

  • data_dir: ~/.neb por omisión; NEB_DATA absoluta, con ~ y con /c/... de Git Bash; relativa se ignora
  • rutas derivadas y named_path (incluidos state/<x>, cache/<x> y los nombres inválidos)
  • load_config: defaults, merge por tipo, BOM, JSON ilegible, JSON sueltos de antes de 8.0.0 solo sin
    config.json, legacy_config_sources
  • set_value: crea config.json (con lo de los JSON sueltos), no pisa lo demás, rechaza llaves y tipos
    ajenos y un config.json ilegible, escritura atómica
  • ensure_dir rechaza un enlace
  • la CLI

Framework: unittest (stdlib). HOME temporal y NEB_DATA fuera del entorno; nunca toca ~/.neb.
  py -m unittest discover -s hooks/tests -p test_neb_paths.py
"""
import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "lib")))
import _entorno  # noqa: E402,F401
import neb_paths as np_  # noqa: E402


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

    def cfg(self):
        return np_.load_config(self.home, self.env)


class TestRutas(Base):
    def test_omision_es_home_punto_neb(self):
        self.assertEqual(np_.data_dir(self.home, {}), os.path.join(self.home, ".neb"))

    def test_neb_data_absoluta(self):
        target = os.path.join(self.home, "otra", "carpeta")
        self.assertEqual(np_.data_dir(self.home, {"NEB_DATA": target}), os.path.normpath(target))

    def test_neb_data_con_tilde(self):
        self.assertEqual(np_.data_dir(self.home, {"NEB_DATA": "~/datos"}), os.path.normpath(os.path.join(self.home, "datos")))

    def test_neb_data_relativa_o_vacia_se_ignora(self):
        for value in ("datos", "./datos", "", "   "):
            with self.subTest(value=value):
                self.assertEqual(np_.data_dir(self.home, {"NEB_DATA": value}), os.path.join(self.home, ".neb"))

    @unittest.skipUnless(sys.platform == "win32", "forma /c/... solo en Windows")
    def test_neb_data_forma_git_bash(self):
        self.assertEqual(np_.data_dir(self.home, {"NEB_DATA": "/d/neb/datos"}), "D:\\neb\\datos")

    def test_rutas_derivadas(self):
        d = os.path.join(self.home, ".neb")
        self.assertEqual(np_.config_path(self.home, {}), os.path.join(d, "config.json"))
        self.assertEqual(np_.db_path(self.home, {}), os.path.join(d, "neb.db"))
        self.assertEqual(np_.backups_dir(self.home, {}), os.path.join(d, "backups"))
        self.assertEqual(np_.compas_path(self.home, {}), os.path.join(d, "compas.md"))
        self.assertEqual(np_.approved_plans_dir(self.home, {}), os.path.join(d, "approved-plans"))
        self.assertEqual(np_.research_dir(self.home, {}), os.path.join(d, "research"))
        self.assertEqual(np_.state_dir("preprocess", self.home, {}), os.path.join(d, "state", "preprocess"))
        self.assertEqual(np_.cache_dir("sounds", self.home, {}), os.path.join(d, "cache", "sounds"))
        self.assertEqual(np_.legacy_dir(self.home), os.path.join(self.home, ".claude"))

    def test_named_path(self):
        self.assertEqual(np_.named_path("state/preprocess", self.home, {}), np_.state_dir("preprocess", self.home, {}))
        self.assertEqual(np_.named_path("legacy", self.home, {}), np_.legacy_dir(self.home))
        for bad in ("nada", "state/", "state/../x", "cache/A", "state/a/b"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                np_.named_path(bad, self.home, {})

    def test_no_crea_nada_al_resolver(self):
        np_.db_path(self.home, {})
        np_.load_config(self.home, {})
        self.assertEqual(os.listdir(self.home), [])

    def test_ensure_dir_crea_y_rechaza_enlace(self):
        d = np_.ensure_data_dir(self.home, {})
        self.assertTrue(os.path.isdir(d))
        link = os.path.join(self.home, "enlace")
        try:
            os.symlink(d, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("esta máquina no deja crear enlaces simbólicos")
        with self.assertRaises(ValueError):
            np_.ensure_dir(link)

    def _enlace(self, target, link):
        try:
            os.symlink(target, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            try:
                import _winapi
                _winapi.CreateJunction(target, link)
            except (ImportError, AttributeError, OSError):
                self.skipTest("sin permiso para crear enlaces")

    def test_critico_ensure_dir_con_raiz_rechaza_la_carpeta_de_datos_enlazada(self):
        """Una subcarpeta bajo una carpeta de datos enlazada: con `root`, ValueError y nada escrito en el
        destino del enlace; sin `root`, solo se revisa la carpeta final (contrato anterior)."""
        target = os.path.join(self.home, "destino")
        os.makedirs(target)
        data = os.path.join(self.home, ".neb")
        self._enlace(target, data)
        sub = os.path.join(data, "approved-plans")
        with self.assertRaises(ValueError):
            np_.ensure_dir(sub, root=np_.data_dir(self.home, {}))
        self.assertEqual(os.listdir(target), [])
        np_.ensure_dir(os.path.join(self.home, "otra", "sub"), root=data)   # root no es ancestro: sin error
        self.assertTrue(os.path.isdir(os.path.join(self.home, "otra", "sub")))

    def test_backups_con_neb_data_en_claude_es_neb_backups(self):
        claude = os.path.join(self.home, ".claude")
        self.assertEqual(np_.backups_dir(self.home, {"NEB_DATA": claude}), os.path.join(claude, "neb-backups"))
        self.assertEqual(np_.backups_dir(self.home, {}), os.path.join(self.home, ".neb", "backups"))


class TestLoadConfig(Base):
    def test_sin_nada_da_defaults(self):
        self.assertEqual(self.cfg(), np_.DEFAULTS)

    def test_merge_por_tipo(self):
        self.write(".neb/config.json", json.dumps({
            "notify": {"stop": {"enabled": False, "min_seconds": 30, "max_chimes": "x", "wav": "chimes"},
                       "permission": "no-es-dict"},
            "preprocess": {"mode": "fast", "prefix": 5},
            "language": {"variedad": "rioplatense", "permitir_voseo": True},
            "ajena": 1}))
        cfg = self.cfg()
        self.assertFalse(cfg["notify"]["stop"]["enabled"])
        self.assertEqual(cfg["notify"]["stop"]["min_seconds"], 30)
        self.assertEqual(cfg["notify"]["stop"]["max_chimes"], 5)
        self.assertEqual(cfg["notify"]["stop"]["wav"], "chimes")
        self.assertEqual(cfg["notify"]["permission"], np_.DEFAULTS["notify"]["permission"])
        self.assertEqual(cfg["preprocess"]["mode"], "fast")
        self.assertEqual(cfg["preprocess"]["prefix"], "$$")
        self.assertEqual(cfg["language"]["variedad"], "rioplatense")
        self.assertIs(cfg["language"]["permitir_voseo"], True)
        self.assertNotIn("ajena", cfg)

    def test_bool_no_pasa_por_numero(self):
        self.write(".neb/config.json", json.dumps({"notify": {"stop": {"min_seconds": True, "enabled": 0}}}))
        cfg = self.cfg()
        self.assertEqual(cfg["notify"]["stop"]["min_seconds"], 10)
        self.assertIs(cfg["notify"]["stop"]["enabled"], True)

    def test_bom(self):
        self.write(".neb/config.json", json.dumps({"preprocess": {"mode": "full"}}), encoding="utf-8-sig")
        self.assertEqual(self.cfg()["preprocess"]["mode"], "full")

    def test_ilegible_da_defaults_y_no_cae_a_los_sueltos(self):
        self.write(".neb/config.json", "{no es json")
        self.write(".claude/preprocess.json", json.dumps({"mode": "full"}))
        self.assertEqual(self.cfg(), np_.DEFAULTS)

    def test_sueltos_solo_sin_config(self):
        self.write(".claude/notify-on-stop.json", json.dumps({"enabled": False}))
        self.write(".claude/notify-on-permission.json", json.dumps({"wav": "chimes"}), encoding="utf-8-sig")
        self.write(".claude/preprocess.json", json.dumps({"mode": "fast"}))
        cfg = self.cfg()
        self.assertFalse(cfg["notify"]["stop"]["enabled"])
        self.assertEqual(cfg["notify"]["permission"]["wav"], "chimes")
        self.assertEqual(cfg["preprocess"]["mode"], "fast")
        self.assertEqual(sorted(np_.legacy_config_sources(self.home, self.env)),
                         ["notify-on-permission.json", "notify-on-stop.json", "preprocess.json"])
        self.write(".neb/config.json", "{}")
        self.assertEqual(self.cfg(), np_.DEFAULTS)
        self.assertEqual(np_.legacy_config_sources(self.home, self.env), [])

    def test_section(self):
        self.write(".neb/config.json", json.dumps({"notify": {"stop": {"scaling": "fixed"}}}))
        self.assertEqual(np_.section("notify.stop.scaling", self.home, self.env), "fixed")
        with self.assertRaises(KeyError):
            np_.section("notify.nada", self.home, self.env)

    def test_neb_data_cambia_de_donde_lee(self):
        other = os.path.join(self.home, "otra")
        self.write("otra/config.json", json.dumps({"preprocess": {"mode": "full"}}))
        self.assertEqual(np_.load_config(self.home, {"NEB_DATA": other})["preprocess"]["mode"], "full")


class TestSetValue(Base):
    def read(self):
        with open(np_.config_path(self.home, {}), encoding="utf-8") as f:
            return json.load(f)

    def test_crea_con_schema_y_lo_de_los_sueltos(self):
        self.write(".claude/notify-on-stop.json", json.dumps({"enabled": False, "min_seconds": 40}))
        np_.set_value("preprocess.mode", "fast", self.home, {})
        data = self.read()
        self.assertEqual(data["schema"], 1)
        self.assertEqual(data["preprocess"], {"mode": "fast"})
        self.assertEqual(data["notify"]["stop"], {"enabled": False, "min_seconds": 40})
        self.assertTrue(os.path.exists(os.path.join(self.home, ".claude", "notify-on-stop.json")))

    def test_no_pisa_lo_demas(self):
        self.write(".neb/config.json", json.dumps({"schema": 1, "notify": {"stop": {"wav": "chimes", "extra": 1}},
                                                   "otra": [1]}))
        np_.set_value("notify.stop.min_seconds", 25, self.home, {})
        data = self.read()
        self.assertEqual(data["notify"]["stop"], {"wav": "chimes", "extra": 1, "min_seconds": 25})
        self.assertEqual(data["otra"], [1])

    def test_rechaza_llave_tipo_y_seccion(self):
        for dotted, value in (("preprocess.nada", "x"), ("schema", 2), ("notify.stop", {}),
                              ("preprocess.mode", 3), ("notify.stop.enabled", "false"),
                              ("notify.stop.min_seconds", True)):
            with self.subTest(dotted=dotted), self.assertRaises(ValueError):
                np_.set_value(dotted, value, self.home, {})
        self.assertFalse(os.path.exists(np_.config_path(self.home, {})))

    def test_none_vale_en_llaves_de_texto_opcional(self):
        np_.set_value("language.variedad", "mexico", self.home, {})
        np_.set_value("language.variedad", None, self.home, {})
        self.assertIsNone(self.read()["language"]["variedad"])

    def test_config_ilegible_no_se_pisa(self):
        path = self.write(".neb/config.json", "{roto")
        with self.assertRaises(ValueError):
            np_.set_value("preprocess.mode", "fast", self.home, {})
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "{roto")

    def test_sin_temporales_si_falla_el_replace(self):
        with mock.patch.object(np_.os, "replace", side_effect=OSError("disco")):
            with self.assertRaises(OSError):
                np_.set_value("preprocess.mode", "fast", self.home, {})
        self.assertEqual(os.listdir(np_.data_dir(self.home, {})), [])


class TestCli(Base):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with _entorno.home_en_proceso(self.home), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = np_.main(list(argv))
        return rc, out.getvalue(), err.getvalue()

    def test_path_config_set(self):
        rc, out, _ = self.run_cli("path", "db")
        self.assertEqual((rc, out.strip()), (0, os.path.join(self.home, ".neb", "neb.db")))
        self.assertEqual(self.run_cli("set", "preprocess.mode", '"full"')[0], 0)
        rc, out, _ = self.run_cli("config", "preprocess")
        self.assertEqual((rc, json.loads(out)["mode"]), (0, "full"))

    def test_uso_incorrecto_sale_con_2(self):
        for argv in ((), ("nada",), ("path",), ("path", "nada"), ("set", "preprocess.mode", "{roto"),
                     ("set", "preprocess.mode", "3")):
            with self.subTest(argv=argv):
                self.assertEqual(self.run_cli(*argv)[0], 2)


if __name__ == "__main__":
    unittest.main()
