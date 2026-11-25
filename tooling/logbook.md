# Bitácora de relevo — base y captura (opcional)

Recurso del hook que alimenta la [bitácora de relevo](../workflow/logbook.md). Lo registra el plugin y es de activación voluntaria (`NEB_HOOKS` / `NEB_PROJECT_HOOKS`, § "Activación"). El artefacto y su modelo viven en [`../workflow/logbook.md`](../workflow/logbook.md); el protocolo de uso en [`../process/execution.md`](../process/execution.md) § "Gestión de sesiones (handoff)"; aquí la mecánica.

## Base local

SQLite en `~/.claude/neb.db`, la misma base de los pendientes. Su esquema es el esquema inicial de [`../hooks/logbook-schema.sql`](../hooks/logbook-schema.sql) más los pasos de base de [`migrations.md`](migrations.md); la base corre en WAL, así que una escritura interrumpida se revierte sola. No necesita infraestructura ni red. El hook y cada CLI aplican los pasos de base pendientes al abrirla. En una base anterior a 7.0.0, el paso de base 2 borra en una sola transacción, con respaldo previo verificado, las 19 columnas, los 2 índices y la tabla `event` que 7.0.0 retiró: todo o nada. Si una vista, un trigger o un índice creado a mano usa alguna de esas columnas, o una vista o un trigger usa la tabla `event` (directamente, a través de otra vista o con un `*`), o si una vista ya no abre, el paso no corre y no se borra nada: la base sigue operando en la versión 1, captura incluida, y el paso 3 queda pendiente, porque los dos tienen espera ([`migrations.md`](migrations.md) § "Paso 3: eje proyecto"; en 7.3.0 la base quedaba en `paso-bloqueado`); el arranque y `bootstrap/neb-migrate.py status` nombran cada objeto y cómo quitarlo (`DROP VIEW`, `DROP TRIGGER` o `DROP INDEX`). Al quitarlo, la siguiente conexión aplica el paso. Con un SQLite anterior a 3.35.5 (sin `DROP COLUMN` o con sus defectos previos a 3.35.5), el paso tampoco corre y el motivo dice el requisito ([`migrations.md`](migrations.md) § "Paso 2: retiro de lo de equipo"). Una columna generada o un `CHECK` agregado a mano que nombre una columna retirada no se detecta: el borrado falla, se revierte, deja su motivo en `schema_step_error` y se reintenta.

## Captura (hook `logbook-sync`)

- Eventos: **`Stop`** (cada turno) + **`SessionEnd`** (cierre graceful) + **`PreCompact`** (antes de compactar).
- Deriva el estado del **REQ activo** de la memoria del proyecto (`find_active_reqs` de `hooks/lib/_db_shared.py`); si no hay REQ → registra **sesión exploratoria** liviana (para `--resume` local).
- Guarda estado + `transcript_path` localmente. De la conversación solo guarda el resumen del exploratorio (los primeros 120 caracteres del primer mensaje); el resto no se guarda.
  - **Registro de sesión** (`session_sync`): una fila por sesión con la ruta del `.jsonl` y el cursor de lectura (`read_byte`): cada captura lee solo el tramo nuevo del `.jsonl`, que consume el REQ vinculado, y no lo persiste.
- **REQ vinculado** ([`../workflow/logbook.md`](../workflow/logbook.md) § "REQ vinculado"): en `Stop` y `PreCompact`, después del commit de la captura, liga la sesión a los REQ vinculados cuyo Change MD escribió en el tramo, o sobre los que corrió `vincular` (`link <ruta>`), y registra los nuevos. Tiene un límite de 4 s y nunca corre `git log`: las únicas llamadas a git son 2 por REQ nuevo, para ubicar su repo y su `origin`; un REQ ya registrado no vuelve a llamar a git, y uno que no se pudo registrar (sin `origin`, o con el mismo nombre ya vinculado con otra fecha) las repite en cada captura cuyo tramo traiga esa escritura, dentro del mismo límite. En `SessionEnd` no corre. Si el tramo trae 3 o más Change MD sin vincular, no registra ninguno (barrido) y solo liga los ya vinculados.
- **Terminación abrupta:** ningún hook garantiza correr ante SIGKILL o un corte de luz → se conserva hasta el último turno (`Stop`) completado. Un corte de red no afecta la captura, que no usa la red.

## Salida de `traza`

`/logbook traza [<nombre>|<ruta>|<id>] [--sin-git]` (`trace` en el CLI) responde:

- Sin argumento lista los REQ vinculados (repos, sesiones, última sesión) sin llamar a git.
- Con nombre trae un bloque por cada `project` con ese nombre; con ruta o id, uno solo.
- Lee los commits de git al consultar, en cada repo declarado (refs de `origin` del clon, sin `git fetch`). Una `nota` por repo (`sin-repo`, `timeout`, `error: …`, `omitido: tope de 6 repos`) se reporta tal cual, junto con la `leyenda`: solo cuentan los repos declarados.
- `--sin-git` muestra solo lo que hay en la base, sin commits.
- `works_relacionados` es solo información: los works `req` con el mismo nombre, archivados incluidos.

## Base sin migrar

Hasta 6.x la bitácora vivía en `~/.claude/neb-logbook.db`. Desde 7.0.0 neb solo abre `~/.claude/neb.db`. Esta sección es un residuo de transición: sale en 8.0.0, junto con la guarda que describe.

- **Qué pasa.** Si existe un `neb-logbook.db` con datos y no hay un `neb.db` usable (falta, pesa 0 bytes, no tiene la tabla `work` o no es una base SQLite), neb no crea una base nueva ni toca la vieja:
  - la captura se omite y avisa por `stderr`, que el hook descarta;
  - el arranque de cada sesión avisa de una migración guiada pendiente de 7.0.0 y ofrece abrirla en una sesión nueva;
  - cada CLI que abre la base (`logbook.py`, incluidos `link`, `trace` y `unlink`, y `pendings.py`) responde por `stdout`, con salida 0: `{"ok": false, "motivo": "base-sin-migrar", "detalle": "…", "accion": "…", "comando": "…"}`. `accion` es la migración guiada; `comando`, el migrador a mano.
  - Una base bloqueada por otra sesión no cuenta como sin migrar.
- **Cómo se migra.** En una sesión nueva, `/neb:migrate`: su paso `7.0.0:renombrar-base` corre solo, porque deja respaldo, y no pide cerrar las demás sesiones (desde 7.4.0). Comprueba que nadie más tenga abierta la base vieja; si alguien la abre, el paso queda pendiente y se reintenta en la siguiente corrida. Luego corre el migrador, `bootstrap/migrate-neb-db.py`: integra el `-wal`, saca la base de WAL (lo que solo se logra sin otra conexión abierta), la respalda como `neb-logbook.db.bak-<fecha>` en un solo archivo mientras retiene una lectura que impide a otros confirmar escrituras, vuelve a comprobar que no aparecieron archivos `-wal`, `-shm` ni `-journal`, le cambia el nombre a `neb.db` y la regresa a WAL. Si después reaparece `neb-logbook.db` (una sesión con una versión anterior lo abrió por su nombre viejo), el paso lo dice y, si esa sesión escribió ahí, queda para revisarlo a mano. Con el nombre ya cambiado, el mismo `apply` corre los pasos de base; el respaldo que se conserva es el del paso 3, tomado ya sin lo que retiró el paso 2 ([`migrations.md`](migrations.md) § "Paso 3: eje proyecto").
- **A mano.** El `comando` del JSON corre el mismo migrador: `py "<neb>\bootstrap\migrate-neb-db.py"` en Windows o `python3 "<neb>/bootstrap/migrate-neb-db.py"` fuera de Windows, donde `<neb>` es el clon de `NEB_HOME` o la carpeta del plugin instalado (el JSON lo trae con el intérprete en uso). Con `--dry-run` revisa sin abrir ninguna base. Si otra conexión tiene la base abierta, se niega sin tocar nada.
- **Si hay un `neb.db` no vacío que no sirve.** El migrador no lo pisa: aborta y dice su tamaño, y el paso queda para hacerlo a mano. Muévelo fuera de `~/.claude` (no lo borres sin revisarlo) y vuelve a correr `/neb:migrate`. Si el `neb.db` que ya existe es usable, no hay nada que migrar: esa es la base que neb usa.
- **Si el `neb-logbook.db` no es una base usable.** Si no está vacío pero no es una base SQLite o no tiene la tabla `work`, el migrador lo dice y no lo toca. Muévelo fuera de `~/.claude` (no lo borres sin revisarlo); neb crea un `neb.db` nuevo en la siguiente captura. Si tiene el encabezado de SQLite pero está dañado, el paso `7.0.0:renombrar-base` queda pendiente (lo reporta como si otra sesión la tuviera abierta): muévelo fuera igual.
- **Volver atrás.** Regresa clon y plugin a 6.x, mueve `neb.db` fuera de `~/.claude` y copia el respaldo `neb-logbook.db.bak-<fecha>` a `neb-logbook.db`. Lo capturado después del respaldo se pierde.

## Activación

De activación voluntaria: el plugin registra el hook, y corre si `logbook-sync` está en `NEB_HOOKS` (personal: `env` de `~/.claude/settings.json` o del `settings.local.json` del proyecto) o en `NEB_PROJECT_HOOKS` (`env` del `.claude/settings.json` versionado del proyecto). Ver [`../hooks/README.md`](../hooks/README.md) § "Bajo el plugin de Neb". En Windows requiere Git Bash. Una entrada de settings con clon (`logbook-sync.ps1` con `"shell": "powershell"`, o `logbook-sync.sh`) sigue funcionando; no la combines con la variable, o corre dos veces.

## Modos de fallo (defensivo)

- Sin Python → warning a stderr, `exit 0`.
- Sin REQ activo → registra sesión exploratoria (no falla).
- DB inaccesible o error → `exit 0` (nunca bloquea el turno).
- Base que este código ya no puede operar, o paso de base detenido → la captura no escribe y el CLI responde `ok: false` con el motivo (si el paso detenido y todos los posteriores tienen `espera`, la base sigue operando en su versión); como el `stderr` se descarta, lo dicen el arranque y `neb-migrate.py status` ([`migrations.md`](migrations.md)).
- Base sin migrar → la captura se omite y cada CLI responde `base-sin-migrar` (§ "Base sin migrar").
- Payload sin `session_id`, `cwd`, `transcript_path` o `hook_event_name`, o con alguno vacío → la entrada del hook (`neb-hook.py`, `logbook-sync.ps1` o `logbook-sync.sh`) sale con `exit 0` sin llamar a `logbook.py`: no captura ni escribe en `stdout`.
- Un verbo retirado responde `{"ok": false, "motivo": "verbo-retirado", "verbo": "…", "detalle": "…"}` con lo que lo reemplaza; un verbo desconocido responde «subcomando desconocido». Ninguno de los dos abre la base ni crea works, salvo un primer argumento desconocido con exactamente 6 posicionales y el cuarto `Stop`, `SessionEnd` o `PreCompact`: esa es la forma del hook y entra a captura.
- REQ vinculado (§ "Captura (hook `logbook-sync`)"):
  - Un fallo del vínculo no afecta la captura, que ya está confirmada; la evidencia de sesión de ese tramo se pierde y `vincular` la restituye.
  - Base bloqueada o límite de 4 s vencido → la escritura se omite; la liga de sesión y el registro de ese tramo se pierden, y `vincular` los restituye.
  - Esas omisiones (barrido, choque de fecha —el `nombre` ya vinculado con otra fecha en el mismo `project`—, límite vencido, base bloqueada, falla del vínculo) no dejan rastro visible: su aviso solo va a `stderr`, que el hook descarta. Con `link`, el choque de fecha sí se ve: responde `ok: false` con el motivo.
  - En `traza`, un repo cuyo git falla o tarda más de 5 s sale con su nota y no tumba la consulta.

## Requisitos

Python 3 (`py` / `python` / `python3`) con `sqlite3` (stdlib) 3.35.5 o superior: con uno anterior, el paso de base 2 no corre y la base sigue en la versión 1, con el paso 3 pendiente ([`migrations.md`](migrations.md) § "Paso 2: retiro de lo de equipo"); en Windows, Python 3.12 o superior lo trae. Además, git ≥ 2.31 en el `PATH` para registrar un REQ vinculado por escritura y para los commits de `traza`; sin git, nada se registra por escritura, `traza` sale con la nota de error en cada repo y la captura sigue igual. La captura del hook usa el módulo del plugin cargado. El CLI (`/logbook`, `/pendings-review`) y los wrappers de una entrada de settings usan el clon de `NEB_HOME` si lo hay (un `NEB_HOME` que apunte al caché del plugin se ignora). Cada módulo usa el esquema de su propio árbol: si plugin y clon traen versiones distintas, los dos operan la base mientras la entiendan, y el que ya no la entiende no la toca y lo avisa el arranque ([`migrations.md`](migrations.md) § "Versión y compatibilidad").
