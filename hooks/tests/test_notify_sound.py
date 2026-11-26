#!/usr/bin/env python3
"""test_notify_sound.py — el sonido de notify-on-stop / notify-on-permission (hooks/lib/notify_sound.py, 7.2.0;
config en la carpeta de datos desde 8.0.0).

  • resolve(): cada valor de `wav` (null, ausente, "neb", "chimes", "chimes-loud", ruta absoluta, basura,
    no cadena) en Windows y en POSIX (simulado); `enabled: false`; JSON con BOM; falta el sonido por defecto
  • de dónde sale la config: sección notify.* de <datos>/config.json; config.json gana sobre los JSON
    sueltos de ~/.claude; sin config.json se leen los sueltos; NEB_DATA mueve config y caché
  • la versión fuerte: pico LOUD_PEAK, mismo formato y frames, caché reutilizada y regenerada por mtime,
    escritura atómica (sin temporales ni caché a medias si falla), fuente que no es PCM 16 o en silencio
  • generate=False (el arranque) no crea <datos>/cache/sounds/
  • effective(): valores normalizados (min_seconds, max_chimes, scaling); hook_env() y config_lines()
  • player_available() y diagnose(): frases del aviso del arranque; carga por ruta como la hace el arranque
  • la CLI `<hook>` y `config <hook>` que usan los .ps1/.sh invocados directo
  • los scripts: el .sh con un reproductor falso y el .ps1 con Start-Process sustituido (no suena nada)
  • el WAV versionado (hooks/sounds/neb-chime.wav) es PCM de 16 bit legible

Framework: unittest (stdlib). HOME, WINDIR y WAV temporales, sin NEB_DATA (_entorno); nunca toca ~/.claude
ni ~/.neb reales.
  py -m unittest discover -s hooks/tests -p test_notify_sound.py
"""
import array
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import wave
from datetime import datetime, timedelta, timezone
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.abspath(os.path.join(HERE, "..", "lib"))
HOOKS_DIR = os.path.dirname(LIB)
sys.path.insert(0, HERE)
sys.path.insert(0, LIB)
import _entorno  # noqa: E402 — quita NEB_DATA del entorno antes de todo
import neb_paths  # noqa: E402
import notify_sound as ns  # noqa: E402
from test_neb_root import BASH  # noqa: E402 — Git Bash en Windows, nunca el bash de WSL

HOOK = "notify-on-stop"
POWERSHELL = shutil.which("powershell") if os.name == "nt" else None


def write_wav(path, samples, sampwidth=2, channels=2, rate=44100):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sampwidth)
        w.setframerate(rate)
        if sampwidth == 2:
            w.writeframes(array.array("h", samples).tobytes())
        else:
            w.writeframes(bytes(samples))


def read_wav(path):
    with wave.open(path, "rb") as w:
        p = w.getparams()
        a = array.array("h")
        a.frombytes(w.readframes(p.nframes))
    return p, a


def write_config(folder, hook, data, bom=False):
    """La sección del hook en <folder>/config.json (texto crudo si `data` es str)."""
    os.makedirs(folder, exist_ok=True)
    if not isinstance(data, str):
        key = ns.SECTIONS[hook].split(".")[1]
        data = json.dumps({"schema": 1, "notify": {key: data}})
    with open(os.path.join(folder, "config.json"), "w", encoding="utf-8-sig" if bom else "utf-8") as f:
        f.write(data)


def write_legacy(home, hook, data):
    """El JSON suelto de antes de 8.0.0: ~/.claude/<hook>.json."""
    os.makedirs(os.path.join(home, ".claude"), exist_ok=True)
    with open(os.path.join(home, ".claude", "%s.json" % hook), "w", encoding="utf-8") as f:
        f.write(json.dumps(data))


class Base(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="neb-test-sound-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(os.path.join(self.home, ".claude"))
        self.data = os.path.join(self.home, ".neb")
        self.default = os.path.join(self.tmp, "neb", "hooks", "sounds", "neb-chime.wav")
        write_wav(self.default, [0, 1000, -1000, 0], channels=1)
        self.windir = os.path.join(self.tmp, "Windows")
        self.chimes = os.path.join(self.windir, "Media", "chimes.wav")
        self.env = {"WINDIR": self.windir, "PATH": ""}
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(mock.patch.object(ns, "DEFAULT_WAV", self.default))
        self.stack = stack

    def os_(self, windows):
        self.stack.enter_context(mock.patch.object(ns, "IS_WINDOWS", windows))

    def cfg(self, data, bom=False, hook=HOOK, data_dir=None):
        write_config(data_dir or self.data, hook, data, bom)

    def legacy(self, data, hook=HOOK):
        write_legacy(self.home, hook, data)

    def resolve(self, generate=True, hook=HOOK):
        return ns.resolve(hook, self.env, self.home, generate)

    def sounds_dir(self):
        return os.path.join(self.data, "cache", "sounds")


class TestValores(Base):

    def test_sin_json_null_vacio_y_neb_dan_el_default(self):
        self.os_(False)
        self.assertEqual(self.resolve(), (self.default, None))
        for wav in (None, "", "neb"):
            with self.subTest(wav=wav):
                self.cfg({"wav": wav})
                self.assertEqual(self.resolve(), (self.default, None))
        self.cfg({"enabled": True})
        self.assertEqual(self.resolve(), (self.default, None))

    def test_json_con_bom(self):
        self.os_(False)
        self.cfg({"enabled": False}, bom=True)
        self.assertEqual(self.resolve(), (None, None))

    def test_json_ilegible_cuenta_como_ausente(self):
        self.os_(False)
        self.cfg("{no es json")
        self.assertEqual(self.resolve(), (self.default, None))

    def test_critico_enabled_false_no_da_ruta_ni_motivo(self):
        self.cfg({"enabled": False, "wav": "/no/existe.wav"})
        self.assertEqual(self.resolve(), (None, None))

    def test_enabled_de_otro_tipo_cuenta_como_ausente(self):
        # Criterio de toda la config.json (neb_paths): un valor de otro tipo cae al de omisión (encendido).
        self.os_(False)
        for v in ("false", 0, None):
            with self.subTest(enabled=v):
                self.cfg({"enabled": v})
                self.assertEqual(self.resolve(), (self.default, None))

    def test_is_enabled_con_dict_propio(self):
        for v in (False, "false", 0, None):
            self.assertFalse(ns.is_enabled({"enabled": v}))
        self.assertTrue(ns.is_enabled({}))

    def test_falta_el_default(self):
        self.os_(False)
        os.remove(self.default)
        path, reason = self.resolve()
        self.assertIsNone(path)
        self.assertIn("falta el sonido por defecto", reason)
        self.cfg({"wav": "/no/existe.wav"})
        path, reason = self.resolve()
        self.assertIsNone(path)
        self.assertIn("no existe", reason)
        self.assertIn("falta el sonido por defecto", reason)

    def test_ruta_absoluta(self):
        self.os_(os.name == "nt")                                   # la ruta temporal es de la plataforma real
        otro = os.path.join(self.tmp, "otro.wav")
        write_wav(otro, [1, 2])
        self.cfg({"wav": otro})
        self.assertEqual(self.resolve(), (otro, None))
        falta = os.path.join(self.tmp, "falta.wav")
        self.cfg({"wav": falta})
        self.assertEqual(self.resolve(), (self.default, "no existe %s" % falta))

    def test_rutas_de_windows_iguales_con_cualquier_python(self):
        # PD-993: desde Python 3.13, os.path.isabs('/x') da False en Windows; la regla no depende de la versión.
        self.os_(True)
        existe = os.path.join(self.tmp, "existe.wav")
        write_wav(existe, [1, 2])
        con_unidad = existe.replace(os.sep, "/")
        self.cfg({"wav": con_unidad})
        if os.name == "nt":                                          # isfile de una ruta C:/ solo existe en Windows
            self.assertEqual(self.resolve(), (con_unidad, None))
        falta = "C:/neb-prueba-pd993/falta.wav"
        self.cfg({"wav": falta})
        self.assertEqual(self.resolve(), (self.default, "no existe %s" % falta))
        unc = r"\\localhost\neb-pd993-no-existe$\x.wav"             # localhost: isfile no sale a la red
        self.cfg({"wav": unc})
        self.assertEqual(self.resolve(), (self.default, "no existe %s" % unc))
        sin_unidad = os.path.splitdrive(existe)[1]                   # con raíz y sin unidad; en Windows, el archivo existe
        for wav in (sin_unidad, sin_unidad.replace("\\", "/"), "/Windows/Media/chimes.wav"):
            with self.subTest(wav=wav):
                self.cfg({"wav": wav})
                path, reason = self.resolve()
                self.assertEqual(path, self.default)
                self.assertIn("en Windows la ruta de `wav` lleva la unidad", reason)
        for wav in ("C:relativo.wav", "C:", "//x.wav", "\\\\srv", "\\\\srv\\rec"):   # UNC incompleta: igual en 3.8 y 3.11+
            with self.subTest(wav=wav):
                self.cfg({"wav": wav})
                self.assertEqual(self.resolve(), (self.default, "valor de `wav` no reconocido: %r" % (wav,)))
        for wav in ("//srv/rec/x.wav", "\\\\?\\C:\\x.wav"):
            with self.subTest(wav=wav):
                self.assertTrue(ns._full_path(wav))

    def test_rutas_posix(self):
        self.os_(False)
        self.assertTrue(ns._full_path("/no/existe.wav"))
        self.assertFalse(ns._full_path("relativo.wav"))
        for wav in ("C:\\x.wav", "C:/x.wav", "\\\\srv\\rec\\x.wav"):                # en un POSIX real no son rutas completas
            with self.subTest(wav=wav):
                self.assertFalse(ns._full_path(wav))
        self.assertFalse(ns._rooted_without_drive("/x.wav"), "fuera de Windows /x es ruta completa")

    def test_valor_no_reconocido(self):
        self.os_(False)
        for wav in ("relativo.wav", "Chimes"):
            with self.subTest(wav=wav):
                self.cfg({"wav": wav})
                path, reason = self.resolve()
                self.assertEqual(path, self.default)
                self.assertIn("no reconocido", reason)
        # No cadena: neb_paths lo descarta (otro tipo que el de omisión) y queda el sonido por defecto.
        for wav in (42, ["x"]):
            with self.subTest(wav=wav):
                self.cfg({"wav": wav})
                self.assertEqual(self.resolve(), (self.default, None))

    def test_presets_de_windows_en_posix(self):
        self.os_(False)
        write_wav(self.chimes, [100, -100])
        for wav in ("chimes", "chimes-loud"):
            with self.subTest(wav=wav):
                self.cfg({"wav": wav})
                path, reason = self.resolve()
                self.assertEqual(path, self.default)
                self.assertIn("solo existe en Windows", reason)
        self.assertFalse(os.path.exists(self.sounds_dir()))

    def test_chimes_en_windows(self):
        self.os_(True)
        write_wav(self.chimes, [100, -100])
        self.cfg({"wav": "chimes"})
        self.assertEqual(self.resolve(), (self.chimes, None))

    def test_chimes_sin_el_wav_de_windows(self):
        self.os_(True)
        for wav in ("chimes", "chimes-loud"):
            with self.subTest(wav=wav):
                self.cfg({"wav": wav})
                path, reason = self.resolve()
                self.assertEqual(path, self.default)
                self.assertIn("no se encontró el chimes.wav", reason)
        self.env = {"PATH": ""}   # sin WINDIR ni SystemRoot
        path, reason = self.resolve()
        self.assertEqual(path, self.default)


class TestOrigenDeLaConfig(Base):

    def setUp(self):
        super().setUp()
        self.os_(os.name == "nt")   # la plataforma real: las rutas temporales son completas para ella (7.6.1)
        self.otro = os.path.join(self.tmp, "otro.wav")
        write_wav(self.otro, [1, 2])

    def test_critico_config_json_gana_sobre_los_sueltos(self):
        self.legacy({"enabled": False})
        self.cfg({"wav": self.otro})
        self.assertEqual(self.resolve(), (self.otro, None))
        # Aun sin la sección del hook en config.json: con config.json presente, el suelto ya no se lee.
        self.cfg({}, hook="notify-on-permission")
        self.assertEqual(self.resolve(), (self.default, None))

    def test_critico_sin_config_json_se_leen_los_sueltos(self):
        self.legacy({"enabled": False})
        self.assertEqual(self.resolve(), (None, None))
        self.legacy({"wav": self.otro, "min_seconds": 42})
        self.assertEqual(self.resolve(), (self.otro, None))
        self.assertEqual(ns.effective(HOOK, self.env, self.home)["min_seconds"], 42)

    def test_cada_hook_lee_su_seccion(self):
        os.makedirs(self.data, exist_ok=True)
        with open(os.path.join(self.data, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"notify": {"stop": {"enabled": False}, "permission": {"wav": self.otro}}}, f)
        self.assertEqual(self.resolve(), (None, None))
        self.assertEqual(self.resolve(hook="notify-on-permission"), (self.otro, None))

    def test_neb_data_mueve_la_config(self):
        datos = os.path.join(self.tmp, "datos")
        self.cfg({"enabled": False}, data_dir=datos)
        self.assertEqual(self.resolve(), (self.default, None))   # sin NEB_DATA: ~/.neb, sin config
        self.env["NEB_DATA"] = datos
        self.assertEqual(self.resolve(), (None, None))

    def test_hook_desconocido(self):
        self.assertEqual(ns.load_config("otro-hook", self.home, self.env), {})
        self.assertEqual(ns.effective("otro-hook", self.env, self.home), {})


class TestVersionFuerte(Base):

    SAMPLES = [0, 2005, -2005, 1000, -1, 7, 2004, -32]

    def setUp(self):
        super().setUp()
        self.os_(True)
        write_wav(self.chimes, self.SAMPLES)
        self.cfg({"wav": "chimes-loud"})
        self.cache = os.path.join(self.sounds_dir(), "chimes-loud.wav")

    def test_critico_genera_con_pico_y_formato_del_original(self):
        path, reason = self.resolve()
        self.assertEqual((path, reason), (self.cache, None))
        p_src, _ = read_wav(self.chimes)
        p, a = read_wav(self.cache)
        self.assertEqual(p[:4], p_src[:4])
        self.assertEqual(max(abs(x) for x in a), ns.LOUD_PEAK)
        gain = ns.LOUD_PEAK / 2005
        self.assertEqual(list(a), [round(x * gain) for x in self.SAMPLES])
        self.assertEqual(os.listdir(self.sounds_dir()), ["chimes-loud.wav"])

    def test_recorta_a_16_bit(self):
        write_wav(self.chimes, [1, -1, 0, 0])
        os.utime(self.chimes, None)
        path, _ = self.resolve()
        _, a = read_wav(path)
        self.assertEqual(list(a), [ns.LOUD_PEAK, -ns.LOUD_PEAK, 0, 0])
        with mock.patch.object(ns, "LOUD_PEAK", 40000):
            os.remove(path)
            self.resolve()
        _, a = read_wav(path)
        self.assertEqual(list(a), [32767, -32768, 0, 0])

    def test_reutiliza_la_cache_y_regenera_si_la_fuente_es_mas_nueva(self):
        path, _ = self.resolve()
        os.utime(path, (2_000_000_000, 2_000_000_000))
        os.utime(self.chimes, (1_000_000_000, 1_000_000_000))
        with mock.patch.object(ns, "_read_pcm16", side_effect=AssertionError("no debía regenerar")):
            self.assertEqual(self.resolve(), (path, None))
        os.utime(self.chimes, (2_100_000_000, 2_100_000_000))
        write_wav(self.chimes, [4010, -4010])
        os.utime(self.chimes, (2_100_000_000, 2_100_000_000))
        self.resolve()
        _, a = read_wav(path)
        self.assertEqual(list(a), [ns.LOUD_PEAK, -ns.LOUD_PEAK])

    def test_critico_falla_al_escribir_no_deja_cache_ni_temporal(self):
        def rota(self_, data):
            raise OSError("disco lleno")
        with mock.patch.object(wave.Wave_write, "writeframes", rota):
            path, reason = self.resolve()
        self.assertEqual(path, self.default)
        self.assertIn("disco lleno", reason)
        self.assertEqual(os.listdir(self.sounds_dir()), [])

    def test_carpeta_de_la_cache_que_es_enlace_cae_al_default(self):
        with mock.patch.object(ns.neb_paths, "ensure_dir", side_effect=ValueError("es un enlace")):
            path, reason = self.resolve()
        self.assertEqual(path, self.default)
        self.assertIn("es un enlace", reason)

    def test_fuente_que_no_es_pcm16(self):
        write_wav(self.chimes, [128, 200, 50], sampwidth=1)
        for generate in (True, False):
            with self.subTest(generate=generate):
                path, reason = self.resolve(generate)
                self.assertEqual(path, self.default)
                self.assertIn("16 bit", reason)
        self.assertFalse(os.path.exists(self.cache))

    def test_fuente_ilegible(self):
        with open(self.chimes, "wb") as f:
            f.write(b"no es un wav")
        path, reason = self.resolve()
        self.assertEqual(path, self.default)
        self.assertIn("no se puede leer", reason)

    def test_fuente_en_silencio(self):
        write_wav(self.chimes, [0, 0, 0])
        path, reason = self.resolve()
        self.assertEqual(path, self.default)
        self.assertIn("en silencio", reason)
        self.assertFalse(os.path.exists(self.cache))

    def test_critico_generate_false_no_escribe(self):
        self.assertEqual(self.resolve(generate=False), (self.cache, None))
        self.assertFalse(os.path.exists(self.sounds_dir()))

    def test_critico_la_cache_va_a_la_carpeta_de_datos(self):
        self.assertEqual(self.cache, os.path.join(neb_paths.cache_dir("sounds", self.home, self.env),
                                                  "chimes-loud.wav"))
        self.resolve()
        self.assertTrue(os.path.isfile(self.cache))
        self.assertFalse(os.path.exists(os.path.join(self.home, ".claude", "neb-sounds")))

    def test_neb_data_mueve_la_cache(self):
        datos = os.path.join(self.tmp, "datos")
        self.cfg({"wav": "chimes-loud"}, data_dir=datos)
        self.env["NEB_DATA"] = datos
        path, reason = self.resolve()
        self.assertEqual((path, reason), (os.path.join(datos, "cache", "sounds", "chimes-loud.wav"), None))
        self.assertTrue(os.path.isfile(path))
        self.assertFalse(os.path.exists(self.sounds_dir()))


class TestEfectiva(Base):

    def setUp(self):
        super().setUp()
        self.os_(False)

    def eff(self, hook=HOOK):
        return ns.effective(hook, self.env, self.home)

    def test_valores_por_omision(self):
        self.assertEqual(self.eff(), {"enabled": True, "wav": self.default, "reason": None,
                                      "min_seconds": 10, "max_chimes": 5, "scaling": "per-minute"})
        self.assertEqual(self.eff("notify-on-permission"),
                         {"enabled": True, "wav": self.default, "reason": None})

    def test_critico_normaliza(self):
        casos = [
            ({"min_seconds": -5, "max_chimes": 0, "scaling": "x"}, (0, 1, "per-minute")),
            ({"min_seconds": 7.9, "max_chimes": 99, "scaling": "fixed"}, (7, 20, "fixed")),
            ({"min_seconds": "30", "max_chimes": True}, (10, 5, "per-minute")),
            ({"min_seconds": 0, "max_chimes": 20}, (0, 20, "per-minute")),
        ]
        for data, esperado in casos:
            with self.subTest(data=data):
                self.cfg(data)
                e = self.eff()
                self.assertEqual((e["min_seconds"], e["max_chimes"], e["scaling"]), esperado)

    def test_apagado(self):
        self.cfg({"enabled": False, "max_chimes": 3})
        e = self.eff()
        self.assertEqual((e["enabled"], e["wav"], e["max_chimes"]), (False, None, 3))

    def test_hook_env(self):
        self.cfg({"min_seconds": 3, "max_chimes": 7, "scaling": "fixed"})
        self.assertEqual(ns.hook_env(self.eff()), {
            "NEB_NOTIFY_ENABLED": "true", "NEB_NOTIFY_WAV": self.default, "NEB_NOTIFY_MIN_SECONDS": "3",
            "NEB_NOTIFY_MAX_CHIMES": "7", "NEB_NOTIFY_SCALING": "fixed"})
        self.assertEqual(ns.hook_env(self.eff("notify-on-permission")),
                         {"NEB_NOTIFY_ENABLED": "true", "NEB_NOTIFY_WAV": self.default})

    def test_config_lines(self):
        self.cfg({"enabled": False})
        self.assertEqual(ns.config_lines(self.eff()), ["enabled=false", "wav=", "min_seconds=10",
                                                       "max_chimes=5", "scaling=per-minute"])


class TestReproductorYDiagnostico(Base):

    def _player(self, name="aplay"):
        bindir = os.path.join(self.tmp, "bin")
        os.makedirs(bindir, exist_ok=True)
        exe = os.path.join(bindir, name + (".bat" if os.name == "nt" else ""))
        with open(exe, "w") as f:
            f.write("@echo off\n" if os.name == "nt" else "#!/bin/sh\n")
        os.chmod(exe, 0o755)
        self.env["PATH"] = bindir

    def test_player_available(self):
        self.os_(True)
        self.assertTrue(ns.player_available(self.env))
        self.os_(False)
        self.assertFalse(ns.player_available(self.env))
        self._player()
        self.assertTrue(ns.player_available(self.env))

    def test_diagnose(self):
        self.os_(False)
        self._player()
        self.assertIsNone(ns.diagnose(HOOK, self.env, self.home))
        self.cfg({"enabled": False, "wav": "/falta.wav"})
        self.assertIsNone(ns.diagnose(HOOK, self.env, self.home))
        self.cfg({"wav": "/neb-pd993-no-existe/falta.wav"})
        self.assertTrue(ns.diagnose(HOOK, self.env, self.home).startswith("usa el sonido por defecto: no existe"))
        with mock.patch.object(ns, "IS_WINDOWS", True):              # el aviso del arranque muestra el motivo nuevo
            self.cfg({"wav": "/Windows/Media/x.wav"})
            self.assertIn("en Windows la ruta de `wav` lleva la unidad", ns.diagnose(HOOK, self.env, self.home))
        self.cfg({"wav": "/neb-pd993-no-existe/falta.wav"})
        os.remove(self.default)
        self.assertTrue(ns.diagnose(HOOK, self.env, self.home).startswith("no suena: no existe"))

    def test_diagnose_sin_reproductor(self):
        self.os_(False)
        d = ns.diagnose(HOOK, self.env, self.home)
        self.assertTrue(d.startswith("no suena: no hay reproductor"), d)
        self.cfg({"enabled": False})
        self.assertIsNone(ns.diagnose(HOOK, self.env, self.home))

    def test_diagnose_chimes_loud_no_escribe(self):
        self.os_(True)
        write_wav(self.chimes, [10, -10])
        self.cfg({"wav": "chimes-loud"})
        self.assertIsNone(ns.diagnose(HOOK, self.env, self.home))
        self.assertFalse(os.path.exists(self.sounds_dir()))


class TestCli(Base):

    def _main(self, argv):
        raw = io.BytesIO()
        out = io.TextIOWrapper(raw, encoding="utf-8", newline="")
        with mock.patch.object(ns.sys, "stdout", out), _entorno.home_en_proceso(self.home):
            rc = ns.main(argv)
        out.flush()
        return rc, raw.getvalue().decode("utf-8")

    def test_imprime_la_ruta(self):
        self.os_(False)
        self.assertEqual(self._main(["x", HOOK]), (0, self.default + "\n"))

    def test_hook_desconocido_o_sin_ruta_no_imprime(self):
        self.os_(False)
        self.assertEqual(self._main(["x"]), (0, ""))
        self.assertEqual(self._main(["x", "otro-hook"]), (0, ""))
        os.remove(self.default)
        self.assertEqual(self._main(["x", HOOK]), (0, ""))

    def test_critico_hook_apagado_sale_con_disabled_rc(self):
        self.os_(False)
        self.cfg({"enabled": False})
        self.assertEqual(self._main(["x", HOOK]), (ns.DISABLED_RC, ""))
        self.cfg({}, hook="notify-on-permission")
        self.legacy({"enabled": False})   # el suelto ya no cuenta: hay config.json
        self.assertEqual(self._main(["x", HOOK]), (0, self.default + "\n"))

    def test_falla_del_resolvedor_no_rompe(self):
        with mock.patch.object(ns, "resolve", side_effect=RuntimeError("x")):
            self.assertEqual(self._main(["x", HOOK]), (0, ""))
        with mock.patch.object(ns, "effective", side_effect=RuntimeError("x")):
            self.assertEqual(self._main(["x", "config", HOOK]), (0, ""))

    def test_critico_config_imprime_llave_valor(self):
        self.os_(False)
        self.cfg({"min_seconds": 3, "max_chimes": 50, "scaling": "fixed"})
        self.assertEqual(self._main(["x", "config", HOOK]),
                         (0, "enabled=true\nwav=%s\nmin_seconds=3\nmax_chimes=20\nscaling=fixed\n" % self.default))
        self.cfg({"enabled": False}, hook="notify-on-permission")
        self.assertEqual(self._main(["x", "config", "notify-on-permission"]), (0, "enabled=false\nwav=\n"))

    def test_config_hook_desconocido_no_imprime(self):
        self.assertEqual(self._main(["x", "config", "otro-hook"]), (0, ""))
        self.assertEqual(self._main(["x", "config"]), (0, ""))

    def test_critico_config_como_proceso_sin_retorno_de_carro(self):
        # Lo que lee bash: en Windows el modo texto de stdout escribiría "\r\n".
        self.cfg({"max_chimes": 2})
        r = subprocess.run([sys.executable, os.path.join(LIB, "notify_sound.py"), "config", HOOK],
                           env=_entorno.env_con_home(self.home), capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 0)
        self.assertNotIn(b"\r", r.stdout)
        self.assertIn(b"\nmax_chimes=2\n", r.stdout)
        self.assertTrue(r.stdout.startswith(b"enabled=true\nwav="))


class TestCargaPorRuta(unittest.TestCase):
    """bootstrap/neb-bootstrap-context.py carga notify_sound.py por ruta (importlib), sin hooks/lib en
    sys.path: el `import neb_paths` tiene que resolverse solo."""

    def test_critico_importa_sin_lib_en_sys_path(self):
        code = ("import importlib.util, sys\n"
                "spec = importlib.util.spec_from_file_location('notify_sound', sys.argv[1])\n"
                "mod = importlib.util.module_from_spec(spec)\n"
                "spec.loader.exec_module(mod)\n"
                "print(mod.loud_cache().endswith('chimes-loud.wav'))\n")
        home = _entorno.home_temporal(self)
        r = subprocess.run([sys.executable, "-I", "-c", code, os.path.join(LIB, "notify_sound.py")],
                           env=_entorno.env_con_home(home), capture_output=True, timeout=60, cwd=home)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, b"True"), r.stderr)


def _posix(path):
    return path.replace("\\", "/")


class ScriptBase(unittest.TestCase):
    """Los scripts de verdad con HOME temporal. Nada suena: el .sh encuentra un reproductor falso
    (`afplay`, el primero que busca) que anota cada reproducción; el .ps1 corre con una función
    Start-Process que anota en vez de lanzar el powershell que reproduce."""

    def setUp(self):
        self.home = _entorno.home_temporal(self, claude=True)
        self.data = os.path.join(self.home, ".neb")
        self.marker = os.path.join(self.home, "reproducciones.txt")
        self.wav = os.path.join(self.home, "sonido.wav")
        write_wav(self.wav, [1, -1])

    def cfg(self, data, hook=HOOK):
        write_config(self.data, hook, data)

    def plays(self, wait=0.0):
        """Reproducciones anotadas; espera hasta `wait` segundos a que aparezca alguna (el .sh reproduce
        en segundo plano después de salir)."""
        deadline = time.monotonic() + wait
        while True:
            try:
                with open(self.marker, encoding="utf-8") as f:
                    lines = [line for line in f.read().splitlines() if line]
            except OSError:
                lines = []
            if lines or time.monotonic() >= deadline:
                return lines
            time.sleep(0.1)

    def settled_plays(self, expected_max=20):
        """Espera a que el número de reproducciones deje de crecer (play_n reproduce en serie)."""
        lines = self.plays(wait=10)
        while True:
            time.sleep(0.6)
            again = self.plays()
            if len(again) == len(lines) or len(again) >= expected_max:
                return again
            lines = again

    def transcript(self, minutes_ago):
        ts = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        path = os.path.join(self.home, "t.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "user", "timestamp": ts, "message": {"content": "hola"}}) + "\n")
            f.write(json.dumps({"type": "assistant", "timestamp": ts}) + "\n")
        return path


@unittest.skipUnless(BASH, "requiere bash (Git Bash en Windows)")
class TestScriptSh(ScriptBase):

    def setUp(self):
        super().setUp()
        self.bindir = os.path.join(self.home, "bin")
        os.makedirs(self.bindir)
        self._exe("afplay", '#!/bin/sh\necho "$1" >> "%s"\n' % _posix(self.marker))
        # python3 del PATH = el Python de la prueba (en Git Bash, `python3` puede ser el alias de la Store).
        self._exe("python3", '#!/bin/sh\nexec "%s" "$@"\n' % _posix(sys.executable))

    def _exe(self, name, text):
        path = os.path.join(self.bindir, name)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.chmod(path, 0o755)

    def run_sh(self, hook=HOOK, event=None, path_extra=True, **env):
        e = _entorno.env_con_home(self.home, **env)
        for var in ns.ENV_VARS.values():
            if var not in env:
                e.pop(var, None)
        e.pop("NEB_INTERNAL_SUBSESSION", None)
        e.pop("CLAUDE_PREPROCESS_RECURSION", None)
        if path_extra:
            e["PATH"] = self.bindir + os.pathsep + e.get("PATH", "")
        payload = json.dumps(event or {}).encode("utf-8")
        r = subprocess.run([BASH, os.path.join(HOOKS_DIR, hook + ".sh")], input=payload, env=e,
                           capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def test_critico_directo_respeta_enabled_false(self):
        for hook in ns.HOOKS:
            with self.subTest(hook=hook):
                self.cfg({"enabled": False, "wav": self.wav}, hook=hook)
                self.run_sh(hook)
                time.sleep(0.5)
                self.assertEqual(self.plays(), [])

    def test_critico_directo_lee_config_json(self):
        self.cfg({"wav": self.wav})
        self.run_sh()
        plays = self.plays(wait=10)
        self.assertEqual(len(plays), 1)
        self.assertTrue(plays[0].endswith("sonido.wav"), plays)

    def test_directo_sin_config_json_lee_el_suelto(self):
        write_legacy(self.home, "notify-on-permission", {"enabled": False})
        self.run_sh("notify-on-permission")
        time.sleep(0.5)
        self.assertEqual(self.plays(), [])

    def test_critico_bajo_el_despachador_usa_las_variables(self):
        # config.json apagado, pero el despachador ya resolvió: el script no relee la config.
        self.cfg({"enabled": False})
        self.run_sh(NEB_NOTIFY_WAV=self.wav, NEB_NOTIFY_ENABLED="true", NEB_NOTIFY_MIN_SECONDS="0",
                    NEB_NOTIFY_MAX_CHIMES="5", NEB_NOTIFY_SCALING="fixed")
        self.assertEqual(len(self.plays(wait=10)), 1)

    def test_variable_enabled_false_no_suena(self):
        self.run_sh(NEB_NOTIFY_WAV=self.wav, NEB_NOTIFY_ENABLED="false")
        time.sleep(0.5)
        self.assertEqual(self.plays(), [])

    @unittest.skipUnless(shutil.which("jq"), "la duración del turno requiere jq")
    def test_critico_max_chimes_y_min_seconds_de_config_json(self):
        transcript = self.transcript(minutes_ago=3)   # per-minute: 1 + 3 = 4 chimes, acotado a 2
        self.cfg({"wav": self.wav, "max_chimes": 2, "min_seconds": 0})
        self.run_sh(event={"transcript_path": transcript})
        self.assertEqual(len(self.settled_plays()), 2)
        os.remove(self.marker)
        self.cfg({"wav": self.wav, "min_seconds": 100000})
        self.run_sh(event={"transcript_path": transcript})
        time.sleep(0.5)
        self.assertEqual(self.plays(), [])


@unittest.skipUnless(POWERSHELL, "requiere Windows PowerShell")
class TestScriptPs1(ScriptBase):

    def run_ps1(self, hook=HOOK, event=None, **env):
        e = _entorno.env_con_home(self.home, **env)
        for var in ns.ENV_VARS.values():
            if var not in env:
                e.pop(var, None)
        e.pop("NEB_INTERNAL_SUBSESSION", None)
        e.pop("CLAUDE_PREPROCESS_RECURSION", None)
        script = os.path.join(HOOKS_DIR, hook + ".ps1")
        # Una función gana a un cmdlet del mismo nombre y el script la ve (corre en un ámbito hijo):
        # Start-Process anota en lugar de lanzar el powershell que reproduce.
        # Anota el número de reproducciones del bucle (`-lt N`) o, sin bucle (permission), `play`.
        wrapper = ("function Start-Process { param($FilePath, $ArgumentList, $WindowStyle) "
                   "$m = [regex]::Match(($ArgumentList -join ' '), '-lt (\\d+)'); "
                   "$v = if ($m.Success) { 'play ' + $m.Groups[1].Value } else { 'play' }; "
                   "Add-Content -LiteralPath '%s' -Value $v }; "
                   "& '%s'; exit $LASTEXITCODE" % (self.marker.replace("'", "''"), script.replace("'", "''")))
        r = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", wrapper],
                           input=json.dumps(event or {}).encode("utf-8"), env=e, capture_output=True,
                           timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def test_critico_directo_respeta_enabled_false(self):
        for hook in ns.HOOKS:
            with self.subTest(hook=hook):
                self.cfg({"enabled": False, "wav": self.wav}, hook=hook)
                self.run_ps1(hook)
                self.assertEqual(self.plays(), [])

    def test_critico_directo_lee_config_json(self):
        self.cfg({"wav": self.wav}, hook="notify-on-permission")
        self.run_ps1("notify-on-permission")
        self.assertEqual(self.plays(), ["play"])

    def test_directo_sin_config_json_lee_el_suelto(self):
        write_legacy(self.home, HOOK, {"enabled": False})
        self.run_ps1()
        self.assertEqual(self.plays(), [])

    def test_critico_bajo_el_despachador_usa_las_variables(self):
        self.cfg({"enabled": False})
        self.run_ps1(NEB_NOTIFY_WAV=self.wav, NEB_NOTIFY_ENABLED="true", NEB_NOTIFY_MIN_SECONDS="0",
                     NEB_NOTIFY_MAX_CHIMES="3", NEB_NOTIFY_SCALING="per-minute",
                     event={"transcript_path": self.transcript(minutes_ago=10)})
        self.assertEqual(self.plays(), ["play 3"])

    def test_critico_max_chimes_y_min_seconds_de_config_json(self):
        transcript = self.transcript(minutes_ago=3)
        self.cfg({"wav": self.wav, "min_seconds": 100000})
        self.run_ps1(event={"transcript_path": transcript})
        self.assertEqual(self.plays(), [])
        self.cfg({"wav": self.wav, "min_seconds": 0, "max_chimes": 2})
        self.run_ps1(event={"transcript_path": transcript})
        self.assertEqual(self.plays(), ["play 2"])   # per-minute: 1 + 3 = 4, acotado a 2

    def test_critico_ruta_con_apostrofo_llega_intacta_al_reproductor(self):
        """Una ruta con apóstrofo (C:\\Users\\O'Neil, NEB_DATA) va como literal de comillas simples en el comando del
        powershell que reproduce: sin duplicarlo, el comando no parsea (o inyecta lo que sigue al apóstrofo)."""
        folder = os.path.join(self.home, "O'Neil")
        os.makedirs(folder)
        wav = os.path.join(folder, "fin.wav")
        shutil.copy(self.wav, wav)
        for hook in ns.HOOKS:
            with self.subTest(hook=hook):
                if os.path.exists(self.marker):
                    os.remove(self.marker)
                e = _entorno.env_con_home(self.home, NEB_NOTIFY_WAV=wav, NEB_NOTIFY_ENABLED="true",
                                          NEB_NOTIFY_MIN_SECONDS="0", NEB_NOTIFY_MAX_CHIMES="1",
                                          NEB_NOTIFY_SCALING="fixed")
                # Start-Process parsea el -Command con el parser de PowerShell y anota el argumento de SoundPlayer.
                wrapper = (
                    "function Start-Process { param($FilePath, $ArgumentList, $WindowStyle) "
                    "$cmd = $ArgumentList[-1]; $t = $null; $er = $null; "
                    "$ast = [System.Management.Automation.Language.Parser]::ParseInput($cmd, [ref]$t, [ref]$er); "
                    "if ($er.Count) { $v = 'error' } else { "
                    "$s = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.StringConstantExpressionAst] "
                    "-and $n.Parent -is [System.Management.Automation.Language.CommandAst] -and "
                    "$n.Parent.CommandElements[1].Value -eq 'Media.SoundPlayer' }, $true) | Select-Object -Last 1; "
                    "$v = 'wav ' + $s.Value }; "
                    "Add-Content -LiteralPath '%s' -Value $v -Encoding UTF8 }; "
                    "& '%s'; exit $LASTEXITCODE" % (self.marker.replace("'", "''"),
                                                    os.path.join(HOOKS_DIR, hook + ".ps1").replace("'", "''")))
                event = {"transcript_path": self.transcript(minutes_ago=10)}
                r = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", wrapper],
                                   input=json.dumps(event).encode("utf-8"), env=e, capture_output=True, timeout=120)
                self.assertEqual(r.returncode, 0, r.stderr)
                with open(self.marker, encoding="utf-8-sig") as f:
                    self.assertEqual(f.read().strip(), "wav " + wav)


class TestWavVersionado(unittest.TestCase):

    def test_critico_neb_chime_es_pcm16_legible(self):
        real = os.path.join(os.path.dirname(LIB), "sounds", "neb-chime.wav")
        self.assertEqual(ns.DEFAULT_WAV, real)
        with wave.open(real, "rb") as w:
            self.assertEqual(w.getsampwidth(), 2)
            self.assertGreater(w.getnframes(), 0)
            dur = w.getnframes() / w.getframerate()
        self.assertLessEqual(dur, 2.0)
        self.assertLessEqual(os.path.getsize(real), 300 * 1024)


if __name__ == "__main__":
    unittest.main()
