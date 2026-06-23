# Tooling — hooks y recursos opt-in personales

Extensiones personales del flujo de trabajo con Claude: hooks automáticos y recursos de referencia. Todos son opt-in; ninguno es obligatorio para aplicar la metodología.

## Documentos

1. [Notify on stop](notify-on-stop.md) — hook `Stop` que reproduce un aviso sonoro al cierre de turno (scripts PS1 + bash, config personal — opt-in personal).
2. [Notify on permission](notify-on-permission.md) — hook `Notification` que reproduce un aviso sonoro cuando Claude pide permiso para una herramienta o el prompt input lleva idle > 60 s (scripts PS1 + bash, config personal — opt-in personal).
3. [Prompt preprocessing](prompt-preprocessing.md) — hook `UserPromptSubmit` que corrige prompts antes de pasar a Claude (lineamiento, script Python, slash command — opt-in personal).
4. [Redacción es](redaccion-es.md) — taxonomía de errores de redacción en español + plantilla YAML para correctores (recurso de referencia, no obligatorio).
5. [Logbook](logbook.md) — backend y captura de la bitácora de relevo (hook `logbook-sync` + SQLite local; opt-in por proyecto).
6. [Revisión editorial externa](revision-editorial-externa.md) — guía para usar un agente LLM externo (ChatGPT u otro) como consultor editorial de los `.md`: prompts, contrato de salida `[ACTUAL]`/`[PROPUESTO]`, allowlist de anglicismos, protecciones y lecciones aprendidas (recurso de referencia, no obligatorio).
