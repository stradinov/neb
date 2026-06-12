---
name: wakeup
description: Tour de bienvenida de Neb — conecta o monta tu workspace y define tu primer profile.
---

# /wakeup — tour de bienvenida de Neb

El usuario invocó `/wakeup`. Ejecutá el **tour de bienvenida de Neb** siguiendo el flujo del skill `wakeup` (su definición completa vive en `skills/wakeup/SKILL.md` — no lo dupliques acá):

1. **Presentá** Neb en 2-3 oraciones: qué garantiza (comportamiento explícito, customizable, expandible) y qué no es (no es un generador de código autónomo).
2. **Resolvé el script de setup** con este fallback (un miembro recién instalado no tiene `NEB_HOME`) y corré el dry-run:

   ```bash
   NEB_SRC="${NEB_HOME:-${CLAUDE_PLUGIN_ROOT:-$(ls -d "$HOME"/.claude/plugins/cache/*/neb/*/ 2>/dev/null | sort -V | tail -1)}}"
   bash "$NEB_SRC/bootstrap/setup-workspace.sh" --dry-run
   ```

3. **Consumí la salida** (cascada de detección — no re-detectes a mano):
   - `NEB_WORKSPACE` ya configurado y válido → confirmá "ya estás conectado a `<path>`" y pasá a las opciones del tour.
   - **"Workspace existente detectado en `<dir>`"** (caso típico: el usuario clonó el repo workspace de su equipo) → ofrecé como opción primera **"Conectar este workspace"**; al aceptar, corré `bash "$NEB_SRC/bootstrap/setup-workspace.sh" --existing "<dir>"`.
   - **"Workspace(s) existente(s) encontrado(s) bajo `$HOME`"** (el cwd no era workspace; el script barrió `$HOME`): 1 resultado → ofrecé conectarlo; varios → lista numerada para que elija cuál conectar.
   - Sin workspace (ni en cwd ni en el barrido) → preguntá si tiene uno en otra ruta (`--existing <ruta>`) o si creamos uno nuevo (default / `--base <dir>`).
4. **Ofrecé las opciones** de adopción restantes como lista numerada (definir primer profile, versionar config personal) y ejecutá la que elija.

No dupliques los pasos de `docs/user-guide.md` en la conversación; ejecutalos refiriendo a la guía. Mantené el tour conversacional y opt-in: si el usuario quiere ir directo al trabajo, dejalo. Cerrá indicando que abra una **sesión nueva** para que el hook tome el workspace conectado.
