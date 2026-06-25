# Principios de una buena metodología Claude

Qué características hacen útil a una metodología de trabajo con un agente de IA.

## Características

1. **Explícita** — vive en archivos versionados que el agente lee. No es conocimiento tácito.
2. **Refinable** — tiene un loop de mejora declarado (ver [improvement](../process/improvement.md)).
3. **Mensurable** — métricas concretas (turnos por fase, re-deployments, incidencias, complejidad estimada vs real).
4. **Agnóstica del profile en su core** — `general/` no menciona paths, comandos ni servidores. Lo específico vive en `profiles/<profile>/`.
5. **Personalizable sin romper el equipo** — `personal/<usuario>.md` puede estrechar o agregar, no relajar (ver [personal-vs-team](personal-vs-team.md)).
6. **Importable** — los proyectos referencian al repo vía `@imports` estables sobre los `index.md`.
7. **Reflexiva** — la metodología se aplica a sí misma: editarla es un requerimiento que sigue sus propias fases y gates (profile `self-applied`), por lo que el repo es ejemplo vivo de su propio uso (dogfooding). `self-applied` no es un profile de dominio periférico sino parte integral del núcleo.

> Estas características son las **promesas** que Neb ofrece al adoptante. Su enunciado de cara al usuario y los criterios de aceptación verificables viven en [promises.md](promises.md).

## Fases vs políticas

- **Fases**: lineales y secuenciales (planning → execution → delivery). Orden en `general/index.md`.
- **Políticas**: transversales, aplican siempre. Canónicas: `communication.md`, `models.md`.

Cuando un archivo crece y mezcla fase + política, separar.

**Cuándo separar mixtos** (metodología/proceso):

- **No separar preventivamente**. La fragmentación excesiva viola el principio "una sola fuente de verdad".
- **Separar cuando hay fricción real al consultar**: e.g. al buscar la matriz de cobertura por fase, se navega un archivo de catálogo conceptual; al buscar un principio, se navega un archivo de matrices procedimentales.
- **Abrir REQ de patch separado** por cada mixto que justifique split. Cada split es una decisión de granularidad propia, no una refactorización en bloque.

### Capas del repo y test de pertenencia

Cada `.md` vive en la capa cuyo test de pertenencia cumple (mapa de capas en [`../general/index.md`](../general/index.md) § "Capas del repo"):

| Capa | Test de pertenencia |
|---|---|
| `general/` | ¿Se consulta SIEMPRE, agnóstico de fase y de naturaleza del cambio? (política de operación base) |
| `methodology/` | ¿Define un criterio/vocabulario/catálogo/principio que el proceso CONSULTA, sin prescribir pasos? |
| `process/` | ¿Prescribe pasos/gates atados a una FASE del ciclo 1–9? |
| `workflow/` | ¿Describe el ciclo de vida de un ARTEFACTO que se produce/persiste? |
| `tooling/` | ¿Es hook/recurso opcional, no lineamiento del baseline? |

> **Excepción `docs/`**: la carpeta `docs/` (documentación de cara al adoptante — explicación en `how-it-works.md`, guías how-to en `user-guide.md`) **no** se gobierna por este test: es documentación para humanos, no lineamiento que el agente aplique en el flujo. Sus archivos no se clasifican como Metodología/Proceso.

### Fronteras cohesivas deliberadas

Algunos archivos mezclan capas **por cohesión de dominio** y NO se fragmentan: separar dañaría más la navegación de lo que la pureza aportaría. Son excepciones explícitas, no deuda:

- [`version-control.md`](../process/version-control.md) — git como dominio cohesivo (criterio + operaciones + CHANGELOG); el formato de commit, que es lo customizable, sí se extrajo a [git-conventions.md](git-conventions.md).
- [`../general/agents.md`](../general/agents.md) — catálogo de subagentes del harness de Claude Code + selección; referencia transversal consultada en cualquier fase.
- [`../general/incidents.md`](../general/incidents.md) — protocolo reactivo P1/P2, paralelo al ciclo lineal 1–9; el ciclo de vida del artefacto INCIDENT MD sí vive en `workflow/changes.md`.
- [`plan-review.md`](../process/plan-review.md) — proceso + plantilla de briefing + criterio de activación, intrínsecos entre sí.
- [`roles-catalog.md`](roles-catalog.md) — catálogo + tracking de utilidad (scores) + evolución, cohesivos; la invocación (cuándo/cómo) sí vive aparte en `process/roles-invocation.md`.
- [`personal-vs-team.md`](personal-vs-team.md) — la regla de convivencia personal/equipo incluye el gate "Claude avisa ante un override que contradice el baseline"; cohesivo con la regla, no se separa a `process/`.

### Puntos de customización

Archivos diseñados para que el adoptante los **sobreescriba** sin tocar el resto del núcleo (promesa "Customizable", ver [promises.md](promises.md)): [coding-standards.md](coding-standards.md), [git-conventions.md](git-conventions.md), [done-criteria.md](done-criteria.md), [`../general/communication.md`](../general/communication.md) (interacción), [`../general/models.md`](../general/models.md) (modelos), [personal-vs-team.md](personal-vs-team.md). El contrato "el override estrecha o agrega, nunca relaja" los protege de romper el baseline.

Esta es la **lista canónica** (customizable **por diseño**). Tienen su bloque `> Punto de customización` **materializado**: `coding-standards.md`, `git-conventions.md`, `done-criteria.md`, `communication.md`; **pendiente de materializar**: `models.md`. Las sedes que enumeran lo materializado —[promises.md](promises.md) (promesa 5, celda "Dónde se materializa") y [personal-vs-team.md](personal-vs-team.md) (preconfigurados)— espejan ese **subconjunto materializado**, no la lista por diseño. Al agregar un punto, o al materializar uno pendiente, sincroniza las sedes afectadas.

## Contexto especializado antes de inferir

Ante un tema fuera del antecedente registrado en skills o en la memoria del proyecto, Claude consulta primero los skills aplicables. Si el tema sigue sin cobertura y el impacto del REQ es medio o alto, propone abrir un REQ de research antes de proceder. No infiere desde el vacío en temas especializados.

Jerarquía: skills disponibles → research vigente → inferencia de Claude.

## Suposiciones explícitas antes de afirmar

Toda afirmación se respalda en evidencia del turno actual o se declara como suposición. Hay dos clases de suposición a vigilar:

- **Estado concreto sin verificar** (brecha de contexto): afirmar sobre un archivo, dato, dependiente o configuración cuya fuente existe localmente pero no fue consultada en el turno actual. Acción: verificar (lectura, grep, LSP, consulta a memoria/skill vigente).
- **Dominio sin antecedente** (dominio desconocido): inferir sobre un dominio sin cobertura en skills, memoria del proyecto o research vigente. Acción: aplicar "Contexto especializado antes de inferir" — proponer abrir REQ de research si el impacto es medio/alto (ver [`../profiles/research/conventions.md`](../profiles/research/conventions.md) "Modos de disparo").

Output esperado:

- Plan (Fase 3): el plan separa dependientes/datos **verificados** (con la fuente: grep `X`, lectura de `Y:Z-W`, LSP, skill `<nombre>`, memoria `<archivo>`) de los **asumidos sin verificar** (con la razón y la acción pendiente).
- Cierre de edit (Fase 4): Claude menciona qué fuentes consultó vs cuáles dio por entendidas por contexto previo.
- Respuesta exploratoria (cualquier fase): si un hecho citado no se verificó en el turno actual, marcarlo `[asumido]`, `[memoria sin re-verificar]` o `[dominio sin research]`.

Aplica a todos los profiles. Cubre dos huecos: (a) incluso con skill cargado y memoria vigente, una sesión puede asumir el estado concreto de un archivo sin haberlo abierto; (b) Claude puede confundir analogías superficiales del entrenamiento con conocimiento real del dominio.

Operacionalización: subagente `context-completeness-reviewer` (ver [`../agents/context-completeness-reviewer.md`](../agents/context-completeness-reviewer.md)) audita formalmente las suposiciones en plan-review (Fase 3), cierre de implementación (Fase 4) y pre-entrega final (Fase 7).

## Anti-patrones

- Documentación que repite el código. **No documentar** (criterio para Fase 8, ver [`../process/documentation.md`](../process/documentation.md)): cambios triviales (typo, una línea), listas de archivos modificados (el VCS ya las tiene), estado temporal (ramas, PRs en revisión), decisiones evidentes leyendo el código, logs de "qué hicimos hoy".
- Reglas absolutas sin "por qué".
- Versionado por fecha en el nombre del archivo (git ya tiene historial). *Excepción*: artefactos donde el orden cronológico es información de valor primaria (`<proyecto>/changes/`, `~/.claude/approved-plans/`) — la fecha en el nombre permite ordenar/filtrar sin abrir git log y resiste renombres.
- Sincronizar manualmente entre proyectos (por eso este repo existe).
- **Instruir a Claude cómo razonar o ejecutar internamente, en lugar de qué producir.** Algoritmos paso a paso para tareas de inferencia natural, ciclos de self-management (cambiar modelo, restaurar modelo, etc.) o duplicación de instrucciones del prompt de sistema consumen contexto sin agregar valor — Claude ya las hace solo. Especificar el output esperado o asignar la responsabilidad a un rol.

## Coherencia global sobre cambio mínimo

El prompt de sistema base de Claude prescribe cambio mínimo: no refactor, no cleanup adyacente, default no comments. Para código fuente es virtud. Para entregables del profile `self-applied` (metodología, proceso, artefactos auto-aplicados) es vicio: una edición localizada puede invalidar vocabulario canónico, referencias cruzadas o invariantes que solo se manifiestan cuando otra sesión aplica el lineamiento.

**Override (solo profile `self-applied`)**: antes de cerrar una edición, Claude verifica los tres ejes:

1. **Vocabulario canónico** — ENUM de estados ([../workflow/index.md](../workflow/index.md)), glosario abstracto ([vocabulary.md](vocabulary.md)), distinción metodología/proceso (§ "Fases vs políticas" en este archivo). Términos introducidos o modificados se clasifican según el canónico, o se justifica el cambio del canónico mismo.
2. **Dependientes cross-file** — `grep` del concepto, archivo o regla editada en todo el repo. Match afectado = otro archivo depende semánticamente del término (cita la regla, importa el archivo, replica el ENUM). Los matches afectados se incluyen en el plan o se justifica por qué no aplica.
3. **Referencias** — enlaces relativos e `@imports` apuntan a contenido vigente. Renombres y movimientos arrastran actualización en consumidores.

**Exclusión** (alineada con [`../process/plan-review.md`](../process/plan-review.md) § "Cuándo aplica"): cosméticos puros — typos sin término canónico, reordenamientos dentro de una sección, fix de enlaces rotos. Para esos basta "Detectar y reportar (no fix silencioso)" más abajo.

**Cobertura**: solo `self-applied`. El resto de profiles listados en [../profiles/index.md](../profiles/index.md) sigue el cambio mínimo del prompt de sistema base; ampliaciones específicas se declaran en `profiles/<X>/conventions.md`.

**Relación con otros gates**: este principio es turno-a-turno (Claude lo aplica antes de cerrar cada edit). El subagente `qa-process-engineer` audita formalmente los tres ejes en Fase 3 (plan-review) y Fase 4 (gate de cierre) — ver `profiles/self-applied/roles.md`. "Detectar y reportar (no fix silencioso)" más abajo es reactivo (qué hacer al encontrar inconsistencia mientras editas).

## Lineamientos para editar MDs

Editar la metodología es aplicarla (ver § "Características" — Reflexiva): estos lineamientos son núcleo, no periferia de un profile. **Criterio de corte**: si eliminar una frase no cambia el comportamiento esperado del **consumidor**, no escribirla; si ya está, eliminarla. El consumidor es por defecto el agente (redacción normativa, austera); la documentación de cara al adoptante —`docs/` (excepción de § "Capas del repo y test de pertenencia") y el `README.md`— tiene como consumidor a un humano y **admite** más contexto, ejemplos y analogías moderadas (no es lineamiento que el agente aplique en el flujo). El criterio tiene además un **piso inferior**: la suficiencia (§ Claridad) — no cortar por debajo de lo que el consumidor necesita para actuar.

### Eliminar

- Prosa motivacional o justificativa ("para que el equipo...", "esto evita que...") salvo cuando el "por qué" cambia el comportamiento en edge cases.
- Instrucciones procedimentales internas que prescriben el razonamiento de Claude — conservar el output esperado o la asignación a un rol, no el procedimiento.
- Frases cliché o de relleno ("la metodología es evolutiva", "brevedad, no silencio").
- Encabezados y separadores `---` ornamentales que no abren contenido nuevo.
- Listas tipo "Cuándo leer esto" / "Para qué sirven" cuando son obvias del nombre o contexto.
- Re-explicaciones de reglas ya enunciadas en el mismo archivo.
- Ejemplos que solo re-ilustran una regla ya clara. Antes de cortar un ejemplo aplica la tría: si carga un matiz de conducta aún no enunciado, conviértelo en norma (eleva el matiz a regla); si solo re-ilustra, córtalo; si es una cita literal que Claude debe emitir, consérvala (§ Conservar).
- Redundancias entre archivos — una sola fuente de verdad, enlazar desde el resto.

### Conservar

- Comandos exactos, paths, snippets de código.
- Tablas (alta densidad de información, quick-lookup).
- Frontmatter YAML (`name`, `description`, `type`).
- Citas literales que Claude debe emitir (entre `>`).
- Enlaces relativos a otros archivos.
- El "por qué" cuando determina decisiones en edge cases (no cuando es justificación general).

### Claridad

- **Regla como contrato de output, no como narración del lector.** Redacta qué se produce o qué conducta se espera (observable en el turno), no el efecto en el lector ("el dev obtiene…", "el lector baja al detalle si lo necesita").
- **Término canónico, una sola acepción** (cara redaccional de § "Coherencia global sobre cambio mínimo" eje 1 — vocabulario canónico): no lo reuses en su sentido coloquial (p.ej. "foco", "hilo") ni prestes el marco de un concepto para nombrar otra distinción.
- **Claridad sobre compresión.** Cortar relleno no es empacar condición + acción + opciones en una etiqueta telegráfica densa. Si una frase obliga al lector a reconstruir el referente, desempácala.
- **Suficiencia: condición, acción y consecuencia.** Contrapeso de § Eliminar: una regla normativa está completa cuando enuncia su condición de aplicación, la acción/output esperado y qué se rompe si se omite. Cortar por debajo de ese piso es *escuetez falsa*, no austeridad — el "por qué" que se conserva es el que determina decisiones en edge cases (§ Conservar).

### No tocar

- Estructura de carpetas.
- Nombres de archivos (renombrar rompe imports en proyectos cliente).
- Idioma según convención: **español** en prosa (variedad de este repo: mexicano/tuteo — punto de customización, ver [`../general/communication.md`](../general/communication.md) § "Idioma"); inglés en identifiers/commits/comandos/paths y términos tecnológicos.
- Enlaces que apunten a secciones eliminadas: redirigir al archivo o sección equivalente, no dejar enlace roto.

### Declarar (nunca Patch)

- Cambiar la fuerza o el alcance normativo de una regla no es redacción: relajar o endurecer un lineamiento del baseline (recomendación ↔ obligación), o promover un ejemplo, hipótesis o prosa explicativa a regla, se declara como tal en el plan y en el fragmento del CHANGELOG, y clasifica como Minor o Major según el `CLAUDE.md` del repo § "Versionado SemVer" — nunca Patch.

### Detectar y reportar (no fix silencioso)

- Inconsistencias entre archivos (mismo concepto con valores distintos: numeración de fases, comandos, paths).
- Reglas duplicadas con variaciones leves: identificar la canónica antes de borrar las otras.
