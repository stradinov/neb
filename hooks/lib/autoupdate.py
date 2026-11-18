#!/usr/bin/env python3
"""autoupdate.py — actualización automática del plugin de Neb: estado y decisión del usuario.

Claude Code trae apagada la actualización automática de un marketplace de terceros y el autor no puede
encenderla desde `marketplace.json` (supuesto R28 de methodology/platform-assumptions.md). La decide la
clave `autoUpdate` de la entrada del marketplace, en este orden: `extraKnownMarketplaces.<marketplace>` de
un archivo de settings y, si ahí falta, `plugins/known_marketplaces.json` (mismo supuesto R28; dónde están
los archivos, R26). De los archivos de settings, este script solo lee y escribe el de usuario. Sin la clave
en ninguno, la decisión no está tomada; el arranque la ofrece (bootstrap/neb-bootstrap-context.py) solo si
el settings trae la entrada del marketplace, que es donde `enable` y `disable` escriben. Un cambio rige
desde la siguiente sesión (supuesto R25).

El marketplace y el dir de configuración salen de la ruta del propio script en el caché de plugins,
`<config>/plugins/cache/<marketplace>/<plugin>/<versión>/` (supuesto R27); fuera del caché no aplica. Tampoco
si el dir que sale de la ruta no es el dir de configuración en uso, CLAUDE_CONFIG_DIR o ~/.claude (supuesto
R26): CLAUDE_CODE_PLUGIN_CACHE_DIR fija otra raíz de plugins (R27) y el settings ya no se deduce de la ruta.

Uso:
  autoupdate.py status     estado y de dónde sale; no escribe
  autoupdate.py enable     deja `autoUpdate: true` en la entrada del marketplace del settings de usuario; si el
                           proceso corre con DISABLE_AUTOUPDATER (la app de escritorio, supuesto R29), también
                           `FORCE_AUTOUPDATE_PLUGINS: "1"` en `env`
  autoupdate.py disable    deja `autoUpdate: false`; no toca `env`

`enable` y `disable` respaldan el settings (`settings.json.bak-neb-<AAAAMMDD-HHMMSS>`) antes de escribir y
no escriben si nada cambia. Si el settings no existe o no trae la entrada del marketplace, o si alguno de los
dos archivos no se puede leer, rechazan sin escribir y dicen cómo dejarlo a mano. Lo que escriben conserva el
contenido, el BOM, los fines de línea y la sangría; un settings minificado o con escapes `\\u` queda con el
mismo contenido y otro texto.
Salida: 0 hecho, sin cambios o `status` · 1 rechazado, o `enable`/`disable` fuera del caché · 2 uso.
"""
import copy
import importlib.util
import json
import os
import re
import shutil
import sys
import time

UNDECIDED, ON, OFF, NA = "sin decidir", "encendida", "apagada", "no aplica"
SETTINGS = "settings.json"
KNOWN = "known_marketplaces.json"
MARKETPLACES, KEY, FORCE = "extraKnownMarketplaces", "autoUpdate", "FORCE_AUTOUPDATE_PLUGINS"
REJECTED = "No se escribió nada: "
# Apagan la actualización de plugins igual que DISABLE_AUTOUPDATER (R29), pero son más estrictas y las pone
# el usuario o su organización: `enable` no las contrarresta con FORCE; `status` lo dice.
STRICTER = ("DISABLE_UPDATES", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC")
CACHE_DIR_VAR = "CLAUDE_CODE_PLUGIN_CACHE_DIR"


class _NoChange(ValueError):
    """Nada que cambiar: `update_json` no escribe si `mutate` lanza un ValueError."""

# <config>/plugins/cache/<marketplace>/<plugin>/<versión>/…; el nombre acotado: va a dar al arranque.
_CACHE_RE = re.compile(
    r"^(.+)[/\\]plugins[/\\]cache[/\\]([A-Za-z0-9][A-Za-z0-9._-]{0,39})[/\\][^/\\]+[/\\][^/\\]+[/\\]")


def marketplace_of(path):
    """(dir de configuración, marketplace) del plugin instalado al que pertenece path; None fuera del caché."""
    m = _CACHE_RE.match(os.path.abspath(path)) if path else None
    return (m.group(1), m.group(2)) if m else None


def _read(path):
    """(objeto, ok): {} si el archivo no existe; ok es False si existe y no es un objeto JSON legible."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}, True
    except (OSError, ValueError):
        return None, False
    return (data, True) if isinstance(data, dict) else (None, False)


def _entry(data, *keys):
    for key in keys:
        data = data.get(key) if isinstance(data, dict) else None
    return data if isinstance(data, dict) else None


def lookup(cfg, marketplace):
    """(estado, archivo que lo decide): manda el settings de usuario; si no trae la clave, known_marketplaces.json.
    `no aplica` si un archivo no se puede leer o ninguno conoce el marketplace."""
    settings, ok_settings = _read(os.path.join(cfg, SETTINGS))
    known, ok_known = _read(os.path.join(cfg, "plugins", KNOWN))
    if not (ok_settings and ok_known):
        return NA, None
    entries = ((SETTINGS, _entry(settings, MARKETPLACES, marketplace)), (KNOWN, _entry(known, marketplace)))
    if all(entry is None for _, entry in entries):
        return NA, None
    for source, entry in entries:
        value = (entry or {}).get(KEY)
        if isinstance(value, bool):
            return (ON if value else OFF), source
    return UNDECIDED, None


def state(cfg, marketplace):
    """sin decidir · encendida · apagada · no aplica. Solo lee."""
    return lookup(cfg, marketplace)[0]


def _settings_entry(cfg, marketplace):
    """La entrada del marketplace en el settings de usuario, o None: es donde escriben `enable` y `disable`."""
    return _entry(_read(os.path.join(cfg, SETTINGS))[0], MARKETPLACES, marketplace)


def config_dir(env=None):
    """El dir de configuración en uso: CLAUDE_CONFIG_DIR o ~/.claude (supuesto R26)."""
    env = os.environ if env is None else env
    return env.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def _real(path):
    return os.path.normcase(os.path.realpath(path))


def locate(script_path, env=None):
    """marketplace_of(script_path) si el dir que sale de la ruta es el dir de configuración en uso; si no, None.
    Un caché en otra raíz (CACHE_DIR_VAR, supuesto R27) no dice dónde está el settings, y la variable puede
    faltar en el proceso que corre este script: por eso se compara el dir y no se mira la variable."""
    found = marketplace_of(script_path)
    return found if found and _real(found[0]) == _real(config_dir(env)) else None


def _in_moved_cache(path, env):
    """True si path está en el caché de la raíz de plugins que fija CACHE_DIR_VAR (supuesto R27)."""
    moved = env.get(CACHE_DIR_VAR)
    return bool(moved and _real(path).startswith(os.path.join(_real(moved), "cache") + os.sep))


def pending_offer(script_path, env=None):
    """El marketplace si script_path corre desde el caché, la decisión no está tomada y el settings trae la
    entrada donde escribirla; si no, None. Solo lee."""
    try:
        found = locate(script_path, env)
        if found and state(*found) == UNDECIDED and _settings_entry(*found) is not None:
            return found[1]
    except Exception:  # noqa: BLE001 — lo consume el arranque, que no se rompe por un aviso
        pass
    return None


def _truthy(value):
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _update_json():
    """`update_json` de usage-tracker.py: escritura a un temporal, verificada, que conserva BOM, CRLF y sangría."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "usage-tracker.py")
    spec = importlib.util.spec_from_file_location("neb_usage_tracker", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.update_json


def _backup(path):
    base = "%s.bak-neb-%s" % (path, time.strftime("%Y%m%d-%H%M%S"))
    dest, n = base, 1
    while os.path.exists(dest):
        n += 1
        dest = "%s-%d" % (base, n)
    shutil.copy2(path, dest)
    return dest


def _without_key(entry):
    return {k: v for k, v in entry.items() if k != KEY}


def set_auto_update(cfg, marketplace, value, env=None):
    """Deja `autoUpdate` en value en la entrada del marketplace del settings de usuario; con value True y
    DISABLE_AUTOUPDATER en env, también `env.FORCE_AUTOUPDATE_PLUGINS = "1"`.
    Devuelve (cambios, respaldo, None) —cambios vacío y respaldo None si ya estaba así— o (None, None, motivo).
    Un motivo que abre con REJECTED deja el settings intacto; el otro dice qué se escribió y dónde quedó el
    respaldo."""
    env = os.environ if env is None else env
    path = os.path.join(cfg, SETTINGS)
    known = os.path.join(cfg, "plugins", KNOWN)
    if not os.path.isfile(path):
        return None, None, REJECTED + "no existe %s" % path
    settings, ok = _read(path)
    if not ok:
        return None, None, REJECTED + "%s no es un objeto JSON legible" % path
    if not _read(known)[1]:
        return None, None, REJECTED + "%s no es un objeto JSON legible" % known
    before = _entry(settings, MARKETPLACES, marketplace)
    if before is None:
        return None, None, REJECTED + "%s no trae la entrada `%s` en `%s`" % (path, marketplace, MARKETPLACES)
    force = value and _truthy(env.get("DISABLE_AUTOUPDATER"))

    def mutate(data):
        current = _entry(data, MARKETPLACES, marketplace)
        if current is None:
            raise ValueError("%s ya no trae la entrada `%s` en `%s`" % (path, marketplace, MARKETPLACES))
        changes = []
        if current.get(KEY) is not value:
            new = dict(current)
            new[KEY] = value
            data[MARKETPLACES][marketplace] = new
            changes.append((MARKETPLACES, marketplace, new))
        if force:
            block = data.setdefault("env", {})
            if not isinstance(block, dict):
                raise ValueError("`env` de %s no es un objeto" % path)
            if block.get(FORCE) != "1":
                block[FORCE] = "1"
                changes.append(("env", FORCE, "1"))
        if not changes:
            raise _NoChange()
        return changes

    try:
        mutate(copy.deepcopy(settings))
        update_json = _update_json()
        backup = _backup(path)
    except _NoChange:
        return [], None, None
    except (OSError, ValueError, ImportError, AttributeError) as e:
        return None, None, REJECTED + str(e)
    raced = []

    def mutate_once(data):      # si otro proceso ya dejó ese valor, update_json no escribe
        try:
            return mutate(data)
        except _NoChange:
            raced.append(True)
            raise

    changes, error = update_json(path, mutate_once)
    if not changes:
        try:
            os.remove(backup)
        except OSError:
            pass
        if raced:
            return [], None, None
        return None, None, REJECTED + (error or "no se aplicó el cambio").rstrip(".")
    after = _settings_entry(cfg, marketplace)
    if after is None or after.get(KEY) is not value or _without_key(after) != _without_key(before):
        return None, None, ("Se escribió %s, pero la entrada `%s` no quedó como se esperaba; el settings anterior "
                            "está en %s" % (path, marketplace, backup))
    return changes, backup, None


def _manual(cfg, marketplace, value):
    """Cómo dejar la decisión a mano. Sin la entrada en el settings, el bloque completo, con el `source` que
    Claude Code guarda en known_marketplaces.json (la misma forma que escribe `plugin marketplace add`)."""
    settings = os.path.join(cfg, SETTINGS)
    wanted = "true" if value else "false"
    data, ok = _read(settings)
    if not ok:
        return ("Para dejarlo a mano: corrige primero el JSON de %s; después pon `\"%s\": %s` en la entrada `%s` "
                "de `%s`. Si la entrada no está, corre de nuevo este comando con el JSON corregido: muestra el "
                "bloque completo." % (settings, KEY, wanted, marketplace, MARKETPLACES))
    if _entry(data, MARKETPLACES, marketplace) is not None:
        return ("Para dejarlo a mano: pon `\"%s\": %s` en la entrada `%s` de `%s` en %s."
                % (KEY, wanted, marketplace, MARKETPLACES, settings))
    source = (_entry(_read(os.path.join(cfg, "plugins", KNOWN))[0], marketplace) or {}).get("source")
    shown = json.dumps(source, ensure_ascii=False) if isinstance(source, dict) else "{ … el origen del marketplace … }"
    return ("Para dejarlo a mano: agrega a %s, dentro de `%s`, la entrada del marketplace:\n"
            "  \"%s\": { \"source\": %s, \"%s\": %s }"
            % (settings, MARKETPLACES, marketplace, shown, KEY, wanted))


def _status(cfg, marketplace, env):
    current, source = lookup(cfg, marketplace)
    settings = _read(os.path.join(cfg, SETTINGS))[0]
    forced = (_entry(settings, "env") or {}).get(FORCE) == "1"
    disabled = _truthy(env.get("DISABLE_AUTOUPDATER"))
    lines = ["Marketplace: %s" % marketplace,
             "Dir de configuración: %s" % cfg,
             "Actualización automática: %s%s" % (current, " (según %s)" % source if source else ""),
             "%s en `env` del settings: %s" % (FORCE, "sí" if forced else "no"),
             "DISABLE_AUTOUPDATER en este proceso: %s" % ("sí" if disabled else "no")]
    if current == ON and disabled and not forced:
        lines.append("Con DISABLE_AUTOUPDATER (la app de escritorio) la actualización de plugins no corre sin "
                     "%s=1; `enable` la agrega." % FORCE)
    stricter = [name for name in STRICTER if _truthy(env.get(name))]
    if stricter and not forced:
        lines.append("Con %s la actualización de plugins tampoco corre sin %s=1; `enable` no la agrega en ese "
                     "caso: decídelo tú." % (" y ".join(stricter), FORCE))
    if current != NA and _settings_entry(cfg, marketplace) is None:
        lines.append("El settings no trae la entrada del marketplace: `enable` y `disable` no escriben ahí. "
                     + _manual(cfg, marketplace, True))
    return "\n".join(lines)


def main(argv=None, script=None, env=None):
    argv = sys.argv[1:] if argv is None else argv
    env = os.environ if env is None else env
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    if len(argv) != 1 or argv[0] not in ("status", "enable", "disable"):
        sys.stderr.write("uso: autoupdate.py status | enable | disable\n")
        return 2
    action = argv[0]
    path = script or __file__
    found = locate(path, env)
    if not found:
        by_hand = ("decídelo a mano: la clave `%s` en la entrada del marketplace, dentro de `%s` de tu settings de "
                   "usuario." % (KEY, MARKETPLACES))
        same = "con el mismo CLAUDE_CONFIG_DIR que tu sesión de Claude Code, o sin él si tu sesión no lo usa"
        by_path = marketplace_of(path)
        # Con la variable cubriendo la ruta no se sabe si su raíz es la de siempre (y el proceso trae otro
        # CLAUDE_CONFIG_DIR) o una movida: no se nombra el dir que sale de la ruta, que puede no ser de configuración.
        if _in_moved_cache(path, env):
            print("Este script corre desde el caché de plugins de la raíz que fija %s, y de esa ruta no se deduce "
                  "tu settings. Si esa raíz es la `plugins` de tu dir de configuración, corre este comando %s. "
                  "Si no, %s" % (CACHE_DIR_VAR, same, by_hand))
        elif by_path:
            print("Este script corre desde el caché de plugins de %s, que no es el dir de configuración de este "
                  "proceso (%s). Corre este comando %s. Si ya es así, %s"
                  % (by_path[0], config_dir(env), same, by_hand))
        else:
            print("Este script no corre desde el caché de plugins de Claude Code (plugin cargado con "
                  "`--plugin-dir` o desde un clon): no hay marketplace que configurar.")
        return 0 if action == "status" else 1
    cfg, marketplace = found
    if action == "status":
        print(_status(cfg, marketplace, env))
        return 0
    value = action == "enable"
    changes, backup, error = set_auto_update(cfg, marketplace, value, env)
    if error:
        print("%s.\n%s" % (error, _manual(cfg, marketplace, value)))
        return 1
    if not changes:
        print("Sin cambios: la actualización automática del marketplace `%s` ya estaba %s."
              % (marketplace, ON if value else OFF))
        return 0
    for key, sub, new in changes:
        shown = json.dumps(new[KEY] if key == MARKETPLACES else new)
        print("%s: `%s.%s%s` = %s" % (os.path.join(cfg, SETTINGS), key, sub,
                                       ".%s" % KEY if key == MARKETPLACES else "", shown))
    print("Respaldo: %s" % backup)
    print("Rige desde la siguiente sesión de Claude Code." if value
          else "El plugin se queda en la versión instalada hasta que lo actualices a mano.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
