# Configuración y carpeta de datos de Neb

Dónde guarda Neb lo suyo y cómo se configura. El único resolvedor de las rutas y de la configuración es [`../hooks/lib/neb_paths.py`](../hooks/lib/neb_paths.py): los hooks, el arranque, los CLI y la migración guiada lo usan, y ninguno arma estas rutas por su cuenta.

## Carpeta de datos

La **carpeta de datos de Neb** (`<datos>` en la documentación) es:

- `NEB_DATA`, si es una ruta absoluta. `~` se expande contra el home, y en Windows la forma `/c/...` de Git Bash pasa a `C:\...`;
- si no, `~/.neb`. Un `NEB_DATA` vacío o relativo se ignora: una ruta relativa resolvería distinto según el directorio desde el que corre cada proceso.

**Por qué fuera de `~/.claude`.** `~/.claude` es el dir de configuración de Claude Code. Los datos de Neb (pendientes, bitácora, brújula, planes, configuración) no son de Claude Code: viven aparte para poder llevarlos a otra herramienta de IA sin tener que desenredarlos de los de Claude Code. Por lo mismo, **no siguen a `CLAUDE_CONFIG_DIR`**: con esa variable, Claude Code usa otro dir de configuración (supuesto R26 de [`../methodology/platform-assumptions.md`](../methodology/platform-assumptions.md)), y la carpeta de datos sigue siendo `NEB_DATA` o `~/.neb`.

**Lo que se queda en el dir de configuración de Claude Code** (`~/.claude` o `CLAUDE_CONFIG_DIR`): `settings.json` (con su bloque `env`: `NEB_HOOKS`, `NEB_WORKSPACE`, `NEB_HOME`), `projects/` (transcripts y la memoria del proyecto en `memory/`), `plugins/` y `backups/`. Neb los lee y, en los casos que documenta (la migración guiada, `/wakeup`, la actualización automática), los escribe; no los muda.

**Dónde declarar `NEB_DATA`.** Como variable de entorno del usuario en el sistema operativo, para que la vean igual los hooks, el Bash de Claude y una terminal propia. Declarada solo en el `env` de `settings.json`, la ven los hooks y el Bash de Claude Code pero no un CLI que corras en otra terminal, que resolvería `~/.neb` y operaría otra base (supuesto R33 de [`../methodology/platform-assumptions.md`](../methodology/platform-assumptions.md)). Un cambio en `NEB_DATA` rige en las sesiones que se abren después.

**Cambiar de carpeta.** Neb no muda de una carpeta de datos a otra: la migración 8.0.0 solo muda lo que estaba en `~/.claude`. Para cambiar `NEB_DATA` cuando ya hay datos, mueve tú la carpeta completa con todas las sesiones de Claude Code cerradas y después cambia la variable; si no, la carpeta nueva arranca vacía y la vieja deja de leerse.

**Protección.** Neb crea la carpeta y sus subcarpetas con permiso solo para el usuario donde el sistema lo respeta, y nunca escribe a través de un enlace (symlink o junction): con la carpeta de datos como enlace, la captura no escribe y cada CLI responde `carpeta-de-datos` ([`logbook.md`](logbook.md)). Para guardar los datos en otro lugar, `NEB_DATA` lleva la ruta real.

**`NEB_DATA` en `~/.claude`.** Se admite: no hay mudanza, y la base, `compas.md`, `approved-plans/` y `research/` se quedan donde estaban. `config.json` queda en `~/.claude/config.json`, el estado y la caché en `~/.claude/state/` y `~/.claude/cache/`, y los respaldos de la base y de la migración guiada van a `~/.claude/neb-backups/`, porque `~/.claude/backups/` es de Claude Code ([`migrations.md`](migrations.md) § "Respaldo y vuelta atrás").

## Árbol

| Ruta | Qué guarda | Doc |
|---|---|---|
| `<datos>/config.json` | La configuración de Neb (§ "config.json") | este archivo |
| `<datos>/compas.md` | La brújula de prioridades de los pendientes | [`../skills/pendings-review/SKILL.md`](../skills/pendings-review/SKILL.md) |
| `<datos>/neb.db` | Pendientes y bitácora de relevo (SQLite; con sus `-wal`/`-shm`, el candado `.neb-migrate.lock` y `.neb-requisitos.json`) | [`pendings.md`](pendings.md), [`logbook.md`](logbook.md), [`migrations.md`](migrations.md) |
| `<datos>/approved-plans/` | Lugar de caída de los planes aprobados en plan mode | [`../workflow/approved-plans.md`](../workflow/approved-plans.md) |
| `<datos>/research/` | Research cross-proyecto o sin dueño (no versionado) | [`../research/README.md`](../research/README.md) |
| `<datos>/backups/` | Respaldos de la base, de la configuración y manifiestos de la migración guiada | [`migrations.md`](migrations.md) |
| `<datos>/state/<nombre>/` | Estado efímero (p. ej. `state/preprocess/<session_id>.json`, el modo de `/preprocess`) | [`prompt-preprocessing.md`](prompt-preprocessing.md) |
| `<datos>/cache/<nombre>/` | Lo que se regenera solo (p. ej. `cache/sounds/chimes-loud.wav`) | [`notify-on-stop.md`](notify-on-stop.md) |

## config.json

Un solo archivo para toda la configuración de Neb. Solo hace falta escribir lo que cambia; el resto toma su valor por omisión. Esquema completo con los valores por omisión:

```json
{
  "schema": 1,
  "notify": {
    "stop": { "enabled": true, "wav": null, "min_seconds": 10, "max_chimes": 5, "scaling": "per-minute" },
    "permission": { "enabled": true, "wav": null }
  },
  "preprocess": { "mode": "off", "model": "claude-haiku-4-5-20251001", "prefix": "$$" },
  "language": {
    "base": "es",
    "variedad": null,
    "registro": null,
    "tratamiento": null,
    "permitir_voseo": null,
    "extranjerismos": null
  }
}
```

| Sección | Qué configura | Llaves y valores |
|---|---|---|
| `notify.stop` | Aviso sonoro al cierre de turno | [`notify-on-stop.md`](notify-on-stop.md) § "Configuración personal default" |
| `notify.permission` | Aviso sonoro al pedir permiso | [`notify-on-permission.md`](notify-on-permission.md) § "Configuración personal default" |
| `preprocess` | Corrector de prompts | [`prompt-preprocessing.md`](prompt-preprocessing.md) § "Configuración personal default" |
| `language` | Idioma y perillas de redacción del individuo | § "Sección language" |

Reglas de lectura (todas las secciones):

- `schema` es `1`. Neb lo escribe al crear el archivo; no se edita.
- Se lee en UTF-8 con o sin BOM (`Out-File -Encoding utf8` de Windows PowerShell 5.1 escribe BOM).
- Una llave ausente, o de un tipo distinto del de su valor por omisión, toma el valor por omisión: `"enabled": "false"` no apaga (no es booleano), `"max_chimes": "3"` no cuenta. Una llave con valor por omisión `null` acepta `null` o texto; `permitir_voseo`, `null` o booleano.
- Un archivo ilegible (JSON roto, o que no es un objeto) aplica todos los valores por omisión. Leer nunca hace fallar a un hook.
- Las llaves que Neb no conoce se ignoran al leer y se conservan al escribir con `set`.
- Un valor del tipo correcto pero fuera de lo admitido lo normaliza el consumidor de su sección (p. ej. `max_chimes` se acota a `[1, 20]`; un `mode` fuera de los tres deja el corrector en `off`): lo dice el doc de cada sección.

## Leer y cambiar la configuración

Desde Git Bash, Linux o Mac (`NEB_SRC` es la raíz del plugin instalado o tu clon de `NEB_HOME`; `py` también puede ser `python` o `python3`):

```bash
py "$NEB_SRC/hooks/lib/neb_paths.py" path data              # la carpeta de datos
py "$NEB_SRC/hooks/lib/neb_paths.py" path db                # también: config, backups, compas, approved-plans,
                                                            # research, legacy, state/<x>, cache/<x>
py "$NEB_SRC/hooks/lib/neb_paths.py" config                 # la config efectiva, con los valores por omisión
py "$NEB_SRC/hooks/lib/neb_paths.py" config language        # una sección
py "$NEB_SRC/hooks/lib/neb_paths.py" set language.tratamiento '"usted"'
py "$NEB_SRC/hooks/lib/neb_paths.py" set language.permitir_voseo true
py "$NEB_SRC/hooks/lib/neb_paths.py" set language.variedad null
```

- `set <sección.llave> <valor>` escribe una sola llave de forma atómica, sin tocar las demás, e imprime la ruta de `config.json`. El valor va como JSON: un texto con sus comillas, una ruta de Windows con `/`, y `null` para volver a «no declarada» en una llave cuyo valor por omisión es `null` (en las demás, `set` con el valor por omisión). En Windows PowerShell 5.1 las comillas internas se pierden al pasar el argumento: escríbelas como `'\"usted\"'`.
- Si `config.json` no existe, `set` lo crea con `schema` y con lo que dijeran los JSON sueltos anteriores (§ "Transición desde 7.x").
- Sale con 2, sin escribir, si la llave no existe en el esquema, si es una sección completa, si el valor es de otro tipo o si `config.json` no es JSON legible (no pisa lo que escribiste: corrígelo a mano).
- `path` y `config` solo leen y salen con 0; un nombre de ruta desconocido sale con 2.

Editar `config.json` a mano también sirve: rige en el siguiente evento de cada hook, sin reiniciar la sesión.

## Sección language

La declaración **estructurada** del idioma y las perillas de redacción del individuo para la conversación con Claude. Es un punto de customización: **sustituye** el valor por omisión, no estrecha una regla ([`../methodology/personal-vs-team.md`](../methodology/personal-vs-team.md) § "Puntos de customización vs reglas de proceso"). Alcance y precedencia: [`../general/communication.md`](../general/communication.md) § "Idioma".

| Llave | Valores | Por omisión |
|---|---|---|
| `base` | El idioma, código ISO 639-1 | `"es"` |
| `variedad` | `mexico` · `espana` · `rioplatense` · `andino` · `caribeno` · `neutro` ([`redaccion-es.md`](redaccion-es.md) § "A. Variedad regional del español") | `null` |
| `registro` | `formal_academico` · `formal_profesional` · `neutro` · `informal` · `literario` · `tecnico` ([`redaccion-es.md`](redaccion-es.md) § "C. Registro") | `null` |
| `tratamiento` | `tuteo` · `usted`: cómo se dirige Claude al dev | `null` |
| `permitir_voseo` | `true` · `false` ([`redaccion-es.md`](redaccion-es.md) § "E. Zonas grises (toggles individuales)") | `null` |
| `extranjerismos` | `traducir_siempre` · `traducir_si_hay_equivalente_claro` · `marcar_pero_no_cambiar` · `respetar_si_estan_en_cursiva` · `respetar_todos` ([`redaccion-es.md`](redaccion-es.md) § "F. Tratamiento de extranjerismos") | `null` |

- `null` es «no declarada»: rige lo que fije el overlay del adoptante o, sin él, el núcleo.
- Neb no valida los valores contra estas listas: un valor fuera de ellas llega tal cual al arranque. Usa los de la tabla.
- Hoy solo `es` tiene lineamientos de redacción (`general/communication.md` § "Idioma" y [`redaccion-es.md`](redaccion-es.md)); con otro `base`, las demás perillas no tienen lista de valores que las respalde. El soporte de varios idiomas es un REQ posterior.
- El arranque inyecta las perillas declaradas (las que no son `null`; `base`, solo si no es `es`) como el bloque de idioma del individuo, después de la configuración personal; un cambio rige desde la siguiente sesión.

## Transición desde 7.x

Hasta 7.x la configuración vivía en tres JSON sueltos de `~/.claude`: `notify-on-stop.json`, `notify-on-permission.json` y `preprocess.json` (secciones `notify.stop`, `notify.permission` y `preprocess`). Mientras `config.json` no exista, Neb los sigue leyendo con las mismas reglas; en cuanto `config.json` existe, rige solo ese. El paso `8.0.0:fusionar-config` de la migración guiada los junta en `config.json` y los borra, con respaldo ([`../migrations/8.0.0.md`](../migrations/8.0.0.md)). La lectura de los JSON sueltos es un residuo de transición: sale en 9.0.0.
