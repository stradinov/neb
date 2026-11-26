# Validation prompts — skill: logbook

Casos de validación del skill. Cada caso trae el prompt, lo esperado y cómo se monta.

Montaje común: sesión con `NEB_HOME` apuntando al árbol bajo prueba. Ningún caso abre la base real del dev: cada llamada al CLI lleva `HOME` y `USERPROFILE` apuntando a un directorio temporal `T` (en Windows la ruta sale de `USERPROFILE`), fijados solo en el entorno de esa llamada. La sesión no se lanza con esas variables, porque romperían la configuración y la autenticación de Claude Code. Para las llamadas que hace la sesión, antes del prompt recibe esta instrucción: «en cada llamada a `LB`, antepón `HOME='<T>' USERPROFILE='<T>' NEB_DATA=''`, solo a esa llamada» (con `NEB_DATA` vacía, la carpeta de datos es `T/.neb`, aunque el dev haya fijado la suya). En bash, una asignación antepuesta a una función queda en el entorno de los comandos que la función lanza. `T` va en forma Windows (`C:\...`), para no depender de la conversión de rutas de Git Bash hacia `py` o `python`. Esa instrucción es parte del montaje, no del prompt que se evalúa. El aislamiento se comprueba por el contenido, no por la fecha de la base real, que el hook de captura de la propia sesión cambia: `LB list` devuelve solo los works sembrados en `T` (sus ids), y en los casos 5 y 5b sale `base-sin-mudar`, que contra la base real no saldría. Salvo donde el caso dice otra cosa, `T/.neb/neb.db` se siembra con el hook de captura (`logbook.py` con los 6 posicionales que pasa el hook, `T` como sexto, y el evento `Stop`, con el mismo entorno antepuesto): un work `req` (con un `active_*.md` de prueba, con la forma de `templates/active-req.md.template`, en la memoria del proyecto dentro de `T`) y un work `exploratory` (una captura desde un directorio sin `active_*.md`).

Los casos 5 y 5b ejercitan la base sin mudar: son residuos de transición y salen en 9.0.0.

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

5. `/logbook`, con la base sin mudar.
   - **Esperado:** la salida es `{"ok": false, "motivo": "base-sin-mudar", ...}`. Claude muestra el `detalle` y la `accion` (el siguiente inicio de sesión la muda sola, o `/neb:migrate`), no corre la migración guiada por su cuenta (pide OK explícito) y no corre otros verbos.
   - **Montaje:** en `T/.claude/` hay un `neb.db` no vacío y no existe `T/.neb/`. Ese `neb.db` se crea ejecutando el esquema inicial: `py -c "import sqlite3,sys;sqlite3.connect(sys.argv[1]).executescript(open(sys.argv[2],encoding='utf-8').read())" <db> hooks/logbook-schema.sql`. Comprobar al final que no se creó `T/.neb/` y que `T/.claude/neb.db` conserva tamaño y fecha.

5b. `/logbook traza <nombre>`, con la base sin mudar.
   - **Esperado:** el mismo motivo `base-sin-mudar` con su `detalle` y su `accion`, no un `motivo` que empiece con `error:`. `traza` abre la base antes de cualquier otra comprobación; por eso el caso usa `traza` y no `vincular`, que primero valida la ruta y el repo.
   - **Montaje:** el del caso 5.

## Negativos (NO deben disparar el skill)

6. «cuáles son mis pendientes»
   - **Esperado:** carga `pendings-review`, no `logbook`.
   - **Montaje:** ninguno.

7. «implementa la fase 4», con un REQ activo.
   - **Esperado:** no carga `logbook`; sigue el flujo del REQ activo.
   - **Montaje:** una sesión con un `active_*.md` de prueba en la memoria del proyecto.
