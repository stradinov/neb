---
name: pendings-review
description: >
  Cargar SIEMPRE que el dev consulte, revise, priorice, cure o "pase lista" a sus pendientes —
  incluyendo preguntas de lectura simple como "cuáles son mis pendientes", "qué tengo pendiente",
  "mis pendientes activos", o filtradas por cliente/tópico ("qué tengo de alpha", "pendientes de
  seguridad"). También: marcar obsoletos, curar cliente/tópico/slug/banda de un pendiente, agrupar
  relacionados (candidatos a REQ conjunto), sugerir soluciones, "deja esta sesión en mis pendientes"
  o "rankéame los pendientes según <criterio/roadmap>". Es la ÚNICA vía de consulta del dev: opera
  neb.db y aplica la capa de valor (banda curada > brújula compas.md por tópico + bonus por
  cliente), no el volcado plano. El CLI pendings.py list/show es acceso de bajo nivel/debug y NO
  sustituye al skill. NO cargar solo para implementación normal ajena a los pendientes.
---

# Skill: pendings-review (revisión, curaduría y priorización de pendientes)

Opera el pase unificado de pendientes sobre `neb.db`. El modelo de datos vive en el change MD
`2026-06-14-neb-pendings-sqlite-nucleo.md` y en `2026-09-22-pendings-taxonomia-cliente-topico.md`;
la mecánica del backend (ejes curados, `curated`, columna `slug`, `compas.md` v2, jerarquía de
prioridad) en [`../../tooling/pendings.md`](../../tooling/pendings.md). Este skill **ejecuta** — no
repite esos lineamientos. Traduce los enums de la DB (inglés) al español al mostrar.

## Resolver el módulo

```bash
NEB_SRC="${NEB_HOME:-${CLAUDE_PLUGIN_ROOT:-$(ls -d "$HOME"/.claude/plugins/cache/*/neb/*/ 2>/dev/null | sort -V | tail -1)}}"
PD() { py "$NEB_SRC/hooks/lib/pendings.py" "$@" 2>/dev/null || python "$NEB_SRC/hooks/lib/pendings.py" "$@"; }
```

## Operaciones

### Pase unificado (default, `/pendings-review`)
1. `PD triage [--cliente <slug>] [--topico <slug>]` → JSON: `items` (cada uno con `slug`, `cliente`, `topico`, `curated`, `suggestions`, `band`, `source`, `rationale`), `groups` (componentes de `pending_link` entre abiertos), `suggested` (sin curar, con sugerencia del matching), `unclassified` (sin curar, sin sugerencia) y `catalog` (los valores válidos de cada eje: `{"cliente": [...], "topico": [...]}`). Los filtros por eje acotan todo el JSON — úsalos cuando el dev pregunta por un cliente o un tópico; un valor fuera del catálogo devuelve `{"ok": false, "error", "catalog"}`.
2. **Triage inline** (sin subagente): por cada pending, muestra su cita canónica **`[slug]` (`PD-<id>`)** —si `slug` es `null`, cita `PD-<id>`— · cliente · tópico · banda · origen (`curated`→"curada", `compas`, `intrinsic`→"intrínseca", `prompt`, `unclassified`→"sin clasificar") · una línea de rationale. Nunca `#NNN` (ver [`../../tooling/pendings.md`](../../tooling/pendings.md) § "Cómo citar un pendiente"). **Traduce los enums**: `open`→"abierto", `obsolete`→"obsoleto", `no-longer-applies`→"ya no aplica", `resolved-otherwise`→"resuelto de otra forma"; `related`→"relacionado", `depends`→"depende", `blocks`→"bloquea"; `high/medium/low`→alta/media/baja.
3. **Curar los que faltan** = `suggested` ∪ `unclassified` ∪ los `items` con `curated` pero `cliente` o `topico` en `null` (curados a medias). Muestra la propuesta inline como tabla `PD-id · slug propuesto (si es null) · cliente · tópico` —parte de `suggested_cliente`/`suggested_topico` (la mejor sugerencia del matching por eje; `suggestions` trae hasta 3 por eje, por score) y corrígela con tu lectura del `context_origin`, siempre con valores del `catalog`— y luego **una sola** `AskUserQuestion` con tres opciones: aplicar todo · aplicar con los ajustes que indique el dev · curar después (el pase no se bloquea). Si son más de ~20, propone los más recientes y deja el resto para el siguiente pase. Con el OK, `PD curate <id> --cliente <c> --topico <t> [--band alta|media|baja] [--slug <slug>]` por cada uno (la salida es JSON `{"ok": true|false, ...}`; si `ok` es `false`, muestra `error` y no insistas a ciegas). Un pendiente curado en ambos ejes no vuelve a la lista: el matching no lo toca.
4. **Obsolescencia**:
   - señal dura (work ligado cerrado) → ya viene auto-archivado con causa por el gancho de A (`on_work_archived`); solo infórmalo.
   - "al recuperarlo" / juicio → **SUGERENCIA CON CONFIRMACIÓN**: propón marcar obsoleto + causa; pide OK antes de `PD archive <id> <causa>` (el verbo CLI es `archive`, que establece `status='obsolete'` con la causa). Nunca auto-archives por juicio en el MVP.
5. **Agrupación**: `groups` son los vínculos explícitos (`pending_link`, cualquier relación) entre abiertos — candidatos a REQ conjunto. Para meter un pendiente a un grupo: `PD curate <id> --relacionado <id|slug>` (repetible; la cita debe ser exacta: `PD-<id>` o slug completo). Por qué no agrupa el tema compartido: [`../../tooling/pendings.md`](../../tooling/pendings.md) § "Ejes curados".
6. **Soluciones profundas (fan-out top-K)**: solo bajo demanda y solo para los top-K (por defecto K=3) pendings de mayor banda, despacha el subagente `pendings-recommender` (Task) pasándole `[slug] (PD-id) · cliente · tópico · banda + origen · grupo` y el `context_origin`. El triage liviano queda inline; el fan-out es opcional.

### Priorizar por criterio externo — `priorizar <criterio o roadmap>`
`PD rank "<criterio>"` (texto libre) o `PD rank --roadmap <proyecto>`; el JSON trae `order`, `scores` y `slugs` (id → slug, para citar). Jerarquía de fuentes y su porqué: [`../../tooling/pendings.md`](../../tooling/pendings.md) § "Jerarquía de fuentes de priorización" — en corto, **prompt > banda curada > compas.md > intrínsecas**; el criterio del prompt es efímero y ningún pase recalcula una banda curada.

### Brújula insuficiente → aprender
Si `compas.md` no existe o la cobertura es baja, NO inventes pesos: `PD infer-objectives` propone objetivos sobre el eje tópico; **preséntalos con AskUserQuestion** (opciones seleccionables, no prosa) y con el OK del dev `PD write-compas '[["nombre", peso, ["topico", ...], "roadmap|null", {"cliente": bonus}], ...]'` escribe `~/.claude/compas.md` (v2; el 5º elemento —bonus por cliente— es opcional). La brújula se aprende, no se queda muda.

### Dejar la sesión en pendientes — `recordar-sesion`
Crea un pending tipo `session` que referencia el work exploratorio + transcript del logbook (`PD remember-session`). Al recuperarlo, el contexto = el `.jsonl` local (lectura), sobrevive a archivar la sesión.

## Notas
- No edites `neb.db` a mano: usa los subcomandos (preservan estados reversibles y la bitácora append-only `pending_note`).
- `revive <id>` reactiva un obsoleto (limpia la causa + agrega nota de reactivación). Todo es reversible y auditado.
- La única vía para persistir una banda es `PD curate <id> --band <alta|media|baja>` (la DB guarda el enum inglés; el CLI traduce). Sobre un pendiente sin curar hay que dar `--cliente`/`--topico` en la misma llamada (si no, `ok: false`). No escribas `pending_topic` por SQL.
- `PD backfill-slugs` rellena `pending.slug` desde el tag `[slug]` de pendientes viejos (solo tags únicos); las citas históricas resuelven igual sin correrlo.
- En local-only la prioridad es informativa para el propio dev; no hay sync cross-dev de pendings en el núcleo.
