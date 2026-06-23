---
name: pendings-review
description: >
  Cargar SIEMPRE que el dev consulte, revise, priorice o "pase lista" a sus pendientes —
  incluyendo preguntas de lectura simple como "cuáles son mis pendientes", "qué tengo pendiente",
  "mis pendientes activos". También: marcar obsoletos, recomendar prioridad por tema, agrupar
  relacionados (candidatos a REQ conjunto), sugerir soluciones, "deja esta sesión en mis
  pendientes" o "rankéame los pendientes según <criterio/roadmap>". Es la ÚNICA vía de consulta
  del dev: opera neb.db y aplica la capa de valor (prioriza por banda + brújula compas.md), no el
  volcado plano. El CLI pendings.py list/show es acceso de bajo nivel/debug y NO sustituye al
  skill. NO cargar solo para implementación normal ajena a los pendientes.
---

# Skill: pendings-review (revisión y priorización de pendientes)

Opera el pase unificado de pendientes sobre `neb.db`. El modelo de datos vive en el change MD
`2026-06-14-neb-pendings-sqlite-nucleo.md`; la mecánica del backend en
[`../../tooling/pendings.md`](../../tooling/pendings.md). Este skill **ejecuta** — no repite esos
lineamientos. Traduce los enums de la DB (inglés) al español al mostrar.

## Resolver el módulo

```bash
NEB_SRC="${NEB_HOME:-${CLAUDE_PLUGIN_ROOT:-$(ls -d "$HOME"/.claude/plugins/cache/*/neb/*/ 2>/dev/null | sort -V | tail -1)}}"
PD() { py "$NEB_SRC/hooks/lib/pendings.py" "$@" 2>/dev/null || python "$NEB_SRC/hooks/lib/pendings.py" "$@"; }
```

## Operaciones

### Pase unificado (default, `/pendings-review`)
1. `PD triage` → JSON de pendings activos con su tema, banda recomendada y grupos (pre-filtro SQL/FTS de B; agrupación por tema compartido, NO O(N²)).
2. **Triage inline** (sin subagente): por cada pending, muestra su cita canónica **`[slug]` (`PD-<id>`)** · tema(s) · banda · origen del peso (prompt/compas/intrínseco/sin-clasificar) · una línea de rationale. Cita por `[slug]` y, si muestras número, el `id` de `neb.db` como `PD-<id>` — nunca `#NNN` (ver [`../../tooling/pendings.md`](../../tooling/pendings.md) § "Cómo citar un pendiente"). **Traduce los enums**: `open`→"abierto", `obsolete`→"obsoleto", `no-longer-applies`→"ya no aplica", `resolved-otherwise`→"resuelto de otra forma"; `related`→"relacionado", `depends`→"depende", `blocks`→"bloquea".
3. **Obsolescencia**:
   - señal dura (work ligado cerrado) → ya viene auto-archivado con causa por el gancho de A (`on_work_archived`); solo infórmalo.
   - "al recuperarlo" / juicio → **SUGERENCIA CON CONFIRMACIÓN**: propón marcar obsoleto + causa; pide OK antes de `PD archive <id> <causa>` (el verbo CLI es `archive`, que establece `status='obsolete'` con la causa). Nunca auto-archives por juicio en el MVP.
4. **Agrupación**: muestra los grupos de relacionados (vía `pending_link` + tema compartido) como candidatos a REQ conjunto.
5. **Soluciones profundas (fan-out top-K)**: solo bajo demanda y solo para los top-K (por defecto K=3) pendings de mayor banda, despacha el subagente `pendings-recommender` (Task) para que proponga abordaje. El triage liviano queda inline; el fan-out es opt-in.

### Priorizar por criterio externo — `priorizar <criterio o roadmap>`
`PD rank "<criterio>"` (texto libre) o `PD rank --roadmap <proyecto>`. Jerarquía: **prompt > compas.md > señales intrínsecas**. `compas.md` es la fuente única de los pesos persistentes; el criterio del prompt es efímero. Si un objetivo de compas referencia un roadmap, el orden fino sale del roadmap real (`roadmap/<proyecto>`, frontmatter `priority`/`subsystems`).

### Brújula insuficiente → aprender
Si `compas.md` no existe o la cobertura es baja, NO inventes pesos: `PD infer-objectives` propone objetivos; **preséntalos con AskUserQuestion** (opciones seleccionables, no prosa) y con el OK del dev `PD write-compas` escribe `~/.claude/compas.md`. La brújula se aprende, no se queda muda.

### Dejar la sesión en pendientes — `recordar-sesion`
Crea un pending tipo `session` que referencia el work exploratorio + transcript del logbook (`PD remember-session`). Al recuperarlo, el contexto = el `.jsonl` local (lectura), sobrevive a archivar la sesión.

## Notas
- No edites `neb.db` a mano: usa los subcomandos (preservan estados reversibles y la bitácora append-only `pending_note`).
- `revive <id>` reactiva un obsoleto (limpia la causa + agrega nota de reactivación). Todo es reversible y auditado.
- Al persistir prioridad en `pending_topic.priority_band`, traduce la banda de vuelta a **inglés** (`alta→high`, `media→medium`, `baja→low`); la DB guarda siempre el enum inglés.
- En local-only la prioridad es informativa para el propio dev; no hay sync cross-dev de pendings en el núcleo.
