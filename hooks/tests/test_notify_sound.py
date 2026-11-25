#!/usr/bin/env python3
"""test_notify_sound.py — el sonido de notify-on-stop / notify-on-permission (hooks/lib/notify_sound.py, 7.2.0).

  • resolve(): cada valor de `wav` (null, ausente, "neb", "chimes", "chimes-loud", ruta absoluta, basura,
    no cadena) en Windows y en POSIX (simulado); `enabled: false`; JSON con BOM; falta el sonido por defecto
  • la versión fuerte: pico LOUD_PEAK, mismo formato y frames, caché reutilizada y regenerada por mtime,
    escritura atómica (sin temporales ni caché a medias si falla), fuente que no es PCM 16 o en silencio
  • generate=False (el arranque) no crea ~/.claude/neb-sounds/
  • player_available() y diagnose(): frases del aviso del arranque
  • la CLI que usan los .ps1/.sh invocados directo
  • el WAV versionado (hooks/sounds/neb-chime.wav) es PCM de 16 bit legible

Framework: unittest (stdlib). HOME, WINDIR y WAV temporales; nunca toca ~/.claude.
  py -m unittest discover -s hooks/tests -p test_notify_sound.py
"""
import array
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import wave
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.abspath(os.path.join(HERE, "..", "lib"))
sys.path.insert(0, LIB)
import notify_sound as ns  # noqa: E402

HOOK = "notify-on-stop"


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


class Base(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="neb-test-sound-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(os.path.join(self.home, ".claude"))
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

    def cfg(self, data, bom=False, hook=HOOK):
        path = os.path.join(self.home, ".claude", "%s.json" % hook)
        text = data if isinstance(data, str) else json.dumps(data)
        with open(path, "w", encoding="utf-8-sig" if bom else "utf-8") as f:
            f.write(text)

    def resolve(self, generate=True, hook=HOOK):
        return ns.resolve(hook, self.env, self.home, generate)

    def sounds_dir(self):
        return os.path.join(self.home, ".claude", "neb-sounds")


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
        self.cfg({"wav": "neb", "enabled": True}, bom=True)
        self.assertEqual(self.resolve(), (self.default, None))

    def test_json_ilegible_cuenta_como_ausente(self):
        self.os_(False)
        self.cfg("{no es json")
        self.assertEqual(self.resolve(), (self.default, None))

    def test_enabled_false_no_da_ruta_ni_motivo(self):
        for v in (False, "false", 0, None):
            with self.subTest(enabled=v):
                self.cfg({"enabled": v, "wav": "/no/existe.wav"})
                self.assertEqual(self.resolve(), (None, None))

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
        self.os_(False)
        otro = os.path.join(self.tmp, "otro.wav")
        write_wav(otro, [1, 2])
        self.cfg({"wav": otro})
        self.assertEqual(self.resolve(), (otro, None))
        falta = os.path.join(self.tmp, "falta.wav")
        self.cfg({"wav": falta})
        self.assertEqual(self.resolve(), (self.default, "no existe %s" % falta))

    def test_valor_no_reconocido(self):
        self.os_(False)
        for wav in ("relativo.wav", "Chimes", 42, ["x"]):
            with self.subTest(wav=wav):
                self.cfg({"wav": wav})
                path, reason = self.resolve()
                self.assertEqual(path, self.default)
                self.assertIn("no reconocido", reason)

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
        self.cfg({"wav": os.path.join(self.tmp, "falta.wav")})
        self.assertTrue(ns.diagnose(HOOK, self.env, self.home).startswith("usa el sonido por defecto: no existe"))
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
        out = io.StringIO()
        with mock.patch.object(ns.sys, "stdout", out), \
                mock.patch.dict(os.environ, {"HOME": self.home, "USERPROFILE": self.home}):
            rc = ns.main(argv)
        return rc, out.getvalue()

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
        for v in (False, "false"):
            with self.subTest(enabled=v):
                self.cfg({"enabled": v})
                self.assertEqual(self._main(["x", HOOK]), (ns.DISABLED_RC, ""))

    def test_falla_del_resolvedor_no_rompe(self):
        with mock.patch.object(ns, "resolve", side_effect=RuntimeError("x")):
            self.assertEqual(self._main(["x", HOOK]), (0, ""))


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
