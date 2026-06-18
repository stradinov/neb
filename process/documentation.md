# Documentación y memoria

Qué documentar al cerrar un requerimiento. Paths concretos en [workflow/](../workflow/).

## Qué se documenta

1. **MD del requerimiento** (`<proyecto>/changes/`) — el **registro del requerimiento** (ver [`methodology/vocabulary.md`](../methodology/vocabulary.md) § "Registro del requerimiento"); se crea como draft al aprobar el plan y se confirma en el cierre de delivery (no en esta fase), salvo **entrega temprana** del registro cuando el entorno de validación es compartido. Detalle: [workflow/changes.md](../workflow/changes.md) § "Ciclo de vida del draft".

2. **Memoria del proyecto** — contexto duradero en `project_<nombre>.md` (decisiones de diseño no obvias, bugs resueltos, convenciones); el estado del REQ y su sección "Pendiente de entrega" en el `active_<proyecto>_<slug>.md`. Detalle: [workflow/memory.md](../workflow/memory.md).

3. **`CLAUDE.md` del repositorio** — solo si se agregó arquitectura nueva, módulos relevantes, o convenciones que un futuro lector necesita.

## Qué NO se documenta

Los criterios de exclusión (cambios triviales, listas de archivos modificados, estado temporal, decisiones evidentes del código, logs de "qué hicimos hoy") viven en [`../methodology/principles.md`](../methodology/principles.md) § Anti-patrones.

(El cierre formal del requerimiento — pregunta al usuario y push final — vive en [delivery.md](delivery.md). Esta fase ejecuta solo la documentación pendiente.)
