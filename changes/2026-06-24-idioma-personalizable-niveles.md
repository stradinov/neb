# Idioma personalizable por niveles (individuo / adoptante / núcleo)

**Estado:** Implementado y validado (Fase 4) — commit pendiente
**Fecha cierre:** 2026-06-24
**Fecha inicio:** 2026-06-24
**Complejidad estimada:** media
**Riesgo de regresión:** bajo  <!-- toca prosa normativa de 3-4 archivos; no rompe imports; no toca código -->

## Contexto

La § "Idioma" de [`general/communication.md`](../general/communication.md) fija "español mexicano (tuteo)" como baseline duro del núcleo, fusionando en una sola línea dos ámbitos de naturaleza opuesta: la **conversación dev↔Claude** (canal efímero, personalizable) y la **prosa de los `.md`** (artefacto compartido versionado, de equipo). La [promesa 5 (Personalizable)](../methodology/promises.md) ya lista "interacción con Claude" como punto de personalización, pero —a diferencia de `coding-standards.md`, `git-conventions.md` y `done-criteria.md`, que tienen su bloque `> Punto de customización:`— `communication.md` **no lo materializa**. Gap promesa↔materialización.

**Antecedente que acota el diseño:** el REQ [`2026-06-22-idioma-tuteo-anglicismos.md`](2026-06-22-idioma-tuteo-anglicismos.md) (v5.6.0, 2 rondas de plan-review) decidió deliberadamente (a) política de idioma en `communication.md` como **sede única** ("no una 3ª fuente"); (b) barrido del repo a mexicano/tuteo. Este REQ **respeta la sede única**: no dispersa la política, la **estratifica dentro de communication.md**.

**Decisión del dev (2026-06-24):**
- Usuario objetivo: **ambos** — individuo (vía `personal/<usuario>.md`) y adoptante (vía overlay).
- Default del núcleo: **idioma español, sin especificar variedad ni registro**. La variedad (mexicano), el registro (tuteo) y la política de voseo dejan de ser baseline del núcleo y pasan a ser **customización**.

## Modelo de diseño

Tres niveles de override (todos preexistentes en Neb): núcleo/equipo (`general/`) · adoptante (overlay / `profiles/<profile>/`) · individuo (`personal/<usuario>.md` + por-proyecto `<proyecto>/.claude/personal.md`).

La § Idioma se descompone en sub-reglas con dueño explícito:

| Sub-regla | Baseline del núcleo | Customizable por |
|---|---|---|
| Conversación dev↔Claude | idioma = español | variedad/registro: individuo + adoptante |
| Errores Claude→dev | idioma = español | sigue a conversación |
| Prosa de los `.md` | idioma = español | variedad: adoptante (convención del repo) |
| Código / identifiers / commits / términos tecnológicos | inglés | (equipo / convención de industria) |

## Decisión de diseño abierta (para plan-review)

**D1 — ¿Dónde vive el valor concreto de variedad de este repo (`mexico`/tuteo/no-voseo)?**
- **(i) Sede única estratificada (recomendada):** se queda en `communication.md`, pero reetiquetado: baseline núcleo = español; el valor `mexico`/tuteo se declara ahí mismo como *valor de customización de este repo, sobreescribible*. Respeta la sede única del REQ del 22-jun; una sola fuente. Costo: convive baseline-núcleo y valor-adoptante en `general/` (impureza de capa menor, auto-documentada y natural en self-applied).
- **(ii) Pureza de capa:** núcleo `communication.md` = español sin variedad; valor `mexico` baja a `CLAUDE.md` del repo (capa adoptante). Más fiel a la promesa 2 (agnóstica), pero reintroduce parte de la dispersión que el 22-jun evitó.

Recomiendo **(i)**. El plan abajo asume (i).

## Alcance

### Entra

1. **[`methodology/personal-vs-team.md`](../methodology/personal-vs-team.md)** — distinguir **regla de proceso** (tiene eje de severidad → estrecha/agrega/nunca relaja) de **punto de customización** (sin eje de severidad → el override sustituye). Se usa el término canónico ya vigente "punto de customización" (`principles.md` lo enumera); no se acuña término nuevo. Corregir "Preferencias de comunicación **más estrictas**" (l. 51) → preferencias sustituibles. Sumar `communication.md § Idioma` a los puntos de customización preconfigurados (l. 11).

   Redacción propuesta (bloque nuevo tras "Regla central"):
   > ## Puntos de customización vs reglas de proceso
   >
   > | Tipo | Override personal | Ejemplos |
   > |---|---|---|
   > | **Regla de proceso** (tiene eje de severidad) | Estrecha o agrega, **nunca relaja** | gates, plan de pruebas, firma de commits, revisión |
   > | **Punto de customización** (sin eje de severidad) | **Sustituye** el default | idioma/variedad/registro, formato de salida, alias |
   >
   > La "Regla central" gobierna las **reglas de proceso**. Un **punto de customización** no tiene baseline de severidad que relajar: el override lo reemplaza. Por eso `permitir_voseo: true` en un `personal.md` es legítimo aunque el default del equipo sea no-voseo — sustituye una preferencia, no relaja un control.

2. **[`general/communication.md` § Idioma](../general/communication.md)** — reestructurar dentro de la sede única (D1-i):

   Redacción propuesta:
   > ## Idioma
   >
   > El **idioma base es español** en todo lo que el agente produce para el dev y el repo. La **variedad regional, el registro y la tolerancia a extranjerismos** son punto de customización, no baseline del núcleo.
   >
   > - **Conversación dev↔Claude** y **errores Claude→dev**: español; variedad y registro según el punto de customización.
   > - **Prosa de los `.md`**: español; la variedad la fija la convención del repo/adoptante.
   > - **Commits, código, identifiers, comandos, paths y términos tecnológicos** (commit, prompt, hook, plugin, deploy…): inglés. El resto de anglicismos de prosa se traducen.
   >
   > > **Punto de customización** (promesa 5): variedad regional, registro y extranjerismos se ajustan sin tocar el núcleo. Un **individuo** los declara en `personal/<usuario>.md` § "Preferencias de comunicación" (o, solo para un proyecto, en `<proyecto>/.claude/personal.md`); un **adoptante**, en su overlay. Esquema y perillas (variedad, `permitir_voseo`, registro, extranjerismos): [`../tooling/redaccion-es.md`](../tooling/redaccion-es.md). Variedad de este repo: `variedad: mexico`, `permitir_voseo: false`, tuteo.

3. **[`templates/personal.md.template`](../templates/personal.md.template)** — § "Preferencias de comunicación": ejemplo concreto.
   > ```
   > <!-- Idioma/variedad/registro: SUSTITUYEN el default del equipo (ver tooling/redaccion-es.md).
   >      ej: variedad: rioplatense, permitir_voseo: true, registro: informal
   >      Formato de salida: "respuestas <100 palabras", "tablas con 5+ ítems" -->
   > ```

4. **[`methodology/principles.md` l.141 (§ No tocar)](../methodology/principles.md)** — reblandecer la línea (cambio de fuerza normativa de una invariante de § "No tocar" → se **declara**, nunca Patch). Texto propuesto:
   > - Idioma según convención: **español** en prosa (variedad de este repo: mexicano/tuteo — punto de customización, ver [`../general/communication.md`](../general/communication.md) § "Idioma"); inglés en identifiers/commits/comandos/paths y términos tecnológicos.

5. **[`tooling/revision-editorial-externa.md`](../tooling/revision-editorial-externa.md)** (l.6, l.17) — reencuadrar las 2 ocurrencias de "español mexicano (tuteo)": de regla universal del núcleo a **variedad de este repo** (punto de customización). El agente externo sigue corrigiendo la prosa a mexicano/tuteo porque es la variedad efectiva del repo; cambia el encuadre, no el valor. *(Hallazgo plan-review: archivo del núcleo/tooling que quedaría inconsistente.)*

6. **[`methodology/promises.md` l.11](../methodology/promises.md)** — añadir `communication.md` a la columna "Dónde se materializa" de la promesa 5 (hoy lista personal-vs-team/coding-standards/git-conventions/done-criteria, no communication.md). *(Hallazgo plan-review: materialización incompleta.)*

### No entra

- Mover la política fuera de `communication.md` (respeta sede única del 22-jun) — salvo que D1 cierre en (ii).
- Tocar la prosa ya barrida a mexicano (sigue siendo la variedad de este repo).
- Cambiar el inglés de código/identifiers/commits/términos.
- Anglicismos canónicos y de dominio — intactos.

## Plan de pruebas

| # | Verificación | Umbral binario | Resultado |
|---|---|---|---|
| 1 | communication.md § Idioma separa idioma base de variedad/registro + bloque de customización | grep "Punto de customización" en `general/communication.md` ≥1 y mención "idioma base" presente | ✅ |
| 2 | personal-vs-team.md distingue regla de proceso vs punto de customización; voseo deja de contradecir "nunca relaja" | tabla "Regla de proceso / Punto de customización" presente; l.51 ya no dice "más estrictas" | ✅ |
| 3 | Sede única intacta | "español mexicano" en el núcleo solo en communication.md (valor de repo) + principles.md (enlazado); sin 3ª fuente normativa nueva | ✅ |
| 4 | revision-editorial-externa.md reencuadrado | l.6/l.17 presentan mexicano/tuteo como variedad del repo, no como regla universal | ✅ |
| 5 | promises.md promesa 5 materializa communication.md | grep "communication.md" en la fila de promesa 5 = presente | ✅ |
| 6 | personal.md.template da ejemplo sustituible | grep "variedad" en `templates/personal.md.template` = presente | ✅ |
| 7 | Versionado | `bump-version.sh` 5.9.3→5.10.0 (sincroniza VERSION+plugin.json); `changelog.d/5.10.0.md` creado; `assemble-changelog.py --check` verde | ✅ |

## Hallazgos de plan-review (3 roles, incorporados)

- **context-completeness-reviewer** — 2 filas N (bloqueantes), ambas resueltas en este plan: `revision-editorial-externa.md` estaba fuera de alcance → añadido (Entra #5); `promises.md` l.11 no materializa communication.md → añadido (Entra #6). Premisas validadas OK: los 3 bloques "Punto de customización" existen (coding/git/done); `VERSION`+`plugin.json` son los únicos lugares de versión; no rompe imports (referencias entrantes citan archivo+sección por nombre, no el texto literal).
- **qa-process-engineer** — usar el término canónico "punto de customización" en vez de acuñar "default de preferencia" → aplicado (#1); dar texto exacto para principles.md l.141 y declarar el reblandecimiento de § "No tocar" → aplicado (#4); incluir el override por-proyecto en el bloque de communication.md → aplicado (#2); plan de pruebas con umbral binario → aplicado.
- **process-improvement-analyst** — cambio justificado, no es churn, respeta la sede única, sin ceremonia ni prescripción de razonamiento interno; única sugerencia (término canónico) → aplicada.

## Clasificación SemVer

**Minor** (5.9.3 → 5.10.0): nuevo lineamiento (matiz default/proceso) + nuevo punto de customización + cambio de fuerza normativa del default (mexicano deja de ser baseline del núcleo → declarar, nunca Patch, ver `principles.md` § "Declarar"). No rompe imports.

## Trazabilidad

- **Plan aprobado:** plan-review completo (3 roles, hallazgos incorporados); OK del dev **pendiente** antes de Fase 4.
- **Commits:** pendiente.
- **Pendientes generados:** pendiente.
