# Pendientes — backend, brújula y priorización

Recurso del módulo `hooks/lib/pendings.py` que opera los **pendientes del dev** sobre la misma DB SQLite del logbook (`<datos>/neb.db`; `<datos>` es la carpeta de datos de Neb: `NEB_DATA` si es una ruta absoluta; si no, `~/.neb`). El skill que lo conduce es [`../skills/pendings-review/SKILL.md`](../skills/pendings-review/SKILL.md); el modelo de datos (6 tablas) vive en el esquema inicial [`../hooks/logbook-schema.sql`](../hooks/logbook-schema.sql), en los pasos de base de [`migrations.md`](migrations.md) y los Change MD de los REQ (`neb-pendings-sqlite`, `pendings-taxonomia-cliente-topico`, `neb-eje-proyecto-sin-roadmap`). Aquí: los **ejes curados** (proyecto · tópico) y la curaduría, la **brújula `compas.md`** y la **jerarquía de fuentes** de priorización.

Un pendiente es de tipo `task` (seguimiento) o `session` (sesión pausada): `PD create <task|session> "<contexto>"`. `PD remember-session <work_id> [contexto]` crea un `session` ligado a un work exploratorio de la bitácora (`session_ref`). Cuándo se usa cada uno: [`../workflow/pendings.md`](../workflow/pendings.md).

## Ejes curados (proyecto · tópico) y curaduría

Glosario (el vocabulario abstracto de la metodología no lo fija; es propio de este recurso):

| Término | Qué es |
|---|---|
| **tema** | Una fila de `topic` que clasifica: un hijo de un eje, un tema de legado (sin raíz) o el sentinel `sin-clasificar`. Las raíces también son filas de `topic`, pero no son temas. |
| **eje** | Una de las dos raíces de la jerarquía `topic.parent_id`: `proyecto` (a qué proyecto o ámbito pertenece; puede ser un pseudo-proyecto sin repo) y `topico` (de qué trata). Son contenedores: nunca se sugieren ni se curan. Antes de 7.3.0 la raíz `proyecto` se llamaba `cliente`; el paso de base 3 la renombra al conectar ([`migrations.md`](migrations.md) § "Paso 3: eje proyecto"). Mientras ese paso esté pendiente (tiene espera), el CLI opera degradado: el catálogo `proyecto` queda vacío, los hijos de `cliente` cuentan como temas sin eje y la raíz `cliente` tampoco se sugiere ni se cura. |
| **proyecto / tópico** | Un hijo de la raíz correspondiente. Un pendiente curado tiene **hasta uno por eje** (el skill cura ambos; uno curado a medias sigue apareciendo en el paso de curación). El catálogo vive en la DB (lo siembra `bootstrap/seed-pendings-taxonomy.py` desde un `taxonomy.json` del adoptante) y se lee en el JSON de `PD triage` (`catalog`); el núcleo no trae valores. |
| **curaduría** | `pending_topic.curated = 1` sobre un tema **activo**: clasificación decidida (pase del dev, `curate`). La vigente. Si el tema se archiva, esa fila queda como historial y el pendiente vuelve al flujo de curación. |
| **sugerencia** | `pending_topic.curated = 0`: lo que escribe el matching por keywords (`classify`), con `priority_score` = nº de tokens coincidentes. Solo para pendientes **sin** curaduría; el matching nunca pisa una fila curada ni escribe sobre un pendiente curado. Un texto largo matchea decenas de temas: para priorizar y para proponer la curaduría cuenta solo la **mejor sugerencia por eje** (`triage` la expone como `suggested_proyecto`/`suggested_topico`), nunca el máximo de todas. `classify` guarda solo las mejores `SUGGESTIONS_PER_AXIS` (3) por eje, por score (las que `triage` expone en `suggestions`); las de temas de legado sin eje se guardan todas, porque cuentan para el peso de compas y podarlas cambiaría la banda. |

Las filas sobre temas **archivados** se conservan como historial (bandas incluidas) y las lecturas las ignoran (`_pending_topics` filtra `status='active'`). Al archivar el pendiente, ese historial sobrevive solo en las filas curadas: sus sugerencias se borran todas, también las que estaban sobre temas archivados.

Cuando un pendiente se vuelve obsoleto —`PD archive` o el cierre de su work ligado (`on_work_archived`)— se borran todas sus sugerencias (`curated=0`) en la misma transacción; sus filas curadas quedan. Un obsoleto reactivado (`revive`) conserva su curaduría; si no estaba curado, el siguiente `triage` le regenera las sugerencias (`reclassify`, porque ya no tiene sugerencia vigente).

El índice FTS5 `neb_fts` indexa **solo los temas** (`kind='topic'`): el matching corre el texto de cada pendiente contra él, así que los cuerpos de los pendientes no se indexan. El rebuild completo de `_ensure_fts` limpia las filas `pending` que haya dejado una versión anterior.

- **`PD curate <id|slug> [--proyecto <p>] [--topico <t>] [--slug <s>] [--band alta|media|baja] [--relacionado <ref>]...`** — única vía de escritura de la curaduría. La cita del pendiente (y la de `--relacionado`) debe ser **exacta** (`PD-<id>` o slug completo; un substring no cura). Reemplaza por eje (una fila curada por eje; `is_primary=1` solo en el tópico), borra las sugerencias del pendiente sobre temas activos, persiste la banda en inglés **en todas sus filas curadas** (sobre un pendiente sin curar exige `--proyecto`/`--topico` en la misma llamada), fija la cita canónica y crea vínculos `pending_link` `related`. Siempre responde JSON por stdout (`{"ok": true, ...}` o `{"ok": false, "error": "..."}`) — el wrapper del skill descarta stderr; ante un error no persiste nada (transacción).
- **`PD triage [--proyecto <p>] [--topico <t>]`** devuelve, además de `items`, `groups` y `catalog` (`{"proyecto": [...], "topico": [...]}`), dos conjuntos disjuntos: `suggested` (abiertos sin curar con ≥1 sugerencia vigente) y `unclassified` (abiertos sin curar y sin sugerencia). Su unión = todo lo que espera curaduría. `groups` = componentes conexas de `pending_link` (cualquier relación) **entre abiertos** — el tema compartido dejó de agrupar: con pocos valores por eje, cualquier tema compartido une a medio backlog en un solo bloque. Un filtro fuera del catálogo es error, no "sin pendientes". `--cliente` ya no existe (corte limpio en 7.3.0, sin alias).
- **Siembra y rollback**: `bootstrap/seed-pendings-taxonomy.py --from <triage.json> --catalog <taxonomy.json> [--db] [--apply] [--force] [--backup-dir <dir>] [--rollback <bak>]`. El catálogo trae las llaves `proyecto` y `topico`, y cada item del triage la llave `proyecto`; una llave `cliente` (forma anterior a 7.3.0) en cualquiera de los dos es error explícito que pide renombrarla. Dry-run por defecto (también sobre una DB sin migrar). Si la base no pasó el paso de base 3 y conserva la raíz `cliente`, `--apply` aborta sin respaldo ni escritura y dice cómo resolverlo (`neb-migrate.py status`), y el dry-run lo avisa ([`migrations.md`](migrations.md) § "Paso 3: eje proyecto"); si no, `--apply` toma un respaldo con la API `backup()` de SQLite sobre una conexión plana (nunca copia de archivo), lo verifica (`integrity_check` + conteos) y calcula el plan y siembra en **una** transacción; salta los pendientes ya curados salvo `--force`; el score del pase se hereda cuando la banda coincide. `--rollback <bak>` restaura lógicamente lo sembrado (`pending.slug` y `last_reviewed_at`, `pending_topic`, `topic`, `topic_link`, `pending_link`) dejando `work`/`event`/`session_sync` intactos; lo creado después del respaldo (temas, slug, vínculos de pendientes nuevos) se pierde y el siguiente `triage` lo re-sugiere. Un respaldo de una siembra anterior a 7.3.0 trae la raíz `cliente`: `--rollback` la restaura renombrada a `proyecto` en la misma transacción (el paso de base 3 no vuelve a correr sobre una base ya migrada), y si el respaldo ya trae otro tema `proyecto`, lo mueve a `proyecto-<id>` como el paso de base (desde 7.4.0) y lo avisa. Una raíz de eje archivada (p. ej. por el seed de 7.2.x corrido a mano sobre una base de 7.3.0 o posterior) el `--apply` la re-activa siempre.

## Qué es `compas.md`

Brújula de priorización personal: archivo Markdown **local, no versionado, mantenido por Claude** en `<datos>/compas.md` (ruta exacta: `neb_paths.py path compas`). Mientras no exista, el parser lee `~/.claude/compas.md`, donde vivía hasta 7.x, si sigue ahí: la migración 8.0.0 lo muda y esa lectura de respaldo sale en 9.0.0. `write_compas()` escribe siempre en `<datos>/`. Es la **fuente ÚNICA del peso de cada tema** — los `topic` de la DB no llevan peso. El recomendador la **parsea una vez por llamada** de `triage` o `rank` (no cachea el peso en la DB ni entre llamadas). Aplica solo a los pendientes **sin banda curada** (ver jerarquía abajo).

**Formato v3 (objetivos → peso por tópico + bonus por proyecto):**

```markdown
---
version: 3
updated_at: 2026-11-24
owner: <usuario>
---

## Objetivo: Seguridad y continuidad
- **Peso:** 90
- **Temas:** seguridad, respaldo-dr

## Objetivo: Avanzar alpha
- **Peso:** 70
- **Temas:** funcionalidad-ux
- **Proyectos:** alpha=+15, beta=+10
```

- `- **Peso:** <int>` en `[0,100]` (por defecto 0 si ausente/no numérico, clamp).
- `- **Temas:** <csv>` → slugs del eje **tópico** (`split(',')`, trim, `normalize()`: minúsculas y sin acentos —NFKD con descarte de combinantes `Mn`—, espejo del `remove_diacritics` del matching FTS5). Un slug de proyecto aquí **no** pondera (el recomendador toma el peso solo de temas del eje tópico o sin eje).
- `- **Proyectos:** <slug=+bonus, ...>` (opcional) → **bonus aditivo** por proyecto (eje `proyecto`), `[0,100]`; se suma una sola vez (el mayor bonus entre los proyectos del pendiente) y el total se recorta a 100.
- Un tema (o proyecto) en >1 objetivo gana el **mayor** peso/bonus (max). No mencionado → 0.
- `write_compas()` escribe siempre v3 (`PD write-compas` recibe por objetivo `["nombre", peso, ["topico", ...]]` o `["nombre", peso, ["topico", ...], {"<proyecto>": bonus}]`; una lista de 5 elementos, la forma anterior con roadmap, es error).
- Corte limpio en 7.3.0: el parser no reconoce las líneas `- **Clientes:**` ni `- **Roadmap:**` de v1/v2 (se ignoran sin aviso, y un compas con `Clientes:` pierde sus bonos mientras no se migre). El paso `compas-proyectos` de la migración guiada 7.3.0 lo reescribe a v3 con respaldo; desde 7.5.0 corre solo al iniciar sesión (o con `/neb:migrate`).

El parser **tolera la ausencia** de `compas.md` (degrada a señales intrínsecas). `compas.md` NO se versiona ni se incluye en el repo; este documento es solo su formato y contrato. La plantilla literal la materializa `write_compas()` solo tras OK del dev.

## Vía de consulta del dev: el skill, no el CLI crudo

Toda consulta del dev sobre sus pendientes —desde "cuáles son mis pendientes" hasta priorizar o pasar lista— se atiende por el skill [`pendings-review`](../skills/pendings-review/SKILL.md), que aplica la **capa de valor**: prioriza por banda, consulta la brújula `compas.md` y, si falta o la cobertura es baja, dispara `infer_objectives` para aprenderla (ver jerarquía abajo).

Los verbos `list` y `show` de `pendings.py` son **acceso de bajo nivel / debug** (volcado JSON sin priorización ni brújula). NO son una vía de consulta equivalente ofrecida al dev: usarlos para responder "cuáles son mis pendientes" **salta la capa de valor** y oculta el nudge de `compas.md`. Resérvalos para inspección puntual, scripting o diagnóstico.

## Cómo citar un pendiente (notación canónica)

La **cita canónica de un pendiente es su `[slug]`**, persistido en la columna `pending.slug` (kebab-case, **único** entre todos los pendientes —índice parcial `uq_pending_slug`—, histórico: un slug de cerrado no se recicla). El tag `[nombre-req]` que vive en `context_origin` es el **fallback histórico** para pendientes sin columna (nunca se reescribe: `context_origin` es inmutable). Cuando se muestra un número, es **siempre el `id` de `neb.db`**, escrito `PD-<id>` (p.ej. `PD-170`). `pendings.py show` resuelve por cualquiera de las vías, en este orden:

```bash
PD show 170            # por id de neb.db (rowid)
PD show PD-170         # idem (acepta prefijo PD- o #)
PD show alpha-pem-ppk  # por slug: 1º columna pending.slug (kind `slug`) → 2º tag exacto [slug] en
                       # context_origin (`slug-exact`) → 3º substring (`slug-loose`); lista candidatos si es ambiguo
```

El slug se fija con `PD curate <id> --slug <s>` (o lo siembra el pase); `PD backfill-slugs` rellena la columna desde el tag inicial `[slug]` de los pendientes viejos **solo cuando el tag es único** (los repetidos quedan `NULL` y siguen resolviendo por el fallback).

**El `#NNN` del `pendings.md` histórico queda RETIRADO como cita de pendiente.** Esa numeración del markdown plano **no es clave en `neb.db`**: la migración asignó `id` autoincrement y descartó el número del `.md` (sobrevive solo como texto en el prefijo `NN.` de `context_origin`). Por eso `#NNN` colisiona (un mismo número apunta a varios items) y `show NNN` resolvería al item equivocado. Al citar un pendiente —en chat, memorias, Change MDs— usar `[slug]` (y `PD-<id>` si se necesita el número). Nunca `#NNN`.

## Jerarquía de fuentes de priorización

De mayor a menor:

1. **Criterio explícito del prompt** (efímero, `PD rank "<criterio>"`) — manda en esa consulta; NO se escribe a `compas.md` salvo que el dev lo pida (`write-compas`).
2. **Banda curada** — `pending_topic.curated=1` con `priority_band` (pase del dev o `curate --band`): es la recomendación tal cual (`source='curated'`), sin compas ni señales intrínsecas, para que ningún pase automático la pise. Un pendiente curado **sin** banda cae a la fuente siguiente.
3. **`compas.md`** — peso por **tópico** vía objetivos + **bonus por proyecto**.
4. **Señales intrínsecas** del pending — work ligado + fase (`work.req_state` vía `pending.work_ref`), bloqueo (`pending_link.relation='blocks'` saliente sube prioridad), urgencia en `context_origin` (`urgente|crítico|bloqueante|P1|P2`), recencia (`last_reviewed_at IS NULL`).
5. **Si insuficiente** → `infer_objectives` infiere una propuesta de objetivos (solo sobre temas del eje tópico o sin eje; los proyectos van como bonus), el skill **pregunta** al dev (AskUserQuestion) y, con el OK, `write_compas` **escribe** `compas.md`. La brújula se aprende, no inventa pesos.

**Bandas (presentación):** `score>=67`→alta · `34..66`→media · `<34`→baja. Una banda curada sin score trae 80/50/20.

> Por qué la banda curada manda: una brújula por tema no reproduce un juicio por pendiente — dentro de un mismo tópico conviven P0 y P3 — así que la banda decidida ítem por ítem es el dato, y compas es el default para lo que aún no se decidió.

## Traducción de enums (DB inglés → presentación español)

La DB guarda **siempre** el enum en inglés; la presentación (skill/recomendador) traduce al mostrar y vuelve a inglés al escribir:

| DB (inglés) | Presentación (español) |
|---|---|
| `pending.status` `open` / `obsolete` | abierto / obsoleto |
| `obsolete_cause` `no-longer-applies` / `resolved-otherwise` | ya no aplica / resuelto de otra forma |
| `topic.status` `active` / `archived` | activo / archivado |
| `relation` `related` / `depends` / `blocks` | relacionado / depende / bloquea |
| `priority_band` `high` / `medium` / `low` | alta / media / baja |
| `recommend_priority.source` `prompt` / `curated` / `compas` / `intrinsic` / `unclassified` | prompt / curada / compas / intrínseca / sin clasificar |

`pending_topic.curated` no es un enum sino un flag `0/1` (sugerencia / curado). `band_to_db('alta')='high'` (y `media→medium`, `baja→low`): el caller que persista `pending_topic.priority_band` traduce de vuelta a inglés — la única vía es `PD curate --band`; `priority_score` se persiste tal cual.

## Convención de paths

Citar archivos según la tabla de referencias del [`CLAUDE.md`](../CLAUDE.md) (nombre + repo para archivos del núcleo; paths absolutos solo en `personal/*.md`).
