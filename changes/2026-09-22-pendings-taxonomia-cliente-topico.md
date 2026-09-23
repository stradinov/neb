# Taxonomía curada de pendientes (cliente · tópico), slug persistible y compás sobre esa taxonomía

**Estado:** En progreso
**Fecha inicio:** 2026-09-22
**Fecha cierre:** —
**Complejidad estimada:** alta  <!-- 14 elementos (tabla de planning: 7+ = alta); el borrador inicial decía media -->
**Complejidad real:** —
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

- [ ] `[crítico]` Migración idempotente sobre copia de la DB real: `_connect` ×2 → columnas + índice, 0 errores; `count(pending)`, `pending_note` y las 2,728 filas de `pending_topic` con `priority_band` intactas.
- [ ] `[crítico]` El hook `logbook-sync` sigue capturando tras la migración: `test_logbook_sync_regression.py` + `test_logbook_sync_errors.py` verdes y un Stop real en la sesión tras el merge.
- [ ] `[crítico]` Respaldos pre-migración y pre-siembra existen, pasan `PRAGMA integrity_check` y `--rollback` sobre la copia restaura `pending.slug`, `pending_topic`, `topic` y `pending_link` dejando `work`/`event`/`transcript_local` intactos.
- [ ] Seed sobre copia: los pendientes del pase quedan con exactamente 1 cliente + 1 tópico activos; los posteriores al pase aparecen en `unclassified`; invariante de bandas (la fila primaria previa == la fila curada del tópico); 0 del pase sin slug; 24 temas archivados, 7 reusados, 2 raíces + 35 hijos; 156 links; segunda corrida = 0 cambios (digest); una corrida posterior a un `curate` no lo pisa.
- [ ] `PD show <slug>` resuelve por la columna (kind `slug`); una muestra de 10 slugs históricos citados en memorias resuelve al mismo id (columna o fallback).
- [ ] `PD triage`: 71 grupos con máximo 8, solo entre `open`; `suggested ∩ unclassified = ∅`; `classify` sobre un pendiente nuevo escribe solo `curated=0` y nunca una raíz.
- [ ] `recommend_priority`: todos los curados devuelven `source='curated'` con su banda; un pendiente sin curar usa compas v2 con el bonus por cliente.
- [ ] Suite `py -m unittest discover -s hooks/tests` completa en verde (187 previos + nuevos).
- [ ] Dogfooding `/pendings-review` en la misma sesión tras la siembra real; escaneo de términos vetados limpio antes del push.

### Resultado

| # | Flujo | Resultado |
|---|-------|-----------|
| 1 | `[crítico]` Migración idempotente sobre copia, datos intactos | |
| 2 | `[crítico]` `logbook-sync` captura tras la migración (suite + Stop real) | |
| 3 | `[crítico]` Respaldos verificados + rollback lógico sobre copia | |
| 4 | Seed sobre copia (conteos, invariante de bandas, idempotencia, no pisa curaduría) | |
| 5 | Resolución por slug (columna + fallback histórico) | |
| 6 | `triage`: grupos por link, conjuntos disjuntos, raíces excluidas | |
| 7 | `recommend_priority`: curada > compas v2 | |
| 8 | Suite completa verde | |
| 9 | Dogfooding del skill + escaneo de términos vetados | |

**Fecha:** —
**Validador:** dev

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

## Incidencias

## Entregas

### Revisión
- Entrega ejecutada:
- Fecha:

### Final (Aprobación)
- Entrega ejecutada:
- Fecha:
- Autorización por:

## Resultado post-entrega

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
- **Commits:** —
- **Pendientes generados:** ninguno por ahora.
- **Tema radar:** —

## Métricas

| Métrica                                          | Valor |
|--------------------------------------------------|-------|
| Turnos — Fase 1 Clarificación                    |       |
| Turnos — Fase 2 Estimación                       |       |
| Turnos — Fase 3 Propuesta                        |       |
| Turnos — Fase 4 Implementación                   |       |
| Turnos — Fase 5 Validación                       |       |
| Turnos — Fase 6 Control de cambios               |       |
| Turnos — Fase 7 Producción                       |       |
| Turnos — Fase 8 Documentación                    |       |
| Turnos — Fase 9 Retroalimentación de Metodología |       |
| **Turnos total**                                 |       |
| Re-entregas en validación                        |       |
| Incidencias surgidas                             |       |
| Errores de implementación de Claude              |       |
| Faltas de contexto                               |       |
| Implementaciones sin aprobación                  |       |
| Acciones destructivas no autorizadas             |       |
| Out-of-scope edits                               |       |
| Complejidad estimada / real                      | alta / |

## Reporte de cierre

| Señal | Valor |
|---|---|
| Turnos total | — |
| Re-entregas | — |
| Complejidad estimada / real | alta / — |

**Uso de API** *(auto — `usage-tracker.sh`)*

<!-- usage-tracker-start -->
| Modelo | Tokens (in · out · cache_w · cache_r) | Costo USD |
|---|---|---|
| — | — | — |
| **Total** | — | **—** |
<!-- usage-tracker-end -->
