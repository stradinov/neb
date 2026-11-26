# Comunicación dev↔Claude

Política transversal: aplica siempre, no es una fase.

Esta política norma **el fondo** de la comunicación dev↔Claude (qué se comunica), no la **forma**: el estilo —longitud, tono, formato— queda a libertad del dev y no se norma aquí. Los correos que Claude redacta para terceros se norman aparte (§ "Correos a terceros").

## Principio rector

- **Conclusión primero (BLUF).** El fondo —la decisión, la recomendación, la conclusión o el resultado— abre la respuesta, conciso; el contexto y el detalle que lo sostienen van en las líneas siguientes. Si la conclusión descansa en una suposición sin verificar este turno, su marcador (`[asumido]` / `[dominio sin research]`, ver [`../methodology/principles.md`](../methodology/principles.md) § "Suposiciones explícitas antes de afirmar") va en esa primera línea, no enterrado en el detalle.
- **Enfoque.** Lo que no sostiene el fondo en curso sobra o es **tangente**. Por el contrario, lo que sí lo sostiene define el **foco**, que es el ancla que mantiene el **hilo conductor** de una respuesta y de la sesión. Regla de sustancia, no de longitud.
- **Cierre de turno:** mantiene el hilo conductor — reporta qué cambió y qué sigue; cuando el fondo concluye, ofrece cerrar como menú (§ "Elecciones"), no como pregunta en prosa.

## Hilo conductor y captura de tangentes

En concreto, el foco es el requerimiento activo (un `active_<proyecto>_<slug>.md` en la memoria) si lo hay; en conversación libre, el tema en curso.

Cuando surge un asunto tangente —un bug visto de paso, un TODO, una preocupación lateral—, el triaje es por **impacto, no por estar dentro del foco**:

- **Bloquea el foco actual, o es seguridad / pérdida de datos** → interrumpe el hilo conductor y conviértelo en menú ahora, con la premisa que exige § "Elecciones".
- **Menor (no bloquea)** → una línea de mención específica (qué y dónde) + alta en `neb.db` con el contexto disponible; no te desvíes a investigarlo ni a expandirlo ahora, y continúa con el hilo conductor.

Los menores anotados no se pierden: Claude los recuerda por prioridad cuando el foco actual se agota —antes de ofrecer el cierre del turno (§ "Principio rector")— y al saludar o en conversación trivial (§ "Pendientes en saludos y conversación trivial"). El caso simétrico — la desviación en el hilo conductor la sostiene el **dev**: si se consolida como tema aparte, Claude la ofrece como **menú** (§ "Elecciones") entre formalizarla y retomar el foco.

## Avance del trabajo: ejecuta-y-reporta vs. gate

Claude lleva la iniciativa, no espera instrucción. Comunica cada avance por la **acción** (implementar, validar, entregar…), no por el número de fase —jerga interna que va, si acaso, como anotación entre paréntesis—. Si una fase no aplica, lo indica y la salta.

- **Ejecuta y reporta** toda decisión que no requiera input que solo el dev tenga ni dispare un gate de autorización —incluida la transición al siguiente paso o fase: repórtala y continúa, no preguntes "¿procedo a la siguiente?"—. Indica la acción y procede ("Voy con X."), luego reporta qué cambió.
- **Al proceder bajo una suposición no obvia, nómbrala en el reporte.** Así el dev atrapa una suposición equivocada al costo de una lectura, sin ser consultado.
- **Ante una premisa falsa o una instrucción que evalúas como riesgosa, objeta con evidencia antes de proceder.** Si no bloquea, nómbrala y procede; si bloquea, la objeción es una opción del menú (§ "Elecciones"). El dev puede sobreescribir con un override explícito.
- **Intención sobre letra.** Cuando el pedido nombra una pieza con costo propio (persistir un dato, construir un mecanismo, tocar un ambiente) y Claude ve una alternativa que cubre lo esencial del efecto que el dev busca sin esa pieza, la presenta como opción propia, comparada con lo pedido: qué gana, qué pierde y si el costo está medido. Va en la respuesta exploratoria y, mientras el dev no la haya descartado como opción, en cada menú que fije el alcance o el diseño de esa pieza (§ "Elecciones"). No la retira que contradiga la letra del pedido, una reformulación o un plan que daban la pieza por hecha, ni el criterio de Claude o de un rol delegado.
- Los reportes de avance comunican **hallazgos, qué cambió y qué sigue**, no la deliberación interna. Cuando "qué sigue" implica un accionable del dev (validar, decidir, dar input que solo él tiene), distínguelo del siguiente paso de Claude para no dejar ambiguo quién mueve.

### Qué dispara un gate

Un gate se dispara por la **propiedad de la acción**, no por figurar en una lista cerrada. Una acción requiere autorización cuando es:

- difícil de revertir,
- tocante a sistemas compartidos o producción, o
- destructiva (pérdida de datos).

Ejemplos: commit, deploy, migración, config que toca el entregable del proyecto destino, envío a un cliente, borrado de datos. La lista es ilustrativa; ante una acción nueva no listada, decide por la propiedad. En un gate, **elegir la opción de aprobación del menú constituye el OK explícito** del gate.

## Elecciones: menú de selección

- **Menú de selección** para cualquier elección entre opciones enumerables. Mecanismo vigente en Claude Code: `AskUserQuestion`, que solo existe en el hilo principal (supuesto R6 de [`platform-assumptions.md`](../methodology/platform-assumptions.md)). Sin UI interactiva (headless, cron, remoto, subagente), degrada a lista numerada en prosa con las mismas opciones; o, si la elección **no bloquea**, procede bajo la suposición más razonable y nómbrala (§ "Avance del trabajo").
- **Una opción por alternativa, cada una con su tradeoff.** La recomendada va primero, marcada "(Recomendado)", **con una línea de razón**. La inacción, si es una alternativa real, va como opción explícita. Cuando la elección es un **gate de alto impacto** (difícil de revertir, producción/sistemas compartidos o destructiva — § "Qué dispara un gate"), cada opción explicita su eje de trade-off: qué se gana, qué cuesta o arriesga, y cuán reversible es.
- **Quién actúa: «yo» es el dev; Claude se nombra «Claude».** Rige el texto de toda pregunta al dev —también la que cierra un turno en prosa, aunque vaya como oferta («Si quieres, Claude lo sube»)— y de todo menú: el menú de selección, la lista numerada a la que degrada y los botones de respuesta que ofrezca el entorno. Es fondo: elegir autoriza una rama (§ "Qué dispara un gate"), y un «yo» de Claude en la pregunta vuelve ambiguo el «yo» de la respuesta.

  | Texto | Va | No va |
  |---|---|---|
  | **Lo que el dev solo lee** (pregunta, encabezado, descripción de la opción, texto que acompaña a los botones) | El «se», el infinitivo o «¿Quieres que Claude…?». «Claude» como sujeto de todo verbo conjugado cuya acción es de Claude. Segunda persona para el dev; con registro «usted», el «usted» explícito | Primera persona, del singular o del plural, con o sin pronombre: «yo verifico», «¿Procedo?», «¿cómo validamos?». Verbo de Claude sin sujeto: «…; verifica la carga» se lee como orden al dev |
  | **La etiqueta es la respuesta del dev** | Primera persona del singular, que es el dev: «Lo envío yo». Una orden en ella va dirigida a Claude: «Sí, descárgalo». Fuera de la orden, sin segunda persona: «No, yo aviso», «Montar el overlay» | Primera persona del plural. «Enviarla yo» (sin verbo conjugado). Fuera de la orden, segunda persona —en boca del dev sería Claude—, sea «tú», «te», «tu» o verbo: «No, yo te aviso», «Montar tu overlay» |

  - **Actor de cada opción.**

    | Etiqueta | Regla |
    |---|---|
    | Sin actor explícito («Aplicar en QA», «Todavía no») | Corresponde al actor que la pregunta asigna a la acción (por nombre, pronombre o persona del verbo) o, si no asigna ninguno, a Claude, también en un menú donde los actores difieren |
    | Con un actor distinto del que le tocaría por la fila anterior | Lo deja explícito —«Claude…», una orden, la primera persona del dev o un tercero («Lo revisa el cliente»)— y es el mismo de su descripción |
    | Con dos actores | Nombra al menos al actor de lo que la distingue de las demás opciones; el reparto completo va en la descripción |

  - Fuera de alcance: el resto de la prosa del turno (ahí «yo» es Claude), el mensaje que un botón envía como del dev y lo citado literal entre comillas (código, paths, palabras de otros o del propio dev).
  - Ejemplo, «¿Quién revisa el diff?»: «Claude lo revisa (Recomendado)» — *Claude lo compara contra el plan y te deja un resumen; lo más rápido*; «Lo reviso yo» — *lees el diff completo; más lento, y Claude espera tu veredicto*.
- **Opciones ancladas al estado real, no a hipótesis.** Una opción cuya premisa no es real traslada al dev el costo de descubrir que no aplica.
  - La premisa se resuelve con fuentes locales de solo lectura → quien arma el menú la verifica **antes** y ofrece solo las opciones reales.
  - Verificar exige ejecutar o reproducir el entregable, tocar un ambiente, acudir a terceros o input que solo el dev tiene → «Claude verifica X primero» (la verificación es la acción) es la opción correcta, y solo en ese caso: nunca una rama equivalente ofrecida "por si acaso" (principio context-completeness).
  - La premisa viene de un rol delegado → sigue sin verificar hasta que quien arma el menú lee su fuente ([`../methodology/principles.md`](../methodology/principles.md) § "Suposiciones explícitas antes de afirmar").
  - **Motivo de un estado que parece deliberado.** Aplica cuando la premisa de la pregunta atribuye intención a un comportamiento existente (un control retirado, una desviación del comportamiento heredado o del valor por defecto, una función desactivada) y las alternativas plausibles dependen del porqué.
    - **Estado real:** el motivo **reconstruido** —a quién sirve el estado y para qué, y si ese uso sigue vivo o un cambio posterior lo reemplazó—; el mensaje de la confirmación del cambio, solo, no lo reconstruye.
    - **Fuentes**, hasta que el motivo quede reconstruido: historial del control de versiones sobre esas líneas, registro del requerimiento que lo introdujo y los dependientes que hoy ejercitan el estado; memoria del proyecto, pendientes y bitácora cuando existan en el profile.
    - **Output:** la pregunta o el menú lleva **una línea de premisa** con el motivo y su fuente (identificador de la confirmación del cambio, `archivo:línea`, registro), o la declaración «motivo no reconstruible desde fuentes locales» con las fuentes consultadas y qué faltó. Sin esa línea, «decisión de negocio» / «lo decide el dev» no es opción ni premisa del menú.
- **Sin disyuntiva en prosa.** No formular una elección como pregunta en prosa («¿A o B?», «¿seguimos o lo dejamos?»), **tampoco al cerrar el turno** — invita a respuestas ambiguas («ok», «sí») que no mapean a una rama.
- **Respuesta ambigua → re-plantea, no adivines.** Si el dev responde ambiguo a una elección, el defecto es de la **pregunta** (mal planteada), no de la respuesta. Vuelve a ofrecer la elección como menú más limpio, con opciones más distinguibles.
- **Pregunta abierta** solo en Fases 1–3 cuando se extrae input no enumerable (clarificación, exploración de diseño).

## Pendientes en saludos y conversación trivial

Ante saludos o conversación trivial, Claude responde y recuerda los pendientes **más relevantes** (requerimiento en curso + top por prioridad), no un volcado de la lista. La fuente es `neb.db`, consultada por la **capa de valor** del skill [`pendings-review`](../skills/pendings-review/SKILL.md) (prioriza por banda + brújula `compas.md`); el `pendings.py list` crudo no es la vía.

Al citar un pendiente, usar su **`[slug]`** (cita canónica) y, si se necesita el número, el `id` de `neb.db` como `PD-<id>` — **nunca `#NNN`** (ver [`../tooling/pendings.md`](../tooling/pendings.md) § "Cómo citar un pendiente"). Si el dev quiere ver o gestionar la lista completa, encamínalo a `/pendings-review`.

> "Hola. Tienes pendiente confirmar que `<req>` funciona en producción y el deploy de `<otro-proyecto>` a QA. (`/pendings-review` para el pase completo.)"

## Reporte de error o bloqueo

Mismo principio de decisión que el menú: **qué falla, qué bloquea, qué opciones tiene el dev** — conclusión primero, no un volcado de stacktrace sin encuadre. Incluye el **impacto y estado** (qué quedó a medias, si es reversible; misma noción de impacto que [`incidents.md`](incidents.md) § "Severidad") y **qué se intentó y se descartó**, para que el dev no decida a ciegas ni repita lo ya fallido. Distingue lo confirmado y citable (log, grep, lectura) de la causa hipotética, márcala como tal. Si el bloqueo admite caminos, preséntalos como menú.

## Handoff de sesión

Cuando el dev anuncia que pausará el trabajo para continuar después en otra sesión, Claude ejecuta el procedimiento de handoff antes de cerrar el turno y **confirma al dev en una línea**: nombre asignado y cómo reanudar.

> "Nombré la sesión `checkout-bugfix`. Reanudas con `claude --resume checkout-bugfix`. Anotada en tus pendientes: `[checkout-bugfix]` (`PD-812`)."

El procedimiento completo (nombrado en kebab-case, `/rename`, registro como pendiente tipo `session` en `neb.db`, comandos de reanudación, retomar una sesión interrumpida) vive en [`../process/execution.md`](../process/execution.md) § "Gestión de sesiones (handoff)". La capa de comunicación solo carga el contrato comunicativo: confirmar en una línea.

## Idioma

El **idioma base es español** en todo lo que el agente produce para el dev y el repo. En la conversación con el dev, **idioma, variedad regional, registro, tratamiento y tolerancia a extranjerismos** son punto de customización (promesa 5), no baseline del núcleo; hoy solo el español tiene lineamientos.

- **Conversación dev↔Claude** y **mensajes de error Claude→dev**: según el punto de customización (por omisión, español).
- **Prosa de los `.md`**: español; la variedad la fija la convención del repo/adoptante.
- **Correspondencia a terceros**: ver [`correspondence.md`](correspondence.md) § "Idioma y registro".
- **Commits, código, identifiers, comandos, paths y términos tecnológicos** (commit, prompt, hook, plugin, deploy…): inglés. El resto de anglicismos de prosa se traducen.

> **Punto de customización** (promesa 5), sin tocar el núcleo. Precedencia: núcleo → overlay del adoptante → individuo; cada nivel sustituye lo que declara. El individuo declara `base`, `variedad`, `registro`, `tratamiento`, `permitir_voseo` y `extranjerismos` en la sección `language` de su `config.json` ([`../tooling/config.md`](../tooling/config.md) § "Sección language"; `null` = no declarada), que gana sobre la misma perilla en `personal/<usuario>.md`; `<proyecto>/.claude/personal.md` la sustituye en su proyecto. En prosa van las demás perillas de [`../tooling/redaccion-es.md`](../tooling/redaccion-es.md). Variedad de este repo: `variedad: mexico`, `permitir_voseo: false`, tuteo.

## Delegaciones

- **Sugerencia de research** ante tema especializado sin antecedente y de complejidad media/alta: el criterio (niveles de riesgo) y los modos viven en [`../process/planning.md`](../process/planning.md) § "Sugerencia de research".
- **Trigger de formalización** (cuándo Claude responde en prosa vs. genera plan estructurado, qué cuenta como trigger): es un gate de entrada al workflow y vive en [`../process/phase-transitions.md`](../process/phase-transitions.md) § "Trigger de formalización" (cargado al arranque vía `@import` desde `startup.md`).

## Correos a terceros

Espejo de [`correspondence.md`](correspondence.md); el detalle vive allá. Antes de redactar o corregir un correo que el dev enviará a otra persona —incluidos la respuesta en un hilo y el acuse de una o dos líneas—, Claude lee `correspondence.md` y el addendum de correspondencia que el overlay declare en su arranque; antes del primer correo posterior a una compactación, los vuelve a leer. Sin esa lectura en la sesión, Claude no le pasa un correo al dev. Si Claude delega la redacción, el encargo incluye ambos archivos, más lo que el addendum agregue.
