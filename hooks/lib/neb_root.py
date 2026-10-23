#!/usr/bin/env python3
"""neb_root.py — raíz del núcleo de Neb para los consumidores que corren fuera del Bash tool.

Orden: NEB_HOME (clon del maintainer, D4) → CLAUDE_PLUGIN_ROOT → el árbol del llamador.

Un NEB_HOME dentro de `…/plugins/cache/…` se descarta: lo dejaba fijado un /wakeup anterior a
6.14.3 y apunta a una versión vieja del plugin, que Claude Code borra 14 días después del update.
Mismo criterio que `bootstrap/setup-workspace.sh` § 5 y que el `NEB_SRC` de los skills.

Lo usan el arranque (`bootstrap/neb-bootstrap-context.py`) y el esquema del CLI de pendings y logbook.
"""
import os
import re

_CACHE_RE = re.compile(r"[/\\]plugins[/\\]cache[/\\]")


def in_plugin_cache(path):
    """True si `path` cae dentro del caché de plugins de Claude Code (separador `/` o `\\`)."""
    return bool(path) and _CACHE_RE.search(path) is not None


def stale_neb_home(env=None):
    """El NEB_HOME que se descarta por caer en el caché del plugin, o '' si no hay."""
    env = os.environ if env is None else env
    value = env.get("NEB_HOME", "")
    return value if in_plugin_cache(value) else ""


def resolve_neb_root(own_root, env=None):
    """Raíz del núcleo: NEB_HOME fuera del caché, si no CLAUDE_PLUGIN_ROOT, si no `own_root`."""
    env = os.environ if env is None else env
    neb_home = env.get("NEB_HOME", "")
    if neb_home and not in_plugin_cache(neb_home):
        return neb_home
    return env.get("CLAUDE_PLUGIN_ROOT") or own_root
