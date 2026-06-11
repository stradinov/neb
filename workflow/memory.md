# Memoria del proyecto

`project_<nombre>.md` en `~/.claude/projects/.../memory/`. Contexto activo que Claude carga en cada sesión, no histórico.

## Path

```
~/.claude/projects/<workspace-id>/memory/project_<nombre>.md
```

`<workspace-id>` es el slug del path del workspace (ej. `C--Users-alex` en Windows, `home-alex-dev` en Linux/Mac). Indexado por `MEMORY.md` en la misma carpeta — al crear un nuevo `project_<nombre>.md`, agregar línea al index.

## Contenido

Estructura: ver [`templates/project-memory.md.template`](../templates/project-memory.md.template). La sección `## Requerimiento activo` se documenta abajo (no está en la plantilla porque solo existe durante un requerimiento).

## Sección "Pendiente de entrega"

Handoff entre sesiones cuando el requerimiento está en validación esperando entrega final. Lista artefactos a entregar y pasos exactos según el profile (p. ej. deploy vía SSH/SCP para un profile de software, commit etiquetado + notificación para un profile de análisis). Si requiere downtime o ventana, anotarlo.

**Se elimina al confirmar que la entrega final fue aprobada.** Mantenerla viva es una falla de cierre.

## Sección "Requerimiento activo"

Obligatoria mientras hay un requerimiento en curso. Es la fuente de verdad para el hook PreCompact que actualiza el draft del changes MD.

```markdown
## Requerimiento activo
- **Nombre:** <slug del requerimiento>
- **Path del proyecto:** <path absoluto local>
- **Draft changes MD:** changes/YYYY-MM-DD-<req>.md
- **Estado:** En progreso | En validación | Listo para aprobación | Cerrado (ver [`workflow/index.md`](index.md) "Estados del requerimiento")
- **Plan resumido:** <3-5 líneas del plan aprobado>
- **Archivos modificados hasta ahora:** lista
- **Próximos pasos:** lista
```

Se elimina al cerrar el requerimiento (junto con "Pendiente de entrega").

## Qué NO va

- Historia detallada del requerimiento → `<proyecto>/changes/`.
- Lista de archivos modificados de un commit → git lo tiene.
- Contexto de la sesión actual → tareas o archivo de plan.
- Convenciones ya en el `CLAUDE.md` del proyecto → no duplicar.

## Cuándo crear / actualizar

- **Crear**: al aprobar el plan, si no existe `project_<nombre>.md`.
- **Actualizar**: en cada transición de fase relevante (incidencias resueltas, entrega para revisión, entrega final). Incluye "Requerimiento activo".
- **Limpiar "Pendiente de entrega" y "Requerimiento activo"**: al confirmar que la entrega final fue aprobada.
