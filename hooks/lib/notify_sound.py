#!/usr/bin/env python3
"""notify_sound.py — qué sonido y con qué valores suenan los hooks notify-on-stop y notify-on-permission.

Único resolvedor de la configuración de los dos hooks: las secciones `notify.stop` y `notify.permission`
del config.json de la carpeta de datos, que lee hooks/lib/neb_paths.py (con su respaldo a los JSON sueltos
`~/.claude/notify-on-{stop,permission}.json` mientras config.json no exista). Lo usan:
  • hooks/neb-hook.py (despachador del plugin): pasa los valores efectivos al script en variables de
    entorno (`hook_env`: NEB_NOTIFY_WAV, NEB_NOTIFY_ENABLED, NEB_NOTIFY_MIN_SECONDS, …);
  • los .ps1/.sh invocados directo (entradas de settings.json anteriores a 6.15.0), por la CLI `config`;
  • bootstrap/neb-bootstrap-context.py: el aviso del arranque, en modo diagnóstico (no escribe).

Valores de `wav` (lineamiento: tooling/notify-on-stop.md):
  null / ausente / "neb"  → hooks/sounds/neb-chime.wav (CC0, en todo SO)
  "chimes"                → %WINDIR%\\Media\\chimes.wav (solo Windows)
  "chimes-loud"           → chimes.wav amplificado, generado en local en <datos>/cache/sounds/ (solo Windows)
  ruta completa           → esa ruta, si existe: en Windows, con unidad o UNC (`C:/…`, `\\\\srv\\rec\\…`);
                            fuera, empieza con `/`. En Windows, `/x.wav` (sin unidad) tiene motivo propio
Cualquier otro caso cae en neb-chime.wav con su motivo. No se redistribuye audio de terceros sin licencia:
chimes.wav se lee de la máquina del dev y la versión fuerte se genera ahí.
Un valor de otro tipo que el de neb_paths.DEFAULTS (`"enabled": "false"`, `"wav": 42`) cuenta como ausente:
es el criterio de toda la config.json.

CLI:
  notify_sound.py <hook>          imprime la ruta resuelta (o nada) y sale con 0; con el hook apagado no
                                  imprime nada y sale con 3 (DISABLED_RC)
  notify_sound.py config <hook>   imprime la config efectiva, una línea `llave=valor` por campo: enabled
                                  (true|false), wav (vacío si no hay ruta) y, en notify-on-stop,
                                  min_seconds, max_chimes y scaling ya normalizados. Sale con 0. Formato
                                  pensado para leerse sin jq en bash y con `-split '=', 2` en PowerShell.
Solo stdlib. Defensivo: nunca levanta hacia el hook.
"""
import array
import ntpath
import os
import posixpath
import shutil
import sys
import tempfile
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
# El arranque carga este módulo por ruta (importlib) sin hooks/lib en sys.path: sin esto, `import neb_paths`
# fallaría y el aviso de sonido desaparecería en silencio.
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import neb_paths  # noqa: E402

# Hook → sección de config.json.
SECTIONS = {"notify-on-stop": "notify.stop", "notify-on-permission": "notify.permission"}
HOOKS = tuple(SECTIONS)
# Viaja con el plugin: la copia en caché trae los binarios del repo intactos (supuesto R27 de
# methodology/platform-assumptions.md).
DEFAULT_WAV = os.path.join(os.path.dirname(HERE), "sounds", "neb-chime.wav")
PLAYERS = ("afplay", "paplay", "aplay", "play")      # el mismo orden que los .sh
LOUD_PEAK = 15926   # pico de la versión fuerte: reproduce el chimes-loud.wav histórico muestra por muestra
LOUD_NAME = "chimes-loud.wav"
SOUNDS_CACHE = "sounds"   # <datos>/cache/sounds/
IS_WINDOWS = os.name == "nt"
DISABLED_RC = 3     # salida de la CLI `<hook>` cuando el hook está apagado
# Acotamiento de los valores de notify-on-stop (los scripts lo repiten como red de seguridad).
MAX_CHIMES_RANGE = (1, 20)
SCALINGS = ("fixed", "per-minute")
# Campo de la config efectiva → variable de entorno con que el despachador se lo pasa al script.
ENV_VARS = {
    "enabled": "NEB_NOTIFY_ENABLED",
    "wav": "NEB_NOTIFY_WAV",
    "min_seconds": "NEB_NOTIFY_MIN_SECONDS",
    "max_chimes": "NEB_NOTIFY_MAX_CHIMES",
    "scaling": "NEB_NOTIFY_SCALING",
}


def _full_path(wav):
    """True si `wav` es una ruta completa en la plataforma de IS_WINDOWS, igual con cualquier Python: en Windows,
    con unidad o UNC y separador tras ella (`C:/x.wav`, `\\\\srv\\rec\\x.wav`; no `/x.wav` ni `C:x.wav`); fuera,
    empieza con `/`. No usa os.path.isabs: desde Python 3.13, en Windows da False para `/x.wav`, y con 3.12 True."""
    if not IS_WINDOWS:
        return posixpath.isabs(wav)
    drive, rest = ntpath.splitdrive(wav)
    return bool(drive) and rest[:1] in ("/", "\\")


def _rooted_without_drive(wav):
    """En Windows, una ruta con raíz pero sin unidad (`/x.wav`, `\\x.wav`): su unidad depende de dónde corre el hook.
    No cuenta lo que empieza con dos separadores (`//x.wav`, `\\\\srv`, UNC incompleta): hasta Python 3.10 su unidad
    sale vacía y desde 3.11 no; sin esta excepción el motivo cambiaría con la versión."""
    sep = ("/", "\\")
    return IS_WINDOWS and not ntpath.splitdrive(wav)[0] and wav[:1] in sep and wav[1:2] not in sep


def load_config(hook, home=None, env=None):
    """La sección del hook en la config efectiva (valores por omisión incluidos) como dict; {} si el hook
    no es de sonido. Nunca levanta: neb_paths cae a los valores por omisión ante un config.json ilegible."""
    name = SECTIONS.get(hook)
    if name is None:
        return {}
    try:
        cfg = neb_paths.section(name, home, env)
    except Exception:  # noqa: BLE001 — el hook no se rompe por la config
        return {}
    return dict(cfg) if isinstance(cfg, dict) else {}


def is_enabled(cfg):
    """Criterio del resolvedor: `enabled` ausente cuenta como encendido; `false`, `null`, `0` y la cadena
    "false" apagan. Con la config de neb_paths solo llega un booleano; el criterio amplio queda para quien
    pase un dict propio."""
    value = cfg.get("enabled", True)
    return value not in (False, None, 0, "false")


def windows_chimes(env=None):
    env = os.environ if env is None else env
    windir = env.get("WINDIR") or env.get("SystemRoot")
    return os.path.join(windir, "Media", "chimes.wav") if windir else None


def loud_cache(home=None, env=None):
    """Ruta de la versión fuerte: <datos>/cache/sounds/chimes-loud.wav. No la crea."""
    return os.path.join(neb_paths.cache_dir(SOUNDS_CACHE, home, env), LOUD_NAME)


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


def ensure_loud(src, home=None, env=None):
    """Ruta de la versión fuerte de `src`, generándola si falta o si `src` es más nueva.
    Ganancia por pico (LOUD_PEAK / pico), con recorte a 16 bit. Escribe a un temporal en la misma carpeta
    y lo sustituye de golpe (os.replace): dos sesiones a la vez o un proceso muerto no dejan un WAV a medias.
    La carpeta la crea neb_paths.ensure_dir (0700, rechaza enlaces).
    ValueError si la fuente no es PCM de 16 bit o está en silencio, o si la carpeta es un enlace."""
    cache = loud_cache(home, env)
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
    neb_paths.ensure_dir(folder, root=neb_paths.data_dir(home, env))
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


def _resolve_cfg(cfg, env, home, generate):
    """resolve() sobre una config ya leída (effective() la lee una sola vez)."""
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
                return ensure_loud(src, home, env), None
            _check_source(src)
            return loud_cache(home, env), None
        except (ValueError, OSError) as e:
            return _fallback("no se pudo generar `chimes-loud`: %s" % e)
    if _full_path(wav):
        if os.path.isfile(wav):
            return wav, None
        return _fallback("no existe %s" % wav)
    if _rooted_without_drive(wav):
        return _fallback("en Windows la ruta de `wav` lleva la unidad (C:/…): %s" % wav)
    return _fallback("valor de `wav` no reconocido: %r" % (wav,))


def resolve(hook, env=None, home=None, generate=True):
    """(ruta | None, motivo | None) del sonido de `hook`.

    ruta None con motivo None: el dev apagó el hook en su config (`enabled: false`).
    motivo no None: la configuración no se pudo cumplir; la ruta, si la hay, es el respaldo.
    generate=False (arranque): no escribe nada; para "chimes-loud" valida la fuente y devuelve la
    ruta de la caché aunque todavía no exista.
    `env` decide WINDIR/SystemRoot y NEB_DATA (la carpeta de datos)."""
    env = os.environ if env is None else env
    return _resolve_cfg(load_config(hook, home, env), env, home, generate)


def _int(value, default):
    """Entero de un número de la config (un float se trunca); `default` si no es número."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    try:
        return int(value)
    except (ValueError, OverflowError):   # nan, inf
        return default


def effective(hook, env=None, home=None, generate=True):
    """Config efectiva y normalizada del hook, con la ruta del sonido ya resuelta:
    {"enabled": bool, "wav": ruta | None, "reason": motivo | None} y, en notify-on-stop, además
    min_seconds (>= 0), max_chimes (acotado a MAX_CHIMES_RANGE) y scaling (uno de SCALINGS; otro valor cae
    a "per-minute"). Con el hook apagado: enabled False y wav None. Un hook que no es de sonido: {}."""
    env = os.environ if env is None else env
    if hook not in SECTIONS:
        return {}
    cfg = load_config(hook, home, env)
    wav, reason = _resolve_cfg(cfg, env, home, generate)
    out = {"enabled": is_enabled(cfg), "wav": wav, "reason": reason}
    if hook == "notify-on-stop":
        stop = neb_paths.DEFAULTS["notify"]["stop"]
        lo, hi = MAX_CHIMES_RANGE
        scaling = cfg.get("scaling")
        out.update(
            min_seconds=max(0, _int(cfg.get("min_seconds"), stop["min_seconds"])),
            max_chimes=min(hi, max(lo, _int(cfg.get("max_chimes"), stop["max_chimes"]))),
            scaling=scaling if scaling in SCALINGS else "per-minute",
        )
    return out


def _text(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    return "" if value is None else str(value)


def hook_env(values):
    """Variables de entorno (ENV_VARS) para el script con los valores de effective(); `reason` no viaja."""
    return {var: _text(values[key]) for key, var in ENV_VARS.items() if key in values}


def config_lines(values):
    """Las líneas `llave=valor` de la CLI `config`, en el orden de ENV_VARS."""
    return ["%s=%s" % (key, _text(values[key])) for key in ENV_VARS if key in values]


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


def _write(lines):
    # "\n" literal por stdout.buffer: en Windows el modo texto escribiría "\r\n" y el `\r` quedaría pegado
    # al valor que lee bash.
    try:
        data = "".join(line + "\n" for line in lines).encode("utf-8")
        sys.stdout.flush()
        buf = getattr(sys.stdout, "buffer", None)
        if buf is not None:
            buf.write(data)
            buf.flush()
        else:
            sys.stdout.write(data.decode("utf-8"))
    except (OSError, ValueError):
        pass


def main(argv):
    """CLI (ver el docstring del módulo). `<hook>`: imprime la ruta y sale con 0; sin ruta, no imprime
    nada; sale con DISABLED_RC si el dev apagó el hook, para que el script invocado directo salga sin sonar
    en vez de caer en el sonido por defecto. `config <hook>`: las líneas `llave=valor` de effective()."""
    if len(argv) == 3 and argv[1] == "config":
        if argv[2] not in HOOKS:
            return 0
        try:
            values = effective(argv[2])
        except Exception:  # noqa: BLE001 — el hook no se rompe por el resolvedor
            return 0
        _write(config_lines(values))
        return 0
    if len(argv) != 2 or argv[1] not in HOOKS:
        return 0
    try:
        path, reason = resolve(argv[1])
    except Exception:  # noqa: BLE001 — el hook no se rompe por el resolvedor
        return 0
    if path is None and reason is None:
        return DISABLED_RC
    if path:
        _write([path])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
