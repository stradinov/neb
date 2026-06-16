# Refactor de `general/communication.md` — política orientada a decisiones (raíz: borrador `communication_1.md` + análisis multi-lente)

- **Fecha:** 2026-06-15
- **Profile:** self-applied
- **Versión:** 4.10.0 (minor — cambios de fuerza normativa + nuevos lineamientos; sin ruptura de imports)
- **Estado:** Implementado; commit local en `main` (sin push). Entrega final (push → propagación a clientes) y validación en uso pendientes; ediciones en pausa.

## Contexto / origen

El dev trabaja una reescritura de `general/communication.md` (borrador `~/Downloads/communication_1.md`) que reestructura la política: introduce BLUF como principio rector, gates por **propiedad de la acción**, captura de tangentes por impacto, y elimina la sección de estilo (`## Tono y forma`) delegando estilo a libertad del dev. Objetivo declarado: **diálogo rico en contexto con hilo conductor claro**, buenas prácticas de comunicación escrita **para toma de decisiones**, sin que el documento sea un **parche para limitaciones de Claude** (anti-patrón `principles.md` § Anti-patrones, L88).

Se corrió una revisión multi-lente adversarial del borrador (5 lentes: anti-patrón, comunicación-para-decisiones, consistencia-metodología, gaps de cobertura, coherencia/redacción; cada hallazgo verificado adversarialmente). Resultado: 25 hallazgos confirmados/matizados, 6 rechazados. El borrador es **mejora neta** y **no cae en el anti-patrón** (remueve los dos peores parches de la versión viva).

## Premisa del REQ

El nuevo `general/communication.md` = **borrador `communication_1.md` + correcciones Tier 1/2/3** de este plan. La reestructura del borrador se adopta (validada como mejora neta por el análisis); este REQ la integra al árbol vivo y cierra sus defectos/gaps.

## Decisión de diseño abierta (default propuesto)

- **Aviso `autoCompactEnabled` (Tier 1.1):** opción **(a) conservar el contrato inline** en `communication.md` § "Pendientes en saludos…" (recomendada — es lo que `hooks/README.md:24` ya asume; no hay SessionStart hook ejecutable; la capa correcta es comunicación). Alternativa (b): construir el hook + reapuntar README. El plan asume (a).

## Cambios

### Tier 1 — defectos / proceso (bloqueantes para mergear)

1. **Aviso `autoCompactEnabled` huérfano (delegación circular).** Borrador § Delegaciones (L87) delega el aviso a `hooks/README.md`, pero `hooks/README.md:24` lo delega de vuelta a `communication.md` y declara "no hay SessionStart hook ejecutable". Fix (opción a): reintroducir el failsafe inline en § "Pendientes en saludos…" (verificar flag; `false`/ausente/malformado → aviso inline con cita literal; silencio si `true`); en § Delegaciones dejar solo el **refresco automático del draft vía hook `PreCompact`**.
2. **Contradicción interna "1–2 oraciones".** § Principio rector (L11) "Cierre de turno: 1–2 oraciones" es norma de longitud que choca con L5 ("no se norma estilo") y L10 ("sustancia, no longitud"). Fix: quitar el cuantificador → "Cierre de turno: qué cambió y qué sigue." (sin dependientes externos — grep confirma que "1–2 oraciones" solo aparece en este archivo).
3. **Declarar fuerza normativa (proceso).** El relajamiento de reglas de estilo (concisión / emojis / "una oración por update" / "sin clichés": obligación → libertad del dev) se declara **Minor** en este MD y en `changelog.d/4.10.0.md`, nunca Patch (`principles.md` § "Declarar (nunca Patch)"). **Excluir del delta** `'"¿OK?" retirado'`: esa norma no se relaja, se refuerza (§ Elecciones "sin disyuntiva en prosa").

### Tier 2 — gaps de comunicación para decisiones (Minor; prácticas atemporales, no parches de modelo)

4. **Confianza en la conclusión (recortado tras review — NO eje nuevo).** No se crea vocabulario ni "eje de confianza". `principles.md` § "Suposiciones explícitas antes de afirmar" (L65-76) YA obliga a marcar `[asumido]`/`[dominio sin research]` en toda afirmación no verificada. Único delta: **posicionar** ese marcador ya obligatorio en la primera línea del BLUF cuando la conclusión descansa en él. Una cláusula corta en § Principio rector, enlazando principles.md (no duplica). NO se toca § Elecciones para esto (las opciones inciertas ya se rigen por L39 "verifico X primero"). → Reduce a Patch (reposiciona una obligación existente), no lineamiento nuevo.
5. **Desacuerdo / push-back (recortado tras review — bullet, NO sección).** Evita role/ceremony inflation y respeta SSOT (`principles.md` L119): un **bullet** en § "Avance del trabajo" — ante premisa falsa o instrucción que Claude evalúa como riesgosa, objeta con evidencia antes de proceder; no-bloquea → nómbrala y procede; bloquea → la objeción es una opción del menú (§ Elecciones); el dev puede override. Reusa primitivas existentes.
6. **Tangente del dev (recortado tras review — solo el contrato de output).** El "Claude atiende y reancla en una línea" se **ELIMINA**: es manejo conversacional que un modelo capaz hace sin instrucción (mismo caso que el "re-anclaje multi-turno" ya rechazado por parche-de-modelo). Se conserva SOLO el contrato verificable: una desviación del dev que se consolida como tema propio se ofrece como **menú** (§ Elecciones) — formalizarla vs. retomar el foco. Media línea en § Hilo conductor.
7. **Estructura del reporte de error/bloqueo.** Ampliar § "Reporte de error o bloqueo" con elementos de contenido (no template rígido): **impacto/estado** (qué quedó a medias, reversibilidad; noción de severidad por referencia a `incidents.md`), **qué se intentó y descartó**, y separar lo **confirmado/citable** de la **causa hipotética**.
8. **Granularidad del tradeoff por impacto.** § Elecciones (L38): "una línea de razón" como baseline; cuando la elección es un **gate de alto impacto** (propiedad ya definida en § "Qué dispara un gate"), cada opción explicita su eje de trade-off (gana / cuesta-arriesga / reversibilidad).
9. **"Rico en contexto" vs "Enfoque" — REVERTIDO tras comentario del dev.** Se intentó volver "Enfoque" posicional; el dev lo rechazó: alteraba la sustancia de la norma original ("lo que no sostiene la conclusión ni la decisión en curso sobra") y quedaba confuso. Se conserva la redacción original. Tensión rico-vs-enfoque considerada resuelta sin cambio: "rico" = el contexto que SÍ sostiene puede ser rico; "sobra" filtra el ruido.

### Tier 3 — higiene de coherencia (Patch, poda)

- L18: cortar la coletilla "Es además el camino correcto cuando no hay UI interactiva… (ver § Elecciones)" (la regla canónica de degradación sin-UI vive completa en L37; cruce circular).
- L53: cortar el eslogan "El ciclo es capturar → priorizar → re-superficiar." (conservar la 1ª oración con el puntero a § Pendientes).
- L39: reducir "Es el principio context-completeness (no asumir; verificar) aplicado al diseño de opciones." → solo "(principio context-completeness)" al cierre de la regla operativa.
- L48: anglicismo "on-topic" → "dentro del foco". (Término ancla canónico = "foco", ya definido en L46; "hilo conductor" se conserva en el título por resonar con el objetivo del dev.)
- L61: recortar el glose "(numeración markdown muerta que no resuelve; …)" — vive en el canónico `tooling/pendings.md` § "Cómo citar un pendiente" ya enlazado; conservar la regla operativa + enlace.
- L19: precisar que "qué sigue" distinga el siguiente paso de Claude del accionable pendiente del dev (validar/decidir/input) cuando aplique.

### Cross-references a reapuntar (eje 3 — `principles.md` § Coherencia global; el borrador elimina `## Tono y forma` y `## Hilo de la metodología`)

| Archivo:línea | Cita actual | Reapuntar a |
|---|---|---|
| `general/index.md:11` | descriptor "tono, idioma, hilo de la metodología" | Reescribir descriptor (no es ancla §, es texto que el grep de validación caza) → p.ej. "BLUF, idioma, hilo conductor, handoff". **Omitido en v1 del plan; cazado por QA review (mi grep era case-sensitive).** |
| `hooks/README.md:24` | communication.md "Hilo de la metodología" | § "Pendientes en saludos y conversación trivial" — **condicionado a Tier 1.1 opción (a)**: si no se reintroduce el failsafe inline ahí, el reapunte no resuelve y la delegación circular persiste. |
| `process/execution.md:65` | §"Hilo de la metodología" | § "Handoff de sesión" |
| `workflow/pendings.md:61` | §"Hilo de la metodología" | § "Handoff de sesión" |
| `general/onboarding.md:19` | § "Tono y forma" | § "Elecciones: menú de selección" |
| `skills/wakeup/SKILL.md:41` | § "Tono y forma" | § "Elecciones: menú de selección" |
| `process/phase-transitions.md:7` | § "Tono y forma" (tono prosa vs estructura) | **Eliminar la remisión circular**: el trigger de formalización es canónico en la propia `phase-transitions.md` (el borrador L86 ya apunta communication→phase-transitions). Reescribir L7 sin remitir a la sección eliminada. NO § "Principio rector" (corrección del QA review; precedente: incidente 3.10.1). |

> Referencias en `changelog.d/*` y `CHANGELOG.md` son históricas (estado pasado) — no se tocan.

## Declaraciones de fuerza normativa (Minor)

- Relajamiento de reglas de estilo a libertad del dev (cambio #3).
- Nuevos lineamientos: desacuerdo (#5, bullet), contrato de menú para tangente consolidada del dev (#6, recortado), estructura de reporte de bloqueo (#7), granularidad de tradeoff en gates de alto impacto (#8).
- #4 ya NO es lineamiento nuevo (reposiciona una obligación existente de principles.md) → Patch dentro del REQ.
- **Transición de fase/paso sin gate no se consulta** (elevado del ejemplo cortado): resuelve la asimetría que 3.9.0 (b) / 3.10.0 habían diferido ("¿Procedo a Fase X?"). Cambio de comportamiento del baseline → declarado.

## Plan de validación

- Coherencia estática: grep post-edit **case-insensitive** de "hilo de la metodología" / "tono y forma" → 0 referencias vivas rotas (incluir `general/index.md`; las únicas restantes deben ser históricas en `changelog.d/*` y `CHANGELOG.md`).
- Las **7** referencias reapuntadas (incl. `index.md`) resuelven a secciones existentes del nuevo `communication.md`, o quedan sin remisión a sección eliminada (`phase-transitions.md:7`).
- `principles.md` § Coherencia global (3 ejes) verificado antes de cerrar.
- `assemble-changelog.py` corrido tras crear `changelog.d/4.10.0.md`; `VERSION` → 4.10.0.
- Dogfooding: la propia sesión aplica el lineamiento (ambiente único).

## Pendientes / follow-ups

- **PD-194** (fuera de scope, preexistente): drift `workflow/pendings.md:59` apunta "Procedimiento completo" a `workflow/metrics.md` vs `process/execution.md:47`. Reconciliar aparte.
- Rechazados del análisis (no accionar): re-anclaje multi-turno (sería parche de modelo), handoff bien delegado, falsos positivos de redundancia "nombra la suposición" / "sin disyuntiva".

## Notas de redacción (retroalimentación Fase 9)

Errores de redacción de Claude detectados en el diálogo de ajuste, inferidos como patrón (para mejora, no como bitácora de incidentes):

1. **Vocabulario interno prestado fuera de su dominio.** Reusé el lenguaje del anti-patrón ("regula qué producir, no cómo redactarlo") para una distinción distinta (fondo vs forma/estilo) → frase críptica. Lección: no arrastrar la jerga de un concepto a otro contexto; nombrar la distinción real en términos llanos (quedó "norma el fondo, no la forma"). *(Origen: comentario del dev sobre L5.)*
2. **Regla redactada como descripción del lector/escenario, no como contrato de output.** "El dev obtiene el fondo en la primera línea y baja al detalle solo si lo necesita" narra la conducta del lector (suena a título de caso de uso) en vez de instruir qué produce Claude. Lección: redactar lineamientos como output accionable ("el fondo abre, conciso; el detalle después"), no como narración del efecto en el lector. Corolario: la versión narrativa además repetía la idea ya dicha en la 1ª oración (tres restatements). *(Origen: comentario del dev sobre el bullet BLUF.)*
3. **Prosa de justificación que no cambia comportamiento ni estructura.** "Así un diálogo rico en contexto no degenera en ruido" reformula el objetivo: no es norma de fondo ni da estructura a la respuesta → no aporta en la práctica. Lección: aplicar el criterio de corte (principles.md L108) sin auto-justificar; una frase que solo reafirma el porqué/objetivo se elimina (el objetivo "rico en contexto" ya queda operativo en § Enfoque). Notable: el análisis multi-lente previo la había **defendido como "load-bearing"** — sesgo de sobre-retención de rationale. *(Origen: comentario del dev sobre la frase de cierre del BLUF.)*
7. **Etiqueta comprimida + cláusula densa = poco clara.** Abrí con "Recíproco:" (fuerza al lector a reconstruir respecto a qué) seguido de una cláusula que empaqueta condición + acción + opciones ("una desviación del dev que se consolida como tema propio se ofrece como menú — formalizarla vs. retomar el foco"). Lección: hacer explícita la relación ("el caso simétrico, cuando la desviación la sostiene el dev") en vez de una etiqueta telegráfica, y desempacar condición→acción→opciones. *(Origen: comentario del dev sobre la frase "Recíproco…".)*
4. **Reformular una norma existente le alteró la sustancia + reincidencia.** Al "operativizar" § Enfoque cambié su sustancia (de "lo que no sostiene la conclusión sobra" → "no suprimirla, solo reposiciónala"), contradiciendo la regla original, y quedó confuso. Peor: reintroduje "donde el dev baja solo si lo necesita" — el mismo patrón de descripción-del-lector ya anotado en #2. Lección: al reformular una regla existente, preservar su sustancia operativa y contrastar el borrador contra los errores ya anotados (no reincidir). Doble origen: un hallazgo del análisis (`rico-vs-enfoque`, matizado) me indujo a tocar una norma que no necesitaba cambio. *(Origen: comentario del dev sobre § Enfoque.)*
5. **Colisión de término: "hilo" idiomático vs "hilo conductor" canónico.** Dejé "Claude lleva el hilo" (sentido: lleva la iniciativa) conviviendo con "hilo conductor" (el ancla/foco) → confundibles. El análisis ya lo había marcado (`inconsistencia-terminologica-hilo-foco`) y yo opté por conservarlo como idiomático; la colisión se materializó al introducir "hilo conductor" en otros bullets. Lección: si una palabra es término canónico en el doc, no reusarla con otro sentido aunque sea idiomática. Corregido → "lleva la iniciativa". *(Origen: comentario del dev sobre L15.)* Reincidencia: en "Cierre de turno" escribí "con el foco en el asunto de fondo", reusando "foco" en sentido coloquial ("poner el foco en") que choca con el "foco" canónico (ancla); reformulado quitándolo. Regla: el término canónico no se reusa en su acepción coloquial.
6. **No apliqué el criterio de corte a ejemplos ilustrativos.** Conservé del borrador `> "Terminé la implementación, sigo con la validación." — avance sin gate…`, que solo ilustra (la norma ya está en el bullet "Ejecuta y reporta"). Lección/distinción (criterio de **tres vías** para cada `>`): **convertir a norma** si el ejemplo carga un matiz de conducta no enunciado (elevar el matiz a regla, no borrarlo); **cortar** si solo re-ilustra una norma ya escrita; **conservar** si es cita literal que Claude debe emitir (principles.md § Conservar). El binario "cortar/conservar" era pobre: un ejemplo puede ser fuente de una norma. Debí clasificar cada `>` por esta tría al adoptar el borrador. Refuerzo posterior: corté L21 ("Terminé la implementación…") juzgándola pura ilustración, pero cargaba el matiz "transición de fase sin gate no se consulta"; el dev pidió convertirla. Sesgo a corregir: ante la duda cortar/convertir, default a convertir si el ejemplo nombra un modo de fallo concreto. *(Origen: comentario del dev sobre el ejemplo de avance sin gate.)*
