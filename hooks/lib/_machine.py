#!/usr/bin/env python3
"""
_machine.py — catálogo de operaciones de los pasos guiados de catálogo (Neb, desde 6.49.0).

Un paso guiado de catálogo es un dato: el nombre de una operación de aquí y sus argumentos. Cada operación
trae cuatro funciones:

    validate(**args)                   al cargar la migración: ValueError si los argumentos no sirven
    detect(ctx, **args) -> bool        ¿hay algo que hacer? Solo lee
    mode(ctx, **args)   -> "solo" | "dev"
                                       "solo": la corrida deja con qué deshacerlo y corre sin preguntar (M5);
                                       "dev": no deja respaldo y pide al dev (`apply --include`)
    apply(ctx, allow_no_backup=False, **args) -> {"estado", "respaldo", "detalle"}
                                       estado: aplicado | sin-cambio | manual | fallo

Nada aquí imprime ni guarda el valor de una variable. Documento: tooling/migrations.md § "Migración guiada".
"""

import glob
import importlib.util
import json
import os
import re
import stat
import sys
import time
from datetime import datetime, timezone

import _migrations
import neb_paths

_HERE = os.path.dirname(os.path.abspath(__file__))

USER_ENV_NAME_RE = re.compile(r"NEB_[A-Z0-9_]+")
ENV_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
CRED_URL_RE = re.compile(r"://\S*[@?#]")      # usuario:clave@, token@, ?token=, #… tras el esquema (conservador)
SECRET_KEY_RE = re.compile(r"TOKEN|SECRET|PASS|KEY|AUTH|CRED|WEBHOOK", re.I)   # nombre que suena a secreto
SETTINGS_FILES = ("settings.json", "settings.local.json")
SETTINGS_BACKUP_PREFIX = "settings-env."
# <carpeta de la base>/backups/ (desde 8.0.0; la regla completa, en _migrations.backup_dir).
BACKUP_DIR_NAME = "backups"


def _stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


_UT = None


def _usage_tracker():
    """update_json y DELETE de usage-tracker.py (nombre con guion: se carga por ruta)."""
    global _UT
    if _UT is None:
        spec = importlib.util.spec_from_file_location("neb_usage_tracker_machine",
                                                      os.path.join(_HERE, "usage-tracker.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _UT = mod
    return _UT


def is_link(path):
    """Enlace simbólico o junction (Path.is_junction es de 3.12). Otros reparse points no son enlaces."""
    try:
        if os.path.islink(path):
            return True
        tag = getattr(os.lstat(path), "st_reparse_tag", 0)
        return tag in (getattr(stat, "IO_REPARSE_TAG_SYMLINK", 0xA000000C),
                       getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003))
    except FileNotFoundError:
        return False
    except OSError:
        return True


# --------------------------------------------------------------------------- contexto

class Ctx:
    """Lo que una operación o un paso guiado necesita de la máquina. Las pruebas inyectan home, db_path, config_dir,
    data_dir y user_env.

    claude_dir   <home>/.claude: lo de Claude Code y lo que los pasos guiados de 7.x miran ahí
    legacy_dir   la carpeta donde Neb guardaba sus datos hasta 7.x (neb_paths.legacy_dir: <home>/.claude, nunca
                 CLAUDE_CONFIG_DIR); el origen de la mudanza de 8.0.0
    data_dir     la carpeta de datos de Neb (neb_paths.data_dir: NEB_DATA absoluta o <home>/.neb; desde 8.0.0)
    config_dir   el dir de configuración de Claude Code, donde viven los settings (CLAUDE_CONFIG_DIR o
                 <home>/.claude, supuesto R26)
    db_path      la base (por omisión <data_dir>/neb.db, la de _db_shared.resolve_db_path)
    backups_dir  <carpeta de la base>/backups/ (_migrations.backup_dir)"""

    def __init__(self, home=None, db_path=None, user_env=None, config_dir=None, data_dir=None):
        self.home = home or os.path.expanduser("~")
        self.claude_dir = os.path.join(self.home, ".claude")
        self.legacy_dir = neb_paths.legacy_dir(self.home)
        self.data_dir = data_dir or neb_paths.data_dir(self.home)
        self.config_dir = config_dir or os.environ.get("CLAUDE_CONFIG_DIR") or self.claude_dir
        self.db_path = db_path or os.path.join(self.data_dir, neb_paths.DB_NAME)
        self.backups_dir = _migrations.backup_dir(self.db_path)
        self.user_env = user_env if user_env is not None else default_user_env()
        self.started = time.time()            # inicio de la corrida: la poda no toca respaldos de esta corrida
        self.exclusivo_ok = lambda: None      # el programa la fija para un paso exclusivo (segunda comprobación)

    def settings_path(self, ruta=None):
        return os.path.join(self.config_dir, ruta or "settings.json")


def _private_dir(path):
    if is_link(path):
        raise OSError(f"{path} es un enlace: no se escribe un respaldo ahí")
    os.makedirs(path, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


# --------------------------------------------------------------------------- settings_env_remove

def _read_env(path):
    """Bloque env de un settings.json, o {} si el archivo no existe. ValueError si no es JSON válido."""
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8-sig") as fh:
        data = json.load(fh)
    env = data.get("env") if isinstance(data, dict) else None
    return env if isinstance(env, dict) else {}


def _present(env, claves):
    return [k for k in claves if k in env]


def _needs_dev(env, present, secretas):
    """Sin respaldo (pide al dev) si la clave es secreta o lo parece, o si el valor parece llevar una
    credencial en la URL: un olvido en `secretas` no deja un secreto copiado en la carpeta de respaldos."""
    return any(k in secretas or SECRET_KEY_RE.search(k) for k in present) or \
        any(isinstance(env[k], str) and CRED_URL_RE.search(env[k]) for k in present)


def settings_env_validate(claves, secretas=(), ruta=None):
    if not isinstance(claves, (list, tuple)) or not claves or \
            not all(isinstance(k, str) and ENV_KEY_RE.fullmatch(k) for k in claves):
        raise ValueError("settings_env_remove: `claves` es una lista no vacía de nombres de variable")
    if not isinstance(secretas, (list, tuple)) or not all(k in claves for k in secretas):
        raise ValueError("settings_env_remove: cada clave de `secretas` está en `claves`")
    if ruta is not None and ruta not in SETTINGS_FILES:
        raise ValueError("settings_env_remove: `ruta` es settings.json o settings.local.json del dir de "
                         "configuración")


def settings_env_detect(ctx, claves, secretas=(), ruta=None):
    return bool(_present(_read_env(ctx.settings_path(ruta)), claves))


def settings_env_mode(ctx, claves, secretas=(), ruta=None):
    env = _read_env(ctx.settings_path(ruta))
    return "dev" if _needs_dev(env, _present(env, claves), secretas) else "solo"


def settings_env_apply(ctx, claves, secretas=(), ruta=None, allow_no_backup=False):
    """Quita claves del bloque env con update_json (marca de borrado verificada). El respaldo guarda solo los
    pares quitados, nunca el archivo (llevaría cualquier secreto). Con una clave secreta o credenciales en la
    URL no hay respaldo: corre solo con allow_no_backup (el dev respondió en el menú). Si el archivo cambia
    entre la lectura y la escritura, no escribe."""
    path = ctx.settings_path(ruta)
    try:
        env = _read_env(path)
    except (OSError, ValueError) as e:
        return {"estado": "fallo", "respaldo": None, "detalle": f"no se pudo leer {path}: {type(e).__name__}"}
    present = _present(env, claves)
    if not present:
        return {"estado": "sin-cambio", "respaldo": None, "detalle": "ninguna clave presente"}
    pairs = {k: env[k] for k in present}
    no_backup = _needs_dev(env, present, secretas)
    if no_backup and not allow_no_backup:
        return {"estado": "fallo", "respaldo": None,
                "detalle": "una clave es secreta o trae credenciales: pide al dev (sin respaldo)"}
    ctx_check = ctx.exclusivo_ok()             # paso exclusivo: segunda comprobación antes de escribir
    if ctx_check:
        return {"estado": "pendiente", "respaldo": None, "detalle": ctx_check}
    backup = None
    if not no_backup:
        try:
            backup = _write_settings_backup(ctx, path, pairs)
        except (OSError, ValueError) as e:
            return {"estado": "fallo", "respaldo": None,
                    "detalle": f"respaldo fallido, no se tocó nada: {type(e).__name__}: {getattr(e, 'strerror', '') or e}"}
    ut = _usage_tracker()

    def mutate(data):
        block = data.get("env")
        if not isinstance(block, dict) or any(block.get(k, ut.DELETE) != v for k, v in pairs.items()):
            raise ValueError("el settings cambió mientras corría el paso; se reintenta en el siguiente inicio de "
                             "sesión (o con /neb:migrate)")
        for k in present:
            del block[k]
        return [("env", k, ut.DELETE) for k in present]
    changes, err = ut.update_json(path, mutate)
    if err:
        if backup:
            _remove_quiet(backup)
        return {"estado": "fallo", "respaldo": None, "detalle": err}
    if backup:
        _prune_settings_backups(ctx)
    return {"estado": "aplicado", "respaldo": backup,
            "detalle": "quitadas de env: " + ", ".join(k for _e, k, _v in changes)}


def _write_settings_backup(ctx, settings, pairs):
    """Archivo nuevo (O_EXCL) con permiso solo para el usuario donde el sistema lo respeta; en Windows hereda
    los permisos de la carpeta, los mismos que el settings.json."""
    _private_dir(ctx.backups_dir)
    dest = os.path.join(ctx.backups_dir, f"{SETTINGS_BACKUP_PREFIX}{_stamp()}.json")
    payload = {"settings": settings, "env": pairs}
    fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    with open(dest, encoding="utf-8") as fh:
        if json.load(fh) != payload:
            raise ValueError("el respaldo no se leyó igual")
    return dest


def _prune_settings_backups(ctx):
    """Queda el respaldo más reciente de corridas anteriores fuera; los de esta corrida se conservan todos."""
    for p in glob.glob(os.path.join(glob.escape(ctx.backups_dir), SETTINGS_BACKUP_PREFIX + "*.json")):
        try:
            if os.path.getmtime(p) < ctx.started - 1:
                os.remove(p)
        except OSError:
            pass


def _remove_quiet(path):
    try:
        os.remove(path)
    except OSError:
        pass


# --------------------------------------------------------------------------- user_env_remove

class WindowsUserEnv:
    """Variables de entorno de Windows en el registro. Presencia sin leer el valor (RegQueryValueExW sin
    búfer); borrado con winreg y aviso al sistema con SendMessageTimeoutW, sin terminal."""
    kind = "windows"
    _MACHINE_KEY = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"

    def __init__(self):
        import winreg                       # noqa: F401 — falla fuera de Windows
        self._winreg = winreg

    def _has(self, root, subkey, name):
        import ctypes
        from ctypes import wintypes
        w = self._winreg
        try:
            key = w.OpenKey(root, subkey, 0, w.KEY_QUERY_VALUE)
        except OSError:
            return False
        try:
            fn = ctypes.windll.advapi32.RegQueryValueExW
            fn.argtypes = [wintypes.HKEY, wintypes.LPCWSTR, wintypes.LPDWORD, wintypes.LPDWORD,
                           ctypes.c_void_p, wintypes.LPDWORD]
            fn.restype = wintypes.LONG
            size = wintypes.DWORD(0)
            return fn(wintypes.HKEY(key.handle), name, None, None, None, ctypes.byref(size)) == 0
        finally:
            key.Close()

    def present_user(self, name):
        return self._has(self._winreg.HKEY_CURRENT_USER, "Environment", name)

    def present_machine(self, name):
        return self._has(self._winreg.HKEY_LOCAL_MACHINE, self._MACHINE_KEY, name)

    def delete_user(self, name):
        w = self._winreg
        with w.OpenKey(w.HKEY_CURRENT_USER, "Environment", 0, w.KEY_SET_VALUE) as key:
            w.DeleteValue(key, name)

    def broadcast(self):
        try:
            import ctypes
            from ctypes import wintypes
            fn = ctypes.windll.user32.SendMessageTimeoutW
            fn.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPCWSTR, wintypes.UINT,
                           wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
            fn.restype = ctypes.c_ssize_t
            result = ctypes.c_size_t(0)
            fn(wintypes.HWND(0xFFFF), 0x001A, 0, "Environment", 0x0002, 5000, ctypes.byref(result))
        except Exception:  # noqa: BLE001 — el aviso es accesorio: una terminal nueva lee el registro igual
            pass


class PosixUserEnv:
    """Fuera de Windows no hay registro: la presencia se lee del entorno de este proceso y el borrado es
    manual. `[asumido]` el entorno de un hook o del Bash de Claude Code incluye el bloque env de settings.json:
    por eso user_env_detect descarta las variables que el settings declara."""
    kind = "posix"

    def present_user(self, name):
        return name in os.environ

    def present_machine(self, name):
        return False

    def delete_user(self, name):
        raise OSError("fuera de Windows no se borra por programa")

    def broadcast(self):
        pass


def default_user_env():
    if sys.platform == "win32":
        try:
            return WindowsUserEnv()
        except ImportError:
            pass
    return PosixUserEnv()


def _valid_name(nombre):
    return isinstance(nombre, str) and USER_ENV_NAME_RE.fullmatch(nombre) is not None


def user_env_validate(nombre):
    if not _valid_name(nombre):
        raise ValueError("user_env_remove: `nombre` cumple NEB_[A-Z0-9_]+ completo")


def user_env_detect(ctx, nombre):
    if not _valid_name(nombre):
        return False
    env = ctx.user_env
    if env.kind != "windows":
        for ruta in SETTINGS_FILES:
            try:
                if nombre in _read_env(ctx.settings_path(ruta)):
                    return False               # viene de un settings, no del perfil del shell
            except (OSError, ValueError):
                pass
    return env.present_user(nombre) or env.present_machine(nombre)


def user_env_mode(ctx, nombre):
    return "dev"                           # el valor no se guarda en ningún lado: nunca corre solo


def user_env_apply(ctx, nombre, allow_no_backup=False):
    if not _valid_name(nombre):
        return {"estado": "fallo", "respaldo": None, "detalle": "nombre fuera del patrón NEB_[A-Z0-9_]+"}
    if not allow_no_backup:
        return {"estado": "fallo", "respaldo": None, "detalle": "quitar una variable de usuario pide al dev"}
    env = ctx.user_env
    if env.kind != "windows":
        return {"estado": "manual", "respaldo": None,
                "detalle": f"quita `{nombre}` de tu perfil de shell (~/.bashrc, ~/.zshrc, ~/.profile…) y abre "
                           "una terminal nueva; si no quieres hacerlo, responde «No aplicarlo»"}
    if env.present_machine(nombre):
        return {"estado": "manual", "respaldo": None,
                "detalle": f"`{nombre}` está a nivel de máquina: quítala en Variables de entorno del sistema "
                           "(pide permisos de administrador); si no quieres hacerlo, responde «No aplicarlo»"}
    if not env.present_user(nombre):
        return {"estado": "sin-cambio", "respaldo": None, "detalle": f"`{nombre}` no está"}
    ctx_check = ctx.exclusivo_ok()
    if ctx_check:
        return {"estado": "pendiente", "respaldo": None, "detalle": ctx_check}
    try:
        env.delete_user(nombre)
    except FileNotFoundError:                  # otra sesión la quitó entre la detección y el borrado
        return {"estado": "sin-cambio", "respaldo": None, "detalle": f"`{nombre}` ya no está"}
    except OSError as e:
        return {"estado": "fallo", "respaldo": None,
                "detalle": f"no se pudo quitar `{nombre}`: {getattr(e, 'strerror', '') or type(e).__name__}"}
    env.broadcast()
    if env.present_user(nombre):
        return {"estado": "fallo", "respaldo": None, "detalle": f"`{nombre}` sigue en el registro"}
    return {"estado": "aplicado", "respaldo": None,
            "detalle": f"`{nombre}` quitada; las sesiones y terminales ya abiertas la conservan hasta reiniciarse"}


# --------------------------------------------------------------------------- catálogo

class Op:
    def __init__(self, validate, detect, mode, apply):
        self.validate, self.detect, self.mode, self.apply = validate, detect, mode, apply


OPS = {
    "settings_env_remove": Op(settings_env_validate, settings_env_detect, settings_env_mode, settings_env_apply),
    "user_env_remove": Op(user_env_validate, user_env_detect, user_env_mode, user_env_apply),
}
