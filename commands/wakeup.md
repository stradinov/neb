---
name: wakeup
description: Tour de bienvenida de Neb — conecta o monta tu workspace y define tu primer profile.
---

# /wakeup — recorrido de bienvenida de Neb

El usuario invocó `/wakeup`. Ejecuta el **recorrido de bienvenida de Neb** siguiendo el flujo del skill `wakeup` (su definición completa vive en `skills/wakeup/SKILL.md` — no lo dupliques acá):

1. **Presenta** Neb en 2-3 oraciones: qué garantiza (comportamiento explícito, personalizable, expandible) y qué no es (no es un generador de código autónomo).
2. **Resuelve el script de configuración** con esta ruta de reserva (una instalación reciente no tiene `NEB_HOME`) y corre la simulación:

   ```bash
   NEB_SRC="${NEB_HOME:-${CLAUDE_PLUGIN_ROOT:-$(ls -d "$HOME"/.claude/plugins/cache/*/neb/*/ 2>/dev/null | sort -V | tail -1)}}"
   bash "$NEB_SRC/bootstrap/setup-workspace.sh" --dry-run
   ```

3. **Consume la salida** (cascada de detección — no repitas la detección a mano):
   - `NEB_WORKSPACE` ya configurado y válido → confirma "ya estás conectado a `<path>`" y pasa a las opciones del recorrido.
   - **"Workspace existente detectado en `<dir>`"** (caso típico: el usuario clonó el repositorio del espacio de trabajo de su equipo) → ofrece como opción primera **"Conectar este espacio de trabajo"**; al aceptar, corre `bash "$NEB_SRC/bootstrap/setup-workspace.sh" --existing "<dir>"`.
   - **"Workspace(s) existente(s) encontrado(s) bajo `$HOME`"** (el cwd no era espacio de trabajo; el script barrió `$HOME`): 1 resultado → ofrece conectarlo; varios → lista numerada para que elija cuál conectar.
   - Sin espacio de trabajo (ni en cwd ni en el barrido) → pregunta si tiene uno en otra ruta (`--existing <ruta>`) o si creamos uno nuevo (por defecto / `--base <dir>`).
4. **Ofrece las opciones** de adopción restantes como lista numerada (definir primer profile, versionar la configuración personal) y ejecuta la que elija.

No dupliques los pasos de `docs/user-guide.md` en la conversación; ejecútalos remitiendo a la guía. Mantén el recorrido conversacional y opcional: si el usuario quiere ir directo al trabajo, déjalo. Cierra indicando que abra una **sesión nueva** para que el hook tome el espacio de trabajo conectado.
