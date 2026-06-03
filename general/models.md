# Modelos

Política transversal. Claude usa el modelo más económico disponible para tareas mecánicas (comandos locales, edición trivial, búsquedas) y un modelo más capaz para análisis, plan y razonamiento de alto valor.

El dev puede forzar un modelo con `/model <modelo>`; esa instrucción tiene prioridad.

Para automatizar la selección por tipo de tarea, configurar en `~/.claude/settings.json` (ver Claude Code docs).
