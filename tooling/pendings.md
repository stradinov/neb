# Pendientes — backend, brújula y priorización

Recurso del módulo `hooks/lib/pendings.py` que opera los **pendientes del dev** sobre la misma DB SQLite del logbook (`~/.claude/neb.db`; resolver dual-mode `neb.db ∨ neb-logbook.db`). El skill que lo conduce es [`../skills/pendings-review/SKILL.md`](../skills/pendings-review/SKILL.md); el modelo de datos (6 tablas) vive en [`../hooks/logbook-schema.sql`](../hooks/logbook-schema.sql) y los change MD de los REQ (`neb-pendings-sqlite`, `pendings-taxonomia-cliente-topico`). Aquí: los **ejes curados** (cliente · tópico) y la curaduría, la **brújula `compas.md`**, la **jerarquía de fuentes** de priorización y la **normalización slug↔subsistema**.

## Ejes curados (cliente · tópico) y curaduría

Glosario (el vocabulario abstracto de la metodología no lo fija; es propio de este recurso):

| Término | Qué es |
|---|---|
| **tema** | Una fila de `topic` que clasifica: un hijo de un eje, un tema de legado (sin raíz) o el sentinel `sin-clasificar`. Las raíces también son filas de `topic`, pero no son temas. |
| **eje** | Una de las dos raíces de la jerarquía `topic.parent_id`: `cliente` (quién / para quién) y `topico` (de qué trata). Son contenedores: nunca se sugieren ni se curan. |
| **cliente / tópico** | Un hijo de la raíz correspondiente. Un pendiente curado tiene **hasta uno por eje** (el skill cura ambos; uno curado a medias sigue apareciendo en el paso de curación). El catálogo vive en la DB (lo siembra `bootstrap/seed-pendings-taxonomy.py` desde un `taxonomy.json` del adoptante) y se lee en el JSON de `PD triage` (`catalog`); el núcleo no trae valores. |
| **curaduría** | `pending_topic.curated = 1` sobre un tema **activo**: clasificación decidida (pase del dev, `curate`). La vigente. Si el tema se archiva, esa fila queda como historial y el pendiente vuelve al flujo de curación. |
| **sugerencia** | `pending_topic.curated = 0`: lo que escribe el matching por keywords (`classify`), con `priority_score` = nº de tokens coincidentes. Solo para pendientes **sin** curaduría; el matching nunca pisa una fila curada ni escribe sobre un pendiente curado. Un texto largo matchea decenas de temas: para priorizar y para proponer la curaduría cuenta solo la **mejor sugerencia por eje** (`triage` la expone como `suggested_cliente`/`suggested_topico`), nunca el máximo de todas. |

Las filas sobre temas **archivados** se conservan como historial (bandas incluidas) y las lecturas las ignoran (`_pending_topics` filtra `status='active'`).

- **`PD curate <id|slug> [--cliente <c>] [--topico <t>] [--slug <s>] [--band alta|media|baja] [--relacionado <ref>]...`** — única vía de escritura de la curaduría. La cita del pendiente (y la de `--relacionado`) debe ser **exacta** (`PD-<id>` o slug completo; un substring no cura). Reemplaza por eje (una fila curada por eje; `is_primary=1` solo en el tópico), borra las sugerencias del pendiente sobre temas activos, persiste la banda en inglés **en todas sus filas curadas** (sobre un pendiente sin curar exige `--cliente`/`--topico` en la misma llamada), fija la cita canónica y crea vínculos `pending_link` `related`. Siempre responde JSON por stdout (`{"ok": true, ...}` o `{"ok": false, "error": "..."}`) — el wrapper del skill descarta stderr; ante un error no persiste nada (transacción).
- **`PD triage [--cliente <c>] [--topico <t>]`** devuelve, además de `items`, `groups` y `catalog`, dos conjuntos disjuntos: `suggested` (abiertos sin curar con ≥1 sugerencia vigente) y `unclassified` (abiertos sin curar y sin sugerencia). Su unión = todo lo que espera curaduría. `groups` = componentes conexas de `pending_link` (cualquier relación) **entre abiertos** — el tema compartido dejó de agrupar: con pocos valores por eje, cualquier tema compartido une a medio backlog en un solo bloque. Un filtro fuera del catálogo es error, no "sin pendientes".
- **Siembra y rollback**: `bootstrap/seed-pendings-taxonomy.py --from <triage.json> --catalog <taxonomy.json> [--db] [--apply] [--force] [--backup-dir <dir>] [--rollback <bak>]`. Dry-run por defecto (también sobre una DB sin migrar); `--apply` toma un respaldo con la API `backup()` de SQLite sobre una conexión plana (nunca copia de archivo), lo verifica (`integrity_check` + conteos) y calcula el plan y siembra en **una** transacción; salta los pendientes ya curados salvo `--force`; el score del pase se hereda cuando la banda coincide. `--rollback <bak>` restaura lógicamente lo sembrado (`pending.slug` y `last_reviewed_at`, `pending_topic`, `topic`, `topic_link`, `pending_link`) dejando `work`/`event`/`transcript_*` intactos; lo creado después del respaldo (temas, slug, vínculos de pendientes nuevos) se pierde y el siguiente `triage` lo re-sugiere.

## Qué es `compas.md`

Brújula de priorización personal: archivo Markdown **local, no versionado, mantenido por Claude** en `~/.claude/compas.md`. Es la **fuente ÚNICA del peso de cada tema** — los `topic` de la DB no llevan peso. El recomendador la **parsea en cada pase** de `/pendings-review` (no cachea el peso en la DB). Aplica solo a los pendientes **sin banda curada** (ver jerarquía abajo).

**Formato v2 (objetivos → peso por tópico + bonus por cliente + roadmap opcional):**

```markdown
---
version: 2
updated_at: 2026-09-22
owner: <usuario>
---

## Objetivo: Seguridad y continuidad
- **Peso:** 90
- **Temas:** seguridad, respaldo-dr
- **Roadmap:** —

## Objetivo: Avanzar roadmap de alpha
- **Peso:** 70
- **Temas:** funcionalidad-ux
- **Roadmap:** alpha
- **Clientes:** alpha=+15, beta=+10
```

- `- **Peso:** <int>` en `[0,100]` (por defecto 0 si ausente/no numérico, clamp).
- `- **Temas:** <csv>` → slugs del eje **tópico** (`split(',')`, trim, `normalize()`). Un slug de cliente aquí **no** pondera (el recomendador toma el peso solo de temas del eje tópico o sin eje).
- `- **Clientes:** <slug=+bonus, ...>` (opcional) → **bonus aditivo** por cliente (eje `cliente`), `[0,100]`; se suma una sola vez (el mayor bonus entre los clientes del pendiente) y el total se recorta a 100.
- `- **Roadmap:** <proyecto|—>` → si trae un proyecto, ese objetivo delega el **orden fino** entre sus pendings al roadmap real (repo `roadmap`).
- Un tema (o cliente) en >1 objetivo gana el **mayor** peso/bonus (max). No mencionado → 0.
- `version: 1` (sin `Clientes:`) sigue parseando igual; `write_compas()` escribe siempre v2.

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

**El `#NNN` del `pendings.md` histórico queda RETIRADO como cita de pendiente.** Esa numeración del markdown plano **no es clave en `neb.db`**: la migración asignó `id` autoincrement y descartó el número del `.md` (sobrevive solo como texto en el prefijo `NN.` de `context_origin`). Por eso `#NNN` colisiona (un mismo número apunta a varios items) y `show NNN` resolvería al item equivocado. Al citar un pendiente —en chat, memorias, change MDs— usar `[slug]` (y `PD-<id>` si se necesita el número). Nunca `#NNN`.

## Jerarquía de fuentes de priorización

De mayor a menor:

1. **Criterio explícito del prompt** (efímero) — manda en esa consulta; NO se escribe a `compas.md` salvo que el dev lo pida (`write-compas`).
2. **Banda curada** — `pending_topic.curated=1` con `priority_band` (pase del dev o `curate --band`): es la recomendación tal cual (`source='curated'`), sin compas ni señales intrínsecas, para que ningún pase automático la pise. Un pendiente curado **sin** banda cae a la fuente siguiente.
3. **`compas.md`** — peso por **tópico** vía objetivos + **bonus por cliente**; un objetivo puede delegar el orden fino a un roadmap.
4. **Señales intrínsecas** del pending — work ligado + fase (`work.req_state` vía `pending.work_ref`), bloqueo (`pending_link.relation='blocks'` saliente sube prioridad), urgencia en `context_origin` (`urgente|crítico|bloqueante|P1|P2`), recencia (`last_reviewed_at IS NULL`).
5. **Si insuficiente** → `infer_objectives` infiere una propuesta de objetivos (solo sobre temas del eje tópico o sin eje; los clientes van como bonus), el skill **pregunta** al dev (AskUserQuestion) y, con el OK, `write_compas` **escribe** `compas.md`. La brújula se aprende, no inventa pesos.

**Bandas (presentación):** `score>=67`→alta · `34..66`→media · `<34`→baja. Una banda curada sin score trae 80/50/20.

> Por qué la banda curada manda: una brújula por tema no reproduce un juicio por pendiente — dentro de un mismo tópico conviven P0 y P3 — así que la banda decidida ítem por ítem es el dato, y compas es el default para lo que aún no se decidió.

## Normalización slug↔subsistema (roadmap)

`normalize()` (definida en `pendings.py`, reusada por el recomendador) = minúsculas + sin acentos (NFKD + descarte de combinantes `Mn`) — espejo del `remove_diacritics` del matching FTS5 de la capa de temas. El emparejamiento con el roadmap es **token-match dentro del CSV** de la columna `Subsistemas` del `roadmap.md` (o el frontmatter `subsystems:` de cada `initiatives/INIT-*/initiative.md`, que **gana si diverge**). Ejemplo (proyecto `alpha`): `subsystems: [catálogo, pedidos]` → tokens `{catalogo, pedidos}`; un tema `catalogo` del pending matchea `catálogo` del roadmap. El bonus por iniciativa: `alta`+15 · `media`+8 · `baja`+3 (clamp a 100).

**Override de ruta del roadmap:** env `NEB_ROADMAP_DIR` (por defecto `~/roadmap`). Si el dev mueve el repo sin establecer el env, el orden fino degrada silenciosamente a solo el peso de `compas.md` (no rompe).

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

Citar archivos según la tabla de referencias del [`CLAUDE.md`](../CLAUDE.md) (nombre + repo para archivos del núcleo; paths absolutos solo en `personal/*.md`). El repo `roadmap` se localiza vía "Directorio de repos locales" del `personal/<usuario>.md`; en el núcleo el valor por defecto es `~/roadmap` con override `NEB_ROADMAP_DIR`.
