# Catálogo de roles

Catálogo de roles universales, dimensiones del plan, implementación persona/subagente y evolución. La invocación de roles (default por stack, algoritmo de detección, modo de anuncio, cobertura por fase) vive en [`../process/roles-invocation.md`](../process/roles-invocation.md).

## Dimensiones del plan

Catálogo canónico. Indicadores genéricos universales; cada stack puede extender con indicadores específicos en su `stacks/<stack>/roles.md`.

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

## Roles universales (stacks de software)

### Software Engineer

Rol principal en stacks de software. Diseña y ejecuta el código siguiendo patrones del stack y convenciones del proyecto. Genera el plan inicial en Fase 3.

### Code Reviewer

Foco: calidad del código, idiomaticidad del stack, ausencia de regresiones, cumplimiento de convenciones específicas del stack (sanitización, naming, estructura).

### Security Reviewer

Foco: auth, sanitización de input, manejo de secrets, exposición de datos sensibles, autorización por capa, vulnerabilidades comunes del stack (SQLi, XSS, CSRF según aplique).

### Database Engineer

Foco: DDL, migraciones, queries, integridad referencial, índices, planes de ejecución, riesgo de bloqueo o deadlock en operaciones largas.

### SysAdmin / SRE

Foco: deploy, configs de servidor, performance en runtime, observabilidad, capacidad, recuperación ante fallos.

## Implementación de roles

Cada rol del catálogo se implementa de una de dos formas:

| Implementación | Definición | Cuándo usar |
|---|---|---|
| **Persona** | Claude asume la identidad del rol dentro del mismo contexto conversacional. Sin llamada API separada. | Rol principal (conduce la sesión); revisores sin isolation crítico; roles ad-hoc no formalizados |
| **Subagente** | Claude invoca una instancia aislada vía `Agent(subagent_type=<nombre>, prompt=<briefing>)`. El subagente recibe solo lo que el padre le pasa en el `prompt` — no ve la conversación. Definido como `agents/<nombre>.md` en el repo. | Revisores adversariales donde la isolation mejora el rigor (plan-review, diagnóstico de defecto en Fase 9) |

### Limitaciones de los subagentes

- **Sin contexto heredado** — requieren briefing explícito en cada invocación (ver plantilla en [`../process/plan-review.md`](../process/plan-review.md)).
- **Sin anidamiento** — el rol principal no puede invocar subagentes desde dentro de otro subagente.
- **Costo y latencia** — cada invocación es una llamada API completa; se acumula si hay N revisores por plan.
- **Stateless** — no recuerdan invocaciones previas.
- **Disponibilidad por sesión** — los custom role agents instalados en `~/.claude/agents/` durante una sesión no están disponibles hasta la siguiente, o hasta ejecutar `/reload-plugins`.

### Criterio para promover un rol de persona a subagente

1. El rol es adversarial por diseño (revisa output que otro produjo).
2. La isolation mejora la calidad de la revisión de forma observable (subagente no conoce la justificación del autor → revisión más estricta).
3. Se invoca con frecuencia suficiente para justificar el costo (≥3 invocaciones reales, análogo al criterio de roles ad-hoc).

Los roles definidos como subagentes tienen su `.md` en `agents/` del repo y se instalan con `bootstrap/install-agents.sh`. Los demás son persona.

## Roles ad-hoc

Si un REQ requiere un revisor no listado (ej. Accessibility Reviewer, Domain Analyst, Performance Reviewer cuando aún no está canonizado), el dev puede pedir un rol ad-hoc inline al revisar la propuesta de roles. Si un rol ad-hoc se repite en N=3 REQs, se promueve al catálogo en next minor (ver "Evolución de roles" abajo).

## Resumen de utilidad

Tracking del valor real de cada rol/sub-foco. Score se ajusta en Fase 9 (ver [`../process/improvement.md`](../process/improvement.md)) según el comportamiento del rol en plan-review.

| Rol | Tipo | Impl. | Stack | Utilidad | Última act. |
|---|---|---|---|---|---|
| Business Analyst | principal | persona | requirements-analysis | 1.0 | 2026-05-06 |
| Process Architect | principal | persona | self-applied | 1.0 | 2026-05-03 |
| Stack Author | principal | persona | stack-authoring | 1.0 | 2026-05-15 |
| QA Process Engineer | revisor | **subagente** (`qa-process-engineer`) | self-applied | 0.0 | 2026-05-17 |
| Process Improvement Analyst | revisor | **subagente** (`process-improvement-analyst`) | self-applied | 0.9 | 2026-05-17 |
| Software Engineer | principal | persona | software (futuro) | 1.0 | 2026-05-03 |
| Code Reviewer | revisor | persona | software (futuro) | 1.0 | 2026-05-17 |
| Security Reviewer | revisor | persona | software (futuro) | 1.0 | 2026-05-17 |
| Database Engineer | revisor | persona | software (futuro) | 1.0 | 2026-05-14 |
| Skill QA Engineer | revisor | **subagente** (`skill-qa-engineer`) | skill-authoring | 1.0 | 2026-05-14 |
| Fact-Check Reviewer | revisor | **subagente** (`fact-check-reviewer`) | research | 1.0 | 2026-05-17 |
| Context Completeness Reviewer | revisor | **subagente** (`context-completeness-reviewer`) | transversal (todos los stacks) | 0.0 | 2026-05-21 |
| SysAdmin / SRE | revisor | persona | software (futuro) | 1.0 | 2026-05-03 |
| Frontend Reviewer | revisor por dimensión | persona | software (futuro) | 1.0 | 2026-05-03 |
| Observability Reviewer | revisor por dimensión | persona | software (futuro) | 1.0 | 2026-05-03 |
| Performance Reviewer | revisor por dimensión | persona | software (futuro) | 1.0 | 2026-05-03 |

> En la columna **Stack**, `software (futuro)` denota stacks de software por agregar. Ver § "Roles universales (stacks de software)".

## Evolución de roles

Mecanismo de auto-mejora del catálogo: defectos no cazados disparan ajustes de focos o creación de roles nuevos.

### Atribución del defecto

Cuando se detecta un defecto en la implementación (vía métricas `Errores de implementación`, patches retrospectivos, o reportes en validación diferida en uso), Claude pregunta en Fase 9: *"¿Hubo defecto que ningún rol cazó? ¿Era responsabilidad de un rol existente o requiere uno nuevo?"*

Criterios de atribución por tipo de defecto:

| Tipo de defecto | Atribución |
|---|---|
| Inconsistencia entre archivos / contradicción con política | QA Process Engineer / Code Reviewer |
| Sesgo de stack en vocabulario canónico | QA Process Engineer (sub-foco existente) |
| Ceremonia innecesaria / valor cuestionable | Process Improvement Analyst |
| Vulnerabilidad de seguridad | Security Reviewer |
| Performance issue / query lenta | Performance Reviewer / Database Engineer |
| DDL inconsistente / migración rota | Database Engineer |
| Bug funcional en código | Code Reviewer / Software Engineer |

### Acciones

| Atribución | Acción | Ejemplo histórico |
|---|---|---|
| Cae dentro del mandato de un rol existente, foco no lo enunciaba explícitamente | **Ajustar foco** del rol con sub-foco/bullet nuevo. REQ tipo `docs:` (patch) | sub-foco agnóstico-stack agregado a QA tras un defecto de sesgo de stack |
| Tipo de defecto no cubierto por ningún rol del catálogo | **Crear rol nuevo** solo si: (a) el foco no encaja conceptualmente como sub-foco; (b) se anticipa reuso (≥2 casos previsibles). REQ minor | (Hipotético) Accessibility Reviewer tras issues recurrentes de a11y |
| Defecto cae en dimensión nueva (no de rol) | **Ajustar catálogo de dimensiones** (`Dimensiones del plan` arriba) | (Hipotético) dimensión "i18n" agregada |

### Preferencia explícita

Ante duda entre ajustar foco vs crear rol → **ajustar foco**. Crear rol solo si:

1. El sub-foco no encaja conceptualmente en ningún rol existente.
2. Se anticipa que el nuevo rol será invocado en otros REQs (al menos 2-3 casos previsibles).

Esta regla previene role inflation. Roles ad-hoc usados una sola vez no se promueven al catálogo.

### Trazabilidad

CHANGELOG entry del ajuste menciona explícitamente *"tras detección del defecto X en REQ Y"* — análogo a "tras revisión agregada de N changes".

## Utilidad de roles

Heurística de ajuste del score (análoga a [`../workflow/metrics.md`](../workflow/metrics.md) "Heurística de ajuste de utilidad" pero para roles).

### Eventos

| Evento | Δ score |
|---|---|
| Rol invocado en plan-review → caza defecto / aporta hallazgo material | +1 |
| Rol invocado pero sin hallazgos | -0.1 |
| Rol no invocado en 5 plan-reviews consecutivos donde aplicaría | -0.5 |
| Defecto que el rol debió cazar pero no lo hizo (descubierto post-cierre) | -1 |

### Rangos

| Score | Interpretación | Acción |
|---|---|---|
| ≥ +3 | Core | Mantener prioritario |
| +1 a +3 | Útil | Sin acción |
| 0 a +1 | Neutral / nuevo | Observar |
| -1 a 0 | Marginal | Revisar foco o pertinencia |
| < -1 sostenido por 2 evaluaciones consecutivas | Candidato a deprecar | Propuesta explícita en revisión agregada |

**Cap**: min -2, max +5.

**Score inicial al introducir un rol nuevo**: 1.0.

Trigger del ajuste: en Fase 9 cuando un rol cazó (o no cazó cuando debió) un defecto. Revisión agregada (ver [`../process/improvement.md`](../process/improvement.md)) verifica scores periódicamente y propone deprecaciones de roles con score sostenido bajo.
