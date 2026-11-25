#!/usr/bin/env python3
"""notify_sound.py — qué sonido reproducen los hooks notify-on-stop y notify-on-permission.

Único resolvedor del valor `wav` de `~/.claude/notify-on-{stop,permission}.json`. Lo usan:
  • hooks/neb-hook.py (despachador del plugin): resuelve y pasa la ruta en NEB_NOTIFY_WAV;
  • los .ps1/.sh invocados directo (entradas de settings.json anteriores a 6.15.0), por la CLI;
  • bootstrap/neb-bootstrap-context.py: el aviso del arranque, en modo diagnóstico (no escribe).

Valores de `wav` (lineamiento: tooling/notify-on-stop.md):
  null / ausente / "neb"  → hooks/sounds/neb-chime.wav (CC0, en todo SO)
  "chimes"                → %WINDIR%\\Media\\chimes.wav (solo Windows)
  "chimes-loud"           → chimes.wav amplificado, generado en local en ~/.claude/neb-sounds/ (solo Windows)
  ruta absoluta           → esa ruta, si existe
Cualquier otro caso cae en neb-chime.wav con su motivo. No se redistribuye audio de terceros sin licencia:
chimes.wav se lee de la máquina del dev y la versión fuerte se genera ahí.

CLI: `notify_sound.py <hook>` imprime la ruta resuelta (o nada) y sale con 0; con el hook apagado en su
JSON (`enabled: false`) no imprime nada y sale con 3.
Solo stdlib. Defensivo: nunca levanta hacia el hook.
"""
import array
import json
import os
import shutil
import sys
import tempfile
import wave

HOOKS = ("notify-on-stop", "notify-on-permission")
HERE = os.path.dirname(os.path.abspath(__file__))
# Viaja con el plugin: la copia en caché trae los binarios del repo intactos (supuesto R27 de
# methodology/platform-assumptions.md).
DEFAULT_WAV = os.path.join(os.path.dirname(HERE), "sounds", "neb-chime.wav")
PLAYERS = ("afplay", "paplay", "aplay", "play")      # el mismo orden que los .sh
LOUD_PEAK = 15926   # pico de la versión fuerte: reproduce el chimes-loud.wav histórico muestra por muestra
LOUD_NAME = "chimes-loud.wav"
IS_WINDOWS = os.name == "nt"
DISABLED_RC = 3     # salida de la CLI cuando el hook está apagado en su JSON


def _home(home):
    return os.path.expanduser("~") if home is None else home


def load_config(hook, home=None):
    """El JSON personal del hook como dict; {} si falta o no se puede leer (los scripts usan sus valores
    por defecto en ese caso). utf-8-sig: `Out-File -Encoding utf8` de PowerShell 5.1 escribe BOM."""
    path = os.path.join(_home(home), ".claude", "%s.json" % hook)
    try:
        with open(path, encoding="utf-8-sig") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return {}
    return cfg if isinstance(cfg, dict) else {}


def is_enabled(cfg):
    """Criterio del resolvedor: `enabled` ausente cuenta como encendido; `false`, `null`, `0` y la cadena
    "false" apagan. Los scripts solo coinciden en los booleanos; en la vía directa respetan este criterio
    por la salida DISABLED_RC de la CLI."""
    value = cfg.get("enabled", True)
    return value not in (False, None, 0, "false")


def windows_chimes(env=None):
    env = os.environ if env is None else env
    windir = env.get("WINDIR") or env.get("SystemRoot")
    return os.path.join(windir, "Media", "chimes.wav") if windir else None


def loud_cache(home=None):
    return os.path.join(_home(home), ".claude", "neb-sounds", LOUD_NAME)


def _read_pcm16(path):
    """(params, muestras) de un WAV PCM de 16 bit; ValueError si no lo es o no se puede leer."""
    try:
        with wave.open(path, "rb") as w:
            params = w.getparams()
            if params.sampwidth != 2:
                raise ValueError("%s no es PCM de 16 bit" % path)
            data = w.readframes(params.nframes)
    except (wave.Error, EOFError, OSError) as e:
        raise ValueError("no se puede leer %s (%s)" % (path, e))
    samples = array.array("h")
    samples.frombytes(data[:len(data) - len(data) % 2])
    if sys.byteorder == "big":
        samples.byteswap()
    return params, samples


def _check_source(path):
    """Diagnóstico sin leer las muestras: el encabezado dice PCM de 16 bit. ValueError si no."""
    try:
        with wave.open(path, "rb") as w:
            if w.getsampwidth() != 2:
                raise ValueError("%s no es PCM de 16 bit" % path)
    except (wave.Error, EOFError, OSError) as e:
        raise ValueError("no se puede leer %s (%s)" % (path, e))


def ensure_loud(src, home=None):
    """Ruta de la versión fuerte de `src`, generándola si falta o si `src` es más nueva.
    Ganancia por pico (LOUD_PEAK / pico), con recorte a 16 bit. Escribe a un temporal en la misma carpeta
    y lo sustituye de golpe (os.replace): dos sesiones a la vez o un proceso muerto no dejan un WAV a medias.
    ValueError si la fuente no es PCM de 16 bit o está en silencio."""
    cache = loud_cache(home)
    try:
        if os.path.getmtime(cache) >= os.path.getmtime(src):
            return cache
    except OSError:
        pass
    params, samples = _read_pcm16(src)
    peak = max((abs(s) for s in samples), default=0)
    if peak == 0:
        raise ValueError("%s está en silencio" % src)
    gain = LOUD_PEAK / peak
    out = array.array("h", (max(-32768, min(32767, round(s * gain))) for s in samples))
    if sys.byteorder == "big":
        out.byteswap()
    folder = os.path.dirname(cache)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".chimes-loud-", suffix=".wav", dir=folder)
    try:
        with os.fdopen(fd, "wb") as f, wave.open(f, "wb") as w:
            w.setparams(params)
            w.writeframes(out.tobytes())
        os.replace(tmp, cache)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return cache


def _fallback(reason):
    if os.path.isfile(DEFAULT_WAV):
        return DEFAULT_WAV, reason
    return None, "%s, y falta el sonido por defecto (%s)" % (reason, DEFAULT_WAV)


def resolve(hook, env=None, home=None, generate=True):
    """(ruta | None, motivo | None) del sonido de `hook`.

    ruta None con motivo None: el dev apagó el hook en su JSON (`enabled: false`).
    motivo no None: la configuración no se pudo cumplir; la ruta, si la hay, es el respaldo.
    generate=False (arranque): no escribe nada; para "chimes-loud" valida la fuente y devuelve la
    ruta de la caché aunque todavía no exista."""
    env = os.environ if env is None else env
    cfg = load_config(hook, home)
    if not is_enabled(cfg):
        return None, None
    wav = cfg.get("wav")
    if wav is None or wav in ("", "neb"):
        if os.path.isfile(DEFAULT_WAV):
            return DEFAULT_WAV, None
        return None, "falta el sonido por defecto (%s)" % DEFAULT_WAV
    if not isinstance(wav, str):
        return _fallback("valor de `wav` no reconocido: %r" % (wav,))
    if wav in ("chimes", "chimes-loud"):
        if not IS_WINDOWS:
            return _fallback("el preset `%s` solo existe en Windows" % wav)
        src = windows_chimes(env)
        if not src or not os.path.isfile(src):
            return _fallback("no se encontró el chimes.wav de Windows (%s)" % src)
        if wav == "chimes":
            return src, None
        try:
            if generate:
                return ensure_loud(src, home), None
            _check_source(src)
            return loud_cache(home), None
        except (ValueError, OSError) as e:
            return _fallback("no se pudo generar `chimes-loud`: %s" % e)
    if os.path.isabs(wav):
        if os.path.isfile(wav):
            return wav, None
        return _fallback("no existe %s" % wav)
    return _fallback("valor de `wav` no reconocido: %r" % (wav,))


def player_available(env=None):
    """En POSIX, algún reproductor que los .sh saben usar; en Windows lo da el sistema."""
    if IS_WINDOWS:
        return True
    env = os.environ if env is None else env
    return any(shutil.which(p, path=env.get("PATH")) for p in PLAYERS)


def diagnose(hook, env=None, home=None):
    """Frase para el aviso del arranque, o None si el hook suena como se configuró o está apagado.
    Solo lee."""
    path, reason = resolve(hook, env, home, generate=False)
    if path is None and reason is None:
        return None
    if not player_available(env):
        return "no suena: no hay reproductor de audio en el PATH (%s)" % ", ".join(PLAYERS)
    if reason is None:
        return None
    if path is None:
        return "no suena: %s" % reason
    return "usa el sonido por defecto: %s" % reason


def main(argv):
    """Imprime la ruta y sale con 0; sin ruta, no imprime nada. Sale con DISABLED_RC si el dev apagó el
    hook en su JSON: el script invocado directo sale sin sonar en vez de caer en el sonido por defecto
    (sin `jq`, el .sh no lee `enabled`; el .ps1 toma la cadena "false" como encendido)."""
    if len(argv) != 2 or argv[1] not in HOOKS:
        return 0
    try:
        path, reason = resolve(argv[1])
    except Exception:  # noqa: BLE001 — el hook no se rompe por el resolvedor
        return 0
    if path is None and reason is None:
        return DISABLED_RC
    if path:
        try:
            sys.stdout.write(path + "\n")
        except (OSError, ValueError):
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
