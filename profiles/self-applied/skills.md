# Skills (profile: self-applied)

Skills aplicables cuando el cwd está en el repo de Neb y el profile activo es `self-applied`:

| Skill | Aplica en | Descripción |
|---|---|---|
| `wakeup` | Primer uso / `/wakeup` | Recorrido de bienvenida: presenta Neb, detecta el estado de la instalación y guía la configuración inicial (montar overlay, definir el primer profile). |
| `pendings-review` | `/pendings-review`, "cuáles son mis pendientes / qué tengo pendiente", "qué tengo de <cliente> / de <tópico>", o "revisa/prioriza/cura mis pendientes" | Pase unificado sobre `neb.db` y **única vía de consulta del dev**: muestra cada pendiente con sus ejes curados (cliente · tópico), cura los nuevos con una confirmación por pase (`PD curate`), marca obsoletos, recomienda prioridad (prompt > banda curada > compas.md por tópico + bonus por cliente > intrínsecas), agrupa relacionados por vínculo explícito y sugiere soluciones (fan-out top-K). Traduce enums al español. El CLI `list`/`show` es bajo nivel/debug, no sustituye al skill. |

Los skills se auto-descubren del plugin (`skills/<nombre>/SKILL.md`). Registro completo en [`skills/README.md`](../../skills/README.md).
