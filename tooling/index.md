# Tooling — hooks y recursos opcionales personales

Extensiones personales del flujo de trabajo con Claude: hooks automáticos y recursos de referencia, más la configuración y la carpeta de datos que comparten. Los hooks y recursos son opcionales; ninguno es obligatorio para aplicar la metodología.

## Documentos

1. [Configuración y carpeta de datos](config.md) — dónde guarda Neb lo suyo (`NEB_DATA` o `~/.neb`) y su único archivo de configuración, `config.json` (secciones de los hooks e idioma del individuo); léelo antes que los hooks que se configuran ahí.
2. [Notify on stop](notify-on-stop.md) — hook `Stop` que reproduce un aviso sonoro al cierre de turno (scripts PS1 + bash, config personal — opcional personal).
3. [Notify on permission](notify-on-permission.md) — hook `Notification` que reproduce un aviso sonoro cuando Claude pide permiso para una herramienta o el prompt input lleva idle > 60 s (scripts PS1 + bash, config personal — opcional personal).
4. [Prompt preprocessing](prompt-preprocessing.md) — hook `UserPromptSubmit` que corrige prompts antes de pasar a Claude (lineamiento, script Python, slash command — opcional personal).
5. [Redacción es](redaccion-es.md) — taxonomía de errores de redacción en español + plantilla YAML para correctores (recurso de referencia, no obligatorio).
6. [Logbook](logbook.md) — backend y captura de la bitácora de relevo (hook `logbook-sync` + SQLite local; de activación voluntaria con `NEB_HOOKS` / `NEB_PROJECT_HOOKS`).
7. [Migraciones](migrations.md) — versión de esquema de `neb.db`, pasos de base, respaldo y vuelta atrás (`bootstrap/neb-migrate.py`), que corren solos con cada actualización; y migración guiada (`migrations/`, al iniciar sesión y `/neb:migrate`), que configura la máquina del dev.
8. [Revisión editorial externa](revision-editorial-externa.md) — guía para usar un agente LLM externo (ChatGPT u otro) como consultor editorial de los `.md`: prompts, contrato de salida `[ACTUAL]`/`[PROPUESTO]`, allowlist de anglicismos, protecciones y lecciones aprendidas (recurso de referencia, no obligatorio).
