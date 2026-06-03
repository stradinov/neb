# Tooling — hooks y recursos opt-in personales

Extensiones personales del flujo de trabajo con Claude: hooks automáticos y recursos de referencia. Todos son opt-in; ninguno es obligatorio para aplicar la metodología.

## Documentos

1. [Notify on stop](notify-on-stop.md) — hook `Stop` que reproduce un aviso sonoro al cierre de turno (scripts PS1 + bash, config personal — opt-in personal).
2. [Notify on permission](notify-on-permission.md) — hook `Notification` que reproduce un aviso sonoro cuando Claude pide permiso para una herramienta o el prompt input lleva idle > 60 s (scripts PS1 + bash, config personal — opt-in personal).
3. [Prompt preprocessing](prompt-preprocessing.md) — hook `UserPromptSubmit` que corrige prompts antes de pasar a Claude (lineamiento, script Python, slash command — opt-in personal).
4. [Redacción es](redaccion-es.md) — taxonomía de errores de redacción en español + plantilla YAML para correctores (recurso de referencia, no obligatorio).
