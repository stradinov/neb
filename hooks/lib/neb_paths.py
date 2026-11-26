#!/usr/bin/env python3
"""neb_paths.py — carpeta de datos de Neb y su config.json (desde 8.0.0).

Único resolvedor de dónde guarda Neb lo suyo y de qué dice su configuración. Antes de 8.0.0 todo vivía
suelto en `~/.claude/`; desde 8.0.0 vive en la carpeta de datos:

    <datos>/                 NEB_DATA (ruta absoluta) o, si no, ~/.neb
      config.json            notify.stop · notify.permission · preprocess · language
      compas.md
      neb.db                 (+ -wal/-shm y el candado .neb-migrate.lock)
      approved-plans/
      research/
      backups/
      state/<nombre>/        estado efímero (p. ej. state/preprocess/<session_id>.json)
      cache/<nombre>/        regenerable (p. ej. cache/sounds/chimes-loud.wav)

Lo de Claude Code (settings.json, projects/, plugins/) se queda en `~/.claude` o en CLAUDE_CONFIG_DIR.

`NEB_DATA` se toma solo si es absoluta, con `~` expandido contra el home explícito y la forma `/c/...` de
Git Bash pasada a Windows. Cualquier otro valor se ignora (cae a ~/.neb): una ruta relativa resolvería
distinto según el cwd de quien corre.

Lectura de config.json: utf-8-sig (`Out-File -Encoding utf8` de PowerShell 5.1 escribe BOM). Una llave
ausente, de otro tipo o un archivo ilegible caen al valor por omisión: leer nunca levanta hacia un hook.
Mientras config.json no exista (máquina que todavía no corrió la migración 8.0.0), `load_config` lee los
JSON sueltos anteriores (`~/.claude/notify-on-{stop,permission}.json`, `~/.claude/preprocess.json`) y
`legacy_config_sources` dice cuáles usaría (diagnóstico; la migración guiada 8.0.0 los junta). Residuo de transición: sale en 9.0.0.

Sin dependencias fuera de la biblioteca estándar ni de módulos hermanos: lo importan `_machine`, el
arranque y los hooks.

CLI (salida 0 salvo uso incorrecto, 2):
    neb_paths.py path <nombre>      imprime una ruta: data, config, db, backups, compas, approved-plans,
                                    research, legacy, o state/<x> / cache/<x>
    neb_paths.py config [sección]   imprime la config efectiva (con valores por omisión) como JSON
    neb_paths.py set <sección.llave> <valor-json>
                                    escribe una llave en config.json (lo crea si falta) sin tocar las demás
"""
import copy
import json
import os
import re
import stat
import sys
import tempfile

DATA_ENV = "NEB_DATA"
DATA_DIR_NAME = ".neb"
LEGACY_DIR_NAME = ".claude"
CONFIG_NAME = "config.json"
DB_NAME = "neb.db"
COMPAS_NAME = "compas.md"
BACKUPS_NAME = "backups"
APPROVED_PLANS_NAME = "approved-plans"
RESEARCH_NAME = "research"
CONFIG_SCHEMA = 1

# Valores por omisión. Cada sección de nivel 1 es un dict; config.json solo necesita lo que cambia.
# language: `base` es el idioma (ISO 639-1); las demás perillas en None significan «lo que fije el overlay
# del adoptante o, sin él, el núcleo» (general/communication.md § "Idioma", tooling/redaccion-es.md).
DEFAULTS = {
    "schema": CONFIG_SCHEMA,
    "notify": {
        "stop": {"enabled": True, "wav": None, "min_seconds": 10, "max_chimes": 5, "scaling": "per-minute"},
        "permission": {"enabled": True, "wav": None},
    },
    "preprocess": {"mode": "off", "model": "claude-haiku-4-5-20251001", "prefix": "$$"},
    "language": {
        "base": "es",
        "variedad": None,
        "registro": None,
        "tratamiento": None,
        "permitir_voseo": None,
        "extranjerismos": None,
    },
}

# Tipo de las llaves cuyo valor por omisión es None (sin entrada aquí: texto).
NULLABLE_TYPES = {"language.permitir_voseo": bool}

# Fuentes sueltas de antes de 8.0.0: (archivo en ~/.claude, ruta de la sección en config.json).
LEGACY_SOURCES = (
    ("notify-on-stop.json", ("notify", "stop")),
    ("notify-on-permission.json", ("notify", "permission")),
    ("preprocess.json", ("preprocess",)),
)

_DRIVE_POSIX_RE = re.compile(r"^/[a-zA-Z]/")


# --------------------------------------------------------------------------- rutas

def home_dir(home=None):
    return os.path.expanduser("~") if home is None else home


def _normalize(value, home):
    """NEB_DATA normalizada, o '' si no sirve (vacía o relativa)."""
    value = (value or "").strip()
    if not value:
        return ""
    if value == "~" or value.startswith("~/") or value.startswith("~\\"):
        value = os.path.join(home, value[2:]) if len(value) > 1 else home
    if sys.platform == "win32" and _DRIVE_POSIX_RE.match(value):
        value = value[1].upper() + ":\\" + value[3:].replace("/", "\\")
    if not os.path.isabs(value):
        return ""
    return os.path.normpath(value)


def data_dir(home=None, env=None):
    """Carpeta de datos de Neb: NEB_DATA si es absoluta; si no, <home>/.neb. No la crea."""
    home = home_dir(home)
    env = os.environ if env is None else env
    return _normalize(env.get(DATA_ENV, ""), home) or os.path.join(home, DATA_DIR_NAME)


def legacy_dir(home=None):
    """Carpeta donde Neb guardaba sus datos antes de 8.0.0 (siempre <home>/.claude, no CLAUDE_CONFIG_DIR)."""
    return os.path.join(home_dir(home), LEGACY_DIR_NAME)


def config_path(home=None, env=None):
    return os.path.join(data_dir(home, env), CONFIG_NAME)


def db_path(home=None, env=None):
    return os.path.join(data_dir(home, env), DB_NAME)


def same_path(a, b):
    """True si `a` y `b` nombran lo mismo: igual grafía (abspath + normcase) o, si ambos existen, el mismo archivo o
    carpeta en disco (os.path.samefile: nombre corto 8.3, unidad subst, UNC a la misma unidad, symlink en la ruta,
    mayúsculas en un volumen que no las distingue). Comparar solo la grafía haría que una mudanza tomara una
    carpeta por otra distinta de sí misma."""
    if os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b)):
        return True
    try:
        return os.path.samefile(a, b)
    except (OSError, ValueError):
        return False


def backups_dir(home=None, env=None):
    """<datos>/backups; con NEB_DATA en una carpeta `.claude`, <datos>/neb-backups: `~/.claude/backups/` es de
    Claude Code (misma regla que _migrations.backup_dir)."""
    folder = data_dir(home, env)
    name = "neb-backups" if os.path.basename(folder.rstrip("\\/")).lower() == LEGACY_DIR_NAME else BACKUPS_NAME
    return os.path.join(folder, name)


def compas_path(home=None, env=None):
    return os.path.join(data_dir(home, env), COMPAS_NAME)


def approved_plans_dir(home=None, env=None):
    return os.path.join(data_dir(home, env), APPROVED_PLANS_NAME)


def research_dir(home=None, env=None):
    return os.path.join(data_dir(home, env), RESEARCH_NAME)


def state_dir(name, home=None, env=None):
    return os.path.join(data_dir(home, env), "state", name)


def cache_dir(name, home=None, env=None):
    return os.path.join(data_dir(home, env), "cache", name)


def _is_link(path):
    """Symlink o junction (Windows)."""
    try:
        if os.path.islink(path):
            return True
        st = os.lstat(path)
    except OSError:
        return False
    return bool(getattr(st, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def ensure_dir(path, root=None):
    """Crea `path` (y padres) con 0700 si falta. ValueError si es un enlace o no es carpeta. Con `root` (un
    ancestro de `path`, p. ej. la carpeta de datos), revisa también cada carpeta de `root` a `path`: una carpeta
    de datos enlazada no se cuela por una subcarpeta."""
    chain = [path]
    if root is not None:
        stop = os.path.normcase(os.path.abspath(root))
        cur = os.path.abspath(path)
        while os.path.normcase(cur) != stop:
            parent = os.path.dirname(cur)
            if parent == cur:          # root no es ancestro: solo se revisa `path`
                chain = [path]
                break
            cur = parent
            chain.append(cur)
    for item in chain:
        if _is_link(item):
            raise ValueError(f"{item} es un enlace: Neb no escribe a través de enlaces")
    if not os.path.isdir(path):
        os.makedirs(path, mode=0o700, exist_ok=True)
        if not os.path.isdir(path):
            raise ValueError(f"{path} no es una carpeta")
    return path


def ensure_data_dir(home=None, env=None):
    return ensure_dir(data_dir(home, env))


PATH_NAMES = {
    "data": data_dir,
    "config": config_path,
    "db": db_path,
    "backups": backups_dir,
    "compas": compas_path,
    "approved-plans": approved_plans_dir,
    "research": research_dir,
}


def named_path(name, home=None, env=None):
    """Ruta por nombre (los de PATH_NAMES, `legacy`, `state/<x>` o `cache/<x>`); ValueError si no existe."""
    if name in PATH_NAMES:
        return PATH_NAMES[name](home, env)
    if name == "legacy":
        return legacy_dir(home)
    kind, _, sub = name.partition("/")
    if kind in ("state", "cache") and re.fullmatch(r"[a-z0-9][a-z0-9-]*", sub or ""):
        return (state_dir if kind == "state" else cache_dir)(sub, home, env)
    raise ValueError(f"ruta desconocida: {name}")


# --------------------------------------------------------------------------- config

def _read_json(path):
    """dict del archivo, None si falta; {} si es ilegible o no es un objeto."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            value = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _same_kind(default, value, dotted=""):
    """True si `value` sirve en lugar de `default` (bool no pasa por número; None acepta None o el tipo de
    NULLABLE_TYPES, texto por omisión)."""
    if default is None:
        return value is None or isinstance(value, NULLABLE_TYPES.get(dotted, str))
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, (int, float)):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, type(default))


def _merge(defaults, user, prefix=""):
    """Copia de `defaults` con lo de `user` que tiene el mismo tipo; recursivo en los dicts."""
    out = copy.deepcopy(defaults)
    if not isinstance(user, dict):
        return out
    for key, default in defaults.items():
        if key not in user:
            continue
        value = user[key]
        dotted = prefix + key
        if isinstance(default, dict):
            out[key] = _merge(default, value, dotted + ".")
        elif _same_kind(default, value, dotted):
            out[key] = value
    return out


def _legacy_raw(home):
    """(config armada con los JSON sueltos de ~/.claude, lista de archivos que había)."""
    raw, used = {}, []
    for name, section in LEGACY_SOURCES:
        value = _read_json(os.path.join(legacy_dir(home), name))
        if value is None:
            continue
        used.append(name)
        node = raw
        for part in section[:-1]:
            node = node.setdefault(part, {})
        node[section[-1]] = value
    return raw, used


def legacy_config_sources(home=None, env=None):
    """Los JSON sueltos de antes de 8.0.0 que `load_config` usaría hoy (vacía si config.json existe)."""
    home = home_dir(home)
    if os.path.lexists(config_path(home, env)):
        return []
    return _legacy_raw(home)[1]


def load_config(home=None, env=None):
    """Config efectiva: DEFAULTS con lo que diga config.json (o, si falta, los JSON sueltos anteriores).
    Nunca levanta."""
    home = home_dir(home)
    raw = _read_json(config_path(home, env))
    if raw is None:
        raw = _legacy_raw(home)[0]
    return _merge(DEFAULTS, raw)


def section(name, home=None, env=None):
    """Una sección de la config efectiva por ruta con puntos (`notify.stop`, `preprocess`, `language`)."""
    node = load_config(home, env)
    for part in name.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(name)
        node = node[part]
    return node


def _atomic_write_json(path, value):
    folder = os.path.dirname(path)
    ensure_dir(folder)
    if _is_link(path):
        raise ValueError(f"{path} es un enlace: Neb no escribe a través de enlaces")
    fd, tmp = tempfile.mkstemp(prefix=CONFIG_NAME + ".", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def set_value(dotted, value, home=None, env=None):
    """Escribe una llave de nivel 2 o 3 (`preprocess.mode`, `notify.stop.wav`) en config.json, sin tocar
    las demás. La llave debe existir en DEFAULTS y el valor ser del mismo tipo. Si config.json falta, lo
    crea con `schema` y lo que dijeran los JSON sueltos de antes de 8.0.0 (no los borra: eso es de la
    migración). ValueError si la llave o el valor no sirven, o si config.json no es JSON legible
    (no se pisa lo que el dev escribió)."""
    parts = dotted.split(".")
    node = DEFAULTS
    for part in parts:
        if not isinstance(node, dict) or part not in node or part == "schema":
            raise ValueError(f"llave desconocida: {dotted}")
        node = node[part]
    if isinstance(node, dict):
        raise ValueError(f"{dotted} es una sección: escribe una de sus llaves")
    if not _same_kind(node, value, dotted):
        raise ValueError(f"valor de otro tipo para {dotted}")
    home = home_dir(home)
    path = config_path(home, env)
    current = _read_json(path)
    if current is None:
        # Nace config.json: lleva lo que decían los JSON sueltos, que load_config deja de leer desde ahora.
        current = {"schema": CONFIG_SCHEMA, **_legacy_raw(home)[0]}
    elif current == {} and os.path.getsize(path) > 0:
        try:
            with open(path, encoding="utf-8-sig") as f:
                json.load(f)
        except (OSError, ValueError):
            raise ValueError(f"{path} no es JSON legible: corrígelo a mano antes de escribir")
    target = current
    for part in parts[:-1]:
        child = target.get(part)
        if not isinstance(child, dict):
            child = {}
            target[part] = child
        target = child
    target[parts[-1]] = value
    _atomic_write_json(path, current)
    return path


# --------------------------------------------------------------------------- CLI

def main(argv):
    if not argv:
        print(__doc__.split("CLI", 1)[1].strip(), file=sys.stderr)
        return 2
    cmd, args = argv[0], argv[1:]
    try:
        if cmd == "path" and len(args) == 1:
            print(named_path(args[0]))
            return 0
        if cmd == "config" and len(args) <= 1:
            value = section(args[0]) if args else load_config()
            print(json.dumps(value, ensure_ascii=False, indent=2))
            return 0
        if cmd == "set" and len(args) == 2:
            print(set_value(args[0], json.loads(args[1])))
            return 0
    except (ValueError, KeyError) as e:
        print(f"neb_paths: {e}", file=sys.stderr)
        return 2
    print(f"neb_paths: uso incorrecto: {' '.join(argv)}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
