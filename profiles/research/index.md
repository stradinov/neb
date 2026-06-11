# Profile: research

Investigación multi-fuente verificada: buscar y cruzar fuentes independientes (web vía `WebSearch`/`WebFetch`, conectores MCP internos y —en research exploratorio— una voz LLM externa), sintetizar resultados y producir un documento citable desde cualquier profile o requerimiento.

## Cuándo aplica este profile

Overlay sobre `self-applied`. Se activa cuando:

- El cwd está dentro de `methodology/research/` (investigación sobre la metodología misma).
- El REQ pide explícitamente investigar, buscar fuentes, o comparar opciones en un tema especializado.
- Para investigación en un proyecto (`<proyecto>/research/...`) o cross-proyecto (`~/.claude/research/...`): activación **explícita** por el dev al abrir el REQ — sin auto-detección por path para evitar colisión con el profile del proyecto.

Si el REQ también toca la metodología general (`general/`, `methodology/`, `process/`, `tooling/`, etc.), el profile activo es `research` para el documento de investigación y `self-applied` para el resto. Si hay ambigüedad, anunciar y preguntar.

## Glosario del profile

| Término | Significado |
|---|---|
| **Entregable** | Documento markdown de investigación: síntesis destilada + frontmatter YAML (ver [conventions.md](conventions.md) §Trazabilidad) |
| **Entrega para revisión** | Síntesis destilada presentada al dev en la sesión (sin gate formal de utilidad — hereda la validación diferida de `self-applied`) |
| **Entrega final** | Commit del documento en su ubicación según scope + cita en el change que lo originó |
| **Ambiente de revisión** | Uso del research en REQs/decisiones posteriores (validación diferida en uso) |
| **Estado aprobado** | Research `vigente` sin reporte negativo tras ≥2 usos en otros REQs |
| **Dependientes** | Documentos o archivos que citan este research (ver §Trazabilidad en conventions.md) |
| **Flujos críticos** | Sub-preguntas marcadas `[crítico]` cuando el propósito es una decisión — foco del gate F4 (su divergencia no resuelta lo dispara) |
| **Síntesis** | Output destilado por el Process Architect — nunca recitar respuestas crudas de las fuentes |
| **Divergencia material** | Dos o más fuentes entregan respuestas contradictorias en claims centrales. Si el Process Architect no la resuelve con una fuente autoritativa adicional en una dimensión `[crítico]`, activa el Fact-Check Reviewer en F4 |

> Overlay sobre `self-applied`: los términos del vocabulario abstracto no listados (Elaboración asistida/autónoma, Entrega base) se heredan de [`self-applied`](../self-applied/index.md). La tabla concretiza los que difieren en el dominio de investigación + términos propios.

## Fases adaptadas

| Fase general | Adaptación en research |
|---|---|
| **Fase 1 — Clarificación** | Reformular la pregunta de investigación, fuentes esperadas, alcance temporal/temático, propósito (`exploratorio` o `decisión`) y criterio de "útil" para el propósito declarado |
| **Fase 2 — Estimación** | Baja: ≤2 fuentes, búsqueda directa · Media: multi-fuente con cruce · Alta: multi-fuente + verificación adversarial (voz externa Gemini si `exploratorio`) |
| **Fase 3 — Propuesta** | Plan = fuentes/motor a consultar + prompts + dimensiones + criterio de éxito. Plan de pruebas = dimensiones esperadas (criterio de éxito) + flujos `[crítico]` si `propósito = decisión`. Plan-review obligatorio cuando `propósito = decisión` |
| **Fase 4 — Ejecución** | Ejecutar el motor de investigación (`WebSearch`/`WebFetch` de piso; `deep-research` opcional; Gemini inline si `exploratorio`), capturar síntesis destilada. Gate: `fact-check-reviewer` si `propósito = decisión` o divergencia no resuelta en dimensión `[crítico]` |
| **Fase 5 — Validación** | **Validación diferida en uso** (hereda de `self-applied`): no hay gate síncrono ni matriz formal. La síntesis se presenta al dev; su utilidad se valida al usarse en REQs posteriores. La calidad de claims ya pasó por el gate F4 |
| **Fase 6 — Control de cambios** | Estado `Listo para aprobación`: dev autoriza el commit/entrega del research (no valida utilidad — diferida en uso) |
| **Fase 7 — Entrega final** | Commit en ubicación según scope + cita desde el change originador. Gate: `fact-check-reviewer` pre-commit |
| **Fase 8 — Documentación** | Change MD del REQ + actualizar memoria del proyecto (decisión derivada, no el research entero). Bump SemVer solo si el research modifica la metodología directamente |
| **Fase 9 — Mejora** | Δ score de fuentes/motor por utilidad real; patrón de preguntas que no se beneficiaron de la voz externa (candidato a restringir Gemini para esos casos) |

## Archivos clave del profile

| Propósito | Archivo |
|---|---|
| Convenciones: disparo, formato, trazabilidad, síntesis | [profiles/research/conventions.md](conventions.md) |
| Entrega: commit, cita, ubicación por scope, gate F7 | [profiles/research/deployment.md](deployment.md) |
| Roles: Process Architect (principal) + Fact-Check Reviewer (revisor) | [profiles/research/roles.md](roles.md) |
| Troubleshooting | [profiles/research/troubleshooting.md](troubleshooting.md) |
| Skills del profile | [profiles/research/skills.md](skills.md) |
| Investigaciones sobre la metodología | [research/README.md](../../research/README.md) |

## Documentos

1. [Deployment](deployment.md) — cómo se commitea + ubicación según scope + gate F7.
2. [Conventions](conventions.md) — modos de disparo, formato del documento, trazabilidad, síntesis.
3. [Troubleshooting](troubleshooting.md) — divergencia entre fuentes, fuente no verificable, alucinación.
4. [Roles](roles.md) — Process Architect (principal) + Fact-Check Reviewer (subagente revisor).
