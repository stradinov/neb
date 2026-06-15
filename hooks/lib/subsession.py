#!/usr/bin/env python3
"""subsession.py — Detección de subsesión interna del corrector de prompts.

Cuando `preprocess-prompt.py` invoca `claude -p` para corregir un prompt, esa
subsesión hereda el entorno del dev y dispararía los hooks de Neb (SessionStart,
Stop, SessionEnd, Notification…) produciendo **efectos espurios**:

- SessionStart (`neb-bootstrap-context.py`): inyecta el arranque de Neb → el
  corrector Haiku, con instrucciones de asistente + pendientes en contexto,
  **responde** la pregunta en vez de corregir ortografía.
- Stop (`usage-tracker.sh`): cuenta los tokens de Haiku contra el REQ activo.
- Stop/SessionEnd/PreCompact (`logbook-sync`): escribe la subsesión a la bitácora.
- Stop/Notification (`notify-on-*`): "chime fantasma".

`preprocess-prompt.py` marca el entorno del subproceso con una bandera; **todo
hook de Neb con efectos de sesión debe ser inerte cuando la detecta**.

Bandera canónica: ``NEB_INTERNAL_SUBSESSION``.
Alias legacy (DEPRECADO, retiro diferido a un major): ``CLAUDE_PREPROCESS_RECURSION``
— se mantiene mientras conviven plugins de distinta versión en el equipo (un hook
de una versión vieja todavía exporta/consume el nombre legacy).

Snippet canónico para hooks shell (no importan este módulo):

  bash:        if [ "${NEB_INTERNAL_SUBSESSION:-}" = "1" ] || [ "${CLAUDE_PREPROCESS_RECURSION:-}" = "1" ]; then exit 0; fi
  PowerShell:  if ($env:NEB_INTERNAL_SUBSESSION -eq '1' -or $env:CLAUDE_PREPROCESS_RECURSION -eq '1') { exit 0 }
"""
import os

INTERNAL_SUBSESSION_ENV = "NEB_INTERNAL_SUBSESSION"
LEGACY_ENV = "CLAUDE_PREPROCESS_RECURSION"


def is_internal_subsession(env=None):
    """True si el entorno marca una subsesión interna del corrector (bandera
    canónica o alias legacy). Acepta un dict de entorno explícito para testear sin
    tocar ``os.environ``."""
    env = os.environ if env is None else env
    return env.get(INTERNAL_SUBSESSION_ENV) == "1" or env.get(LEGACY_ENV) == "1"


def mark_internal_subsession(env):
    """Setea ambas banderas (canónica + alias legacy) en ``env`` y lo devuelve.
    Lo usa ``preprocess-prompt.py`` al construir el entorno del subproceso
    ``claude -p``; el alias mantiene compatibilidad con hooks de versiones viejas
    durante la transición."""
    env[INTERNAL_SUBSESSION_ENV] = "1"
    env[LEGACY_ENV] = "1"
    return env
