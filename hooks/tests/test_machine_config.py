#!/usr/bin/env python3
"""
test_machine_config.py — catálogo de operaciones de los pasos guiados (hooks/lib/_machine.py, 6.49.0).

  • settings_env_remove: el respaldo trae solo los pares quitados; el resto del archivo intacto; sin la clave
    no escribe; con una clave secreta o credenciales en la URL (cualquier forma), ningún respaldo y pide al
    dev; si el archivo cambia entre la lectura y la escritura, no escribe; la poda no borra respaldos de la
    misma corrida; el settings sale del dir de configuración (CLAUDE_CONFIG_DIR); argumentos validados;
  • user_env_remove contra un registro inyectable (nunca el real): patrón de nombre (también con salto de
    línea al final), el valor nunca en la salida, máquina y fuera de Windows responden `manual`.

Homes temporales; nunca ~/.claude ni el registro real.
  py -m unittest discover -s hooks/tests -p test_machine_config.py
"""

import glob
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
NEB = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(NEB, "hooks", "lib"))

import _machine

SECRET = "valor-secreto-9f3a"


class FakeUserEnv:
    """Registro de variables en memoria. Guarda valores para comprobar que nunca salen."""

    def __init__(self, kind="windows", user=None, machine=None, delete_fails=False, sticky=False):
        self.kind = kind
        self.user = dict(user or {})
        self.machine = dict(machine or {})
        self.delete_fails, self.sticky = delete_fails, sticky
        self.deleted, self.broadcasts = [], 0

    def present_user(self, name):
        return name in self.user

    def present_machine(self, name):
        return name in self.machine

    def delete_user(self, name):
        if self.delete_fails:
            raise OSError(5, "Acceso denegado")
        self.deleted.append(name)
        if not self.sticky:
            del self.user[name]

    def broadcast(self):
        self.broadcasts += 1


class Base(unittest.TestCase):

    def setUp(self):
        p = mock.patch.dict(os.environ)
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop("CLAUDE_CONFIG_DIR", None)
        self.home = tempfile.mkdtemp(prefix="neb-test-machine-")
        self.addCleanup(shutil.rmtree, self.home, True)
        self.claude = os.path.join(self.home, ".claude")
        os.makedirs(self.claude)
        self.settings = os.path.join(self.claude, "settings.json")
        self.env = FakeUserEnv()
        self.ctx = _machine.Ctx(self.home, user_env=self.env)

    def put(self, data, path=None):
        with open(path or self.settings, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

    def load(self, path=None):
        with open(path or self.settings, encoding="utf-8") as fh:
            return json.load(fh)

    def backups(self):
        return glob.glob(os.path.join(self.ctx.backups_dir, "settings-env.*.json"))


class TestSettingsEnvRemove(Base):

    def settings_data(self):
        return {"model": "x", "env": {"NEB_PRUEBA_A": "uno", "OTRA": "se-queda", "NEB_PRUEBA_TOKEN": SECRET},
                "enabledPlugins": {"p@m": True}}

    def test_respaldo_trae_solo_los_pares_quitados_y_el_resto_queda(self):
        self.put(self.settings_data())
        self.assertTrue(_machine.settings_env_detect(self.ctx, ["NEB_PRUEBA_A"]))
        self.assertEqual(_machine.settings_env_mode(self.ctx, ["NEB_PRUEBA_A"]), "solo")
        r = _machine.settings_env_apply(self.ctx, ["NEB_PRUEBA_A"])
        self.assertEqual(r["estado"], "aplicado")
        with open(r["respaldo"], encoding="utf-8") as fh:
            backup = json.load(fh)
        self.assertEqual(backup["env"], {"NEB_PRUEBA_A": "uno"})
        self.assertNotIn(SECRET, json.dumps(backup))
        want = self.settings_data()
        del want["env"]["NEB_PRUEBA_A"]
        self.assertEqual(self.load(), want)
        self.assertFalse(_machine.settings_env_detect(self.ctx, ["NEB_PRUEBA_A"]))

    def test_poda_conserva_los_respaldos_de_la_corrida_y_borra_los_viejos(self):
        self.put({"env": {"NEB_PRUEBA_A": "uno", "NEB_PRUEBA_B": "dos"}})
        r1 = _machine.settings_env_apply(self.ctx, ["NEB_PRUEBA_A"])
        r2 = _machine.settings_env_apply(self.ctx, ["NEB_PRUEBA_B"])           # misma corrida
        self.assertTrue(os.path.isfile(r1["respaldo"]) and os.path.isfile(r2["respaldo"]))
        past = self.ctx.started - 3600
        os.utime(r1["respaldo"], (past, past))
        os.utime(r2["respaldo"], (past, past))
        self.put({"env": {"NEB_PRUEBA_A": "tres"}})
        r3 = _machine.settings_env_apply(_machine.Ctx(self.home, user_env=self.env), ["NEB_PRUEBA_A"])
        self.assertEqual(self.backups(), [r3["respaldo"]])

    def test_sin_la_clave_no_escribe(self):
        self.put({"env": {"OTRA": "x"}})
        before = os.path.getmtime(self.settings)
        with open(self.settings, "rb") as fh:
            raw = fh.read()
        self.assertFalse(_machine.settings_env_detect(self.ctx, ["NEB_PRUEBA_A"]))
        r = _machine.settings_env_apply(self.ctx, ["NEB_PRUEBA_A"])
        self.assertEqual(r["estado"], "sin-cambio")
        with open(self.settings, "rb") as fh:
            self.assertEqual(fh.read(), raw)
        self.assertEqual(os.path.getmtime(self.settings), before)
        self.assertEqual(self.backups(), [])

    def test_sin_settings_no_hay_nada_que_hacer(self):
        self.assertFalse(_machine.settings_env_detect(self.ctx, ["NEB_PRUEBA_A"]))
        self.assertFalse(os.path.exists(self.settings))

    def test_clave_secreta_sin_respaldo_y_pide_al_dev(self):
        self.put(self.settings_data())
        claves, secretas = ["NEB_PRUEBA_A", "NEB_PRUEBA_TOKEN"], ["NEB_PRUEBA_TOKEN"]
        self.assertEqual(_machine.settings_env_mode(self.ctx, claves, secretas), "dev")
        r = _machine.settings_env_apply(self.ctx, claves, secretas)            # sin la respuesta del dev
        self.assertEqual(r["estado"], "fallo")
        self.assertEqual(self.load(), self.settings_data())
        r = _machine.settings_env_apply(self.ctx, claves, secretas, allow_no_backup=True)
        self.assertEqual(r["estado"], "aplicado")
        self.assertIsNone(r["respaldo"])
        self.assertEqual(self.backups(), [])
        self.assertNotIn(SECRET, json.dumps(r))
        self.assertEqual(self.load()["env"], {"OTRA": "se-queda"})

    def test_solo_el_endpoint_presente_corre_solo(self):
        self.put({"env": {"NEB_PRUEBA_A": "https://ejemplo.test/api"}})
        self.assertEqual(_machine.settings_env_mode(self.ctx, ["NEB_PRUEBA_A", "NEB_PRUEBA_TOKEN"],
                                                    ["NEB_PRUEBA_TOKEN"]), "solo")

    def test_url_con_credenciales_pide_al_dev_en_cualquier_forma(self):
        for url in ("https://usuario:" + SECRET + "@ejemplo.test/api", "https://" + SECRET + "@ejemplo.test",
                    "https://:" + SECRET + "@ejemplo.test", "https://u:" + SECRET + "/x@ejemplo.test"):
            self.put({"env": {"NEB_PRUEBA_A": url}})
            self.assertEqual(_machine.settings_env_mode(self.ctx, ["NEB_PRUEBA_A"]), "dev", url)
            r = _machine.settings_env_apply(self.ctx, ["NEB_PRUEBA_A"])        # sin la respuesta del dev
            self.assertEqual(r["estado"], "fallo", url)
            r = _machine.settings_env_apply(self.ctx, ["NEB_PRUEBA_A"], allow_no_backup=True)
            self.assertEqual(r["estado"], "aplicado", url)
            self.assertNotIn(SECRET, json.dumps(r))
        self.assertEqual(self.backups(), [])

    def test_nombre_de_secreto_o_url_con_consulta_pide_al_dev_sin_marcarlo(self):
        # Un olvido en `secretas` no deja el valor copiado en neb-backups/.
        for env in ({"NEB_PRUEBA_WEBHOOK": SECRET}, {"NEB_PRUEBA_API_KEY": SECRET},
                    {"NEB_PRUEBA_A": "https://ejemplo.test/api?token=" + SECRET},
                    {"NEB_PRUEBA_A": "https://hooks.ejemplo.test/services/T/B#" + SECRET}):
            self.put({"env": env})
            claves = list(env)
            self.assertEqual(_machine.settings_env_mode(self.ctx, claves), "dev", env)
            r = _machine.settings_env_apply(self.ctx, claves)                  # sin la respuesta del dev
            self.assertEqual(r["estado"], "fallo", env)
            self.assertEqual(self.load(), {"env": env})
        self.assertEqual(self.backups(), [])

    def test_settings_invalido_es_fallo_y_no_se_toca(self):
        with open(self.settings, "w", encoding="utf-8") as fh:
            fh.write("{roto " + SECRET)
        r = _machine.settings_env_apply(self.ctx, ["NEB_PRUEBA_A"])
        self.assertEqual(r["estado"], "fallo")
        self.assertNotIn(SECRET, json.dumps(r))
        with open(self.settings, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "{roto " + SECRET)

    def test_settings_local(self):
        local = os.path.join(self.claude, "settings.local.json")
        self.put({"env": {"NEB_PRUEBA_A": "x"}}, local)
        r = _machine.settings_env_apply(self.ctx, ["NEB_PRUEBA_A"], ruta="settings.local.json")
        self.assertEqual(r["estado"], "aplicado")
        self.assertEqual(self.load(local), {"env": {}})

    def test_settings_del_dir_de_configuracion(self):
        config = tempfile.mkdtemp(prefix="neb-test-config-")
        self.addCleanup(shutil.rmtree, config, True)
        os.environ["CLAUDE_CONFIG_DIR"] = config
        ctx = _machine.Ctx(self.home, user_env=self.env)
        self.put({"env": {"NEB_PRUEBA_A": "home"}})                          # ~/.claude: no es el que se usa
        live = os.path.join(config, "settings.json")
        self.put({"env": {"NEB_PRUEBA_A": "config", "OTRA": "y"}}, live)
        r = _machine.settings_env_apply(ctx, ["NEB_PRUEBA_A"])
        self.assertEqual(r["estado"], "aplicado")
        self.assertEqual(self.load(live), {"env": {"OTRA": "y"}})
        self.assertEqual(self.load(), {"env": {"NEB_PRUEBA_A": "home"}})
        self.assertTrue(r["respaldo"].startswith(os.path.join(self.claude, "neb-backups")))

    def test_cambio_entre_lectura_y_escritura_no_escribe(self):
        self.put({"env": {"NEB_PRUEBA_A": "uno"}})
        real_backup = _machine._write_settings_backup

        def backup_y_otro_proceso_escribe(ctx, settings, pairs):
            dest = real_backup(ctx, settings, pairs)
            self.put({"env": {"NEB_PRUEBA_A": SECRET}})                        # otro proceso cambia el valor
            return dest
        with mock.patch.object(_machine, "_write_settings_backup", backup_y_otro_proceso_escribe):
            r = _machine.settings_env_apply(self.ctx, ["NEB_PRUEBA_A"])
        self.assertEqual(r["estado"], "fallo")
        self.assertIn("cambió", r["detalle"])
        self.assertEqual(self.load(), {"env": {"NEB_PRUEBA_A": SECRET}})
        self.assertEqual(self.backups(), [])                                   # el respaldo de esa corrida se borró

    def test_respaldo_en_carpeta_enlazada_no_se_escribe(self):
        target = tempfile.mkdtemp(prefix="neb-test-afuera-")
        self.addCleanup(shutil.rmtree, target, True)
        try:
            os.symlink(target, self.ctx.backups_dir, target_is_directory=True)
        except (OSError, NotImplementedError):
            try:
                import _winapi                                         # junction: no pide permisos en Windows
                _winapi.CreateJunction(target, self.ctx.backups_dir)
            except (ImportError, OSError, AttributeError):
                self.skipTest("sin enlaces simbólicos ni junctions")
        self.put({"env": {"NEB_PRUEBA_A": "uno"}})
        r = _machine.settings_env_apply(self.ctx, ["NEB_PRUEBA_A"])
        self.assertEqual(r["estado"], "fallo")
        self.assertEqual(os.listdir(target), [])
        self.assertEqual(self.load(), {"env": {"NEB_PRUEBA_A": "uno"}})

    def test_argumentos_validados(self):
        v = _machine.settings_env_validate
        v(["NEB_A"], ["NEB_A"], "settings.local.json")
        for bad in ((), ([],), (["NEB A"],), ("NEB_A",), (["NEB_A"], ["OTRA"]),
                    (["NEB_A"], (), "/etc/passwd"), (["NEB_A"], (), "../settings.json"), (["NEB_A"], (), "x.json")):
            with self.assertRaises((ValueError, TypeError), msg=repr(bad)):
                v(*bad)
        _machine.user_env_validate("NEB_PRUEBA_X")
        for bad in ("PATH", "NEB_X\n", None):
            with self.assertRaises(ValueError):
                _machine.user_env_validate(bad)


class TestUserEnvRemove(Base):

    def test_quita_la_variable_sin_imprimir_su_valor(self):
        self.env.user["NEB_PRUEBA_X"] = SECRET
        self.assertTrue(_machine.user_env_detect(self.ctx, "NEB_PRUEBA_X"))
        self.assertEqual(_machine.user_env_mode(self.ctx, "NEB_PRUEBA_X"), "dev")
        r = _machine.user_env_apply(self.ctx, "NEB_PRUEBA_X", allow_no_backup=True)
        self.assertEqual(r["estado"], "aplicado")
        self.assertEqual(self.env.deleted, ["NEB_PRUEBA_X"])
        self.assertEqual(self.env.broadcasts, 1)
        self.assertNotIn(SECRET, json.dumps(r))
        self.assertFalse(_machine.user_env_detect(self.ctx, "NEB_PRUEBA_X"))

    def test_sin_la_respuesta_del_dev_no_borra(self):
        self.env.user["NEB_PRUEBA_X"] = SECRET
        r = _machine.user_env_apply(self.ctx, "NEB_PRUEBA_X")
        self.assertEqual(r["estado"], "fallo")
        self.assertEqual(self.env.deleted, [])

    def test_nombre_fuera_del_patron_se_rechaza(self):
        for name in ("PATH", "neb_prueba", "NEB_", "NEB_PRUEBA_X\n", "NEB_PRUEBA X", "XNEB_A", None):
            self.env.user[str(name)] = SECRET
            self.assertFalse(_machine.user_env_detect(self.ctx, name), repr(name))
            r = _machine.user_env_apply(self.ctx, name, allow_no_backup=True)
            self.assertEqual(r["estado"], "fallo", repr(name))
        self.assertEqual(self.env.deleted, [])

    def test_variable_de_maquina_es_manual(self):
        self.env.machine["NEB_PRUEBA_X"] = SECRET
        self.assertTrue(_machine.user_env_detect(self.ctx, "NEB_PRUEBA_X"))
        r = _machine.user_env_apply(self.ctx, "NEB_PRUEBA_X", allow_no_backup=True)
        self.assertEqual(r["estado"], "manual")
        self.assertIn("No aplicarlo", r["detalle"])
        self.assertEqual(self.env.deleted, [])
        self.assertNotIn(SECRET, json.dumps(r))

    def test_fuera_de_windows_es_manual(self):
        env = FakeUserEnv(kind="posix", user={"NEB_PRUEBA_X": SECRET})
        ctx = _machine.Ctx(self.home, user_env=env)
        r = _machine.user_env_apply(ctx, "NEB_PRUEBA_X", allow_no_backup=True)
        self.assertEqual(r["estado"], "manual")
        self.assertEqual(env.deleted, [])

    def test_fuera_de_windows_lo_del_settings_no_cuenta_como_variable_de_usuario(self):
        env = FakeUserEnv(kind="posix", user={"NEB_PRUEBA_X": SECRET})
        ctx = _machine.Ctx(self.home, user_env=env)
        self.assertTrue(_machine.user_env_detect(ctx, "NEB_PRUEBA_X"))
        self.put({"env": {"NEB_PRUEBA_X": SECRET}})
        self.assertFalse(_machine.user_env_detect(ctx, "NEB_PRUEBA_X"))

    def test_fuera_de_windows_lo_del_settings_local_tampoco_cuenta(self):
        env = FakeUserEnv(kind="posix", user={"NEB_PRUEBA_X": SECRET})
        ctx = _machine.Ctx(self.home, user_env=env)
        self.put({"env": {"NEB_PRUEBA_X": SECRET}}, os.path.join(self.claude, "settings.local.json"))
        self.assertFalse(_machine.user_env_detect(ctx, "NEB_PRUEBA_X"))

    def test_quitada_por_otra_sesion_antes_del_borrado_es_sin_cambio(self):
        class Gone(FakeUserEnv):
            def delete_user(self, name):
                del self.user[name]
                raise FileNotFoundError(2, "no está")
        env = Gone(user={"NEB_PRUEBA_X": SECRET})
        r = _machine.user_env_apply(_machine.Ctx(self.home, user_env=env), "NEB_PRUEBA_X", allow_no_backup=True)
        self.assertEqual(r["estado"], "sin-cambio")

    def test_ausente_es_sin_cambio(self):
        r = _machine.user_env_apply(self.ctx, "NEB_PRUEBA_X", allow_no_backup=True)
        self.assertEqual(r["estado"], "sin-cambio")

    def test_borrado_que_falla_o_no_surte_efecto_es_fallo(self):
        for env in (FakeUserEnv(user={"NEB_PRUEBA_X": SECRET}, delete_fails=True),
                    FakeUserEnv(user={"NEB_PRUEBA_X": SECRET}, sticky=True)):
            r = _machine.user_env_apply(_machine.Ctx(self.home, user_env=env), "NEB_PRUEBA_X",
                                        allow_no_backup=True)
            self.assertEqual(r["estado"], "fallo")
            self.assertNotIn(SECRET, json.dumps(r))

    def test_exclusivo_comprueba_antes_de_borrar(self):
        self.env.user["NEB_PRUEBA_X"] = SECRET
        self.ctx.exclusivo_ok = lambda: "otra sesión abrió la base"
        r = _machine.user_env_apply(self.ctx, "NEB_PRUEBA_X", allow_no_backup=True)
        self.assertEqual(r["estado"], "pendiente")
        self.assertEqual(self.env.deleted, [])


class TestCatalogo(unittest.TestCase):

    def test_operaciones_registradas(self):
        self.assertEqual(sorted(_machine.OPS), ["settings_env_remove", "user_env_remove"])

    def test_posix_no_borra_por_programa(self):
        env = _machine.PosixUserEnv()
        with self.assertRaises(OSError):
            env.delete_user("NEB_PRUEBA_X")


if __name__ == "__main__":
    unittest.main()
