# Pendientes — backend, brújula y priorización

Recurso del módulo `hooks/lib/pendings.py` que opera los **pendientes del dev** sobre la misma DB SQLite del logbook (`~/.claude/neb.db`; resolver dual-mode `neb.db ∨ neb-logbook.db`). El skill que lo conduce es [`../skills/pendings-review/SKILL.md`](../skills/pendings-review/SKILL.md); el modelo de datos (6 tablas) vive en [`../hooks/logbook-schema.sql`](../hooks/logbook-schema.sql) y el change MD del REQ. Aquí: la **brújula `compas.md`**, la **jerarquía de fuentes** de priorización y la **normalización slug↔subsistema**.

## Qué es `compas.md`

Brújula de priorización personal: archivo Markdown **local, no versionado, mantenido por Claude** en `~/.claude/compas.md`. Es la **fuente ÚNICA del peso de cada tema** — los `topic` de la DB no llevan peso. El recomendador la **parsea en cada pase** de `/pendings-review` (no cachea el peso en la DB).

**Formato (objetivos → peso + temas + roadmap opcional):**

```markdown
---
version: 1
updated_at: 2026-06-14
owner: <usuario>
---

## Objetivo: Atender reportes de clientes
- **Peso:** 90
- **Temas:** alpha, beta, gamma
- **Roadmap:** —

## Objetivo: Avanzar roadmap de alpha
- **Peso:** 70
- **Temas:** alpha
- **Roadmap:** alpha
```

- `- **Peso:** <int>` en `[0,100]` (default 0 si ausente/no numérico, clamp).
- `- **Temas:** <csv>` → slugs (`split(',')`, trim, `normalize()`).
- `- **Roadmap:** <proyecto|—>` → si trae un proyecto, ese objetivo delega el **orden fino** entre sus pendings al roadmap real (repo `roadmap`).
- Un tema en >1 objetivo gana el **mayor peso** (max). Temas no mencionados → peso 0.

El parser **tolera la ausencia** de `compas.md` (degrada a señales intrínsecas). `compas.md` NO se versiona ni se incluye en el repo; este documento es solo su formato y contrato. La plantilla literal la materializa `write_compas()` solo tras OK del dev.

## Vía de consulta del dev: el skill, no el CLI crudo

Toda consulta del dev sobre sus pendientes —desde "cuáles son mis pendientes" hasta priorizar o pasar lista— se atiende por el skill [`pendings-review`](../skills/pendings-review/SKILL.md), que aplica la **capa de valor**: prioriza por banda, consulta la brújula `compas.md` y, si falta o la cobertura es baja, dispara `infer_objectives` para aprenderla (ver jerarquía abajo).

Los verbos `list` y `show` de `pendings.py` son **acceso de bajo nivel / debug** (volcado JSON sin priorización ni brújula). NO son una vía de consulta equivalente ofrecida al dev: usarlos para responder "cuáles son mis pendientes" **salta la capa de valor** y oculta el nudge de `compas.md`. Reservalos para inspección puntual, scripting o diagnóstico.

## Cómo citar un pendiente (notación canónica)

La **cita canónica de un pendiente es su `[slug]`** (el tag `[nombre-req]` que vive en `context_origin`): es estable y único en intención. Cuando se muestra un número, es **siempre el `id` de `neb.db`**, escrito `PD-<id>` (p.ej. `PD-170`). `pendings.py show` resuelve cualquiera de las dos vías:

```bash
PD show 170            # por id de neb.db (rowid)
PD show PD-170         # idem (acepta prefijo PD- o #)
PD show uma-pem-ppk-desfasados   # por [slug]: tag exacto → substring; lista candidatos si es ambiguo
```

**El `#NNN` del `pendings.md` histórico queda RETIRADO como cita de pendiente.** Esa numeración del markdown plano **no es clave en `neb.db`**: la migración asignó `id` autoincrement y descartó el número del `.md` (sobrevive solo como texto en el prefijo `NN.` de `context_origin`). Por eso `#NNN` colisiona (un mismo número apunta a varios items) y `show NNN` resolvería al item equivocado. Al citar un pendiente —en chat, memorias, change MDs— usar `[slug]` (y `PD-<id>` si se necesita el número). Nunca `#NNN`.

## Jerarquía de fuentes de priorización

De mayor a menor:

1. **Criterio explícito del prompt** (efímero) — manda en esa consulta; NO se escribe a `compas.md` salvo que el dev lo pida (`write-compas`).
2. **`compas.md`** — peso por tema vía objetivos; un objetivo puede delegar el orden fino a un roadmap.
3. **Señales intrínsecas** del pending — work ligado + fase (`work.req_state` vía `pending.work_ref`), bloqueo (`pending_link.relation='blocks'` saliente sube prioridad), urgencia en `context_origin` (`urgente|crítico|bloqueante|P1|P2`), recencia (`last_reviewed_at IS NULL`).
4. **Si insuficiente** → `infer_objectives` infiere una propuesta de objetivos, el skill **pregunta** al dev (AskUserQuestion) y, con el OK, `write_compas` **escribe** `compas.md`. La brújula se aprende, no inventa pesos.

**Bandas (presentación):** `score>=67`→alta · `34..66`→media · `<34`→baja.

## Normalización slug↔subsistema (roadmap)

`normalize()` (definida en `pendings.py`, reusada por el recomendador) = minúsculas + sin acentos (NFKD + descarte de combinantes `Mn`) — espejo del `remove_diacritics` del matching FTS5 de la capa de temas. El emparejamiento con el roadmap es **token-match dentro del CSV** de la columna `Subsistemas` del `roadmap.md` (o el frontmatter `subsystems:` de cada `initiatives/INIT-*/initiative.md`, que **gana si diverge**). Ejemplo (proyecto `alpha`): `subsystems: [catálogo, pedidos]` → tokens `{catalogo, pedidos}`; un tema `catalogo` del pending matchea `catálogo` del roadmap. El bonus por iniciativa: `alta`+15 · `media`+8 · `baja`+3 (clamp a 100).

**Override de ruta del roadmap:** env `NEB_ROADMAP_DIR` (default `~/roadmap`). Si el dev mueve el repo sin setear el env, el orden fino degrada silenciosamente a solo el peso de `compas.md` (no rompe).

## Traducción de enums (DB inglés → presentación español)

La DB guarda **siempre** el enum en inglés; la presentación (skill/recomendador) traduce al mostrar y vuelve a inglés al escribir:

| DB (inglés) | Presentación (español) |
|---|---|
| `pending.status` `open` / `obsolete` | abierto / obsoleto |
| `obsolete_cause` `no-longer-applies` / `resolved-otherwise` | ya no aplica / resuelto de otra forma |
| `topic.status` `active` / `archived` | activo / archivado |
| `relation` `related` / `depends` / `blocks` | relacionado / depende / bloquea |
| `priority_band` `high` / `medium` / `low` | alta / media / baja |

`band_to_db('alta')='high'` (y `media→medium`, `baja→low`): el caller que persista `pending_topic.priority_band` traduce de vuelta a inglés; `priority_score` se persiste tal cual.

## Convención de paths

Citar archivos según la tabla de referencias del [`CLAUDE.md`](../CLAUDE.md) (nombre + repo para archivos del núcleo; paths absolutos solo en `personal/*.md`). El repo `roadmap` se localiza vía "Directorio de repos locales" del `personal/<usuario>.md`; en el núcleo el default es `~/roadmap` con override `NEB_ROADMAP_DIR`.
