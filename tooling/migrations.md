# Migraciones de `neb.db` — versión de esquema, pasos de base y migración guiada

Cómo cambia el esquema de `~/.claude/neb.db` de una versión de Neb a otra sin que plugin, clon y sesiones abiertas tengan que coincidir de versión (desde 6.48.0), y cómo una versión configura la máquina del dev (migración guiada, desde 6.49.0). La regla de qué debe traer una versión que cambia el esquema o pide configurar la máquina vive en [`../process/version-control.md`](../process/version-control.md) § "Flujo al cerrar REQ"; aquí, la mecánica. Código: `hooks/lib/_migrations.py` (mecanismo y pasos de base), `hooks/lib/_db_shared.py` (conexión y reparaciones), `hooks/lib/_guided.py` y `hooks/lib/_machine.py` (pasos guiados y su catálogo), `bootstrap/neb-migrate.py` (estado y operación).

## Esquema con el módulo

Cada módulo toma el esquema del árbol en el que vive (`hooks/logbook-schema.sql` junto a `hooks/lib/`), nunca el del árbol de `NEB_HOME`: la captura del plugin usa el del plugin y el CLI del clon, el del clon. El 5.º argumento de la captura (`guide_dir`) se sigue aceptando, porque los wrappers de versiones anteriores lo envían, y ya no decide el esquema.

`hooks/logbook-schema.sql` es el esquema inicial (versión de esquema 1 = el esquema de 6.47.0) y **no se edita**. Todo cambio posterior del esquema de datos es un paso de base. Una base nueva se crea con el esquema inicial más todos los pasos, así que una base nueva y una migrada llegan al mismo esquema por el mismo camino. El esquema vigente lo imprime `py bootstrap/neb-migrate.py schema`.

## Versión y compatibilidad

La base guarda sus pasos aplicados en la tabla `schema_step` (número, mínima compatible que deja, título, versión de Neb que lo aplicó, fecha y respaldo previo). El código trae su **versión de esquema** en `SCHEMA_VERSION`. Con `V` = último paso aplicado a la base (0 sin tabla), `F` = **mínima compatible** (el máximo de `min_code`) y `C` = versión de esquema del código:

| Caso | Qué hace el código |
|---|---|
| `V == C` | Opera |
| `V < C` | Aplica los pasos `V+1 … C` y opera |
| `V > C` y `C >= F` | Opera sin migrar y sin reparaciones: la base es más nueva pero compatible |
| `V > C` y `C < F` | No toca la base: cada CLI responde `{"ok": false, "motivo": "base-incompatible", "detalle": …, "accion": …}` y la captura no escribe |

Un código anterior a 6.48.0 no conoce la regla: sobre una base de 6.48.0 funciona igual que antes (mismo esquema, dos tablas de más: `schema_step` y `schema_step_error`); sobre una base que ya pasó un paso que quita columnas falla como fallaba antes de este mecanismo. Ese es el riesgo de una versión que sube la mínima compatible mientras alguna máquina sigue con código anterior a 6.48.0; el aviso del arranque lo nombra cuando ve un árbol así.

## Pasos de base

Un **paso de base** es un cambio del esquema de `neb.db` escrito en código (lista `STEPS` de `hooks/lib/_migrations.py`). Lo aplica la primera conexión de una versión que lo trae. Atributos:

| Atributo | Qué significa |
|---|---|
| `n`, `titulo` | Número consecutivo y nombre |
| `aplicar(con)` | El cambio. Corre dentro de `BEGIN IMMEDIATE` junto con su fila de `schema_step`: queda todo o nada. Recibe la conexión sin control de la transacción: `commit()`, `rollback()`, `executescript`, `cursor()` y `BEGIN`/`COMMIT`/`END`/`ROLLBACK`/`SAVEPOINT`/`RELEASE` (también tras un comentario) lanzan error, igual que `PRAGMA foreign_keys=…`, que dentro de la transacción no surte efecto, y si SQLite revierte la transacción por su cuenta (disco lleno, una cláusula `OR ROLLBACK`) la siguiente sentencia también; así nada se confirma suelto |
| `min_code` | Mínima compatible que deja. Sube solo si el código anterior escribiría datos inválidos o perdería datos: una escritura válida suya fallaría (columna `NOT NULL` sin `DEFAULT`, `UNIQUE`, `CHECK` o trigger nuevos) o escribiría sobre un dato que desaparece o cambia de significado. Si ese código solo ve degradada una vista (p. ej. la de pendientes), no sube: subirla deja sin base, captura incluida, a las sesiones abiertas con la versión anterior, y una versión nueva no puede pedir que se cierren. Un paso que solo agrega la conserva |
| `destructivo` | Borra o reescribe datos: lleva respaldo previo (§ "Respaldo y vuelta atrás"), salvo en una base que se acaba de crear en esa misma conexión |
| `espera` | El código nuevo funciona aunque el paso no se haya aplicado. Si no se puede, la conexión sigue con la base en `V` y se reintenta en la siguiente |
| `precheck(con)` | Opcional, solo lectura: motivo por el que el paso no puede correr todavía (p. ej. una vista del usuario sobre una columna). Corre antes del candado y del respaldo |

Cuando un paso no se puede aplicar (candado ocupado, `precheck` con motivo, respaldo fallido o error en `aplicar`, que revierte): si ese paso y todos los posteriores tienen `espera`, la conexión sigue con la base en `V`; si alguno no la tiene, un candado ocupado da la conexión vacía (como antes) y un bloqueo que no se resuelve solo responde `paso-bloqueado`. Un respaldo fallido o un error de `aplicar` (también una excepción que no es de SQLite) dejan su motivo en `schema_step_error`, porque el `stderr` de la captura no lo ve nadie: lo muestran el arranque y `neb-migrate.py status`. Un `precheck` con motivo (o que lanza) y un candado ocupado no se guardan: el arranque y `status` recalculan el `precheck`; un candado ocupado que se repite en un paso con `espera` solo deja su aviso en el `stderr` de la captura, que nadie ve.

- **Espera tras un fallo guardado**: durante 10 minutos las conexiones no reintentan el paso (cada intento de un paso destructivo copia la base con el candado tomado). `py bootstrap/neb-migrate.py apply` lo reintenta ya.
- **Reversión de SQLite**: si SQLite revierte la transacción del paso (disco lleno, `OR ROLLBACK`), el paso falla como cualquier error: nada quedó confirmado, el respaldo se borra y se reintenta tras la espera.
- **Otro proceso avanzó la base**: si al tomar el candado (o tras un `precheck` con motivo) la base ya está en ese paso o más allá, la conexión vuelve a leer `V` y `F` y aplica otra vez la regla de compatibilidad.

El **paso 1** es el esquema inicial: las sentencias del archivo (sin sus `PRAGMA`, que dentro de una transacción no surten efecto y que la conexión ya fija) más las columnas que una base anterior no tenga, en una sola transacción `BEGIN IMMEDIATE` junto con su fila de `schema_step`. Relee la versión con el candado tomado: si otro proceso ya avanzó la base, no hace nada, así que un paso 1 tardío no vuelve a crear lo que el paso 2 retiró. Es idempotente (todo es `IF NOT EXISTS`). Con el candado ocupado, la conexión se comporta como con cualquier paso sin `espera`.

### Paso 2: retiro de lo de equipo

Desde 7.0.0 (`SCHEMA_VERSION = 2`). Borra lo que era del backend central y del candado de relevo: 14 columnas de `work` (`owner`, `lock_state`, `takeover_by`, `locked_at`, `payload_version`, `origin_dev`, `dirty`, `synced_at`, `remote_id`, `conflict`, `last_error`, `last_error_at`, `transcript_error`, `transcript_error_at`), 5 de `session_sync` (`work_id`, `synced_byte`, `transcript_error`, `transcript_error_at`, `root_cwd`), los índices `idx_work_dirty` e `idx_session_sync_work` y la tabla `event`. `min_code = 2`: una 6.48.x o 6.49.x deja de operar la base y lo dice el arranque. Es `destructivo` (respaldo previo verificado) y tiene `espera`: 7.0.0 funciona con esas columnas presentes, así que, si el paso no corre, la captura sigue con la base en la versión 1. Desde 7.4.0 el paso 3 que lo sigue también tiene `espera`, así que eso vale con los dos: un paso 2 detenido deja la base en la versión 1, con el paso 3 pendiente. En 7.3.0 el paso 3 no tenía `espera` y un paso 2 detenido respondía `paso-bloqueado` (§ "Paso 3: eje proyecto").

- **Todo o nada.** Su `precheck` lo detiene sin borrar nada en dos casos, y el arranque y `neb-migrate.py status` dicen el motivo:
  - el SQLite del Python que corre neb es anterior a 3.35.5 (sin `DROP COLUMN`, o con los defectos de `DROP COLUMN` que 3.35.5 corrigió): el motivo dice la versión y pide instalar un Python que lo traiga desde https://www.python.org/downloads/ (en Windows, Python 3.12 o superior). neb no descarga nada;
  - un objeto creado a mano usa lo que el paso retira: una vista, un trigger o un índice que nombra una columna retirada, una vista o un trigger que usa `event` (directamente, por otra vista o con un `*`), o una vista que ya no abre. El motivo nombra cada objeto, lo que usa y el `DROP VIEW`, `DROP TRIGGER` o `DROP INDEX` que lo quita; al quitarlo, la siguiente conexión aplica el paso.
- **Relectura dentro del candado.** `aplicar` vuelve a leer lo que queda y los objetos del usuario: borra solo lo que existe (sobre una base a medias, un `DROP COLUMN` de una columna ausente revertiría el paso siempre) y, si entre el `precheck` y el candado apareció un objeto que lo bloquea, falla sin borrar nada: el fallo queda en `schema_step_error` y el paso se reintenta tras la espera o con `apply`.
- **Lo que no detecta**: una columna generada o un `CHECK` agregados a mano que nombren una columna retirada. El `DROP COLUMN` falla, el paso se revierte y su motivo queda en `schema_step_error`.
- **Cuánto dura el candado**, medido sobre una copia de una base real: respaldo e `integrity_check`, 0.16 s; los 19 `DROP COLUMN`, 0.03 s; el candado de escritura, unos 0.2 s en total, lejos de los 5 s de `busy_timeout` con que espera la captura de otra sesión. Por eso cada columna sale con su `DROP COLUMN` y no se reconstruyen las tablas, que además pediría apagar las claves foráneas fuera de la transacción (con ellas encendidas, borrar `work` pondría en nulo `pending.work_ref`).

Fuera de los pasos quedan tres reparaciones que corren después de ellos en cada conexión con `V <= C` (nunca sobre una base más nueva que el código), sin respaldo: el índice `uq_pending_slug` si falta; la limpieza de las tablas de transcripts retiradas en 6.41.0, como desde entonces; y, desde 7.4.0, la mínima compatible del paso 3 que dejó 7.3.0 (§ "Paso 3: eje proyecto").

Con la base en versión 1 o más, el esquema inicial ya no se reaplica en cada conexión: una tabla borrada a mano deja de recrearse sola.

### Paso 3: eje proyecto

Desde 7.3.0 (`SCHEMA_VERSION = 3`). Renombra la raíz del eje curado de los pendientes: el tema raíz (`parent_id IS NULL`) con slug `cliente` pasa a slug `proyecto` y nombre `Proyecto` ([`pendings.md`](pendings.md)); su descripción también cambia si es la que puso el seed («Raíz del eje cliente (contenedor; no es un tema)» pasa a la del eje proyecto), y una escrita a mano se conserva. Solo esa fila: los hijos siguen colgando del mismo `id`, así que las curaciones de `pending_topic`, los `topic_link` y el resto de las tablas no cambian, y las `keywords` de la raíz tampoco. Sin raíz `cliente` no hace nada: una base nueva, una con triage pero sin taxonomía sembrada (solo el sentinel `sin-clasificar` y temas planos) o un tema `cliente` que no es raíz; la raíz `proyecto` la crea el seed (`bootstrap/seed-pendings-taxonomy.py`).

| Atributo | Valor | Por qué |
|---|---|---|
| `min_code` | 2 (desde 7.4.0) | El código 7.0.0 a 7.2.x opera la base renombrada: busca la raíz `cliente`, que ya no está, así que ve degradada su vista de pendientes (catálogo `cliente` vacío, sin bonos por proyecto); su captura y su triage siguen funcionando. Escribe dos cosas sobre el eje, y ninguna sube la mínima: sus sugerencias `curated=0` pueden caer sobre la raíz `proyecto` (o sus hijos), que 7.4.0 ignora al leer y borra en el siguiente `triage` (§ "Sugerencias sobre una raíz", abajo); y su `seed-pendings-taxonomy.py --apply`, corrido a mano, archivaría la raíz `proyecto` y crearía una `cliente` con los hijos, que el `--apply` de 7.4.0 deshace (re-activa la raíz y devuelve los hijos). Ninguna corre sola ni pierde datos: la siembra deja su respaldo. Fuera de la base, un `write-compas` de 7.2.x (solo con OK del dev en esa sesión) escribe `compas.md` v2 con `Clientes:` y, si sus objetivos no traen los bonos, los pierde; `7.3.0:compas-proyectos` vuelve a marcarse y lo lleva a v3, y el respaldo `compas.pre-7.3.0.*` conserva la brújula anterior. 7.3.0 lo registró con 3 y las sesiones abiertas con 7.2.x perdían la base entera: lo corrige la reparación de abajo |
| `destructivo` | sí | Reescribe una fila: respaldo previo verificado (`neb.pre-paso-3.<fecha UTC>.db`) aunque no haya raíz que renombrar, salvo en una base recién creada |
| `espera` | sí (desde 7.4.0) | 7.4.0 opera la base con la raíz `cliente` presente, degradado: el catálogo del eje proyecto queda vacío, los hijos de `cliente` cuentan como temas sin eje, la raíz `cliente` nunca se sugiere y `curate --proyecto` responde error sin escribir. Si el paso no corre (candado ocupado, o un paso 2 detenido que deja la base en la versión 1), la conexión sigue en su versión y el paso se reintenta. En 7.3.0 no tenía `espera` y eso respondía `paso-bloqueado` |
| `precheck` | ninguno (desde 7.4.0) | `topic.slug` es `UNIQUE`: si la raíz `cliente` existe y ya hay un tema con slug `proyecto` (en cualquier posición), `aplicar` lo mueve en la misma transacción, con el respaldo del paso, a `proyecto-<id>` (o `proyecto-<id>-<n>` si ese está tomado; determinista por el `id`) y la raíz toma `proyecto`; sus curaciones cuelgan por `id` y no cambian. Si `proyecto` aparece en «- **Temas:**» de `~/.claude/compas.md`, lo cambia por el slug nuevo el paso guiado `7.4.0:compas-tema-proyecto` (`compas.md` resuelve por slug). En 7.3.0 el choque detenía el paso y pedía al dev un `UPDATE` a mano |

- **Relectura dentro del candado.** `aplicar` vuelve a buscar la raíz `cliente` (si ya no está, no escribe) y el tema `proyecto` que choca, así que también mueve uno creado por otra sesión justo antes de tomar el candado.
- **Respaldo que queda.** La poda es por paso (§ "Respaldo y vuelta atrás"): el respaldo del paso 3 se toma siempre, haya o no raíz `cliente`, y solo reemplaza a un `neb.pre-paso-3.*` anterior:
  - una base ya en la versión 2 (toda instalación con 7.0.0 a 7.2.x) conserva el `neb.pre-paso-2.*` que dejó 7.0.0, la única copia con las 19 columnas de equipo, junto al `neb.pre-paso-3.*`; la fila del paso 2 en `schema_step` sigue apuntando a él;
  - una base que llega de 6.x pasa por los pasos 2 y 3 en la misma conexión y queda con los dos: `neb.pre-paso-2.*` (con lo de equipo) y `neb.pre-paso-3.*` (tomado ya sin lo que retiró el paso 2).
- **Reparación de la mínima compatible (7.4.0).** Si `schema_step` tiene la fila del paso 3 con `min_code` 3 y el título de 7.3.0 (una base que migró 7.3.0), el arranque de la primera sesión con 7.4.0 la baja a 2 (es su única escritura, y solo si la fila está y la base no es más nueva que el código), y también cualquier conexión de 7.4.0 con `V <= C`; en una transacción corta y sin respaldo, y ninguna otra fila cambia. Es idempotente: sin esa fila no escribe ni pide el candado, y si el candado está ocupado se reintenta en la siguiente conexión. Así una sesión abierta con 7.0.0 a 7.2.x, que lee la mínima tal cual está en la base, vuelve a operarla sin cerrarla. El código de 7.4.0 no depende de que la reparación haya corrido: `read_version` cuenta esa fila como 2, así que la regla de compatibilidad, `neb-migrate.py status` y el aviso del arranque ya leen 2 antes de bajarla.
- **Siembra con el paso pendiente.** Si la base no pasó el paso 3 y conserva la raíz `cliente`, `bootstrap/seed-pendings-taxonomy.py --apply` aborta sin respaldo ni escritura y dice qué detiene el paso y cómo resolverlo (`neb-migrate.py status`): sembrar crearía una raíz `proyecto` junto a `cliente`, y el paso, al correr, movería esa raíz a otro slug y dejaría el eje partido en dos. El dry-run lo avisa ([`pendings.md`](pendings.md)).
- **Sugerencias sobre una raíz.** El código 7.2.x de una sesión abierta no excluye la raíz `proyecto` de sus candidatos y puede sugerirla como tema (`curated=0`). 7.4.0 ignora al leer toda sugerencia sobre una raíz de eje (`proyecto`, `topico` y `cliente` sin padre) y `reclassify` (y con él `triage`) las borra; una fila `curated=1` no se toca.
- **El resto del cambio del eje** (llaves del triage, `compas.md`, el seed) no es del paso de base: el CLI de [`pendings.md`](pendings.md) y la migración guiada de 7.3.0 (`migrations/7.3.0.md`).

### Escribir un paso

1. Agrega un `Step` al final de `STEPS` con el siguiente número y sube `SCHEMA_VERSION` (una sola línea literal: el arranque la lee de otro árbol como texto).
2. `aplicar` relee lo que va a cambiar y toca solo lo que existe; nunca `commit()` ni `executescript`.
3. Decide `min_code`, `destructivo`, `espera` y `precheck` con la tabla de arriba.
4. Pruebas en `hooks/tests/`: el paso sobre una base de la versión anterior, sobre una base nueva y con su falla sembrada; y, antes del gate de Fase 4, sobre una copia de una base real (`profiles/self-applied/deployment.md` § "Validación").
5. El fragmento de la versión dice qué hace el paso y si sube la mínima compatible.

## Respaldo y vuelta atrás

- Antes de un paso destructivo, el mecanismo copia la base con la API de backup de SQLite desde una conexión aparte a `<carpeta de la base>/neb-backups/neb.pre-paso-<n>.<fecha UTC>.db` y la verifica con `integrity_check`. La copia queda en un solo archivo (`journal_mode=DELETE`): leerla no le deja `-wal` ni `-shm`. Si el respaldo falla, el paso no corre. La carpeta tiene permiso solo para el usuario donde el sistema lo respeta.
- Al confirmar el paso se borran los `neb.pre-paso-<n>.*.db` anteriores de ese mismo paso: queda el último respaldo de cada paso destructivo, y el de un paso no poda el de otro (así el `neb.pre-paso-2.*` de 7.0.0 sobrevive al paso 3). En Windows, uno que otro proceso tenga abierto se queda hasta la siguiente poda de su paso. Si el paso falla, ese respaldo se borra. Los respaldos hechos a mano no se tocan. `neb-migrate.py status` los lista todos y `restore` acepta cualquiera.
- **Volver atrás**: regresar primero plugin y clon a la versión anterior, y después `py bootstrap/neb-migrate.py restore <archivo>` (el script vive en el clon y en el caché del plugin). No hay pasos inversos. De 6.48.0 a 6.47.0 no hace falta `restore`: el paso 1 no es destructivo y 6.47.0 opera la base marcada. `restore`:
  - solo acepta un `neb.pre-paso-*.db` o un `neb.pre-restore.*.db` que esté directamente en `neb-backups/` (no el `neb.pre-vacuum.*.db` que deja el paso `vacuum-neb-db` de la migración guiada 7.3.0: es la base de antes de compactar, con el mismo contenido, y no sirve para volver de versión); ni el archivo ni `neb-backups/` pueden ser enlace o junction (un enlace en una carpeta superior, como `.claude` movida, sí se acepta);
  - conviene correrlo con las sesiones cerradas: lo que otra sesión escriba entre el respaldo de la base actual y la restauración se pierde;
  - se niega si el código que lo corre no podría operar la base restaurada, o si la siguiente conexión volvería a aplicar los pasos que el respaldo no tiene (la actualización automática del plugin puede traer de vuelta la versión nueva); `--remigrar` permite lo segundo a propósito, para recuperar datos y dejar que el paso corra otra vez;
  - respalda antes la base actual como `neb.pre-restore.<fecha UTC>.db` (queda 1, aparte de los de los pasos) y nunca borra el archivo del que restaura;
  - escribe con la API de backup hacia la base viva, con una conexión directa; nunca copia ni renombra archivos (un `-wal` vivo corrompería la copia).

## Migración guiada

Una **migración guiada** es lo que una versión pide además de sus pasos de base: configurar la máquina del dev (quitar una clave de `settings.json`, una variable de entorno de usuario) o un paso que necesita al dev. La versión trae dos archivos en `migrations/`, con su versión semántica de nombre (formato y ejemplo en [`../migrations/README.md`](../migrations/README.md)):

- `migrations/<X.Y.Z>.md`: el prompt. Qué cambia, en qué orden van los pasos, qué se le dice al dev, cómo se verifica y qué se reporta.
- `migrations/<X.Y.Z>.py`: los **pasos guiados** (`STEPS`), cada uno con `id`, `titulo` y `exclusivo` (solo corre cuando ninguna otra conexión usa la base en ese momento). Dos clases:
  - **De catálogo**: el paso es un dato, el nombre de una operación de `hooks/lib/_machine.py` y sus argumentos; detectar y aplicar los hace el catálogo.
  - **Libre**: trae sus propias `detectar(ctx)` y `aplicar(ctx)`, para lo que el catálogo no cubre (p. ej. invocar otro programa del repo). Si deja con qué deshacerlo, lo declara (`respaldo=True`) y `aplicar` devuelve la ruta. `aplicar` también puede responder que no había nada que hacer (`sin-cambio`), que el paso sigue pendiente, que pide algo a mano o que falló.

### Qué está pendiente y qué se guarda

**Pendiente** es lo que la detección dice en el momento: se lee del estado real de la máquina y no se persiste. La detección solo lee; la de un paso libre no escribe ni llama a nada que escriba (se revisa en el gate de la versión que lo trae). Un paso aplicado no deja constancia: si el estado vuelve, la detección lo vuelve a marcar.

Lo único que se guarda es el «no» del dev a un paso, en una tabla del mecanismo que el programa crea con `IF NOT EXISTS`, fuera de los pasos de base:

```sql
CREATE TABLE IF NOT EXISTS migration_skip (
  id          TEXT PRIMARY KEY,   -- '<versión>:<paso>'
  neb_version TEXT NOT NULL,
  at          TEXT NOT NULL,
  detail      TEXT                -- nunca el valor de una variable
);
```

Con fila, el paso sale de lo pendiente hasta que el dev lo pida con `apply --include`; si entonces corre bien, la fila se borra (si no se puede borrar, `apply` lo reporta en `omision_sin_borrar`). Su forma queda fija: un cambio a esta tabla entraría como paso de base, y ese paso debe tolerar que ya exista con esta forma. `neb-migrate.py schema` la imprime aparte. Si la tabla no se puede leer por otra causa que no existir, `apply` no corre ningún paso guiado. `skip` no crea la base si no existe, ni la tabla en una base de una versión de neb más nueva (la regla de compatibilidad: este código no le agrega nada): en los dos casos se niega y el paso sigue pendiente.

### Qué corre solo y qué pide al dev

- **Corre solo** todo paso que deja con qué deshacerlo: un paso de catálogo cuya operación deja respaldo en esa corrida, o un paso libre que lo declara. Corre con `apply --guiados`, que pasa `/neb:migrate`; `apply` a secas solo corre los pasos de base, así que reintentar un paso de base no corre la migración guiada. Sin `--include` no se ejecuta nada más; lo hace cumplir el programa, no el prompt.
  - El respaldo que declara un paso libre se comprueba al volver `aplicar`: que sea un archivo nuevo (no existía antes del paso, contando los que empiezan con punto), no vacío y de esa corrida; que esté directamente en `~/.claude` o en `neb-backups/`; que no sea un enlace ni un archivo vivo (la base y sus `-wal`/`-shm`, un `settings*.json`); y, si es una base SQLite, que esté en un solo archivo (`journal_mode=DELETE`, sin `-wal` ni `-journal`) y pase `integrity_check` (abierta como inmutable, sin dejarle archivos). Si no, el paso es un fallo. Si sirve, queda con permiso solo para el usuario donde el sistema lo respeta.
  - Un paso `exclusivo` nunca pide al dev cerrar sesiones (desde 7.4.0: una versión nueva no puede pedir que se cierren las sesiones abiertas). Comprueba su condición antes de actuar y la vuelve a comprobar con `ctx.exclusivo_ok()` justo antes de la acción que no se deshace (las operaciones del catálogo ya lo hacen); si no se cumple, no hace nada y queda pendiente con su motivo, y se reintenta en la siguiente corrida. La condición por omisión es que ninguna otra conexión tenga la base abierta **en ese momento**: en WAL, pasar a `DELETE` pide acceso exclusivo (una conexión ajena, aunque esté ociosa, lo impide) y se exige volver a WAL; fuera de WAL, un `BEGIN EXCLUSIVE`. No prueba que las demás sesiones estén cerradas (sus hooks abren y cierran la base), y mira la base de `resolve_db_path`: un paso cuya acción no tolera que otra sesión abra la base justo después, o que actúa sobre otro archivo, declara su propia `condicion` y retiene su candado.
  - Si la prueba deja la base fuera de WAL, la regresa antes de responder; un error que no es de candado se reporta con su tipo, no como «otra sesión».
  - `apply --sin-exclusivos` deja pendientes los exclusivos y corre lo demás; es para correrlo a mano: `/neb:migrate` no lo usa. `--include` y `--sin-exclusivos` implican `--guiados`.
  - Sin base, `apply` no la crea (la crea la primera captura): con `--guiados`, corre solo los pasos guiados.
  - Con la base sin migrar (solo existe `neb-logbook.db`, el nombre anterior a 7.0.0), ni `apply` ni `skip` la abren: abrir `neb.db` lo crearía vacío y escondería la base vieja. `apply` a secas responde `base-sin-migrar`; `apply --guiados` corre antes los pasos guiados, entre ellos `7.0.0:renombrar-base`, y, si le cambió el nombre, después los pasos de base; `skip` se niega y el paso sigue pendiente ([`logbook.md`](logbook.md) § "Base sin migrar").
- **Lo que no carga no calla**: una `migrations/<versión>.py` que no carga o un paso cuya detección falla cuenta en el aviso del arranque y deja `apply --guiados` sin `ok`, hasta la versión que lo corrija. Si callara, sus pasos nunca correrían. Del error se reporta su tipo y, si es de sintaxis, la línea; un error de forma de la migración (id repetido, argumento inválido: texto de neb) conserva su mensaje. Si solo hay algo roto, el aviso no ofrece una sesión (nada podría correr). A un paso cuya detección falla, `/neb:migrate` le ofrece «No aplicarlo», que lo saca del aviso; una versión que corrija la detección no lo vuelve a ofrecer.
- **Pide al dev** lo que no deja con qué deshacerlo: quitar un secreto o una variable de usuario, o un paso libre sin respaldo. Solo corre con `apply --include <versión>:<paso>`, y `/neb:migrate` lo pone en un solo menú. Donde no hay herramienta de preguntas (sesión sin interfaz, tarea programada), queda pendiente.

### Catálogo de operaciones

| Operación | Argumentos | Qué hace | Clase |
|---|---|---|---|
| `settings_env_remove` | `claves`, `secretas` (opcional, subconjunto de `claves`), `ruta` (opcional: `settings.json`, por omisión, o `settings.local.json`) | Quita claves del bloque `env` del settings del dir de configuración en uso (`CLAUDE_CONFIG_DIR` o `~/.claude`, supuesto R26) con `update_json`, que verifica el borrado y que nada más cambió. Si ninguna clave está presente, no escribe; si un valor cambió entre la lectura y la escritura, tampoco. El respaldo **no es una copia del archivo** (llevaría cualquier secreto que el dev tenga ahí): guarda solo los pares quitados en `neb-backups/settings-env.<fecha UTC>.json`, un archivo nuevo con permiso solo para el usuario donde el sistema lo respeta (en Windows hereda los permisos de la carpeta, los mismos que el settings). Quedan los de la última corrida | Corre solo; pide al dev, y sin respaldo, si alguna clave presente es de las `secretas` o su nombre lo parece (`TOKEN`, `SECRET`, `PASS`, `KEY`, `AUTH`, `CRED`, `WEBHOOK`), o si un valor trae `@`, `?` o `#` tras el esquema de una URL (`usuario:clave@`, `token@`, `?token=`): un olvido en `secretas` no deja un secreto copiado en `neb-backups/` |
| `user_env_remove` | `nombre` | Variable de entorno de usuario, solo con nombre `NEB_[A-Z0-9_]+` completo. En Windows, la presencia se lee del registro de usuario sin leer el valor (los procesos abiertos conservan el viejo en su entorno); el borrado quita el valor con `winreg` y avisa al sistema con `SendMessageTimeoutW`, sin terminal. Una variable del mismo nombre a nivel de máquina, o cualquier variable fuera de Windows, responde `manual` con la instrucción, y sigue pendiente hasta que el dev la quite o responda «No aplicarlo». Si otra sesión la quitó entre la detección y el borrado, responde `sin-cambio`. Fuera de Windows la presencia se lee del entorno del proceso, sin las variables que declaran `settings.json` y `settings.local.json` (`[asumido]` Claude Code pasa el bloque `env` al entorno de sus hooks y de su Bash) | Pide al dev siempre: el valor no se guarda en ningún archivo ni se imprime |

Nada del catálogo imprime ni guarda el valor de una variable.

### Dónde corre

1. El arranque de cada sesión detecta, en solo lectura, los pasos guiados pendientes del árbol del plugin y avisa con un tope de 900 unidades UTF-16. El aviso pide a Claude no iniciar la migración por su cuenta y ofrecer abrirla en una sesión nueva (supuesto R30 de [`../methodology/platform-assumptions.md`](../methodology/platform-assumptions.md)).
2. En esa sesión, [`/neb:migrate`](../commands/migrate.md), con el mismo árbol del plugin (no el clon de `NEB_HOME`, cuyas migraciones pueden no estar publicadas): estado, prompt de cada versión, `apply`, el menú con lo que pide al dev, verificación por presencia y reporte. Nunca corre `restore`, `apply --include` ni `skip` sin la respuesta del dev en el menú de esa sesión. `[asumido]` una sesión interactiva abierta con `claude "/neb:migrate"` ejecuta el comando con su menú; lo probado es la sesión sin interfaz (R30).
3. A mano: `py bootstrap/neb-migrate.py status`, `apply --guiados [--include <id>…] [--sin-exclusivos]` y `skip <id>`.

**Quién controla lo que se ejecuta**: quien publica en el repo `neb`, igual que con el resto del plugin. Un paso libre es código de la versión que lo trae, y el gate de esa versión revisa que haga solo lo que declara (quién revisa: `profiles/self-applied/roles.md` § "Subagentes por fase"). El mensaje de una excepción de un paso libre, o de una migración que no carga, no se reporta, porque puede traer valores: su `detalle` lleva solo el tipo.

## Estado

`py bootstrap/neb-migrate.py status` (o `--json`) muestra, sin escribir ni crear la base, la versión de Neb y la de esquema del código, la versión y la mínima compatible de la base, su estado (`sin-base`, `sin-migrar`, `ilegible`, `al-dia`, `atras`, `mas-nueva-compatible`, `incompatible`), los pasos detenidos con su motivo, los respaldos y los pasos guiados pendientes (con su clase) y omitidos. `apply` abre la base como lo hace la captura (aplica los pasos pendientes y las reparaciones; reintenta ya un paso con fallo reciente): sirve después de corregir lo que detenía un paso. Solo con `--guiados` corre además los pasos guiados que corren solos.

`status` lee la base en `mode=ro`: sobre una base en WAL sin `-wal`/`-shm` los crea vacíos y quedan ahí; no cambia el contenido de la base.

El arranque de cada sesión avisa, en solo lectura (su única escritura es la reparación de la mínima compatible del paso 3, § "Paso 3: eje proyecto"), cuando un árbol de Neb (el del plugin o el clon de `NEB_HOME`) ya no puede operar la base, cuando un paso de base está detenido, o cuando hay una migración guiada pendiente. Que plugin y clon tengan versiones distintas no es aviso mientras los dos entiendan la base, ni lo es que la base esté atrás (lo normal en la primera sesión tras actualizar).
