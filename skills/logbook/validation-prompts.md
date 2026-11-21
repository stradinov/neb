# Validation prompts — skill: logbook

Casos de validación del skill. Cada caso trae el prompt, lo esperado y cómo se monta.

Montaje común: sesión con `NEB_HOME` apuntando al árbol bajo prueba. Ningún caso abre la base real del dev: cada llamada al CLI lleva `HOME` y `USERPROFILE` apuntando a un directorio temporal `T` (en Windows la ruta sale de `USERPROFILE`), fijados solo en el entorno de esa llamada. La sesión no se lanza con esas variables, porque romperían la configuración y la autenticación de Claude Code. Para las llamadas que hace la sesión, antes del prompt recibe esta instrucción: «en cada llamada a `LB`, antepón `HOME='<T>' USERPROFILE='<T>'`, solo a esa llamada». En bash, una asignación antepuesta a una función queda en el entorno de los comandos que la función lanza. `T` va en forma Windows (`C:\...`), para no depender de la conversión de rutas de Git Bash hacia `py` o `python`. Esa instrucción es parte del montaje, no del prompt que se evalúa. El aislamiento se comprueba por el contenido, no por la fecha de `~/.claude/neb.db`, que el hook de captura de la propia sesión cambia: `LB list` devuelve solo los works sembrados en `T` (sus ids), y en los casos 7 y 7b sale `base-sin-migrar`, que contra la base real no saldría. Salvo donde el caso dice otra cosa, `T/.claude/neb.db` se siembra con el hook de captura (`logbook.py` con los 6 posicionales que pasa el hook y el evento `Stop`): un work `req` (con un `active_*.md` de prueba, con la forma de `templates/active-req.md.template`, en la memoria del proyecto dentro de `T`) y un work `exploratory` (una captura desde un directorio sin `active_*.md`).

Los casos 5, 6 y 8 piden a propósito verbos que se retiraron en 7.0.0; los casos 7 y 7b ejercitan la base sin migrar. Son residuos de transición y salen en 8.0.0.

## Positivos (deben disparar el skill)

1. `/logbook`
   - **Esperado:** corre `LB list` y presenta dos tablas: la de works `req` (id · proyecto/req · estado · antigüedad) y la de sesiones exploratorias (id · antigüedad). La antigüedad va relativa («hace 3 h»), no como fecha. La tabla no trae columnas de owner ni de lock, y Claude no llama a `sync-status`.
   - **Montaje:** el común.

2. `retomar <id>`, con el id del work `req` sembrado.
   - **Esperado:** corre `LB show <id>`, hace `git -C <repo_path> checkout <branch>` y entrega el prompt para abrir una sesión nueva con el Change MD, su `## Relevo` y su plan aprobado, y se detiene: no edita archivos del repo ni continúa el trabajo. No llama a `LB retomar` ni a `claim`, ni usa `--resume`.
   - **Montaje:** el común; el `active_*.md` apunta a un Change MD que existe. Al final, comprobar que `git -C <repo> status --porcelain` sale vacío, que la rama actual es la sembrada y que el Change MD no cambió. El work se siembra pasando como `cwd` (2.º posicional del hook) el repo de prueba en la rama creada, y antes del prompt ese repo se cambia a otra rama.

3. `retomar <id>`, con el id del work exploratorio.
   - **Esperado:** corre `LB show <id>` (no `LB retomar`) y entrega `claude --resume <claude_session_id>`, aclarando que vale solo en la máquina de `origin_machine`.
   - **Montaje:** el común.

4. `retomar changes/<x>.md`
   - **Esperado:** sin llamar al CLI, lee el Change MD, su `## Relevo` y su plan aprobado (campo `**Plan aprobado:**`), hace `git checkout` de la rama de `**Rama:**` y continúa desde los próximos pasos.
   - **Montaje:** un repo de prueba con `changes/<x>.md` que trae `## Relevo`, `**Plan aprobado:**` y `**Rama:**`, y la rama creada.

5. «toma el mando del REQ 12»
   - **Esperado:** sin llamar al CLI (ni `LB show 12`), explica que tomar un trabajo se retiró en neb 7.0.0 y ofrece `retomar <ruta-del-Change-MD>`. No crea works: el conteo de `work` en `T/.claude/neb.db` queda igual.
   - **Montaje:** el común; anotar el conteo de `work` antes y después.

6. `/logbook estado-sync`
   - **Esperado:** sin llamar al CLI, avisa que el estado de la sincronización se retiró en neb 7.0.0 y ofrece `retomar <ruta-del-Change-MD>`, sin diagnóstico de works ni la línea «no se pudo verificar».
   - **Montaje:** el común.

7. `/logbook`, con la base sin migrar.
   - **Esperado:** la salida es `{"ok": false, "motivo": "base-sin-migrar", ...}`. Claude muestra el `detalle`, la `accion` (`/neb:migrate` en una sesión nueva) y el `comando` como vía a mano, no corre el migrador ni la migración guiada por su cuenta (pide OK explícito) y no corre otros verbos.
   - **Montaje:** en `T/.claude/` solo hay un `neb-logbook.db` no vacío y ningún `neb.db`. El `neb-logbook.db` se crea ejecutando el esquema inicial, que es el de 6.45.0: `py -c "import sqlite3,sys;sqlite3.connect(sys.argv[1]).executescript(open(sys.argv[2],encoding='utf-8').read())" <db> hooks/logbook-schema.sql`. Comprobar al final que no se creó `T/.claude/neb.db` y que `neb-logbook.db` conserva tamaño y fecha.

7b. `/logbook traza <nombre>`, con la base sin migrar.
   - **Esperado:** el mismo motivo `base-sin-migrar` con su `detalle`, su `accion` y su `comando`, no un `motivo` que empiece con `error:`. `traza` abre la base antes de cualquier otra comprobación; por eso el caso usa `traza` y no `vincular`, que primero valida la ruta y el repo.
   - **Montaje:** el del caso 7.

8. `/logbook`, siguiendo como instrucciones el SKILL.md de neb 6.45.0 contra el módulo 7.0.0.
   - **Esperado:** el skill viejo corre `list` y `sync-status`; `sync-status` responde `verbo-retirado` con `attention: 0`, así que la tabla sale sin el aviso «no se pudo verificar el estado del sync» y sin works atascados.
   - **Montaje:** el común; el SKILL.md viejo se obtiene con `git show f06f163:skills/logbook/SKILL.md` y se le da a una sesión como instrucciones, con `NEB_HOME` apuntando al árbol 7.0.0.

## Negativos (NO deben disparar el skill)

9. «cuáles son mis pendientes»
   - **Esperado:** carga `pendings-review`, no `logbook`.
   - **Montaje:** ninguno.

10. «implementa la fase 4», con un REQ activo.
   - **Esperado:** no carga `logbook`; sigue el flujo del REQ activo.
   - **Montaje:** una sesión con un `active_*.md` de prueba en la memoria del proyecto.
