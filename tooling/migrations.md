# Migraciones de `neb.db` — versión de esquema y pasos de base

Cómo cambia el esquema de `~/.claude/neb.db` de una versión de Neb a otra sin que plugin, clon y sesiones abiertas tengan que coincidir de versión. Desde 6.48.0. La regla de qué debe traer una versión que cambia el esquema vive en [`../process/version-control.md`](../process/version-control.md) § "Flujo al cerrar REQ"; aquí, la mecánica. Código: `hooks/lib/_migrations.py` (mecanismo y pasos), `hooks/lib/_db_shared.py` (conexión y reparaciones), `bootstrap/neb-migrate.py` (estado y operación).

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

Un código anterior a 6.48.0 no conoce la regla: sobre una base de 6.48.0 funciona igual que antes (mismo esquema, una tabla de más); sobre una base que ya pasó un paso que quita columnas falla como fallaba antes de este mecanismo. Ese es el riesgo de una versión que sube la mínima compatible mientras alguna máquina sigue con código anterior a 6.48.0; el aviso del arranque lo nombra cuando ve un árbol así.

## Pasos de base

Un **paso de base** es un cambio del esquema de `neb.db` escrito en código (lista `STEPS` de `hooks/lib/_migrations.py`). Lo aplica la primera conexión de una versión que lo trae. Atributos:

| Atributo | Qué significa |
|---|---|
| `n`, `titulo` | Número consecutivo y nombre |
| `aplicar(con)` | El cambio. Corre dentro de `BEGIN IMMEDIATE` junto con su fila de `schema_step`: queda todo o nada. Sin `commit()` ni `executescript` adentro (el mecanismo lo detecta), y sin atrapar `sqlite3.Error`: un error que SQLite revierte solo dejaría las sentencias siguientes confirmándose una por una |
| `min_code` | Mínima compatible que deja. Sube cuando una escritura válida del código anterior fallaría (columna `NOT NULL` sin `DEFAULT`, `UNIQUE`, `CHECK` o trigger nuevos) o cuando un dato que ese código lee desaparece o cambia de significado. Un paso que solo agrega la conserva |
| `destructivo` | Borra o reescribe datos: lleva respaldo previo (§ "Respaldo y vuelta atrás"), salvo en una base que se acaba de crear en esa misma conexión |
| `espera` | El código nuevo funciona aunque el paso no se haya aplicado. Si no se puede, la conexión sigue con la base en `V` y se reintenta en la siguiente |
| `precheck(con)` | Opcional, solo lectura: motivo por el que el paso no puede correr todavía (p. ej. una vista del usuario sobre una columna). Corre antes del candado y del respaldo |

Cuando un paso no se puede aplicar (candado ocupado, `precheck` con motivo, respaldo fallido o error en `aplicar`, que revierte): si ese paso y todos los posteriores tienen `espera`, la conexión sigue con la base en `V`; si alguno no la tiene, un candado ocupado da la conexión vacía (como antes) y un bloqueo que no se resuelve solo responde `paso-bloqueado`. Un respaldo fallido o un error de `aplicar` (también una excepción que no es de SQLite) dejan su motivo en `schema_step_error`, porque el `stderr` de la captura no lo ve nadie: lo muestran el arranque y `neb-migrate.py status`. Un `precheck` con motivo o un candado ocupado no se guardan: el arranque recalcula el `precheck`.

- **Espera tras un fallo guardado**: durante 10 minutos las conexiones no reintentan el paso (cada intento de un paso destructivo copia la base con el candado tomado). `py bootstrap/neb-migrate.py apply` lo reintenta ya.
- **Transacción rota**: si `aplicar` confirma algo por su cuenta, lo confirmado ya no se revierte. El paso queda detenido sin reintentos, con su motivo (`transaccion-rota:`) y la ruta del respaldo previo, que se conserva; la salida es `restore` desde ese respaldo.
- **Otro proceso avanzó la base**: si al tomar el candado (o tras un `precheck` con motivo) la base ya está en ese paso o más allá, la conexión vuelve a leer `V` y `F` y aplica otra vez la regla de compatibilidad.

El **paso 1** es el esquema inicial: `executescript` del archivo más las columnas que una base anterior no tenga. Es idempotente; relee la versión justo antes del `executescript` (si otro proceso ya lo registró, no vuelve a agregar columnas) y se registra con relectura e `INSERT OR IGNORE` porque dos procesos pueden llegar a la vez.

Fuera de los pasos quedan dos reparaciones que corren después de ellos en cada conexión con `V <= C` (nunca sobre una base más nueva que el código): el índice `uq_pending_slug` si falta, y la limpieza de las tablas de transcripts retiradas en 6.41.0, sin respaldo, como desde entonces.

Con la base en versión 1 o más, el esquema inicial ya no se reaplica en cada conexión: una tabla borrada a mano deja de recrearse sola.

### Escribir un paso

1. Agrega un `Step` al final de `STEPS` con el siguiente número y sube `SCHEMA_VERSION` (una sola línea literal: el arranque la lee de otro árbol como texto).
2. `aplicar` relee lo que va a cambiar y toca solo lo que existe; nunca `commit()` ni `executescript`.
3. Decide `min_code`, `destructivo`, `espera` y `precheck` con la tabla de arriba.
4. Pruebas en `hooks/tests/`: el paso sobre una base de la versión anterior, sobre una base nueva y con su falla sembrada; y, antes del gate de Fase 4, sobre una copia de una base real (`profiles/self-applied/deployment.md` § "Validación").
5. El fragmento de la versión dice qué hace el paso y si sube la mínima compatible.

## Respaldo y vuelta atrás

- Antes de un paso destructivo, el mecanismo copia la base con la API de backup de SQLite desde una conexión aparte a `<carpeta de la base>/neb-backups/neb.pre-paso-<n>.<fecha UTC>.db` y la verifica con `integrity_check`. La copia queda en un solo archivo (`journal_mode=DELETE`): leerla no le deja `-wal` ni `-shm`. Si el respaldo falla, el paso no corre. La carpeta tiene permiso solo para el usuario donde el sistema lo respeta.
- Al confirmar el paso se borran los demás `neb.pre-paso-*.db`: queda 1 (en Windows, uno que otro proceso tenga abierto se queda hasta la siguiente poda). Si el paso falla, ese respaldo se borra, salvo con la transacción rota. Los respaldos hechos a mano no se tocan.
- **Volver atrás**: regresar primero plugin y clon a la versión anterior, y después `py bootstrap/neb-migrate.py restore <archivo>`. No hay pasos inversos. `restore`:
  - solo acepta un `neb.pre-paso-*.db` o un `neb.pre-restore.*.db` que esté directamente en `neb-backups/`; ni el archivo ni `neb-backups/` pueden ser enlace o junction (un enlace en una carpeta superior, como `.claude` movida, sí se acepta);
  - conviene correrlo con las sesiones cerradas: lo que otra sesión escriba entre el respaldo de la base actual y la restauración se pierde;
  - se niega si el código que lo corre no podría operar la base restaurada, o si la siguiente conexión volvería a aplicar los pasos que el respaldo no tiene (la actualización automática del plugin puede traer de vuelta la versión nueva); `--remigrar` permite lo segundo a propósito, para recuperar datos y dejar que el paso corra otra vez;
  - respalda antes la base actual como `neb.pre-restore.<fecha UTC>.db` (queda 1, aparte de los de los pasos) y nunca borra el archivo del que restaura;
  - escribe con la API de backup hacia la base viva, con una conexión directa; nunca copia ni renombra archivos (un `-wal` vivo corrompería la copia).

## Estado

`py bootstrap/neb-migrate.py status` (o `--json`) muestra, sin escribir ni crear la base, la versión de Neb y la de esquema del código, la versión y la mínima compatible de la base, su estado (`al-dia`, `atras`, `mas-nueva-compatible`, `incompatible`), los pasos detenidos con su motivo y los respaldos. `apply` abre la base como lo hace la captura (aplica los pasos pendientes y las reparaciones): sirve después de corregir lo que detenía un paso.

El arranque de cada sesión avisa, en solo lectura, cuando un árbol de Neb (el del plugin o el clon de `NEB_HOME`) ya no puede operar la base, o cuando un paso de base está detenido. Que plugin y clon tengan versiones distintas no es aviso mientras los dos entiendan la base, ni lo es que la base esté atrás (lo normal en la primera sesión tras actualizar).
