# Taxonomía curada de pendientes (cliente · tópico), slug persistible y compás sobre esa taxonomía

**Estado:** Cerrado
**Fecha inicio:** 2026-09-22
**Fecha cierre:** 2026-09-22
**Complejidad estimada:** alta  <!-- 14 elementos (tabla de planning: 7+ = alta); el borrador inicial decía media -->
**Complejidad real:** alta
**Riesgo de regresión:** medio  <!-- toca classify()/reclassify() y `_migrate()`, que corre en el hook logbook-sync de cada Stop; los datos son del dev y no hay respaldo externo de neb.db -->


## Contexto

El pase completo de pendientes del 2026-09-22 (463 abiertos revisados uno por uno; 120 archivados, 342 clasificados por cliente y tópico) dejó tres límites del modelo actual **medidos**, no supuestos:

1. **Los `topic` no son temas: son slugs de REQ viejos.** El catálogo tiene 31 filas y el emparejamiento es por keywords vía FTS5, así que un solo "tema" toca medio backlog: el más ligado alcanza **325** pendientes, el segundo 256, el tercero 195. Consecuencia directa: la agrupación de `triage_pass()` —que agrupa por tema compartido— devolvió **un solo grupo con 400+ ids**, inservible como "candidatos a REQ conjunto". Los 69 grupos útiles del pase los produjo el criterio de los agentes, no la DB.

2. **El slug —la cita canónica del pendiente— no tiene dónde escribirse.** Por diseño vive como tag `[slug]` dentro de `context_origin`, que es un snapshot **inmutable** (la evolución va a `pending_note`), y `resolve_pending_ref()` solo lo busca ahí. Estado medido: de 463 abiertos, **175 no tenían slug**; de los 288 que sí, había genéricos repetidos (el más repetido ×9, otros ×8, ×7 y ×5). El pase propuso **253 slugs nuevos** con sentido y **no existe forma de guardarlos** sin romper la inmutabilidad de `context_origin`.

3. **`compas.md` pondera sobre ese catálogo roto y además está vencido.** Fue escrito el 2026-06-15 y da peso 90 a la metodología y al parque sincronizado y 20 a los proyectos de mantenimiento; tras un trimestre de incidentes de seguridad y dos PRD sin respaldo, ordena al revés del riesgo. Como los temas que referencia son los del punto 1, el peso se reparte por coincidencia de keywords: en el pase, **402 de 463** pendientes recibieron su banda de `compas` por esa vía. Por eso la prioridad del 22-sep se calculó por impacto y riesgo, y la brújula quedó sin usarse.

La prioridad sí tiene dónde vivir y ya se usó: `pending_topic.priority_band` + `priority_score` (1,864 filas escritas el 22-sep para los 342 vivos). El hueco es la **dimensión** (quién es el cliente, de qué trata) y la **identidad** (el slug).

**Medición adicional (Fase 3):** una brújula por tema no puede reproducir las bandas del pase — dentro de un mismo tópico conviven P0, P1, P2 y P3 (p. ej. `seguridad`: 8/21/23/6) y el techo de coincidencia calibrando peso por peso es ~65 %. Por eso la banda curada por pendiente manda sobre la brújula (ver Decisiones).

## Alcance

### Entra

- **Catálogo semilla de temas curados** en dos ejes, modelados con `topic.parent_id` (dos raíces, `cliente` y `topico`):
  - `cliente`: 18 valores (proyectos y ámbitos del dev). La lista con nombre y keywords vive en `taxonomy.json` del repo privado `methodology` (`onibex/tooling/pendings/`), no en este repo público.
  - `topico`: seguridad, incidente, integracion-sap, integridad-datos, rendimiento, infraestructura, respaldo-dr, costos, observabilidad, deploy-drift, funcionalidad-ux, analitica-reportes, comunicacion-cliente, migracion-plataforma, metodologia, tooling, memoria-docs (17).
  - De los 31 temas viejos, 7 tienen un slug que coincide con un cliente del catálogo: se **reusan** (re-parentados bajo `cliente`, conservan id e historial); los otros 24 pasan a `status='archived'` y sus filas `pending_topic` se conservan (las lecturas filtran `active`).
- **Blindaje de la curaduría**: `pending_topic.curated` (0 = sugerencia del matching, 1 = curado). `classify()` solo actúa sobre pendientes sin filas curadas, escribe `curated=0` y borra solo lo que él mismo puso; las raíces nunca se sugieren.
- **Slug persistible**: columna `pending.slug` (nullable, índice único parcial histórico `WHERE slug IS NOT NULL`); `resolve_pending_ref()` resuelve primero por la columna y conserva el fallback al tag de `context_origin` para no romper citas históricas. Backfill desde el tag existente (`backfill_slugs`) para los tags únicos; los repetidos quedan `NULL` y siguen resolviendo por el fallback. `context_origin` **no se toca**.
- **Siembra del pase del 22-sep**: los pendientes vivos del dataset con su cliente, tópico, banda y slug, más los 71 grupos como `pending_link related` en estrella (156 aristas). `triage_pass()` agrupa por `pending_link` entre `open`.
- **Jerarquía de prioridad nueva**: prompt > **banda curada** (`curated=1 AND is_primary=1`) > `compas.md` > señales intrínsecas. `compas.md` v2 pondera por tópico y agrega un bonus por cliente (`- **Clientes:** a=+15, b=+10`); solo aplica a pendientes sin banda curada.
- **`curate`** como vía de escritura del skill (`PD curate <id> --cliente --topico [--slug] [--band] [--relacionado]`), con reemplazo por eje y salida JSON siempre en stdout.
- Ajuste del skill `pendings-review` (ejes en la presentación, una confirmación por pase para curar los nuevos, filtros en `triage`) y del briefing de `agents/pendings-recommender.md`.

### No entra

- Reescribir `context_origin` de ningún pendiente (rompe el contrato del snapshot inmutable).
- Sync cross-dev de pendientes (sigue siendo local-only por diseño del núcleo).
- Re-triage del backlog: la clasificación de los vivos ya existe y se siembra tal cual.
- Cambiar el ENUM de `obsolete_cause` (lo pide PD-286 y es REQ aparte).
- Reemplazo del hook de arranque que inyecta el puntero de `pendings.md`.

## Decisiones (cerradas con el dev, Fase 3)

| # | Punto | Decisión |
|---|---|---|
| 1 | Dónde persiste el dataset del pase | Repo privado `methodology` (`onibex/tooling/pendings/`): `triage-2026-09-22.json`, `snapshot-2026-09-22.json`, `taxonomy.json`. El script de siembra recibe `--from` y `--catalog`; el repo público no hardcodea nombres de clientes. |
| 2 | Unicidad del slug | Única **histórica** (índice parcial `WHERE slug IS NOT NULL`). Medido: 0 colisiones entre vivos y 0 contra tags de obsoletos. |
| 3 | 31 temas viejos | Reusar los 7 que coinciden con clientes; archivar 24. No se borra nada. |
| 4 | Ejes y brújula | Doble eje con `parent_id`; compas v2 = peso por tópico + bonus por cliente; la banda curada manda sobre la brújula. |
| 5 | Matching FTS | Sugerencia solo para pendientes sin curar, con OK del dev para curar. |
| 6 | Grupos del pase | Se siembran como `pending_link related`; `triage_pass` agrupa por link. |
| 7 | `neb.db` de 0 bytes en la raíz del repo | Borrado. |
| 8 | Registro | Commit temprano `.md`-only (local); el push va al cierre junto con el fragmento de changelog (gate 3 del pre-push). |
| 9 | Respaldo de `neb.db` | Respaldo pre-migración con `sqlite3.Connection.backup()` plano (nunca vía `_connect`, nunca copia de archivo) como primer comando del turno del merge, verificado con `integrity_check` + conteos; segundo respaldo pre-siembra dentro del seed; `--rollback <bak>` restaura lógicamente las 4 tablas tocadas. |

## Plan de pruebas

- [x] `[crítico]` Migración idempotente sobre copia de la DB real: `_connect` ×2 → columnas + índice, 0 errores; `count(pending)`, `pending_note` y las 2,728 filas de `pending_topic` con `priority_band` intactas.
- [x] `[crítico]` El hook `logbook-sync` sigue capturando tras la migración: `test_logbook_sync_regression.py` + `test_logbook_sync_errors.py` verdes y un Stop real en la sesión tras el merge.
- [x] `[crítico]` Respaldos pre-migración y pre-siembra existen, pasan `PRAGMA integrity_check` y `--rollback` sobre la copia restaura `pending.slug`, `pending_topic`, `topic` y `pending_link` dejando `work`/`event`/`transcript_local` intactos.
- [x] Seed sobre copia: los pendientes del pase quedan con exactamente 1 cliente + 1 tópico activos; los posteriores al pase aparecen en `suggested`/`unclassified`; invariante de bandas y scores (la fila primaria previa == la fila curada del tópico); 0 del pase sin slug; 24 temas archivados, 7 reusados, 2 raíces + 35 hijos; vínculos = plan del día (la DB cambió: 70 grupos / 152 en sandbox, 151 en la siembra real); segunda corrida = 0 cambios (digest); una corrida posterior a un `curate` no lo pisa.
- [x] `PD show <slug>` resuelve por la columna (kind `slug`); una muestra de 10 slugs históricos citados en memorias resuelve al mismo id (columna o fallback; la columna acota un tag repetido al vivo).
- [x] `PD triage`: grupos = plan (70) con máximo 8, solo entre `open`; `suggested ∩ unclassified = ∅`; `classify` sobre un pendiente nuevo escribe solo `curated=0` y nunca una raíz.
- [x] `recommend_priority`: todos los curados devuelven `source='curated'` con su banda; un pendiente sin curar usa compas v2 con el bonus por cliente (sobre su mejor sugerencia por eje).
- [x] Suite `py -m unittest discover -s hooks/tests` completa en verde (187 previos + 38 nuevos = 225).
- [x] Dogfooding `/pendings-review` en la misma sesión tras la siembra real; escaneo de términos vetados limpio antes del push.

### Resultado

| # | Flujo | Resultado |
|---|-------|-----------|
| 1 | `[crítico]` Migración idempotente sobre copia, datos intactos | ✅ `_connect` ×2: columnas + `uq_pending_slug`, 2,728 filas con banda intactas, 0 backfill en la migración, `pending_note` intacta |
| 2 | `[crítico]` `logbook-sync` captura tras la migración (suite + Stop real) | ✅ suite (`test_logbook_sync_regression`, `test_logbook_sync_errors.TestMigrate` sin cambios) · ✅ Stop real tras el merge: el hook migró la DB (columnas + índice, 0 backfill), conteos = respaldo pre-migración, `work` de este REQ actualizado sin `last_error`, `event` +1 |
| 3 | `[crítico]` Respaldos verificados + rollback lógico sobre copia | ✅ respaldo pre-siembra con `integrity_check=ok` e idéntico al digest pre-seed; `--rollback` devuelve las tablas sembradas al digest pre-seed sin tocar `work`; test de rollback desde respaldo pre-migración |
| 4 | Seed sobre copia (conteos, invariante de bandas, idempotencia, no pisa curaduría) | ✅ 2 raíces + 35 hijos, 24 archivados, 7 reusados; 327 sembrados con exactamente 1 cliente + 1 tópico iguales al dataset; banda **y score** curados == fila primaria previa 327/327; obsoletos idénticos; 0 sin slug, 0 colisiones; 70 grupos en estrella completos (152 vínculos = plan); backfill 107 = estimado del dry-run; 2ª corrida `changed=False`; un `curate` posterior no se pisa (test) |
| 5 | Resolución por slug (columna + fallback histórico) | ✅ `PD show <slug>` kind `slug`; 10 slugs históricos (memorias + dataset) resuelven a los mismos ids o a un subconjunto (la columna acota un tag repetido al vivo) |
| 6 | `triage`: grupos por link, conjuntos disjuntos, raíces excluidas | ✅ CLI real: grupos = plan, máx 8; `suggested ∩ unclassified = ∅` con los 12 posteriores al pase sin curar; `classified` = solo no curados; `catalog` 18/17 y filtro desconocido → error JSON |
| 7 | `recommend_priority`: curada > compas v2 | ✅ 327/327 `source=curated`; los 11 P0 → alta; compas v2 borrador (17 tópicos + 12 bonus) parsea tras el fix |
| 8 | Suite completa verde | ✅ 225/225 (187 previos + 38 nuevos) |
| 9 | Dogfooding del skill + escaneo de términos vetados | ✅ escaneo limpio (árbol exportado del worktree y `main`) · ✅ dogfooding `PD triage` sobre la DB real tras la siembra: 338 items, 326 curados / 12 sin curar, 70 grupos máx 8, catálogo 18/17, filtro por cliente, `show` por slug; destapó el ruido del matching (corregido, ver Incidencias) |

**Fecha:** 2026-09-22
**Validador:** Claude (sandbox sobre copia de la DB real con `scratchpad/seed/validate_sandbox.py`; siembra real verificada contra el respaldo pre-siembra: 8/8); el dev valida en uso el skill (Fase 9)

## Plan de elaboración

| Elemento | Cambio |
|---|---|
| `hooks/logbook-schema.sql` | `pending.slug`, `pending_topic.curated`; comentarios (índice en `_migrate`; raíces por `parent_id`) |
| `hooks/lib/_db_shared.py` | `_migrate` solo DDL: migraciones de `pending`/`pending_topic` con guard por `sqlite_master` + índice único parcial |
| `bootstrap/seed-pendings-taxonomy.py` (nuevo) | dry-run/apply/force/rollback; respaldo plano verificado; una transacción; catálogo desde `--catalog`; salta curados previos; digest |
| `hooks/lib/pendings.py` | `classify`/`reclassify`/`triage_pass`/`_pending_topics`/compas v2/`recommend_priority`/`infer_objectives`/`resolve_pending_ref`/`curate`/`backfill_slugs`/CLI |
| `hooks/tests/test_pendings_taxonomy.py` (nuevo) + ajustes en `test_pendings_classify.py`, `test_pendings_recommend.py`, `test_logbook_sync_errors.py` | cobertura de migración, backfill, curaduría, triage, compas v2, curate, seed |
| `skills/pendings-review/SKILL.md`, `agents/pendings-recommender.md` | ejes, una confirmación por pase, `curate`, filtros en `triage`, briefing |
| `tooling/pendings.md`, `workflow/pendings.md`, `skills/README.md`, `profiles/self-applied/skills.md` | glosario, columna `slug`, `curated`, compas v2, jerarquía, punteros |
| `changelog.d/6.7.0.md`, `VERSION`, `.claude-plugin/plugin.json`, `CHANGELOG.md` | bump minor; declara cambios normativos (cita canónica = columna; `classify` = sugerencia; jerarquía con banda curada) y de contrato (`triage_pass`, `infer_objectives`) |
| `methodology/onibex/tooling/pendings/` (privado) | dataset, catálogo, doc de re-siembra + fila en `tooling/index.md` |
| `~/.claude/compas.md` v2 · memoria del pase | `write-compas` tras elección de pesos; memoria al cierre |

Mecánica: commit local del registro → worktree (rama desde HEAD) → implementación + suite → validación en sandbox (`USERPROFILE=<scratch>` con la copia y el compas borrador) → gate Fase 4 → diff + OK del dev → respaldo pre-migración → merge → seed real → `write-compas` → dogfooding → bump + changelog + cierre → push.

## Avances realizados

- 2026-09-22 — Plan-review orquestado (5 revisores: `qa-process-engineer`, `process-improvement-analyst`, `context-completeness-reviewer` + lentes de código y BD; 39 hallazgos → 23 tras dedup → 16 confirmados por ≥2 de 3 lentes, 1 refutado, 6 menores incorporados). Plan v2 aprobado por el dev; registro commiteado temprano (local, `10f6ca3`).
- 2026-09-22 — Implementación en el worktree `wip/pendings-taxonomia`: los 14 elementos. Decisiones tomadas en implementación (fuera del plan, declaradas): `pending_axes()`/`axis_catalog()`/`_parse_flags()`; `curate(score=)` para que el seed persista el score del pase; `classify(replace=True)` borra sugerencias solo sobre temas activos (las filas sobre archivados quedan como historial, igual que el seed); `reclassify` toma como delta a los abiertos sin curar sin sugerencia vigente y reconstruye el índice FTS una vez por pase; el índice `uq_pending_slug` tolera `IntegrityError` con aviso (no tumba el hook); "curado" = fila `curated=1` sobre tema **activo**.
- 2026-09-22 — Gate de cierre de Fase 4 (revisión adversarial del artefacto: `qa-process-engineer`, `context-completeness-reviewer`, `process-improvement-analyst` + lentes código/BD; 31 hallazgos → 27 tras dedup → 6 mayores confirmados, 18 menores, 2 refutados). Corregidos los 6 mayores: banda con un solo eje se aplica a todas las filas curadas (H1); `--band` sobre un pendiente sin curar es error, no no-op (H2); la cita de escritura debe ser exacta —un substring no cura ni vincula— (H3); un tema del catálogo archivado sin `--force` salta sus items en vez de abortar la transacción (H4); predicado "curado" con tema activo en `classify`/`reclassify`/`triage_pass`/seed (H6); `triage` expone `catalog` y rechaza filtros fuera de él (H8). De los 18 menores se aplicaron 17 (respaldo con `--db` inexistente = error; prioridad desconocida cura sin banda y slugs inválidos se reportan; verificación del respaldo estricta solo en tablas de pendings; plan calculado dentro de la transacción; rollback restaura también `topic_link` y `last_reviewed_at`, incluso desde un respaldo pre-migración; score heredado del pase; una sola constante de score; glosario y wording de docs; test de slugs duplicados; comentario de cabecera; "18/17" fuera de archivos públicos; formato de la confirmación única del skill; cita `PD-<id>` cuando no hay slug y `rank` con `slugs`; estimado de backfill vía `backfill_slugs(dry_run=True)` también en DB sin migrar; tests de rollback pre-migración y de rollback transaccional del CLI; FTS una vez por pase) y 1 quedó como derivado (H18, ver Trazabilidad). H5 y H7 refutados.
- 2026-09-22 — Validación en sandbox sobre copia de la DB real (`USERPROFILE=<scratch>`, `NEB_HOME=<worktree>`; 37 comprobaciones, todas OK; DB real intacta por mtime + conteos): ver `### Resultado`.
- 2026-09-22 — Entrega: OK del dev al diff; commit `4b795ff` en la rama; respaldo pre-migración `neb-logbook.db.bak-pre-migration-20260923T033303-980037Z` (516 pendientes / 2,728 filas con banda / 254 works, `integrity_check` ok); merge fast-forward a `main`; el Stop real migró la DB; siembra real con `--apply` (respaldo `bak-pre-taxonomy-20260923T034107-960920Z`): 325 curados, 7 reusados, 24 archivados, 325 slugs sin colisión, 151 vínculos, 109 backfill; verificación contra el respaldo 8/8 y dry-run posterior con 0 cambios. `compas.md` v2 "Riesgo primero" escrito (v1 en `compas.md.bak-v1-20260922T213310`). Derivado `[db-shared-field-regex-salto-de-linea]` (PD-517) dado de alta y curado (`neb` · `tooling` · baja).
- 2026-09-22 — Ajuste post-dogfooding (retroalimentación observada en la misma sesión, ver Incidencias): para un pendiente sin curar solo cuenta la **mejor sugerencia por eje** (`_effective_topics`), `triage` expone `suggested_cliente`/`suggested_topico` con `suggestions` acotadas a 3 por eje, el matching ignora stopwords y tokens de <3 letras del lado del tema (`_match_tokens`), el seed resetea las sugerencias no curadas cuando el catálogo cambia, y `taxonomy.json` pierde keywords genéricas. 3 tests nuevos; suite 225/225; re-siembra real: 222 sugerencias reseteadas y recalculadas.

## Incidencias

- **Bug preexistente en `parse_compas` (desde 4.3.0)**, destapado al validar el compás v2 en el sandbox: `normalize()` no recorta espacios, así que de cada objetivo solo el primer tema ponderaba (los demás quedaban como `' beta'`), y con una línea `Temas:` vacía el `\s*` de `_field_value` cruzaba el salto de línea y capturaba la línea siguiente como tema. Corregido en `pendings.py` (`_field_value` con separadores `[ \t]*`; `strip()` antes de `normalize()`), con test de regresión y declarado en `Fixed`. Explica en parte por qué el compás v1 ordenaba raro: de sus 14 temas de "Metodología Neb" solo `neb` pesaba.
- **La DB cambió durante el REQ**: entre el pase (22-sep, 463 abiertos) y la siembra hubo cierres (PD-509 y dos más pasaron a obsoleto) y altas (PD-512…516). Por eso el seed no fija conteos: reporta los del día y la validación compara contra el plan calculado (327 sembrados en sandbox, 325 en la siembra real).
- **Ruido del matching, visto en el dogfooding real**: cada uno de los 12 pendientes sin curar recibía 13–26 sugerencias y `recommend_priority` tomaba el máximo peso entre todas, así que cualquiera que rozara `seguridad` subía a "alta" (el top 5 eran justamente los sin curar); además `comunicacion-cliente` ganaba como tópico en 9 de 12 y `parque` como cliente en 5. Causa raíz: `_topic_tokens` partía las keywords multi-palabra ("aviso al cliente", "confirmar con") en tokens sueltos sin filtrar stopwords (`al`, `con`, `a`, `cliente`), que matchean cualquier texto. Corregido en la misma sesión (mejor sugerencia por eje + stopwords + reset de sugerencias al cambiar el catálogo + keywords podadas); el matching sigue siendo sugerencia, no clasificación.

## Entregas

### Revisión
- Entrega ejecutada: plan-review orquestado (Fase 3) y gate de cierre de Fase 4 (revisión adversarial del artefacto), ambos con verificación por 3 lentes; validación en sandbox sobre copia de la DB real (37/37).
- Fecha: 2026-09-22

### Final (Aprobación)
- Entrega ejecutada: merge a `main` (`4b795ff` + ajuste post-dogfooding), migración real vía el hook, siembra real de `neb.db`, `compas.md` v2, dataset y catálogo en `methodology` (`3f09937`), push a `origin/main` con los 5 gates del pre-push.
- Fecha: 2026-09-22
- Autorización por: dev (OK al diff y a la secuencia completa; elección de pesos "Riesgo primero")

## Resultado post-entrega

- DB real tras la siembra: 338 abiertos (326 curados con 1 cliente + 1 tópico, 12 con sugerencia por eje pendientes de curar en el próximo `/pendings-review`), 2 raíces + 35 hijos activos, 24 temas archivados con su historial, 434 slugs únicos, 161 vínculos, 2,986 filas `pending_topic`; `context_origin`, `pending_note` y las filas de los 138 obsoletos idénticos al respaldo; bandas y scores del pase intactos 325/325.
- Respaldos en `~/.claude/`: `neb-logbook.db.bak-pre-migration-20260923T033303-980037Z` (estado previo a todo) y dos `bak-pre-taxonomy-*` (previos a cada `--apply`); `compas.md.bak-v1-20260922T213310`. Rollback lógico: `py bootstrap/seed-pendings-taxonomy.py --rollback <bak>`; el dev decide cuándo borrarlos.

## Diagnóstico de defectos

| Defecto | Etapa de origen | Tipo de causa | Patrón / aislado | REQ derivado |
|---|---|---|---|---|
| Catálogo de temas = slugs de REQ emparejados por FTS (un tema toca 325 pendientes) | Fase 3 del REQ `neb-pendings-sqlite` (siembra del catálogo desde las secciones del `.md`) | plan | aislado | este REQ |
| Cita canónica `[slug]` sin columna propia (vive en un snapshot inmutable) | Fase 3 del REQ `pending-citation-notation` | plan | aislado | este REQ |

## Trazabilidad

- **Plan aprobado:** `~/.claude/approved-plans/20260922-184056-neb-pendings-taxonomia-cliente-topico.md`
- **Origen:** revisión completa de los 463 pendientes abiertos del 2026-09-22 (workflow de 66 agentes: triage por lote → cazador cronológico → 2 lentes adversariales por cierre → consolidación). Tablero y referencias de sesión: en la memoria del pase.
- **Dataset de la siembra:** `onibex/tooling/pendings/triage-2026-09-22.json` en `methodology` (privado), con `snapshot-2026-09-22.json` y `taxonomy.json`.
- **Memoria:** `project_pendings_triage_20260922.md`.
- **Modelo de datos vigente:** `2026-06-14-neb-pendings-sqlite-nucleo.md` en `methodology/changes` (REQ `neb-pendings-sqlite`) y `tooling/pendings.md`.
- **Pendientes relacionados:** PD-286 (ENUM de `obsolete_cause`: "resuelto por el REQ que lo tomó").
- **Commits:** `10f6ca3` (registro, entrega temprana) · `4b795ff` (entregable) · `esta confirmación` (ajuste post-dogfooding + cierre) · `methodology` `3f09937` + `esta confirmación` (catálogo podado)
- **Pendientes generados:** `[db-shared-field-regex-salto-de-linea]` — `_db_shared._field` (parser de la memoria del REQ activo que corre en cada Stop) conserva el `\s*` que cruza el salto de línea: una línea `- **Estado:**` vacía captura la siguiente. Mismo defecto corregido aquí en `pendings._field_value`; se atiende aparte por su radio de impacto (hot path del hook). Derivado del gate de Fase 4 (H18).
- **Tema radar:** —

## Métricas

| Métrica                                          | Valor |
|--------------------------------------------------|-------|
| Turnos — Fase 1 Clarificación                    | 4 (lectura del MD + medición en la DB + 2 menús de decisiones) |
| Turnos — Fase 2 Estimación                       | 0 (absorbida en el MD: complejidad media → alta al planear) |
| Turnos — Fase 3 Propuesta                        | 5 (plan + plan-review orquestado + consolidación + OK) |
| Turnos — Fase 4 Implementación                   | 9 (worktree, 3 bloques, gate de cierre + correcciones) |
| Turnos — Fase 5 Validación                       | 5 (sandbox ×4 + verificación real) |
| Turnos — Fase 6 Control de cambios               | 2 (diff + OK; commit en rama) |
| Turnos — Fase 7 Producción                       | 4 (respaldo, merge, siembra real, ajuste post-dogfooding) |
| Turnos — Fase 8 Documentación                    | 2 (registro, memoria) |
| Turnos — Fase 9 Retroalimentación de Metodología | 1 (ruido del matching corregido en sesión) |
| **Turnos total**                                 | ~32 (una sesión, con dos cortes de la app) |
| Re-entregas en validación                        | 0 |
| Incidencias surgidas                             | 3 (bug previo de `parse_compas`; DB viva durante el REQ; ruido del matching) |
| Errores de implementación de Claude              | 6 (los mayores del gate de Fase 4, todos corregidos antes de entregar) |
| Faltas de contexto                               | 1 (asumí que el CLI podía apuntar a una copia de la DB; H1 del plan-review) |
| Implementaciones sin aprobación                  | 0 |
| Acciones destructivas no autorizadas             | 0 |
| Out-of-scope edits                               | 0 (el fix de `parse_compas` y el ajuste del matching están en el alcance del REQ; `_db_shared._field` quedó como derivado) |
| Complejidad estimada / real                      | alta / alta |

## Reporte de cierre

| Señal | Valor |
|---|---|
| Turnos total | ~32 |
| Re-entregas | 0 |
| Complejidad estimada / real | alta / alta |

**Uso de API** *(auto — `usage-tracker.sh`)*

<!-- usage-tracker-start -->
| Modelo | Tokens (in · out · cache_w · cache_r) | Costo USD |
|---|---|---|
| — | — | — |
| **Total** | — | **—** |
<!-- usage-tracker-end -->
