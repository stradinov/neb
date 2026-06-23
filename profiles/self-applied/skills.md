# Skills (profile: self-applied)

Skills aplicables cuando el cwd está en el repo de Neb y el profile activo es `self-applied`:

| Skill | Aplica en | Descripción |
|---|---|---|
| `wakeup` | Primer uso / `/wakeup` | Tour de bienvenida: presenta Neb, detecta el estado de la instalación y guía la configuración inicial (montar overlay, definir el primer profile). |
| `pendings-review` | `/pendings-review`, "cuáles son mis pendientes / qué tengo pendiente", o "revisa/prioriza mis pendientes" | Pase unificado sobre `neb.db` y **única vía de consulta del dev**: marca obsoletos, recomienda prioridad por tema (prompt > compas.md > intrínsecas), agrupa relacionados y sugiere soluciones (fan-out top-K). Traduce enums al español. El CLI `list`/`show` es bajo nivel/debug, no sustituye al skill. |

Los skills se auto-descubren del plugin (`skills/<nombre>/SKILL.md`). Registro completo en [`skills/README.md`](../../skills/README.md).
