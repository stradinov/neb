# Cómo funciona Neb

Documentación técnica para comprender la **mecánica interna** de Neb:
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
| 9 | Mejora | Loop de retroalimentación que refina los lineamientos de Neb a partir del uso real. |

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

## Profiles

Un *profile* encapsula lo que no es universal en un proyecto: comandos de
build, convenciones de commit, proceso de deploy y revisores aplicables.
El núcleo de Neb es agnóstico; los profiles lo concretan para un
tipo de proyecto específico.

### Detección automática

Al iniciar trabajo en un directorio, el agente detecta el profile activo
mediante heurísticas de path y estructura del proyecto. El profile permanece
fijo durante la sesión y cambia únicamente cuando el contexto lo requiere.

### Profiles incluidos en el núcleo

- `self-applied` — la propia Neb (el repo se gobierna con sus propias reglas)
- `profile-authoring` — creación de un profile nuevo
- `skill-authoring` — creación de un skill nuevo
- `research` — investigación multi-fuente con verificación adversarial

---

## Personalización sin modificar el núcleo

### Overrides personales (`personal/<usuario>.md`, gitignored)

Preferencias de comunicación, atajos y reglas individuales del desarrollador.
Contrato: un override puede *estrechar o agregar* sobre el baseline, pero
**nunca relajarlo**.

### Overrides de equipo (dentro del profile)

Convenciones de commit, estándares de código, definición de done y reglas
de deploy. Aplican a todos los integrantes que utilicen el profile.

---

## Mecanismo de arranque

Neb se instala como **plugin de Claude Code**. Al iniciar cada sesión, un hook
`SessionStart` del plugin inyecta el arranque con **peso vinculante** (Claude lo
respeta como un `CLAUDE.md` de proyecto): las reglas *always-on* —políticas de
comunicación, detección de profile, onboarding— ensambladas desde
`general/startup.md`, más el overlay y la configuración personal del adoptante.
El resto del contenido se carga on-demand según lo que el contexto requiera.

Los proyectos cliente **no** necesitan ninguna línea de `@import` en su
`CLAUDE.md`: el hook inyecta el arranque en toda sesión, de modo que un
`CLAUDE.md` de proyecto conserva solo sus imports de profile y su contenido
propio. El marcador `<!-- neb: skip -->` en el `CLAUDE.md` de un proyecto
desactiva la inyección para ese repo.

Dos variables fijan los paths del entorno: `NEB_HOME` (el directorio del plugin
instalado / checkout de neb) y `NEB_WORKSPACE` (la raíz del workspace, donde
viven el overlay y `personal/`). Cómo setearlas: [user-guide § Configurar el entorno](user-guide.md).

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

El repo de neb se rige por sus propias reglas. Cualquier modificación a
Neb es un requerimiento que sigue el flujo de Neb: fases, gate de
plan-review, artefactos y versionado. El historial de documentos de cambio
del repo registra cómo se tomó cada decisión de diseño.

---

## Referencias

- [`methodology/promises.md`](../methodology/promises.md) — las promesas de Neb con criterios verificables
- [`process/`](../process/) — detalle de cada fase y sus gates
- [`profiles/index.md`](../profiles/index.md) — catálogo de profiles y heurística de detección
- [`workflow/index.md`](../workflow/index.md) — ubicación y nomenclatura de los artefactos
