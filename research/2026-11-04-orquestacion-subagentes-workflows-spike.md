---
propósito: decisión
descripción_propósito: Fijar qué supuestos de plataforma puede usar el orquestador de Fase 4 de Neb (ejecutores con modelo y esfuerzo por nivel, lanzados con la herramienta Agent o desde un dynamic workflow) y dar la evidencia del registro de supuestos de plataforma de Neb (`methodology/platform-assumptions.md`).
req_originador: "changes/2026-11-04-neb-mecanismos-de-plataforma.md (repo methodology)"
fecha: 2026-11-04
llms_consultados:
  - { proveedor: Claude, modelo: "pruebas empíricas en Claude Code 2.1.309 (app de escritorio, Windows): agentes en claude-sonnet-5-5 y claude-haiku-5-5; lectura de los transcripts JSONL y meta.json de cada agente", fecha_query: 2026-11-04 }
  - { proveedor: Claude, modelo: "referencia del skill workflow-authoring incluido en Claude Code 2.1.309", fecha_query: 2026-11-04 }
  - { proveedor: Claude, modelo: "claude-opus-5-5 (diseño de las pruebas y síntesis)", fecha_query: 2026-11-04 }
status: vigente
---

# Spike: modelo, esfuerzo, herramientas, anidamiento y permisos de subagentes y workflows (Claude Code 2.1.309)

> Originado por el REQ «reglas de proceso y mecanismos de plataforma» de Neb (2026-11-04), que lo cita desde su change MD. Insumo previo: un chat de investigación con fuentes de terceros que él mismo marcó como no verificadas.

## Pregunta central

¿Qué garantiza hoy Claude Code (2.1.309, app de escritorio en Windows) sobre el modelo, el esfuerzo, el prompt, las herramientas, el anidamiento y los permisos de los agentes que un orquestador de Neb lanzaría con la herramienta Agent o desde un dynamic workflow?

## Síntesis

- **Modelo y esfuerzo por llamada funcionan en las dos vías.** Con Agent, el `model` se respetó en 10 de 10 lanzamientos (4 Sonnet, 6 Haiku, más un agente anidado) y el `effort` en 6 de 6. Con `agent()` en un workflow, `model` y `effort` se respetaron en 8 de 8. El esfuerzo cambia el gasto: la misma respuesta de una palabra costó 52 tokens de salida con `low` y 1,089 con el esfuerzo heredado (`max`).
- **Sin `effort` explícito, el agente hereda el esfuerzo de la sesión**, también los agentes de plugin cuyo frontmatter no declara `effort:`.
- **El `model:` del frontmatter de un agente de plugin se respeta**: con Agent (4 de 4) y con `agent({ agentType })` (1 de 1). Un `model` por llamada lo reemplaza en ambas vías (2 de 2 con Agent, 2 de 2 en workflow).
- **`tools:` del frontmatter se respeta** con Agent y con `agentType` en workflows. Las herramientas declaradas que no existen en esta versión se descartan sin aviso. Un agente sin `tools:` recibe casi todas las herramientas de la sesión, incluidos conectores MCP con efectos externos, como enviar correo o mensajes de chat (entre 241 y 248 en las pruebas). Ninguno recibe AskUserQuestion, EnterPlanMode, ExitPlanMode ni Workflow; con Agent tampoco Cron*, DesignSync ni RemoteTrigger, y en un workflow tampoco Agent.
- **El cuerpo del agente se aplica como prompt** con Agent y con `agentType` en un workflow: el canario dio positivo en ambos, el control genérico negativo, y el texto del cuerpo aparece en el prompt de sistema de todos los lanzamientos de ese agente.
- **Anidamiento:** un subagente lanzado con Agent puede lanzar otro (profundidad 2 observada). Un agente de workflow no recibe Agent, Workflow ni AskUserQuestion: solo el script orquesta.
- **Reglas `ask` para `git commit` y `git push`:** se recargan sin reiniciar la sesión y se imponen a `allow: Bash(*)`. En modo auto alcanzan al hilo principal, a un subagente y a un agente de workflow, aunque el clasificador decida las demás llamadas de esos agentes. También alcanzaron a subagente y workflow en bypassPermissions. `Bash(git push:*)` y `PowerShell(git commit:*)` también disparan el aviso. Cada aviso bloquea al agente hasta que el dev responde, y un aviso ya mostrado sigue pendiente aunque la regla se quite después.
- **Una regla por prefijo no es una frontera:** `git -C <ruta> commit` pasó sin aviso (`source: config`, `reasonType: subcommandResults`): no empieza con `git commit`, así que la regla no lo alcanzó.
- **El agente no ve los avisos de permiso:** los cuatro agentes de las pruebas de permisos (T8, G1, T8b y G2) reportaron que no hubo aviso. La evidencia de un evento de permiso está en el transcript (`permissionDecision`), no en el reporte del agente.
- **Costo de arranque:** el primer request de un agente con casi todas las herramientas lleva entre 67 y 70 mil tokens de entrada; uno con herramientas acotadas, unos 16.5 mil (4 veces menos). Los agentes lanzados en el mismo instante no comparten caché; con unos segundos de desfase comparten el ~57 % del prefijo (38,860 tokens leídos de caché).
- **Sin verificar:** `effort:` declarado en el frontmatter, la herramienta advisor (consulta a un segundo modelo en puntos de decisión) e `isolation: 'worktree'`.

## Utilidad declarada

Insumo para (1) el registro de supuestos de plataforma de Neb y (2) el diseño del orquestador de Fase 4 (`/neb:ejecutar-plan`), que se planea en un REQ posterior.

## Preguntas del spike

Las fijó el dev al aprobar el spike; son el criterio de éxito.

| # | Pregunta | Estado |
|---|---|---|
| 1 | ¿Un agente corre con el `model` y el `effort` pedidos, con Agent, y con el `model:` de su frontmatter si es de plugin? | Respondida: sí (S1–S5). `effort:` en frontmatter, sin verificar (S6) |
| 2 | ¿Desde un workflow se respetan `model`, `effort`, el cuerpo del agente, `tools:` e `isolation`? | Respondida: sí, salvo `isolation`, que no se probó |
| 3 | ¿Qué opciones acepta `agent()`? ¿Existe `workflow()`? | Respondida desde la referencia de la versión (S12); `model`, `effort` y `agentType`, probados |
| 4 | ¿Una regla `ask` para `git commit` se impone a `Bash(*)` en modo auto, también en subagentes y workflows? | Respondida: sí en los tres casos, también en bypassPermissions; no cubre formas equivalentes como `git -C` (S15 a S17, S20, S21) |
| 5 | ¿Un subagente puede lanzar subagentes? | Respondida: sí con Agent, no en workflows (S10, S11) |
| 6 | ¿La herramienta advisor está disponible y la heredan los subagentes? | Opcional; no se probó |

## Dimensiones investigadas

| Dimensión | Hallazgo | Evidencia | Discrepancias |
|---|---|---|---|
| Modelo por llamada (Agent) | Respetado: 10 de 10 (4 Sonnet, 6 Haiku), más el anidado | `message.model` de cada respuesta y `model` en `meta.json` | El insumo citaba un fallo intermitente en Windows (issue #43869, 2.1.233); no apareció en 24 lanzamientos |
| Esfuerzo por llamada (Agent) | Respetado: 6 de 6 | Campos `effort` y `perTurnEffort`; tokens de salida 52 contra 1,089 con el mismo prompt | — |
| Herencia de esfuerzo | Sin `effort`, hereda el de la sesión (`max`) | T2, T3 ×3, T4, T5, T7, C0, el anidado y W1 | — |
| `model:` de frontmatter (plugin) | Respetado con Agent (T3 ×3, T7) y en workflow (W1) | `claude-sonnet-5-5` sin pasar `model` | — |
| Precedencia llamada > frontmatter | `model` por llamada gana con Agent (T4, C0) y en workflow (W2, C1) | `claude-haiku-5-5` en un agente que declara Sonnet | — |
| `effort:` de frontmatter | Sin verificar | Un agente de usuario creado a mitad de sesión da «Agent type not found»; no se intentó `/reload-plugins` (es un comando del usuario y aplica a agentes de plugin) | — |
| `model` y `effort` en `agent()` | Respetados: 8 de 8 (W2 a W5, G1, G2, C1, C2) | Transcripts de los tres workflows | El insumo decía que `agent()` no documentaba `effort`; la referencia de 2.1.309 lo documenta y funciona |
| `tools:` con Agent y con `agentType` | Respetado: el agente de prueba recibió `Glob, Grep, Read, WebFetch, WebSearch, TaskStop` (T7, W1, W2) | Lista de herramientas reportada por el agente | El insumo decía que `agentType` ignoraba `tools:` y otorgaba Write y Edit; no se reprodujo |
| Herramientas declaradas inexistentes | `LS`, `NotebookRead`, `TodoWrite` y `BashOutput`, declaradas en el frontmatter, no aparecen y no hay aviso | Frontmatter del agente contra la lista reportada | — |
| Cuerpo del agente con `agentType` | Aplicado con Agent (C0) y en workflow (C1); el control sin `agentType` responde que no (C2) | Canario sobre una frase literal del cuerpo; el texto del cuerpo aparece en el prompt de sistema de los lanzamientos de ese agente y de ningún agente genérico | El insumo citaba un reporte de 0 de 16 en workflows; no se reprodujo |
| Herramientas de un agente sin `tools:` | Casi todas las de la sesión, con conectores MCP: 241 (T5) a 248 (W3, W5). Ninguno recibe AskUserQuestion, EnterPlanMode, ExitPlanMode ni Workflow; con Agent tampoco Cron*, DesignSync ni RemoteTrigger; en workflow tampoco Agent, y sí ListAgents, ReportFindings, SendUserFile y FetchInboxMessage | Listas reportadas por los agentes, contra la lista de herramientas del hilo principal; W4 listó 44 porque no incluyó las diferidas | — |
| Contexto que recibe un subagente | Las instrucciones de `CLAUDE.md` y la memoria automática sí; la conversación del padre y el arranque de `SessionStart`, no (S23) | Transcripts de T8 y G1 | Contradecía a Neb (`methodology/roles-catalog.md` decía que recibe solo el `prompt`; corregido en 6.17.0) |
| Anidamiento con Agent | Posible: `spawnDepth: 2` y `parentAgentId` | `meta.json` del agente anidado | Coincide con el insumo; contradecía a Neb (`process/roles-invocation.md`, `process/plan-review.md`, `methodology/roles-catalog.md`; corregido en 6.17.0) |
| Anidamiento en workflow | Imposible: sin Agent, Workflow ni AskUserQuestion | W5 respondió «SIN-HERRAMIENTA-DE-SUBAGENTES»; listas de W1 a W5 | Coincide con el insumo |
| Sub-workflows | `workflow(nombre o {scriptPath}, args)`, un solo nivel; comparte concurrencia, contador de agentes y presupuesto | Referencia `workflow-authoring` de 2.1.309, cargada en la sesión; no está en disco ni se probó en ejecución | El insumo lo atribuía a guías de terceros |
| Recarga de definiciones | Agentes: no se recargan a mitad de sesión. Reglas de permisos: sí | «not found» del agente nuevo; `permissionDecision.ruleSource: projectSettings` tras agregar la regla | Coincide con `general/agents.md` § "Limitación de sesión" |
| Regla `ask` frente a `allow: Bash(*)` | Aviso que bloquea hasta la respuesta del dev: hilo principal en auto (P1 a P3); subagente y agente de workflow en auto (T8b, G2) y en bypassPermissions (T8, G1) | `permissionDecision: accept, source: user_temporary, ruleSource: projectSettings` en las siete pruebas; las horas de los commits del repo, y la del push de P2, coinciden con las aprobaciones | Los cuatro agentes reportaron que no hubo aviso |
| Formas equivalentes del comando | `git -C <ruta> commit` no coincide con `Bash(git commit:*)` y pasa sin aviso (P4) | `permissionDecision: accept, source: config, reasonType: subcommandResults` | — |
| Lanzar un workflow | La definición de la herramienta Workflow instruye al modelo a lanzarla solo con opt-in explícito del usuario. Es una instrucción al modelo, no un bloqueo técnico. La tarjeta de aprobación de Claude Code depende del modo de permisos y no se evaluó | Definición de la herramienta en la sesión | El insumo dice que en bypassPermissions la tarjeta no aparece |
| Costo de arranque | Entre 67 y 70 mil tokens de entrada con casi todas las herramientas; ~16.5 mil con herramientas acotadas. Lanzamientos simultáneos: 0 tokens de caché compartida. Con segundos de desfase: 38,860 tokens leídos de caché (~57 % del prefijo) | `usage` del primer request de cada agente | El insumo citaba 16 a 21 mil, cifra que solo vale para agentes acotados |

## Supuestos de plataforma (primera tabla del registro)

| # | Supuesto | Versión | Resultado | Cómo repetir la prueba |
|---|---|---|---|---|
| S1 | Agent respeta `model` por llamada | 2.1.309 | Sí | Lanzar con `model` distinto al de la sesión y leer `message.model` en `subagents/agent-*.jsonl` |
| S2 | Agent respeta `effort` por llamada | 2.1.309 | Sí | Lanzar con `effort: low` y leer `effort` / `perTurnEffort` |
| S3 | Sin `effort`, el agente hereda el esfuerzo de la sesión | 2.1.309 | Sí | Lanzar sin `effort` |
| S4 | `model:` del frontmatter de un agente de plugin se respeta | 2.1.309 | Sí (Agent y workflow) | Lanzar un agente de plugin con `model:` sin pasar `model` |
| S5 | `model` por llamada gana sobre el del frontmatter | 2.1.309 | Sí (Agent y workflow) | Lanzar ese agente con otro `model` |
| S6 | `effort:` del frontmatter se respeta | — | Sin verificar | Crear un agente con `effort:`, abrir sesión nueva (o `/reload-plugins` si es de plugin) y lanzarlo sin `effort` |
| S7 | `tools:` del frontmatter se respeta | 2.1.309 | Sí (Agent y workflow) | Pedir al agente la lista de sus herramientas |
| S8 | El cuerpo del agente forma parte de su prompt | 2.1.309 | Sí (Agent y workflow) | Canario con una frase literal del cuerpo, más un control sin `agentType` |
| S9 | Un agente sin `tools:` recibe casi todas las herramientas de la sesión, conectores MCP incluidos. No recibe AskUserQuestion (S22), EnterPlanMode, ExitPlanMode ni Workflow; con Agent tampoco Cron*, DesignSync ni RemoteTrigger; en workflow tampoco Agent (S11) | 2.1.309 | Sí | Pedir la lista de herramientas a un `general-purpose` |
| S10 | Un subagente lanzado con Agent puede lanzar subagentes | 2.1.309 | Sí | Pedirle que lance uno y leer `spawnDepth` en `meta.json` |
| S11 | Un agente de workflow no recibe Agent, Workflow ni AskUserQuestion | 2.1.309 | Sí | Pedirle la lista de herramientas |
| S12 | `agent()` acepta `model`, `effort`, `agentType`, `schema` e `isolation`; `workflow()` anida un nivel | 2.1.309 | Documentado en la referencia de la versión; `model`, `effort` y `agentType`, probados | Cargar el skill `workflow-authoring` |
| S13 | Las definiciones de agentes no se recargan a mitad de sesión | 2.1.309 | Sí (agentes de usuario) | Crear un agente y lanzarlo en la misma sesión |
| S14 | Las reglas de permisos se recargan a mitad de sesión | 2.1.309 | Sí | Agregar una regla y leer `permissionDecision.ruleSource` |
| S15 | Una regla `ask` se impone a `allow: Bash(*)` en el hilo principal (modo auto) | 2.1.309 | Sí | `git commit` en un repo desechable con la regla puesta |
| S16 | Una regla `ask` alcanza a un subagente | 2.1.309 | Sí (auto y bypassPermissions) | Igual, ejecutado por un subagente, en cada modo |
| S17 | Una regla `ask` alcanza a un agente de workflow | 2.1.309 | Sí (auto y bypassPermissions) | Igual, ejecutado por un agente de workflow, en cada modo |
| S18 | Lanzar un workflow requiere opt-in explícito del usuario | 2.1.309 | Es instrucción al modelo en la definición de la herramienta, no un bloqueo técnico | Revisar la descripción de la herramienta Workflow |
| S19 | Las herramientas declaradas en `tools:` que no existen se descartan sin aviso | 2.1.309 | Sí | Declarar una herramienta inexistente y pedir la lista |
| S20 | `Bash(git push:*)` y `PowerShell(git commit:*)` disparan el aviso igual que `Bash(git commit:*)` | 2.1.309 | Sí (hilo principal, auto) | `git push` a un remoto desechable; `git commit` con la herramienta PowerShell |
| S21 | Una regla por prefijo no alcanza formas equivalentes del comando | 2.1.309 | Sí: `git -C <ruta> commit` pasa sin aviso | Ejecutar la forma equivalente con la regla puesta y leer `permissionDecision` |
| S22 | Un subagente lanzado con Agent no recibe AskUserQuestion | 2.1.309 | Sí: no aparece en la lista completa de T5, incluidas las herramientas diferidas | Pedirle a un `general-purpose` su lista completa de herramientas |
| S23 | Un subagente —lanzado con Agent o desde un workflow— recibe las instrucciones de `CLAUDE.md` y la memoria automática (`MEMORY.md`), pero no la conversación del padre ni el arranque que inyecta `SessionStart` | 2.1.309 | Sí: en los transcripts de T8 (Agent) y G1 (workflow) están el bloque de `CLAUDE.md` y la memoria, y no están la conversación ni el arranque | Buscar en el transcript del subagente una frase del `CLAUDE.md`, una de la memoria y una del arranque |
| S24 | El hook `SessionStart` del plugin corre al iniciar la sesión principal, pero una salida grande no entra completa: el arranque de Neb (58.2 KB) llegó como un adelanto de 2 KB más la ruta del archivo con la salida completa, que Claude tuvo que leer | 2.1.309 | Parcial: el registro `hook_success` de `SessionStart` en el transcript principal marca «Output too large (58.2KB)» y guarda la salida en un archivo; los subagentes no reciben el arranque (S23) | Revisar en el transcript principal el registro `hook_success` de `SessionStart` y si su salida quedó como adelanto |
| S25 | Plan mode es el modo de permisos `plan`; al aprobar con `ExitPlanMode`, la sesión vuelve al modo previo | 2.1.309 | Sí: el campo `permissionMode` de las entradas de la sesión pasó de `auto` a `plan` y volvió a `auto`. `EnterPlanMode` se ejecutó en auto mode sin aviso al dev (`permissionDecision.source: config`); la aprobación de `ExitPlanMode` quedó como `user_temporary` con `grantScope: session`. No consta qué opción eligió el dev en la tarjeta de aprobación | Entrar en plan mode con la sesión en auto, aprobar y consultar el modo |
| S26 | La app de escritorio expone una herramienta con la que Claude consulta y cambia el modo de permisos de la sesión | 2.1.309 | Parcial: la herramienta existe y reportó el modo vigente; no se probó un cambio | Pedirle a Claude que pase a un modo menor y consultar el modo |
| S27 | Un agente de plugin lanzado desde el hilo principal sin `model` en la llamada ni en el frontmatter corre con el modelo y el esfuerzo de la sesión | 2.1.309 | Sí: 10 de 10 lanzamientos de revisores de Neb (`spawnDepth: 1`, sin `model:` ni `effort:` en su frontmatter) corrieron en el modelo y el esfuerzo de la sesión. Desde el hilo principal la sesión y el padre coinciden, así que la prueba no distingue de cuál heredan; tampoco cubre los tipos built-in | Lanzar un agente sin `model` ni `effort` y leer `message.model` y `effort` en su transcript |

## Flujos críticos validados

- `[crítico]` Modelo por llamada: validado en Agent y en workflow.
- `[crítico]` Esfuerzo por llamada: validado en Agent y en workflow.
- `[crítico]` Herramientas acotadas por `tools:`: validado en Agent y en workflow.
- `[crítico]` Regla `ask` para `git commit`: validada en el hilo principal, en un subagente y en un agente de workflow, en modo auto y en bypassPermissions. **No cubre** formas equivalentes del comando (`git -C`).

## Limitaciones

- Muestra chica: 24 lanzamientos (15 con Agent, uno de ellos anidado, y 9 en workflows), más uno fallido por diseño (T6), con 1 a 4 corridas por caso, y 4 pruebas en el hilo principal. Que el fallo intermitente del insumo no apareciera no lo descarta.
- Una sola máquina, una sola versión y una sola interfaz: 2.1.309, app de escritorio en Windows. La CLI no se midió (en esta máquina estaba en 2.1.277). Cada versión o interfaz nueva puede cambiar estos resultados: por eso cada supuesto trae cómo repetir su prueba.
- `message.model` es el modelo que Claude Code registra de la respuesta; no se comparó contra la facturación por modelo.
- Modo de permisos: P1 a P4, T8b y G2 corrieron en auto; T8 y G1, en bypassPermissions (la sesión cambió de modo durante el spike y luego volvió a auto). En auto, las demás llamadas de los subagentes las decide el clasificador (`reasonType: classifier`), pero las reglas `ask` se aplicaron antes.
- `git push` y la variante `PowerShell(...)` se probaron solo en el hilo principal. De las formas equivalentes del comando solo se probó `git -C`; otras (alias de git, variables de entorno, `sh -c`) no.
- No se probaron `effort:` en frontmatter, la herramienta advisor ni `isolation: 'worktree'`.
- S12 y los sub-workflows salen de la referencia cargada en la sesión, que no está en disco.

## Conclusión / Recomendación

- El orquestador debe fijar `model` y `effort` en cada llamada (Agent o `agent()`); no debe depender del frontmatter ni de la herencia, que por defecto da el esfuerzo de la sesión.
- Los ejecutores deben ser agentes propios con `tools:` explícito y escrito con nombres que existan en la versión: arrancan 4 veces más barato y no reciben conectores con efectos externos. Una prueba automática del frontmatter (nombres de herramientas y de campos) evita descartes silenciosos.
- La regla de no-anidamiento de Neb ya no describe la plataforma: vale para agentes de workflow, no para subagentes lanzados con Agent. Es un supuesto que pasa al registro, con su prueba.
- Las reglas `ask` para `git commit` y `git push`, en `Bash(...)` y `PowerShell(...)`, son la primera línea de defensa para que ningún ejecutor confirme cambios: alcanzan al hilo principal, a subagentes y a agentes de workflow, en auto y en bypassPermissions. No son una frontera: `git -C <ruta> commit` las esquiva. Para un bloqueo que no dependa de la forma del comando, la segunda línea sería un hook `PreToolUse` que reconozca el subcomando real de git (no probado aquí). Además, el orquestador debe ordenar a los ejecutores no hacer commit y revisar el transcript y el diff. Un ejecutor que pida un commit detiene la ejecución desatendida hasta que el dev responda; por eso el commit queda en el hilo principal después del gate.
- La auditoría de lo que hizo un ejecutor (modelo, esfuerzo, permisos) sale de su transcript y su `meta.json`, no de su reporte: los ejecutores no ven los avisos de permiso y reportaron que no hubo ninguno.
- Para el costo, lanzar a los ejecutores con unos segundos de desfase permite reusar ~57 % del prefijo en caché; lanzarlos todos en el mismo instante no.

## Anexo: pruebas ejecutadas

Todas con prompts mínimos («Responde únicamente con la palabra: OK» o una pregunta de una línea). El agente de plugin de las pruebas fue `feature-dev:code-explorer` (frontmatter con `model: sonnet` y `tools:` acotado); el canario preguntó si su prompt de sistema contiene la frase literal «expert code analyst specializing in tracing», que está en el cuerpo de ese agente. La regla `ask` se agregó temporalmente a `~/.claude/settings.json`, que en la sesión contó como `projectSettings` porque el directorio de trabajo era el home; se revirtió al terminar. Las pruebas de permisos usaron un repo git desechable.

| Prueba | Vía | Agente | Parámetros | Resultado |
|---|---|---|---|---|
| T1 ×3 | Agent | `general-purpose` | `model: sonnet`, `effort: low` | Sonnet 5.5, `low` (3/3) |
| T1d | Agent | `general-purpose` | `model: haiku`, `effort: low` | Haiku 5.5, `low` |
| T2 | Agent | `general-purpose` | `model: sonnet` | Sonnet 5.5, `max` heredado |
| T3 ×3 | Agent | `feature-dev:code-explorer` | ninguno | Sonnet 5.5 (3/3), `max` heredado |
| T4 | Agent | `feature-dev:code-explorer` | `model: haiku` | Haiku 5.5 |
| T5 | Agent | `general-purpose` | `model: haiku`; lanzar un agente anidado | El anidado corrió (profundidad 2), Haiku 5.5 |
| T6 | Agent | agente de usuario creado a mitad de sesión | — | «Agent type not found» |
| T7 | Agent | `feature-dev:code-explorer` | ninguno; listar herramientas | `Glob, Grep, Read, WebFetch, WebSearch, TaskStop` |
| C0 | Agent | `feature-dev:code-explorer` | `model: haiku`; canario | SÍ |
| T8 | Agent | `general-purpose` | `model: haiku`, `effort: low`; regla `ask` + `git commit` (bypassPermissions) | Aviso mostrado; aprobado por el dev a los ~7.6 min |
| W1 | workflow | `feature-dev:code-explorer` | ninguno; listar herramientas | Sonnet 5.5 (frontmatter), herramientas acotadas |
| W2 | workflow | `feature-dev:code-explorer` | `model: haiku`, `effort: low` | Haiku 5.5, `low`, herramientas acotadas |
| W3 | workflow | genérico | `model: haiku`, `effort: low` | Haiku 5.5, `low`, casi todas las herramientas |
| W4 | workflow | `general-purpose` | `model: sonnet`, `effort: low` | Sonnet 5.5, `low`, sin Agent |
| W5 | workflow | genérico | `model: haiku`, `effort: low`; lanzar un subagente | Sin herramienta para hacerlo |
| G1 | workflow | genérico | `model: haiku`, `effort: low`; regla `ask` + `git commit` (bypassPermissions) | Aviso mostrado; aprobado por el dev a los ~7.6 min |
| C1 | workflow | `feature-dev:code-explorer` | `model: haiku`, `effort: low`; canario | SÍ |
| C2 | workflow | genérico (control) | `model: haiku`, `effort: low`; canario | NO |
| P1 | hilo principal | — | regla `ask` + `git commit` (modo auto) | Aviso mostrado y aprobado |
| P2 | hilo principal | — | regla `ask` + `git push` a un remoto desechable (auto) | Aviso mostrado y aprobado |
| P3 | hilo principal (PowerShell) | — | regla `ask` + `git commit` (auto) | Aviso mostrado y aprobado |
| P4 | hilo principal | — | regla `ask` + `git -C <ruta> commit` (auto) | Sin aviso (`subcommandResults`): la regla por prefijo no lo alcanzó |
| T8b | Agent | `general-purpose` | `model: haiku`, `effort: low`; regla `ask` + `git commit` (auto) | Aviso mostrado; aprobado por el dev a los ~1.3 min |
| G2 | workflow | genérico | `model: haiku`, `effort: low`; regla `ask` + `git commit` (auto) | Aviso mostrado; aprobado por el dev a los ~1.3 min |
