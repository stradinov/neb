---
name: wakeup
description: Tour de bienvenida de Neb — monta tu overlay y define tu primer stack.
---

# /wakeup — tour de bienvenida de Neb

El usuario invocó `/wakeup`. Ejecutá el **tour de bienvenida de Neb** siguiendo el flujo del skill `wakeup` (su definición completa vive en `skills/wakeup/SKILL.md` — no lo dupliques acá):

1. **Presentá** Neb en 2-3 oraciones: qué garantiza (comportamiento explícito, customizable, expandible) y qué no es (no es un generador de código autónomo).
2. **Detectá el estado** del entorno corriendo `bash "${NEB_HOME:-~/.claude/neb}/bootstrap/setup-workspace.sh" --dry-run` y consumí su salida — no re-detectes la estructura a mano (el script es la fuente de verdad).
3. **Ofrecé las opciones** de adopción como lista numerada (montar/configurar workspace, definir primer stack, versionar config personal) y ejecutá la que elija el usuario.

No dupliques los pasos de `docs/user-guide.md` en la conversación; ejecutalos refiriendo a la guía. Mantené el tour conversacional y opt-in: si el usuario quiere ir directo al trabajo, dejalo.
