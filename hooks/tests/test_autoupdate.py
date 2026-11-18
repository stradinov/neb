#!/usr/bin/env python3
"""test_autoupdate.py — actualización automática del plugin: estado y decisión (hooks/lib/autoupdate.py).

Claude Code trae apagada la actualización automática de un marketplace de terceros (supuesto R28); la decide
`autoUpdate` en el settings de usuario y, si ahí falta, en plugins/known_marketplaces.json:
  • marketplace_of: el marketplace y el dir de configuración salen de la ruta en el caché de plugins
  • lookup / state: la tabla de estados, incluido settings `false` con known_marketplaces.json `true`
  • pending_offer: solo hay oferta desde el caché y sin decisión
  • set_auto_update: cambia solo `autoUpdate` (y FORCE_AUTOUPDATE_PLUGINS con DISABLE_AUTOUPDATER, supuesto
    R29); respaldo que no pisa otro; sin cambios no escribe; rechazos sin escribir; BOM, CRLF y sangría
  • la CLI desde un caché simulado: `status` no escribe; `enable` y `disable`; uso; fuera del caché

Framework: unittest (stdlib). Dirs de configuración temporales; nunca toca ~/.claude.
  py -m unittest discover -s hooks/tests -p test_autoupdate.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.abspath(os.path.join(HERE, "..", "lib"))
sys.path.insert(0, LIB)

import autoupdate as au  # noqa: E402

BOM = chr(0xFEFF)
SOURCE = {"source": "github", "repo": "acme/neb"}
BASE = {
    "env": {"NEB_HOOKS": "logbook-sync"},
    "permissions": {"allow": ["Bash(git status)"]},
    "extraKnownMarketplaces": {"neb": {"source": dict(SOURCE)}, "otro": {"source": {"source": "git"}}},
}


class Base(unittest.TestCase):

    def setUp(self):
        self.cfg = tempfile.mkdtemp(prefix="neb-test-cfg-")
        self.addCleanup(shutil.rmtree, self.cfg, True)
        os.makedirs(os.path.join(self.cfg, "plugins"))
        entorno = mock.patch.dict(os.environ)       # la máquina puede traer la variable que mueve el caché
        entorno.start()
        self.addCleanup(entorno.stop)
        os.environ.pop(au.CACHE_DIR_VAR, None)
        os.environ["CLAUDE_CONFIG_DIR"] = self.cfg  # el dir de configuración en uso es el de la prueba
        self.settings =os.path.join(self.cfg, "settings.json")
        self.known = os.path.join(self.cfg, "plugins", "known_marketplaces.json")

    def write(self, path, data, raw=None):
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(raw if raw is not None else json.dumps(data, indent=2) + "\n")

    def load(self, path=None):
        with open(path or self.settings, encoding="utf-8-sig") as f:
            return json.load(f)

    def snapshot(self):
        out = {}
        for root, _, files in os.walk(self.cfg):
            for name in files:
                p = os.path.join(root, name)
                with open(p, "rb") as f:
                    out[os.path.relpath(p, self.cfg)] = f.read()
        return out

    def backups(self):
        return sorted(n for n in os.listdir(self.cfg) if n.startswith("settings.json.bak-neb-"))

    def settings_with(self, value=None, **extra):
        data = json.loads(json.dumps(BASE))
        if value is not None:
            data["extraKnownMarketplaces"]["neb"]["autoUpdate"] = value
        data.update(extra)
        self.write(self.settings, data)
        return data

    def known_with(self, value=None):
        entry = {"source": dict(SOURCE), "installLocation": "x", "lastUpdated": "2026-11-18T00:00:00Z"}
        if value is not None:
            entry["autoUpdate"] = value
        self.write(self.known, {"neb": entry})


class TestMarketplaceOf(Base):

    def test_ruta_en_el_cache(self):
        script = os.path.join(self.cfg, "plugins", "cache", "acme-mkt", "neb", "6.37.0", "hooks", "lib", "autoupdate.py")
        self.assertEqual(au.marketplace_of(script), (os.path.abspath(self.cfg), "acme-mkt"))

    def test_separador_de_windows_y_de_posix(self):
        for sep in ("/", "\\"):
            tail = sep.join(["plugins", "cache", "neb", "neb", "6.37.0", "bootstrap", "x.py"])
            found = au.marketplace_of(self.cfg + sep + tail)
            self.assertIsNotNone(found, sep)
            self.assertEqual(found[1], "neb")

    def test_fuera_del_cache(self):
        self.assertIsNone(au.marketplace_of(os.path.join(self.cfg, "src", "neb", "hooks", "lib", "autoupdate.py")))
        self.assertIsNone(au.marketplace_of(""))
        self.assertIsNone(au.marketplace_of(None))

    def test_cache_sin_plugin_y_version(self):
        self.assertIsNone(au.marketplace_of(os.path.join(self.cfg, "plugins", "cache", "neb", "autoupdate.py")))
        self.assertIsNone(au.marketplace_of(os.path.join(self.cfg, "plugins", "cache", "neb", "neb", "x.py")))

    def test_nombre_fuera_del_patron_no_cuenta(self):
        for name in ("con espacio", "`inyectado`", "a" * 41, "-guion"):
            script = os.path.join(self.cfg, "plugins", "cache", name, "neb", "1.0.0", "x.py")
            self.assertIsNone(au.marketplace_of(script), name)

    def test_cache_anidado_toma_el_ultimo(self):
        inner = os.path.join(self.cfg, "plugins", "cache", "a", "b", "c", "plugins", "cache", "neb", "neb", "1.0.0", "x.py")
        cfg, name = au.marketplace_of(inner)
        self.assertEqual(name, "neb")
        self.assertTrue(cfg.endswith(os.path.join("a", "b", "c")))


class TestEstado(Base):

    def test_sin_la_clave_en_ninguno(self):
        self.settings_with()
        self.known_with()
        self.assertEqual(au.lookup(self.cfg, "neb"), (au.UNDECIDED, None))

    def test_settings_decide(self):
        for value, want in ((True, au.ON), (False, au.OFF)):
            self.settings_with(value)
            self.known_with()
            self.assertEqual(au.lookup(self.cfg, "neb"), (want, "settings.json"))

    def test_settings_manda_sobre_known(self):
        self.settings_with(False)
        self.known_with(True)
        self.assertEqual(au.lookup(self.cfg, "neb"), (au.OFF, "settings.json"))
        self.settings_with(True)
        self.known_with(False)
        self.assertEqual(au.lookup(self.cfg, "neb"), (au.ON, "settings.json"))

    def test_known_decide_si_settings_no_trae_la_clave(self):
        self.settings_with()
        for value, want in ((True, au.ON), (False, au.OFF)):
            self.known_with(value)
            self.assertEqual(au.lookup(self.cfg, "neb"), (want, "known_marketplaces.json"))

    def test_settings_ausente_o_sin_la_entrada(self):
        self.known_with()
        self.assertEqual(au.state(self.cfg, "neb"), au.UNDECIDED)
        self.known_with(True)
        self.assertEqual(au.state(self.cfg, "neb"), au.ON)
        self.write(self.settings, {"env": {}})
        self.assertEqual(au.state(self.cfg, "neb"), au.ON)

    def test_known_ausente(self):
        self.settings_with()
        self.assertEqual(au.state(self.cfg, "neb"), au.UNDECIDED)

    def test_marketplace_que_ningun_archivo_conoce(self):
        self.settings_with()
        self.known_with()
        self.assertEqual(au.state(self.cfg, "desconocido"), au.NA)
        os.remove(self.settings)
        os.remove(self.known)
        self.assertEqual(au.state(self.cfg, "neb"), au.NA)

    def test_archivo_ilegible(self):
        self.known_with()
        self.write(self.settings, None, raw="{ esto no es json")
        self.assertEqual(au.state(self.cfg, "neb"), au.NA)
        self.write(self.settings, None, raw="[1, 2]")
        self.assertEqual(au.state(self.cfg, "neb"), au.NA)
        self.settings_with()
        self.write(self.known, None, raw="{")
        self.assertEqual(au.state(self.cfg, "neb"), au.NA)

    def test_valor_que_no_es_booleano_no_decide(self):
        self.settings_with("true")
        self.known_with()
        self.assertEqual(au.state(self.cfg, "neb"), au.UNDECIDED)
        self.known_with(False)
        self.assertEqual(au.lookup(self.cfg, "neb"), (au.OFF, "known_marketplaces.json"))

    def test_settings_con_bom(self):
        data = self.settings_with(True)
        self.write(self.settings, None, raw=BOM + json.dumps(data))
        self.assertEqual(au.state(self.cfg, "neb"), au.ON)


class TestOferta(Base):

    def script(self, marketplace="neb"):
        return os.path.join(self.cfg, "plugins", "cache", marketplace, "neb", "9.9.9", "bootstrap", "x.py")

    def test_sin_decidir_ofrece(self):
        self.settings_with()
        self.known_with()
        self.assertEqual(au.pending_offer(self.script()), "neb")

    def test_decidido_o_no_aplica_no_ofrece(self):
        self.known_with()
        for value in (True, False):
            self.settings_with(value)
            self.assertIsNone(au.pending_offer(self.script()))
        self.assertIsNone(au.pending_offer(self.script("desconocido")))
        self.assertIsNone(au.pending_offer(os.path.join(self.cfg, "x.py")))

    def test_sin_la_entrada_en_el_settings_no_ofrece(self):
        # Sin decidir, pero `enable` y `disable` rechazarían: la oferta no se podría contestar.
        self.known_with()
        self.assertEqual(au.state(self.cfg, "neb"), au.UNDECIDED)
        self.assertIsNone(au.pending_offer(self.script()))
        self.write(self.settings, {"env": {}, "extraKnownMarketplaces": {"otro": {}}})
        self.assertEqual(au.state(self.cfg, "neb"), au.UNDECIDED)
        self.assertIsNone(au.pending_offer(self.script()))
        for value in (True, False):
            self.assertIsNone(au.set_auto_update(self.cfg, "neb", value, env={})[0])

    def test_cache_fuera_del_dir_de_configuracion_no_ofrece(self):
        # El settings solo se deduce de la ruta si el caché cuelga del dir de configuración en uso.
        # CLAUDE_CODE_PLUGIN_CACHE_DIR fija otra raíz, y puede estar o no en el entorno del proceso.
        self.settings_with()
        self.known_with()
        raiz = os.path.join(self.cfg, "plugins")
        otro = tempfile.mkdtemp(prefix="neb-test-otro-")
        self.addCleanup(shutil.rmtree, otro, True)
        for env in ({"CLAUDE_CONFIG_DIR": self.cfg}, {"CLAUDE_CONFIG_DIR": os.path.join(raiz, "..")},
                    {"CLAUDE_CONFIG_DIR": self.cfg, au.CACHE_DIR_VAR: raiz}):
            self.assertEqual(au.pending_offer(self.script(), env=env), "neb", env)
        for env in ({"CLAUDE_CONFIG_DIR": otro}, {"CLAUDE_CONFIG_DIR": otro, au.CACHE_DIR_VAR: raiz},
                    {"CLAUDE_CONFIG_DIR": otro, au.CACHE_DIR_VAR: ""}, {"CLAUDE_CONFIG_DIR": ""}, {}):
            self.assertIsNone(au.locate(self.script(), env=env), env)
            self.assertIsNone(au.pending_offer(self.script(), env=env), env)

    def test_dir_de_configuracion_en_uso(self):
        self.assertEqual(au.config_dir({"CLAUDE_CONFIG_DIR": self.cfg}), self.cfg)
        por_defecto = os.path.join(os.path.expanduser("~"), ".claude")
        self.assertEqual(au.config_dir({}), por_defecto)
        self.assertEqual(au.config_dir({"CLAUDE_CONFIG_DIR": ""}), por_defecto)

    def test_no_escribe(self):
        self.settings_with()
        self.known_with()
        before = self.snapshot()
        au.pending_offer(self.script())
        au.lookup(self.cfg, "neb")
        self.assertEqual(self.snapshot(), before)

    def test_un_error_no_sale(self):
        with mock.patch.object(au, "state", side_effect=RuntimeError("x")):
            self.assertIsNone(au.pending_offer(self.script()))


class TestDecision(Base):

    def sin_clave(self, data):
        data = json.loads(json.dumps(data))
        data["extraKnownMarketplaces"]["neb"].pop("autoUpdate", None)
        return data

    def test_enable_solo_cambia_la_clave(self):
        before = self.settings_with()
        raw = self.snapshot()["settings.json"]
        changes, backup, error = au.set_auto_update(self.cfg, "neb", True, env={})
        self.assertIsNone(error)
        self.assertEqual([(k, s) for k, s, _ in changes], [("extraKnownMarketplaces", "neb")])
        after = self.load()
        self.assertIs(after["extraKnownMarketplaces"]["neb"]["autoUpdate"], True)
        self.assertEqual(self.sin_clave(after), before)
        self.assertEqual(self.backups(), [os.path.basename(backup)])
        with open(backup, "rb") as f:
            self.assertEqual(f.read(), raw)
        self.assertEqual(au.state(self.cfg, "neb"), au.ON)

    def test_disable_escribe_false_y_no_toca_env(self):
        before = self.settings_with()
        changes, _, error = au.set_auto_update(self.cfg, "neb", False, env={"DISABLE_AUTOUPDATER": "1"})
        self.assertIsNone(error)
        self.assertEqual(len(changes), 1)
        after = self.load()
        self.assertIs(after["extraKnownMarketplaces"]["neb"]["autoUpdate"], False)
        self.assertEqual(self.sin_clave(after), before)
        self.assertEqual(au.state(self.cfg, "neb"), au.OFF)

    def test_disable_no_quita_force(self):
        self.settings_with(True, env={"FORCE_AUTOUPDATE_PLUGINS": "1"})
        au.set_auto_update(self.cfg, "neb", False, env={"DISABLE_AUTOUPDATER": "1"})
        self.assertEqual(self.load()["env"], {"FORCE_AUTOUPDATE_PLUGINS": "1"})

    def test_enable_con_disable_autoupdater_agrega_force(self):
        before = self.settings_with()
        changes, _, error = au.set_auto_update(self.cfg, "neb", True, env={"DISABLE_AUTOUPDATER": "1"})
        self.assertIsNone(error)
        self.assertEqual([(k, s) for k, s, _ in changes],
                         [("extraKnownMarketplaces", "neb"), ("env", "FORCE_AUTOUPDATE_PLUGINS")])
        after = self.load()
        self.assertEqual(after["env"], {"NEB_HOOKS": "logbook-sync", "FORCE_AUTOUPDATE_PLUGINS": "1"})
        after["env"].pop("FORCE_AUTOUPDATE_PLUGINS")
        self.assertEqual(self.sin_clave(after), before)

    def test_enable_sin_disable_autoupdater_no_toca_env(self):
        data = json.loads(json.dumps(BASE))
        del data["env"]
        self.write(self.settings, data)
        for env in ({}, {"DISABLE_AUTOUPDATER": "0"}, {"DISABLE_AUTOUPDATER": ""}):
            au.set_auto_update(self.cfg, "neb", True, env=env)
            self.assertNotIn("env", self.load())

    def test_enable_crea_env_si_falta(self):
        data = json.loads(json.dumps(BASE))
        del data["env"]
        self.write(self.settings, data)
        _, _, error = au.set_auto_update(self.cfg, "neb", True, env={"DISABLE_AUTOUPDATER": "true"})
        self.assertIsNone(error)
        self.assertEqual(self.load()["env"], {"FORCE_AUTOUPDATE_PLUGINS": "1"})

    def test_ya_encendida_completa_force(self):
        self.settings_with(True)
        changes, backup, error = au.set_auto_update(self.cfg, "neb", True, env={"DISABLE_AUTOUPDATER": "1"})
        self.assertIsNone(error)
        self.assertEqual([(k, s) for k, s, _ in changes], [("env", "FORCE_AUTOUPDATE_PLUGINS")])
        self.assertIsNotNone(backup)

    def test_sin_cambios_no_escribe(self):
        for value, env in ((True, {}), (False, {}), (True, {"DISABLE_AUTOUPDATER": "1"})):
            self.settings_with(value, env={"FORCE_AUTOUPDATE_PLUGINS": "1"})
            before = self.snapshot()
            self.assertEqual(au.set_auto_update(self.cfg, "neb", value, env=env), ([], None, None))
            self.assertEqual(self.snapshot(), before)

    def test_sin_cambios_no_reescribe_un_settings_minificado(self):
        data = json.loads(json.dumps(BASE))
        data["extraKnownMarketplaces"]["neb"]["autoUpdate"] = True
        self.write(self.settings, None, raw=json.dumps(data, separators=(",", ":")))
        before = self.snapshot()
        self.assertEqual(au.set_auto_update(self.cfg, "neb", True, env={}), ([], None, None))
        self.assertEqual(self.snapshot(), before)

    def test_respaldo_no_pisa_otro(self):
        self.settings_with()
        first = self.snapshot()["settings.json"]
        with mock.patch.object(au.time, "strftime", return_value="20261118-010203"):
            _, b1, _ = au.set_auto_update(self.cfg, "neb", True, env={})
            second = self.snapshot()["settings.json"]
            _, b2, _ = au.set_auto_update(self.cfg, "neb", False, env={})
        self.assertNotEqual(b1, b2)
        self.assertEqual(self.backups(), ["settings.json.bak-neb-20261118-010203",
                                          "settings.json.bak-neb-20261118-010203-2"])
        snap = self.snapshot()
        self.assertEqual(snap[os.path.basename(b1)], first)
        self.assertEqual(snap[os.path.basename(b2)], second)

    def test_settings_ausente_rechaza(self):
        self.known_with()
        before = self.snapshot()
        changes, backup, error = au.set_auto_update(self.cfg, "neb", True, env={})
        self.assertIsNone(changes)
        self.assertIn("no existe", error)
        self.assertEqual(self.snapshot(), before)

    def test_entrada_ausente_rechaza(self):
        self.write(self.settings, {"env": {}, "extraKnownMarketplaces": {"otro": {}}})
        self.known_with()
        before = self.snapshot()
        for value in (True, False):
            changes, _, error = au.set_auto_update(self.cfg, "neb", value, env={"DISABLE_AUTOUPDATER": "1"})
            self.assertIsNone(changes)
            self.assertIn("no trae la entrada `neb`", error)
        self.assertEqual(self.snapshot(), before)

    def test_settings_ilegible_rechaza(self):
        self.write(self.settings, None, raw="{ roto")
        before = self.snapshot()
        changes, _, error = au.set_auto_update(self.cfg, "neb", True, env={})
        self.assertIsNone(changes)
        self.assertIn("no es un objeto JSON legible", error)
        self.assertEqual(self.snapshot(), before)

    def test_env_que_no_es_objeto_rechaza(self):
        self.settings_with(env="x")
        before = self.snapshot()
        changes, _, error = au.set_auto_update(self.cfg, "neb", True, env={"DISABLE_AUTOUPDATER": "1"})
        self.assertIsNone(changes)
        self.assertIn("`env`", error)
        self.assertEqual(self.snapshot(), before)

    def test_escritura_fallida_no_deja_respaldo(self):
        self.settings_with()
        before = self.snapshot()
        with mock.patch.object(au, "_update_json", return_value=lambda path, mutate: (None, "no se escribió x.")):
            changes, backup, error = au.set_auto_update(self.cfg, "neb", True, env={})
        self.assertIsNone(changes)
        self.assertEqual(error, au.REJECTED + "no se escribió x")
        self.assertEqual(self.snapshot(), before)

    def test_otro_proceso_dejo_el_valor_no_escribe_ni_deja_respaldo(self):
        # Entre la lectura y la escritura otro proceso deja el mismo valor, con otro formato: no se toca.
        self.settings_with()
        real, ajeno = au._backup, {}

        def respaldo_y_carrera(path):
            dest = real(path)
            data = self.load()
            data["extraKnownMarketplaces"]["neb"]["autoUpdate"] = True
            self.write(self.settings, None, raw=json.dumps(data, separators=(",", ":")))
            ajeno["raw"] = self.snapshot()["settings.json"]
            return dest

        with mock.patch.object(au, "_backup", side_effect=respaldo_y_carrera):
            self.assertEqual(au.set_auto_update(self.cfg, "neb", True, env={}), ([], None, None))
        self.assertEqual(self.backups(), [])
        self.assertEqual(self.snapshot()["settings.json"], ajeno["raw"])

    def test_error_al_escribir_tras_la_carrera_no_se_confunde_con_sin_cambios(self):
        self.settings_with()
        with mock.patch.object(au, "_update_json", return_value=lambda path, mutate: (None, "disco lleno")):
            changes, backup, error = au.set_auto_update(self.cfg, "neb", True, env={})
        self.assertIsNone(changes)
        self.assertEqual(error, au.REJECTED + "disco lleno")

    def test_known_ilegible_rechaza(self):
        self.settings_with()
        self.write(self.known, None, raw="{ roto")
        before = self.snapshot()
        for value in (True, False):
            changes, backup, error = au.set_auto_update(self.cfg, "neb", value, env={"DISABLE_AUTOUPDATER": "1"})
            self.assertIsNone(changes)
            self.assertTrue(error.startswith(au.REJECTED), error)
            self.assertIn("known_marketplaces.json no es un objeto JSON legible", error)
        self.assertEqual(self.snapshot(), before)

    def test_los_rechazos_dicen_que_no_se_escribio(self):
        self.known_with()
        self.assertTrue(au.set_auto_update(self.cfg, "neb", True, env={})[2].startswith(au.REJECTED))
        self.write(self.settings, {"env": {}})
        self.assertTrue(au.set_auto_update(self.cfg, "neb", True, env={})[2].startswith(au.REJECTED))
        self.write(self.settings, None, raw="[")
        self.assertTrue(au.set_auto_update(self.cfg, "neb", True, env={})[2].startswith(au.REJECTED))

    def test_entrada_alterada_al_escribir_se_reporta(self):
        self.settings_with()

        def daña(path, mutate):
            data = self.load()
            data["extraKnownMarketplaces"]["neb"] = {"autoUpdate": True}
            self.write(self.settings, data)
            return [("extraKnownMarketplaces", "neb", {})], None

        with mock.patch.object(au, "_update_json", return_value=daña):
            changes, backup, error = au.set_auto_update(self.cfg, "neb", True, env={})
        self.assertIsNone(changes)
        self.assertIn("no quedó como se esperaba", error)
        self.assertEqual(len(self.backups()), 1)
        self.assertIn(self.backups()[0], error)

    def test_conserva_bom_crlf_y_sangria(self):
        data = json.loads(json.dumps(BASE))
        raw = BOM + json.dumps(data, indent=4).replace("\n", "\r\n") + "\r\n"
        self.write(self.settings, None, raw=raw)
        _, _, error = au.set_auto_update(self.cfg, "neb", True, env={"DISABLE_AUTOUPDATER": "1"})
        self.assertIsNone(error)
        with open(self.settings, encoding="utf-8", newline="") as f:
            out = f.read()
        self.assertTrue(out.startswith(BOM))
        self.assertTrue(out.endswith("\r\n"))
        self.assertNotIn("\n", out.replace("\r\n", ""))
        self.assertIn('\r\n    "env": {\r\n        "NEB_HOOKS"', out)
        self.assertIs(self.load()["extraKnownMarketplaces"]["neb"]["autoUpdate"], True)

    def test_otros_marketplaces_intactos(self):
        self.settings_with()
        au.set_auto_update(self.cfg, "neb", True, env={})
        self.assertEqual(self.load()["extraKnownMarketplaces"]["otro"], {"source": {"source": "git"}})


class TestCli(Base):
    """El script como lo corre Claude: desde el caché de plugins, que es de donde saca el marketplace."""

    def setUp(self):
        super().setUp()
        self.lib = os.path.join(self.cfg, "plugins", "cache", "neb", "neb", "9.9.9", "hooks", "lib")
        os.makedirs(self.lib)
        for name in ("autoupdate.py", "usage-tracker.py"):
            shutil.copy(os.path.join(LIB, name), self.lib)
        self.known_with()

    def run_cli(self, *args, script=None, **env):
        e = {k: v for k, v in os.environ.items()
             if k not in ("DISABLE_AUTOUPDATER", "FORCE_AUTOUPDATE_PLUGINS", au.CACHE_DIR_VAR) + au.STRICTER}
        e.update(env)
        e["PYTHONDONTWRITEBYTECODE"] = "1"
        r = subprocess.run([sys.executable, script or os.path.join(self.lib, "autoupdate.py")] + list(args),
                           env=e, capture_output=True, timeout=60)
        return r.returncode, r.stdout.decode("utf-8"), r.stderr.decode("utf-8")

    def test_status_no_escribe(self):
        self.settings_with()
        before = self.snapshot()
        rc, out, err = self.run_cli("status")
        self.assertEqual(rc, 0, err)
        self.assertIn("Marketplace: neb", out)
        self.assertIn("Actualización automática: sin decidir", out)
        self.assertEqual(self.snapshot(), before)

    def test_status_dice_de_donde_sale_y_que_falta(self):
        self.settings_with(True)
        rc, out, _ = self.run_cli("status", DISABLE_AUTOUPDATER="1")
        self.assertEqual(rc, 0)
        self.assertIn("encendida (según settings.json)", out)
        self.assertIn("FORCE_AUTOUPDATE_PLUGINS en `env` del settings: no", out)
        self.assertIn("`enable` la agrega", out)

    def test_status_avisa_de_las_variables_mas_estrictas(self):
        self.settings_with(True)
        rc, out, _ = self.run_cli("status", DISABLE_UPDATES="1")
        self.assertEqual(rc, 0)
        self.assertIn("Con DISABLE_UPDATES la actualización de plugins tampoco corre", out)
        rc, out, _ = self.run_cli("status")
        self.assertNotIn("tampoco corre", out)
        # `enable` no las contrarresta: FORCE solo se agrega con DISABLE_AUTOUPDATER.
        rc, _, _ = self.run_cli("disable")
        rc, _, _ = self.run_cli("enable", DISABLE_UPDATES="1", CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1")
        self.assertEqual(rc, 0)
        self.assertNotIn("FORCE_AUTOUPDATE_PLUGINS", self.load().get("env", {}))

    def test_enable_y_disable(self):
        before = self.settings_with()
        rc, out, err = self.run_cli("enable", DISABLE_AUTOUPDATER="1")
        self.assertEqual(rc, 0, err)
        self.assertIn("`extraKnownMarketplaces.neb.autoUpdate` = true", out)
        self.assertIn('`env.FORCE_AUTOUPDATE_PLUGINS` = "1"', out)
        self.assertIn("Respaldo: ", out)
        after = self.load()
        self.assertIs(after["extraKnownMarketplaces"]["neb"]["autoUpdate"], True)
        self.assertEqual(after["env"]["FORCE_AUTOUPDATE_PLUGINS"], "1")
        self.assertEqual(after["permissions"], before["permissions"])

        rc, out, _ = self.run_cli("enable", DISABLE_AUTOUPDATER="1")
        self.assertEqual(rc, 0)
        self.assertIn("Sin cambios", out)
        self.assertEqual(len(self.backups()), 1)

        rc, out, _ = self.run_cli("disable")
        self.assertEqual(rc, 0)
        self.assertIn("`extraKnownMarketplaces.neb.autoUpdate` = false", out)
        self.assertIs(self.load()["extraKnownMarketplaces"]["neb"]["autoUpdate"], False)
        self.assertEqual(len(self.backups()), 2)

    def test_sin_entrada_rechaza_y_dice_como_hacerlo_a_mano(self):
        self.write(self.settings, {"env": {}})
        before = self.snapshot()
        rc, out, _ = self.run_cli("enable")
        self.assertEqual(rc, 1)
        self.assertIn("No se escribió nada: ", out)
        self.assertIn('"neb": { "source": {"source": "github", "repo": "acme/neb"}, "autoUpdate": true }', out)
        self.assertEqual(self.snapshot(), before)
        rc, out, _ = self.run_cli("disable")
        self.assertEqual(rc, 1)
        self.assertIn('"autoUpdate": false }', out)
        rc, out, _ = self.run_cli("status")
        self.assertEqual(rc, 0)
        self.assertIn("El settings no trae la entrada del marketplace", out)
        self.assertEqual(self.snapshot(), before)

    def test_settings_ilegible_no_propone_agregar_la_entrada(self):
        # El settings trae la entrada pero no parsea: agregar el bloque la duplicaría.
        self.write(self.settings, None,
                   raw='{"extraKnownMarketplaces": {"neb": {"source": {"source": "github"}},}}')
        before = self.snapshot()
        rc, out, _ = self.run_cli("enable")
        self.assertEqual(rc, 1)
        self.assertIn("no es un objeto JSON legible", out)
        self.assertIn("corrige primero el JSON", out)
        self.assertNotIn("agrega a", out)
        self.assertEqual(self.snapshot(), before)

    def otro_cache(self, *raiz):
        """Otra copia del script en <cfg>/<raiz>/cache/…, con un settings y un known_marketplaces.json completos
        junto a esa raíz: los que el script tomaría si dedujera el settings de su ruta."""
        base = os.path.join(self.cfg, *raiz)
        lib = os.path.join(base, "cache", "neb", "neb", "9.9.9", "hooks", "lib")
        os.makedirs(lib)
        for name in ("autoupdate.py", "usage-tracker.py"):
            shutil.copy(os.path.join(LIB, name), lib)
        ajeno = os.path.join(os.path.dirname(base), "settings.json")
        with open(self.settings, encoding="utf-8") as f:
            self.write(ajeno, json.load(f))
        shutil.copy(self.known, os.path.join(base, "known_marketplaces.json"))
        return base, os.path.join(lib, "autoupdate.py"), ajeno

    def test_cache_fuera_del_dir_de_configuracion_no_escribe(self):
        # El caché en otra raíz (CLAUDE_CODE_PLUGIN_CACHE_DIR): el script no toca el settings que saldría de su
        # ruta, que Claude Code no lee. Con la variable en el entorno tampoco nombra el dir de esa ruta; sin
        # ella o vacía no distingue el caso de otro CLAUDE_CONFIG_DIR, y nombra el dir sin el settings.
        self.settings_with()
        casos = []
        for raiz in (("data", "plugins"), ("disco", "raiz")):
            base, script, ajeno = self.otro_cache(*raiz)
            casos += [(script, ajeno, {"CLAUDE_CODE_PLUGIN_CACHE_DIR": base})]
            if raiz[-1] == "plugins":           # sin la variable, solo esta ruta parece un caché
                casos += [(script, ajeno, {}), (script, ajeno, {"CLAUDE_CODE_PLUGIN_CACHE_DIR": ""})]
        before = self.snapshot()
        for script, ajeno, extra in casos:
            for action, esperado in (("status", 0), ("enable", 1), ("disable", 1)):
                rc, out, _ = self.run_cli(action, script=script, DISABLE_AUTOUPDATER="1", **extra)
                self.assertEqual(rc, esperado, (action, extra))
                self.assertIn("decídelo a mano", out)
                self.assertNotIn(ajeno, out)
                if extra.get("CLAUDE_CODE_PLUGIN_CACHE_DIR"):
                    self.assertIn("la raíz que fija CLAUDE_CODE_PLUGIN_CACHE_DIR", out)
                    self.assertNotIn(os.path.dirname(ajeno), out)
                    self.assertIn("Si esa raíz es la `plugins` de tu dir de configuración, corre este comando con "
                                  "el mismo CLAUDE_CONFIG_DIR que tu sesión de Claude Code, o sin él si tu sesión "
                                  "no lo usa. Si no, decídelo a mano", out)
                else:
                    self.assertIn("caché de plugins de %s, que no es el dir de configuración de este proceso (%s)"
                                  % (os.path.dirname(ajeno), self.cfg), out)
        self.assertEqual(self.snapshot(), before)

    def test_otro_dir_de_configuracion_en_la_terminal_lo_dice(self):
        # El caché de siempre, pero el proceso trae otro CLAUDE_CONFIG_DIR que la sesión (o ninguno): no escribe,
        # nombra los dos dirs y dice que se corra con el mismo CLAUDE_CONFIG_DIR que la sesión, o sin él.
        self.settings_with()
        otro = tempfile.mkdtemp(prefix="neb-test-otro-")
        self.addCleanup(shutil.rmtree, otro, True)
        before = self.snapshot()
        for valor, mostrado in ((otro, otro), ("", os.path.join(os.path.expanduser("~"), ".claude"))):
            for action, esperado in (("status", 0), ("enable", 1), ("disable", 1)):
                rc, out, _ = self.run_cli(action, CLAUDE_CONFIG_DIR=valor)
                self.assertEqual(rc, esperado, (action, valor))
                self.assertIn("caché de plugins de %s, que no es el dir de configuración de este proceso (%s)"
                              % (self.cfg, mostrado), out)
                self.assertIn("con el mismo CLAUDE_CONFIG_DIR que tu sesión de Claude Code, o sin él si tu sesión "
                              "no lo usa. Si ya es así, decídelo a mano", out)
                # Con la variable del caché apuntando a la raíz de siempre no se distingue de una raíz movida:
                # la pista de CLAUDE_CONFIG_DIR sale igual, sin nombrar el dir de la ruta.
                rc, out, _ = self.run_cli(action, CLAUDE_CONFIG_DIR=valor,
                                          CLAUDE_CODE_PLUGIN_CACHE_DIR=os.path.join(self.cfg, "plugins"))
                self.assertEqual(rc, esperado, (action, valor))
                self.assertIn("corre este comando con el mismo CLAUDE_CONFIG_DIR que tu sesión", out)
                self.assertNotIn(self.cfg, out)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(os.listdir(otro), [])

    def test_cache_movido_dentro_del_dir_de_configuracion_funciona(self):
        # La variable apunta a la raíz de siempre: el dir que sale de la ruta es el que está en uso.
        self.settings_with()
        rc, out, _ = self.run_cli("enable", CLAUDE_CODE_PLUGIN_CACHE_DIR=os.path.join(self.cfg, "plugins"))
        self.assertEqual(rc, 0, out)
        self.assertIs(self.load()["extraKnownMarketplaces"]["neb"]["autoUpdate"], True)

    def test_settings_ilegible_sin_la_entrada_dice_como_seguir(self):
        self.write(self.settings, None, raw='{"env": {},}')
        rc, out, _ = self.run_cli("enable")
        self.assertEqual(rc, 1)
        self.assertIn("corrige primero el JSON", out)
        self.assertIn("Si la entrada no está, corre de nuevo este comando", out)

    def test_con_entrada_el_rechazo_apunta_a_la_clave(self):
        self.settings_with(env="x")
        rc, out, _ = self.run_cli("enable", DISABLE_AUTOUPDATER="1")
        self.assertEqual(rc, 1)
        self.assertIn("No se escribió nada: ", out)
        self.assertIn('pon `"autoUpdate": true` en la entrada `neb`', out)

    def test_uso(self):
        self.settings_with()
        before = self.snapshot()
        for args in ((), ("otra",), ("enable", "disable")):
            rc, _, err = self.run_cli(*args)
            self.assertEqual(rc, 2, args)
            self.assertIn("uso:", err)
        self.assertEqual(self.snapshot(), before)

    def test_fuera_del_cache(self):
        script = os.path.join(LIB, "autoupdate.py")
        if au.marketplace_of(script):
            self.skipTest("el repo vive dentro de un caché de plugins")
        rc, out, _ = self.run_cli("status", script=script)
        self.assertEqual(rc, 0)
        self.assertIn("no corre desde el caché", out)
        rc, _, _ = self.run_cli("enable", script=script)
        self.assertEqual(rc, 1)
        # Con la variable del caché puesta y el script fuera de ese caché, el mensaje sigue siendo este.
        rc, out, _ = self.run_cli("status", script=script,
                                  CLAUDE_CODE_PLUGIN_CACHE_DIR=os.path.join(self.cfg, "otra"))
        self.assertIn("no corre desde el caché", out)
        self.assertNotIn("a mano", out)
        # Tampoco cuenta como caché un script bajo la raíz que fija la variable pero fuera de su `cache/`.
        rc, out, _ = self.run_cli("status", script=script, CLAUDE_CODE_PLUGIN_CACHE_DIR=os.path.dirname(LIB))
        self.assertIn("no corre desde el caché", out)


if __name__ == "__main__":
    unittest.main()
