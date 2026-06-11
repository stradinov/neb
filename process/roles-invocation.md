# Invocación de roles

Selección de roles por contexto, algoritmo de detección y consolidación, modo de anuncio y cobertura mínima por fase. El catálogo de roles (definiciones, dimensiones, implementación, evolución) vive en [`../methodology/roles-catalog.md`](../methodology/roles-catalog.md).

**Nota sobre nombres de rol**: los roles "Process Architect", "QA Process Engineer" y "Process Improvement Analyst" (y los subagentes `qa-process-engineer`, `process-improvement-analyst`) conservan la palabra "Process" en su nombre. Aquí "Process" se refiere al concepto general de **proceso de metodología** (Process Architect = arquitecto del proceso metodológico), no al nombre actual del profile. La etiqueta sobrevive al rename del profile por inercia conceptual; el rename de roles se evalúa en REQ separado si aparece fricción real.

## Selección de roles por contexto

Claude propone los roles en Fase 3 (Propuesta) antes de generar el plan inicial. Para casos rutinarios usa default sin preguntar; para casos especiales (profile desconocido, tipo REQ raro, plan toca dimensión nueva) pregunta al dev.

### Default por profile

| Profile | Rol principal | Revisores default | Detalle |
|---|---|---|---|
| `self-applied` | Process Architect | QA Process Engineer + Process Improvement Analyst | [profiles/self-applied/roles.md](../profiles/self-applied/roles.md) |
| `profile-authoring` | Profile Author | QA Process Engineer (F3/F4/F7) + Process Improvement Analyst (F9/Incidentes) | [profiles/profile-authoring/roles.md](../profiles/profile-authoring/roles.md) |
| `skill-authoring` | Skill Author | Skill QA Engineer (Fase 5) + Skill Maintainer (periódico) | [profiles/skill-authoring/roles.md](../profiles/skill-authoring/roles.md) |
| `research` | Process Architect | Fact-Check Reviewer (F4 condicional + F7 siempre) | [profiles/research/roles.md](../profiles/research/roles.md) |
| Otros profiles de software (futuros) | Software Engineer | Code Reviewer | — |
| Profile desconocido | (Claude pregunta al dev) | — | — |

### Overrides por dimensión del plan

Cuando el plan toca dimensiones específicas, se agregan revisores adicionales (sin remover los default). Ver tabla "Dimensiones del plan" en [`../methodology/roles-catalog.md`](../methodology/roles-catalog.md).

## Algoritmo de detección y consolidación

Antes de generar el plan, Claude identifica las dimensiones tocadas por los archivos del plan según la tabla anterior, deduplica revisores, agrega el rol principal del profile y reporta la lista consolidada al dev (modo según tabla "Modo de anuncio").

Profile `self-applied` usa roles fijos sin detección por dimensiones (entregable es markdown/documento, no código).

## Modo de anuncio

Cómo Claude reporta la asignación al dev al ejecutar el algoritmo:

| Modo | Comportamiento | Aplica a |
|---|---|---|
| **Silencioso** | Asigna y procede sin notificar. Dev ve los roles al revisar el MD | Patches triviales (typos, fixes de enlaces, cosméticos); profile `self-applied` con roles fijos default y sin extras; repetición exacta del REQ anterior en la misma sesión |
| **Verbose** | Anuncia inline (*"Plan toca [X, Y]. Roles: principal `<rol>`, revisores `<rol>` + `<rol>`. Procedo."*); procede salvo objeción | Casos rutinarios en profile de software con default + 0–2 revisores totales |
| **Verbose obligatorio** | Anuncia inline; procede salvo objeción. La diferencia con verbose normal es que **siempre** se anuncia, no se omite por trivialidad aparente | ≥ 3 revisores totales; revisor especializado activado (Security, Performance, Observability, Database para DDL) |
| **Bloqueante** | Pregunta explícitamente *"¿OK con estos roles?"* y espera respuesta del dev | Profile desconocido; archivo no matchea dimensión y default no aplica claro; conflicto entre dimensiones (ej. `index.php` con auth: routing crítico vs auth); REQ tipo poco común (security review profundo, migración masiva, hotfix de seguridad); dimensión nueva no listada en el catálogo; override solicitado por el dev |

### Regla de prioridad

Si un caso encaja en dos modos, **gana el más restrictivo** según el orden:

```
Bloqueante > Verbose obligatorio > Verbose > Silencioso
```

Ejemplo: REQ con profile desconocido y solo 1 revisor (verbose por revisores; bloqueante por profile) → **bloqueante**.

La tabla puede expandirse vía Fase 9 si surge un caso recurrente no cubierto.

## Cobertura mínima por fase

**Regla**: cada profile debe tener ≥1 subagente formalizado activo en Fase 4 (cierre/gate) y Fase 7 (pre-ejecución/gate). Si el profile no tiene subagente disponible, el dev debe declarar override explícito antes de avanzar. Las fases 1, 2, 6, 8 son conducidas únicamente por el rol principal (persona) — sin gate de subagente.

### Matriz de cobertura por profile × fase (subagentes específicos del profile)

Las fases 1, 2, 6, 8 se omiten (nunca tienen subagente). `—` = fase conducida solo por persona. Esta matriz lista únicamente los subagentes **específicos del profile**; el revisor transversal `context-completeness-reviewer` se invoca adicionalmente en F3/F4/F7 según las condiciones de [`plan-review.md`](plan-review.md) § "Cuándo aplica el `context-completeness-reviewer`".

| Profile | F3 Plan-review | F4 Cierre (gate) | F5 Validación | F7 Pre-ejecución (gate) | F9 Diagnóstico | Incidentes P1/P2 |
|---|---|---|---|---|---|---|
| `self-applied` | `qa-process-engineer` + `process-improvement-analyst` | `qa-process-engineer` | — | `qa-process-engineer` | `process-improvement-analyst` | `process-improvement-analyst` |
| `profile-authoring` | `qa-process-engineer` + `process-improvement-analyst` | `qa-process-engineer` | — | `qa-process-engineer` | `process-improvement-analyst` | `process-improvement-analyst` |
| `skill-authoring` | `skill-qa-engineer` | `skill-qa-engineer` | `skill-qa-engineer` | `skill-qa-engineer` | `process-improvement-analyst` | `process-improvement-analyst` |
| `research` | `qa-process-engineer` + `process-improvement-analyst` (si `propósito = decisión`) | `fact-check-reviewer` (si `propósito = decisión` o divergencia material no resuelta en `[crítico]`) | — | `fact-check-reviewer` (siempre) | `process-improvement-analyst` | `process-improvement-analyst` |
| Profiles de software (futuros) | por dim.: Code Reviewer / Security Reviewer / Database Engineer | Code Reviewer (+ paralelos por dim.) | Security Reviewer (si auth/pagos críticos) | Code Reviewer default | `process-improvement-analyst` | `process-improvement-analyst` |

`process-improvement-analyst` es universal en F9 e Incidentes (no por profile).

Adicionalmente, `context-completeness-reviewer` se invoca de forma **transversal** (todos los profiles) en F3/F4/F7 según las condiciones de [`plan-review.md`](plan-review.md) § "Cuándo aplica el `context-completeness-reviewer`". No reemplaza a los revisores específicos del profile — los complementa auditando suposiciones que el autor no verificó (estado concreto local o dominio sin antecedente).

Ver detalle de cada gate en [`execution.md`](execution.md) (Fase 4) y [`delivery.md`](delivery.md) (Fase 7).
