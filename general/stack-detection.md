# Detección y stack activo

Cómo Claude detecta el stack al iniciar trabajo y lo mantiene como estado durante la sesión. Se carga al arranque vía [`startup.md`](startup.md) (`@import` garantizado; ver [index.md](index.md) para mapa on-demand). La heurística canónica vive en [`stacks/index.md`](../stacks/index.md); este archivo define cuándo y cómo se aplica.

## Al iniciar trabajo

Al entrar a un directorio de proyecto, Claude detecta el stack:

0. **Detectar overlay por path** — si el cwd cae dentro de un path de overlay, activar ese stack **sin subir** al `.git` padre. Overlays por path (en orden de prioridad, primer match gana). `<neb>` es el nombre del directorio del checkout (convencionalmente `neb`):
   - `*/<neb>/stacks/<algo>/` → `stack-authoring`.
   - `*/<neb>/skills/<algo>/` → `skill-authoring`.
   - `*/<neb>/research/` (o descendientes) → `research`. Para investigación en `<proyecto>/research/` o `~/.claude/research/`, activación explícita por el dev (sin auto-detección por path para evitar colisión con otros stacks).

   Prioridad canónica y heurísticas estructurales: [`stacks/index.md`](../stacks/index.md).
1. **Identificar la raíz del proyecto** — subir hasta encontrar `.git` (o equivalente) si el cwd es un subdirectorio.
2. **Leer `CLAUDE.md` del proyecto** si existe — confirmar imports `@~/.claude/neb/stacks/<stack>/...`.
3. **Si imports incompletos o ausentes**, ejecutar heurísticas de [`stacks/index.md`](../stacks/index.md) — primer match gana.
4. **Actuar según resultado**:

| Caso | Acción |
|---|---|
| **Stack disponible** y CLAUDE.md ya importa | Continúa sin aviso |
| **Stack disponible** y CLAUDE.md no importa | Aviso: *"Detecté stack `<X>`. CLAUDE.md no lo importa. Sugerencia: ejecutar `bootstrap/link-into-project.sh`."* |
| **Stack pendiente** (listado sin `stacks/<X>/`) | Aviso: *"Detecté stack `<X>` (Pendiente). Sin convenciones específicas. ¿Crear el stack siguiendo el patrón de `stacks/self-applied/` (ver [CLAUDE.md interno del repo](../CLAUDE.md) "Agregar un stack nuevo") o continuar genérico?"* |
| **Stack desconocido** (ningún indicador match) | Aviso: *"No detecté stack conocido. ¿Continuamos genérico o agregamos heurística + nuevo stack?"* |

Heurísticas y prioridad: orden de tabla en [`stacks/index.md`](../stacks/index.md).

## Stack activo durante la sesión

El **stack activo** es el estado mental que Claude mantiene durante la sesión. Inicia en `none` si la sesión arranca fuera de un proyecto detectable (ej. `~`); si no, queda fijado por la detección inicial.

### Triggers de re-detección

Claude vuelve a aplicar la heurística de [`stacks/index.md`](../stacks/index.md) cuando el prompt entrante:

1. **cwd cambia** — `cd` a subdir, `cd ..`, o cualquier acción que mueva el cwd (incluyendo dentro del mismo repo, ej. raíz ↔ `reqs/<algo>/`).
2. **Referencia path fuera del cwd** — el dev menciona un archivo, dir o repo cuyo path matchea heurística distinta a la del stack activo.
3. **Pide artefacto de otro stack** — edición/lectura de archivo cuyo path encaja en otra fila de la tabla.

No disparan re-detección: saludos, conversación trivial, preguntas meta sin path.

### Política de anuncio

| Situación | Acción |
|---|---|
| Stack activo no cambia | Silencio. Continúa. |
| Stack activo cambia (sin trabajo en curso del anterior) | Anuncio inline 1 línea, procede directo: `[stack: <X> → <Y>] motivo: <cd a foo/reqs/bar \| path mencionado fuera de cwd \| edición en path Z>` |
| Stack activo cambia con trabajo en curso del anterior (plan aprobado activo, edición a medio camino, fase no cerrada) | Pausa: anuncia el cambio y pide confirmación antes de abandonar el contexto previo |

**Skills aplicables**: cuando Claude detecta o re-detecta el stack activo, consulta `skills/README.md` e identifica los skills cuya columna "Stack(s) aplicable(s)" incluye el stack detectado. Si hay skills aplicables, los anuncia en la misma línea del anuncio de stack: `[stack: <X>] skills aplicables: <skill1>, <skill2>`. Si no hay skills aplicables, omite la mención.

### Edge cases

- **Sesión inicia en `~` o dir sin stack mapeable** — `stack activo = none`. Primer prompt con path conocido dispara detección normal y anuncia `[stack: none → <X>]`.
- **Prompt menciona dos stacks** — anunciar ambigüedad y preguntar cuál es driver antes de actuar. No asumir.
- **cwd en el directorio raíz del clon (sin repo detectado)** — `none`; el primer path en el prompt resuelve.
- **Path mencionado pero archivo no existe** — la heurística es estructural (matchea por patrón de path/nombre), no requiere `stat`.

La heurística de [`stacks/index.md`](../stacks/index.md) es la **single source of truth**; esta política la consume sin duplicarla.
