# Memoria del proyecto

Dos tipos de archivo en `~/.claude/projects/.../memory/` (contexto activo que Claude carga, no histórico):
- **`project_<nombre>.md`** — contexto **duradero** del proyecto (Profile, Convenciones, Bugs resueltos). Uno por proyecto.
- **`active_<proyecto>_<slug>.md`** — un **requerimiento activo**. **Uno por REQ**, así que soporta varios REQ del mismo proyecto en paralelo. Se elimina al cerrar el REQ.

## Path

```
~/.claude/projects/<workspace-id>/memory/project_<nombre>.md
```

`<workspace-id>` es el slug del path del workspace (ej. `C--Users-alex` en Windows, `home-alex-dev` en Linux/Mac). Indexado por `MEMORY.md` en la misma carpeta — al crear un nuevo `project_<nombre>.md`, agregar línea al index. Los `active_<proyecto>_<slug>.md` viven en el mismo dir.

> **Ubicación efectiva:** si el dev fija `autoMemoryDirectory` en su `settings.json` (setting nativo de Claude Code), el dir de memoria es ese — los hooks de Neb lo **respetan** (precedencia Local > Project > User; fallback al path derivado del workspace). Permite una memoria única independiente del cwd de arranque; es opt-in personal, no se impone.

## Contenido

Estructura del contexto duradero: ver [`templates/project-memory.md.template`](../templates/project-memory.md.template). Estructura de un REQ activo: ver [`templates/active-req.md.template`](../templates/active-req.md.template) y la sección "Requerimientos activos" abajo.

## Requerimientos activos

Cada REQ en curso vive en su propio archivo `active_<proyecto>_<slug>.md` (estructura completa en [`templates/active-req.md.template`](../templates/active-req.md.template)). **Un archivo por REQ** — varios REQ del mismo proyecto coexisten sin pisarse. Es la **fuente de verdad** local del estado del REQ: la bitácora de relevo (`work`) y el hook PreCompact (que actualiza el draft del change MD) leen estos archivos. Campos canónicos:

```markdown
- **Nombre:** <slug del requerimiento>
- **Path del proyecto:** <path absoluto local>
- **Draft changes MD:** changes/YYYY-MM-DD-<req>.md
- **Estado:** En progreso | En validación | Listo para aprobación | Cerrado (ver [`workflow/index.md`](index.md) "Estados del requerimiento")
- **Plan resumido:** <3-5 líneas del plan aprobado>
- **Archivos modificados hasta ahora:** lista
- **Próximos pasos:** lista
```

Un REQ está **bien-formado** (y entra a la bitácora) si tiene al menos `Nombre` y `Path del proyecto`. Se elimina el archivo completo al cerrar el REQ.

> **Compatibilidad:** los hooks aún leen el formato legacy (sección `## Requerimiento activo` dentro de `project_<nombre>.md`) durante la transición; si un REQ aparece en ambos formatos, gana el `active_*.md`. Migración natural: al próximo update del REQ, escribir el `active_*.md` y quitar la sección legacy.

### "Pendiente de entrega" (dentro del `active_*.md`)

Handoff entre sesiones cuando el REQ está en validación esperando entrega final. Lista artefactos a entregar y pasos exactos según el profile (p. ej. deploy vía SSH/SCP para software, commit etiquetado + notificación para análisis). Si requiere downtime o ventana, anotarlo. Vive **en el `active_*.md` del REQ** (es por-REQ). **Se elimina al confirmar que la entrega final fue aprobada** — mantenerla viva es una falla de cierre.

## Qué NO va

- Historia detallada del requerimiento → `<proyecto>/changes/`.
- Lista de archivos modificados de un commit → git lo tiene.
- Contexto de la sesión actual → tareas o archivo de plan.
- Convenciones ya en el `CLAUDE.md` del proyecto → no duplicar.

## Cuándo crear / actualizar

- **Crear `project_<nombre>.md`**: al aprobar el plan, si no existe (contexto duradero).
- **Crear `active_<proyecto>_<slug>.md`**: al aprobar el plan del REQ (uno por REQ activo).
- **Actualizar**: en cada transición de fase relevante (incidencias resueltas, entrega para revisión, entrega final) — sobre el `active_*.md` del REQ.
- **Eliminar el `active_<proyecto>_<slug>.md`** (incluye su "Pendiente de entrega"): al confirmar que la entrega final fue aprobada.
