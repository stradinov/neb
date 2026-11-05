# Catálogo de roles

Catálogo de roles universales, dimensiones del plan, implementación persona/subagente y evolución. La invocación de roles (default por profile, algoritmo de detección, modo de anuncio, cobertura por fase) vive en [`../process/roles-invocation.md`](../process/roles-invocation.md).

## Dimensiones del plan

Catálogo canónico. Indicadores genéricos universales; cada profile puede extender con indicadores específicos en su `profiles/<profile>/roles.md`.

| Dimensión | Indicadores genéricos | Revisor asociado |
|---|---|---|
| **Frontend (UI/UX)** | Extensiones `.tsx/.jsx/.vue/.html/.scss/.css`; paths `views/`, `templates/`, `js/`, `assets/` | Frontend Reviewer |
| **Backend (lógica de negocio)** | Paths `controllers/`, `classes/`, `services/`; archivos sin acceso BD directo | Code Reviewer |
| **Lógica de BD** (DML / queries / ORM) | Archivos `*Model.*`, queries embebidas, ORM definitions | Database Engineer |
| **Esquema de BD (DDL)** | `migrations/*.sql` con `ALTER`/`CREATE TABLE`/`DROP`/`CREATE INDEX/COLUMN` | Database Engineer (dedupe con anterior) |
| **Instrumentación / observabilidad** | Paths `monitoring/`, `telemetry/`, métricas, logs estructurados, agentes/probes | Observability Reviewer |
| **Auth / seguridad** | Paths `auth/`, archivos con `password`, `token`, `crypt`, `hash`, `session`, `csrf` | Security Reviewer |
| **Routing crítico** | `index.php`, `.htaccess`, `routes.*`, `App.tsx`, redirects | SysAdmin / SRE + Code Reviewer |
| **Performance crítica** | Hot paths declarados en CLAUDE.md, queries con cardinalidad alta, loops sobre tablas grandes | Performance Reviewer |

## Roles universales (profiles de software)

### Software Engineer

Rol principal en profiles de software. Diseña y ejecuta el código siguiendo patrones del profile y convenciones del proyecto. Genera el plan inicial en Fase 3.

### Code Reviewer

Foco: calidad del código, idiomaticidad del profile, ausencia de regresiones, cumplimiento de convenciones específicas del profile (sanitización, naming, estructura).

### Security Reviewer

Foco: auth, sanitización de input, manejo de secrets, exposición de datos sensibles, autorización por capa, vulnerabilidades comunes del profile (SQLi, XSS, CSRF según aplique).

### Database Engineer

Foco: DDL, migraciones, queries, integridad referencial, índices, planes de ejecución, riesgo de bloqueo o deadlock en operaciones largas.

### SysAdmin / SRE

Foco: deploy, configs de servidor, performance en tiempo de ejecución, observabilidad, capacidad, recuperación ante fallos.

## Implementación de roles

Cada rol del catálogo se implementa de una de dos formas:

| Implementación | Definición | Cuándo usar |
|---|---|---|
| **Persona** | Claude asume la identidad del rol dentro del mismo contexto conversacional. Sin llamada API separada. | Rol principal (conduce la sesión); revisores sin isolation crítico; roles ad-hoc no formalizados |
| **Subagente** | Claude invoca una instancia aislada vía `Agent(subagent_type=<nombre>, prompt=<briefing>)` o como agente de un workflow con `agentType`. El subagente recibe el `prompt` del padre, las instrucciones de `CLAUDE.md` y la memoria automática, no la conversación ni el arranque de la sesión (supuestos R11, R12 y R16 de [platform-assumptions.md](platform-assumptions.md)). Definido como `agents/<nombre>.md` en el repo. | Revisores adversariales donde la isolation mejora el rigor (plan-review, diagnóstico de defecto en Fase 9) |

### Limitaciones de los subagentes

- **Sin la conversación** — no ven el contexto conversacional del padre ni el arranque de la sesión (sí las instrucciones de `CLAUDE.md` y la memoria automática, supuesto R12); requieren briefing explícito en cada invocación (ver plantilla en [`../process/plan-review.md`](../process/plan-review.md)).
- **Anidamiento según cómo se lanzan** — un subagente lanzado con Agent puede lanzar otros; un agente de workflow no (supuesto R13). Los flujos de Neb despachan a los revisores desde el hilo principal.
- **Costo y latencia** — cada invocación es una llamada API completa; se acumula si hay N revisores por plan.
- **Stateless** — no recuerdan invocaciones previas.
- **Disponibilidad por sesión** — un agente agregado o editado durante una sesión no está disponible hasta la siguiente; si es del plugin, `/reload-plugins` lo recarga (supuesto R15; ver [`../general/agents.md`](../general/agents.md) § "Limitación de sesión (custom role agents)").

### Criterio para promover un rol de persona a subagente

1. El rol es adversarial por diseño (revisa output que otro produjo).
2. La isolation mejora la calidad de la revisión de forma observable (subagente no conoce la justificación del autor → revisión más estricta).
3. Se invoca con frecuencia suficiente para justificar el costo (≥3 invocaciones reales, análogo al criterio de roles ad-hoc).

Los roles definidos como subagentes tienen su `.md` en `agents/` del repo y se distribuyen en el plugin, auto-descubiertos al instalarlo. Los demás son persona.

## Roles ad-hoc

Si un REQ requiere un revisor no listado (ej. Accessibility Reviewer, Domain Analyst, Performance Reviewer cuando aún no está canonizado), el dev puede pedir un rol ad-hoc inline al revisar la propuesta de roles. Si un rol ad-hoc se repite en N=3 REQs, se promueve al catálogo en next minor (ver "Evolución de roles" abajo).

## Resumen de roles

Inventario de los roles del catálogo: tipo, implementación y profile. La pertinencia de cada rol revisor la pregunta la revisión agregada (ver [`../process/improvement.md`](../process/improvement.md) § "Qué se revisa").

| Rol | Tipo | Impl. | Profile |
|---|---|---|---|
| Process Architect | principal | persona | self-applied |
| Profile Author | principal | persona | profile-authoring |
| QA Process Engineer | revisor | **subagente** (`qa-process-engineer`) | self-applied |
| Process Improvement Analyst | revisor | **subagente** (`process-improvement-analyst`) | self-applied |
| Software Engineer | principal | persona | software (futuro) |
| Code Reviewer | revisor | persona | software (futuro) |
| Security Reviewer | revisor | persona | software (futuro) |
| Database Engineer | revisor | persona | software (futuro) |
| Skill QA Engineer | revisor | **subagente** (`skill-qa-engineer`) | skill-authoring |
| Fact-Check Reviewer | revisor | **subagente** (`fact-check-reviewer`) | research |
| Context Completeness Reviewer | revisor | **subagente** (`context-completeness-reviewer`) | transversal (todos los profiles) |
| SysAdmin / SRE | revisor | persona | software (futuro) |
| Frontend Reviewer | revisor por dimensión | persona | software (futuro) |
| Observability Reviewer | revisor por dimensión | persona | software (futuro) |
| Performance Reviewer | revisor por dimensión | persona | software (futuro) |

> En la columna **Profile**, `software (futuro)` denota profiles de software por agregar. Ver § "Roles universales (profiles de software)".

## Evolución de roles

Mecanismo de auto-mejora del catálogo: defectos no cazados disparan ajustes de focos o creación de roles nuevos.

### Atribución del defecto

Cuando se detecta un defecto en la implementación (vía métricas `Errores de implementación`, patches retrospectivos, o reportes de uso post-cierre), Claude pregunta en Fase 9: *"¿Hubo defecto que ningún rol cazó? ¿Era responsabilidad de un rol existente o requiere uno nuevo?"*

Criterios de atribución por tipo de defecto:

| Tipo de defecto | Atribución |
|---|---|
| Inconsistencia entre archivos / contradicción con política | QA Process Engineer / Code Reviewer |
| Sesgo de profile en vocabulario canónico | QA Process Engineer (sub-foco existente) |
| Sinónimo no declarado / término canónico mezclado | QA Process Engineer (sub-foco precisión terminológica) |
| Obligación sin sujeto acotado (hereda pasos a quien no toca su objeto) | QA Process Engineer (sub-foco verificabilidad) |
| Ceremonia innecesaria / valor cuestionable | Process Improvement Analyst |
| Vulnerabilidad de seguridad | Security Reviewer |
| Performance issue / query lenta | Performance Reviewer / Database Engineer |
| DDL inconsistente / migración rota | Database Engineer |
| Bug funcional en código | Code Reviewer / Software Engineer |

### Acciones

| Atribución | Acción | Ejemplo histórico |
|---|---|---|
| Cae dentro del mandato de un rol existente, foco no lo enunciaba explícitamente | **Ajustar foco** del rol con sub-foco/bullet nuevo. REQ tipo `docs:` (patch) | sub-foco agnóstico-profile agregado a QA tras un defecto de sesgo de profile |
| Tipo de defecto no cubierto por ningún rol del catálogo | **Crear rol nuevo** solo si: (a) el foco no encaja conceptualmente como sub-foco; (b) se anticipa reuso (≥2 casos previsibles). REQ minor | (Hipotético) Accessibility Reviewer tras issues recurrentes de a11y |
| Defecto cae en dimensión nueva (no de rol) | **Ajustar catálogo de dimensiones** (`Dimensiones del plan` arriba) | (Hipotético) dimensión "i18n" agregada |

### Preferencia explícita

Ante duda entre ajustar foco vs crear rol → **ajustar foco**. Crear rol solo si:

1. El sub-foco no encaja conceptualmente en ningún rol existente.
2. Se anticipa que el nuevo rol será invocado en otros REQs (al menos 2-3 casos previsibles).

Esta regla previene role inflation. Roles ad-hoc usados una sola vez no se promueven al catálogo.

### Trazabilidad

CHANGELOG entry del ajuste menciona explícitamente *"tras detección del defecto X en REQ Y"* — análogo a "tras revisión agregada de N REQs".
