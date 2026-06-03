# Cómo funciona neb

Documentación técnica para comprender la **mecánica interna** del framework:
estructura del flujo, componentes y mecanismos. Las **guías de uso** (extender,
montar tu overlay, versionar tu configuración) viven en [user-guide.md](user-guide.md).

---

## Flujo de trabajo

Cada requerimiento sigue un flujo de fases secuenciales:

| Fase | Nombre | Descripción |
|---|---|---|
| 1–3 | Clarificación → Propuesta | El agente extrae requisitos y produce un plan concreto. No avanza a implementación sin aprobación explícita. |
| 4 | Implementación | El agente ejecuta el plan. Ante cualquier desviación, detiene el trabajo y reporta antes de continuar. |
| 5–6 | Validación | Se verifica el cumplimiento de los criterios de aceptación. Un revisor adversarial da visto bueno por dimensión. |
| 7 | Entrega | El cambio se cierra con sus artefactos: documento de cambio, confirmación del cambio, versión si aplica. |
| 9 | Mejora | Loop de retroalimentación que refina los lineamientos del framework a partir del uso real. |

### Gate de plan-review

Antes de aprobar un plan de complejidad media o alta, uno o más revisores
independientes lo auditan por dimensiones: proceso, lógica de datos, seguridad
y convenciones de código. Los revisores son subagentes que el agente principal
invoca; sus hallazgos se incorporan al plan antes de pasar a implementación.

---

## Ciclo de estados de un requerimiento

**En progreso** → **En validación** → **Listo para aprobación** → **Cerrado**

En cualquier estado puede adquirir el sufijo **Bloqueado**, que indica que
requiere input externo antes de continuar. El estado se registra en el
documento de cambio del requerimiento.

---

## Stacks

Un *stack* encapsula lo que no es universal en un proyecto: comandos de
build, convenciones de commit, proceso de deploy y revisores aplicables.
El núcleo del framework es agnóstico; los stacks lo concretan para un
tipo de proyecto específico.

### Detección automática

Al iniciar trabajo en un directorio, el agente detecta el stack activo
mediante heurísticas de path y estructura del proyecto. El stack permanece
fijo durante la sesión y cambia únicamente cuando el contexto lo requiere.

### Stacks incluidos en el núcleo

- `self-applied` — el propio framework (el repo se gobierna con sus propias reglas)
- `requirements-analysis` — análisis iterativo de requerimientos
- `stack-authoring` — creación de un stack nuevo
- `skill-authoring` — creación de un skill nuevo
- `research` — investigación multi-fuente con verificación adversarial

---

## Personalización sin modificar el núcleo

### Overrides personales (`personal/<usuario>.md`, gitignored)

Preferencias de comunicación, atajos y reglas individuales del desarrollador.
Contrato: un override puede *estrechar o agregar* sobre el baseline, pero
**nunca relajarlo**.

### Overrides de equipo (dentro del stack)

Convenciones de commit, estándares de código, definición de done y reglas
de deploy. Aplican a todos los integrantes que utilicen el stack.

---

## Mecanismo de arranque

Al iniciar cada sesión, el agente carga mediante `@import` desde
`general/startup.md` las reglas *always-on*: políticas de comunicación,
detección de stack y onboarding. El resto del contenido se carga
on-demand según lo que el contexto requiera.

Los proyectos cliente referencian el framework con la siguiente línea
en su `CLAUDE.md`:

```
@~/.claude/neb/general/startup.md
```

---

## Artefactos del flujo

| Artefacto | Ubicación | Versionado |
|---|---|---|
| Documento de cambio | `<proyecto>/changes/<fecha>-<nombre>.md` | Sí, en el repo del proyecto |
| Plan aprobado | `~/.claude/approved-plans/<ts>-<proyecto>-<slug>.md` | No (histórico cross-proyecto) |
| Pendientes | `~/.claude/pendings.md` | No (seguimiento cross-sesión) |

Cada documento de cambio registra: contexto y objetivo, decisiones tomadas,
plan de pruebas, historial de estados y estado final. Constituye el rastro
auditable de qué se realizó y por qué.

---

## Carácter auto-aplicado

El repo de neb se rige por sus propias reglas. Cualquier modificación al
framework es un requerimiento que sigue el flujo de neb: fases, gate de
plan-review, artefactos y versionado. El historial de documentos de cambio
del repo registra cómo se tomó cada decisión de diseño.

---

## Referencias

- [`methodology/promises.md`](../methodology/promises.md) — las 11 promesas del framework con criterios verificables
- [`process/`](../process/) — detalle de cada fase y sus gates
- [`stacks/index.md`](../stacks/index.md) — catálogo de stacks y heurística de detección
- [`workflow/index.md`](../workflow/index.md) — ubicación y nomenclatura de los artefactos
