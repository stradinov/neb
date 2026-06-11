# Convenciones (profile: research)

## Modos de disparo

### Explícito (siempre disponible)

El dev pide directamente: "investiga X", "busca fuentes sobre Y", "compara opciones de Z".

Claude abre el REQ de research sin preguntar.

### Conservador (default)

Output esperado de Claude ante pregunta sobre tema especializado sin antecedente en skills/memoria del proyecto y complejidad media o alta (ver `process/planning.md` tabla de Riesgo de regresión):

> "¿Abro un REQ de research sobre `<tema>` antes de proceder?"

El dev puede rechazar; Claude procede sin research.

### Proactivo (bajo condiciones)

Claude propone abrir REQ de research sin que el dev pregunte cuando:
- El prompt toca un tema sin antecedente en skills ni memoria del proyecto, Y
- El REQ activo es de impacto medio o alto (`complejidad: media | alta` según `process/planning.md`), Y
- No existe un research vigente sobre el mismo tema (verificar `methodology/research/` + `<proyecto>/research/`).

Output esperado:

> "Antes de planear, propongo abrir un REQ de research sobre `<tema>` — sin antecedente en skills/memoria y el impacto es medio/alto. ¿Procedo?"

El dev puede rechazar.

## Formato del documento de research

### Frontmatter YAML

Campos obligatorios (4):

```yaml
---
propósito: exploratorio | decisión
fecha: YYYY-MM-DD
llms_consultados:  # motor/fuentes realmente usados; el campo acepta describir el harness, no solo un LLM
  - { proveedor: <Claude|Gemini|...>, modelo: <id del modelo o descripción del motor, ej. "deep-research workflow" | "WebSearch+WebFetch directos">, fecha_query: YYYY-MM-DD }
status: vigente | superseded | deprecated
---
```

Campos opcionales (agregar solo cuando aplican):

```yaml
descripción_propósito: <texto breve cuando propósito = decisión>
req_originador: <path relativo al change MD que originó este research>
supersedes: <path al research anterior>
superseded_by: <path al research que lo reemplaza>
deprecated_at: YYYY-MM-DD
```

Cada campo opcional es **condicional** — se agrega solo en su caso, se omite en el resto:

| Campo | Aplica cuando | Se omite cuando |
|---|---|---|
| `descripción_propósito` | `propósito = decisión` (describe la decisión que alimenta) | `propósito = exploratorio` |
| `req_originador` | el research nació de un REQ/change (lo cita) | research abierto manualmente por el dev — entonces aplica [deployment.md](deployment.md) §Gate F7 punto 3 (1 línea de justificación en el cuerpo) |
| `supersedes` | este research reemplaza a uno anterior | research nuevo sin predecesor (el caso normal) |
| `superseded_by` | este research fue reemplazado por uno posterior (recíproco de `supersedes`) | mientras siga `vigente` |
| `deprecated_at` | el research pasa a `status: deprecated` | mientras siga `vigente` o `superseded` |

Que un campo opcional no aparezca en los research existentes no es deuda: son condicionales/contingentes que aún no aplicaron.

### Estructura del cuerpo

```
# <Título de la investigación>

## Pregunta central

<Una oración que resume qué se investiga>

## Síntesis

<Respuesta destilada — sin recitar outputs crudos de las fuentes. Si hay divergencia material entre fuentes, indicarla explícitamente.>

## Utilidad declarada

<Propósito concreto para el que se realizó esta investigación>

## Dimensiones investigadas

| Dimensión | Hallazgo | Fuentes que coinciden | Discrepancias |
|---|---|---|---|

## Conclusión / Recomendación

<Solo cuando propósito = decisión>

## Anexo: prompts usados

<Por fuente/motor — para reproducibilidad>
```

### Síntesis vs recitar

El cuerpo del documento entrega **síntesis destilada**: inferencias, comparativas, conclusiones. No transcribir outputs crudos de las fuentes; si un claim literal es necesario, citarlo entrecomillado con fuente y fecha. Criterio: si eliminar un párrafo no cambia el entendimiento del lector, no escribirlo.

## Trazabilidad

### Citadores legítimos

| Citador | Dónde se materializa la cita |
|---|---|
| Change MD del REQ originador | Sección "Insumos" del change o cuerpo de justificación |
| Otros changes que lo reutilizan | Inline en la justificación de la decisión |
| Archivos de la metodología | Inline donde alimentó la decisión |
| Skills (`skills/<x>/`) | Body del skill o `references/` |
| Memoria del proyecto (`project_<nombre>.md`) | Línea de referencia si la decisión derivada quedó en memoria |
| Fragment del changelog | Si el research justificó un bump |

### Formato canónico de cita

Cita Markdown con path relativo al consumidor:

```markdown
Decisión basada en [research/2026-01-15-tooling-comparison.md](../../research/2026-01-15-tooling-comparison.md).
```

No usar URLs absolutas ni IDs opacos. Path relativo resiste reubicaciones del repo.

### Búsqueda inversa

Para saber qué documentos citan un research: `grep -r "<slug-del-research>" methodology/ <proyectos>/`.

Si el volumen de research vigente llega a ≥10: agregar tabla índice en `research/README.md` (`Research | Status | Citadores conocidos`).

### Obsolescencia

Un research **no se edita** tras cerrado. Si el landscape cambia (ej. un free tier se depreca), abrir research nuevo con `supersedes:` apuntando al anterior; el anterior pasa a `status: superseded` con `superseded_by:` recíproco.

Excepción: typos, citas rotas, metadata incorrecta — edición directa con commit explicativo, sin cambio de status.

Cuando un research pasa a `superseded`, los documentos que lo citan reciben señal en Fase 9 de su propio REQ.

## Separación core vs profile

Lo universal (triggers de disparo, principio "skills primero / research segundo"): `general/communication.md`, `process/planning.md`, `methodology/principles.md`.

Lo específico de research (frontmatter, síntesis, trazabilidad, mecanismo de investigación multi-fuente): este archivo.

El mecanismo concreto **vive en este archivo** (sección siguiente). Se describe **por capacidad requerida**, no atado al nombre de una herramienta concreta — un harness que el equipo no controla puede cambiar o desaparecer.

### Mecanismo recomendado

El motor de research debe cubrir cuatro capacidades: **fan-out de búsqueda + fetch de fuentes + verificación adversarial de claims + síntesis citada**. Jerarquía de implementación:

| Capa | Implementación | Cuándo usar |
|---|---|---|
| **Piso estable (default)** | `WebSearch` + `WebFetch` conducidos por Claude | Siempre — motor base verificado en uso, sin dependencia de herramientas externas |
| **Acelerador opcional** | skill `deep-research` (fan-out web → fetch → verificación → reporte citado) | Cuando está disponible y funciona. Modo de fallo conocido: sub-agentes con `schema` forzado que no emiten su salida estructurada. Si falla, degradar al piso `WebSearch`/`WebFetch` sin bloquear |
| **Fuentes internas** | conectores MCP (`outlook_email_search`, `sharepoint_search`, …) | Cuando la fuente es correo / SharePoint / sistemas internos, no la web |
| **Orquestación grande** | workflows multi-agente | Research amplio que justifica fan-out paralelo. Acotar el número de agentes y preferir salida en texto sobre `schema` forzado (ver modo de fallo arriba) |
| **Voz externa (LLM)** | **Gemini** (modelo propietario de Google) | **Solo en research `propósito = exploratorio`**, inline en el mismo turno que el `WebSearch` de Claude — segunda voz independiente para ampliar cobertura y reducir sesgo de modelo. No en `decisión`. Groq / Ollama / OpenRouter quedan fuera del profile |

`deep-research` es la implementación **recomendada-hoy**, no un contrato: si cambia o se retira, el piso `WebSearch`/`WebFetch` sigue cumpliendo la capacidad. El campo `llms_consultados` del frontmatter registra el motor realmente usado (ver §Formato del documento).

#### Criterio de re-evaluación

Revisar esta sección si: (a) el harness nativo gana o pierde una capacidad (p. ej. `deep-research` se estabiliza o se retira), (b) aparece un conector o motor relevante, o (c) cambia el free tier de un motor externo (p. ej. Gemini).
