# Detección y profile activo

Cómo Claude detecta el profile al iniciar trabajo y lo mantiene como estado durante la sesión. Se carga al arranque vía [`startup.md`](startup.md) (`@import` garantizado; ver [index.md](index.md) para mapa on-demand). La heurística canónica vive en [`profiles/index.md`](../profiles/index.md); este archivo define cuándo y cómo se aplica.

## Al iniciar trabajo

Al entrar a un directorio de proyecto, Claude detecta el profile:

0. **Detectar overlay por path** — si el cwd cae dentro de un path de overlay, activar ese profile **sin subir** al `.git` padre. Overlays por path (en orden de prioridad, primer match gana). `<neb>` es el nombre del directorio del checkout (convencionalmente `neb`):
   - `*/<neb>/profiles/<algo>/` → `profile-authoring`.
   - `*/<neb>/skills/<algo>/` → `skill-authoring`.
   - `*/<neb>/research/` (o descendientes) → `research`. Para investigación en `<proyecto>/research/` o `~/.claude/research/`, activación explícita por el dev (sin auto-detección por path para evitar colisión con otros profiles).

   Prioridad canónica y heurísticas estructurales: [`profiles/index.md`](../profiles/index.md).
1. **Identificar la raíz del proyecto** — subir hasta encontrar `.git` (o equivalente) si el cwd es un subdirectorio.
2. **Leer `CLAUDE.md` del proyecto** si existe — confirmar imports `@~/.claude/neb/profiles/<profile>/...` y revisar el **marcador de opt-out** (ver §"Opt-out de profile / Neb por proyecto"): si el proyecto declaró `neb-profile: none`, continúa genérico **sin sugerir profile** (no se ejecuta el paso 4 para profile desconocido).
3. **Si imports incompletos o ausentes**, ejecutar heurísticas de [`profiles/index.md`](../profiles/index.md) — primer match gana.
4. **Actuar según resultado**:

| Caso | Acción |
|---|---|
| **Profile disponible** y CLAUDE.md ya importa | Continúa sin aviso |
| **Profile disponible** y CLAUDE.md no importa | Aviso: *"Detecté profile `<X>`. CLAUDE.md no lo importa. Sugerencia: instalar/activar el plugin de Neb (`/plugin install neb@neb` + `/reload-plugins`) y agregar el `@import` del profile al CLAUDE.md del proyecto."* |
| **Profile pendiente** (listado sin `profiles/<X>/`) | Aviso: *"Detecté profile `<X>` (Pendiente). Sin convenciones específicas. ¿Crear el profile siguiendo el patrón de `profiles/self-applied/` (ver [CLAUDE.md interno del repo](../CLAUDE.md) "Agregar un profile nuevo") o continuar genérico?"* |
| **Profile desconocido** (ningún indicador match) | Aviso: *"No detecté profile conocido. ¿Continuamos genérico, agregamos heurística + nuevo profile, o marco este dir como sin-profile (`neb-profile: none`) para no volver a sugerirlo?"* |

Heurísticas y prioridad: orden de tabla en [`profiles/index.md`](../profiles/index.md).

## Opt-out de profile / Neb por proyecto

Un proyecto puede declarar, mediante un **marcador en su `CLAUDE.md`**, que no quiere sugerencias de profile o que no use Neb. El marcador es persistente (sobrevive entre sesiones) y se respeta **antes** de sugerir nada — evita que Claude vuelva a proponer un profile en cada sesión sobre un dir que el dev ya decidió dejar genérico.

| Marcador (en el `CLAUDE.md` del proyecto) | Semántica | Quién lo consume |
|---|---|---|
| `<!-- neb-profile: none -->` | El proyecto **usa Neb** pero no tiene profile: trabajo genérico. Claude no vuelve a sugerir detectar/crear profile en ese dir. | Esta detección (pasos 2 y 4). |
| `<!-- neb: skip -->` | El proyecto **no usa Neb**: el hook `SessionStart` detecta el marcador en el `CLAUDE.md` del proyecto activo y **no inyecta el arranque**. Para proyectos ajenos a Neb donde la metodología no debe actuar. | El hook `SessionStart` (`bootstrap/neb-bootstrap-context.py`, vía `CLAUDE_PROJECT_DIR`) — activo desde v2.0.0 |
| `<!-- neb-logbook: local -->` | El proyecto usa Neb y la bitácora, pero **no publica al catálogo central** (queda local-only) aunque haya `NEB_LOGBOOK_ENDPOINT` — opt-out de compartición **por proyecto**. *(Opt-out por perfil: futuro.)* | El hook `logbook-sync` (`hooks/lib/logbook.py`); ver [`../workflow/logbook.md`](../workflow/logbook.md) §"Entorno compartido" |

Reglas del marcador:

- **Independientes, `neb: skip` prevalece**: si ambos marcadores están presentes, `neb: skip` gana — apaga toda la inyección del arranque, lo que vuelve irrelevante a `neb-profile: none` (que solo apaga las sugerencias de profile).
- **Idempotente**: si el marcador ya está presente, no se duplica.
- **Respeta contenido humano**: se inserta en una zona neutra del `CLAUDE.md`, nunca dentro de bloques `<!-- human -->` … `<!-- /human -->` (ver [`../methodology/change-control-policy.md`](../methodology/change-control-policy.md)).
- **Sin `CLAUDE.md`**: si el proyecto no tiene `CLAUDE.md` y el dev elige marcarlo sin-profile, Claude crea uno mínimo con el marcador.
- **Reversible**: el dev revierte el opt-out borrando el marcador.

## Profile activo durante la sesión

El **profile activo** es el estado mental que Claude mantiene durante la sesión. Inicia en `none` si la sesión arranca fuera de un proyecto detectable (ej. `~`); si no, queda fijado por la detección inicial.

### Triggers de re-detección

Claude vuelve a aplicar la heurística de [`profiles/index.md`](../profiles/index.md) cuando el prompt entrante:

1. **cwd cambia** — `cd` a subdir, `cd ..`, o cualquier acción que mueva el cwd (incluyendo dentro del mismo repo, ej. raíz ↔ `reqs/<algo>/`).
2. **Referencia path fuera del cwd** — el dev menciona un archivo, dir o repo cuyo path matchea heurística distinta a la del profile activo.
3. **Pide artefacto de otro profile** — edición/lectura de archivo cuyo path encaja en otra fila de la tabla.

No disparan re-detección: saludos, conversación trivial, preguntas meta sin path. Tampoco re-dispara en un dir con `neb-profile: none` (el opt-out persiste durante la sesión).

### Política de anuncio

| Situación | Acción |
|---|---|
| Profile activo no cambia | Silencio. Continúa. |
| Profile activo cambia (sin trabajo en curso del anterior) | Anuncio inline 1 línea, procede directo: `[profile: <X> → <Y>] motivo: <cd a foo/reqs/bar \| path mencionado fuera de cwd \| edición en path Z>` |
| Profile activo cambia con trabajo en curso del anterior (plan aprobado activo, edición a medio camino, fase no cerrada) | Pausa: anuncia el cambio y pide confirmación antes de abandonar el contexto previo |

**Skills aplicables**: cuando Claude detecta o re-detecta el profile activo, consulta `skills/README.md` e identifica los skills cuya columna "Profile(s) aplicable(s)" incluye el profile detectado. Si hay skills aplicables, los anuncia en la misma línea del anuncio de profile: `[profile: <X>] skills aplicables: <skill1>, <skill2>`. Si no hay skills aplicables, omite la mención.

### Edge cases

- **Sesión inicia en `~` o dir sin profile mapeable** — `profile activo = none`. Primer prompt con path conocido dispara detección normal y anuncia `[profile: none → <X>]`.
- **Prompt menciona dos profiles** — anunciar ambigüedad y preguntar cuál es driver antes de actuar. No asumir.
- **cwd en el directorio raíz del clon (sin repo detectado)** — `none`; el primer path en el prompt resuelve.
- **Path mencionado pero archivo no existe** — la heurística es estructural (matchea por patrón de path/nombre), no requiere `stat`.

La heurística de [`profiles/index.md`](../profiles/index.md) es la **single source of truth**; esta política la consume sin duplicarla.
