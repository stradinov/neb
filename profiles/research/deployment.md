# Deployment (profile: research)

## Ubicación del documento según scope

| Scope | Path | Versionado |
|---|---|---|
| Investigación sobre la metodología | `methodology/research/<YYYY-MM-DD>-<slug>.md` | Sí — repo `methodology` |
| Investigación sobre un proyecto específico | `<proyecto>/research/<YYYY-MM-DD>-<slug>.md` | Sí — repo del proyecto |
| Investigación cross-proyecto sin dueño claro | `~/.claude/research/<timestamp>-<slug>.md` | No — local del dev |

Naming: `<YYYY-MM-DD>-<slug>.md` donde slug es kebab-case del tema central (ej. `2026-05-17-multi-llm-gratuito`).

## Gate de Fase 7 (pre-commit)

Antes de commitear el documento de research, invocar `fact-check-reviewer`:

1. El `fact-check-reviewer` verifica: claims con evidencia, coherencia de la síntesis, ausencia de alucinaciones evidentes, frontmatter completo.
2. Si el research originó de un REQ, el change MD de ese REQ **debe** citar este research antes de commitear (campo `req_originador` + link inline).
3. Si `req_originador` es null (research abierto manualmente): agregar 1 línea de justificación en el cuerpo del documento.

## Deploy

Hereda de `profiles/self-applied/deployment.md`: deploy = `git commit` + `git push` al repo de `neb` (si scope = metodología) o al repo del proyecto (si scope = proyecto).

El change MD del REQ originador (si aplica) cita el research con el formato canónico de [conventions.md](conventions.md) §Trazabilidad. Ambos van en el mismo commit cuando es posible.

## Validación (Fase 5)

**Diferida en uso** (hereda de `self-applied`): no hay matriz formal ni gate síncrono con el dev. La síntesis se presenta en la sesión; la utilidad real del research se valida al consumirse en REQs/decisiones posteriores. No hay ambiente de QA separado. La calidad de claims ya se verificó en el gate F4 (`fact-check-reviewer`, si `propósito = decisión` o divergencia no resuelta en `[crítico]`).

Criterio de cierre diferido (análogo a `self-applied`, modo diferido): research `vigente` sin reporte negativo tras **≥2 usos** en otros REQs — no ≥10 sesiones como `self-applied`: un research se consume en pocos REQs, no en cada sesión de trabajo. Transición del ENUM: `En progreso` → `En validación` (F5) → `Listo para aprobación` (F6) → `Cerrado` (diferido); ver [`workflow/index.md`](../../workflow/index.md) "Estados del requerimiento".

## Distribución al equipo

`git push` al remote del repo correspondiente. Otros devs reciben el research vía `git pull` normal. Si el research es cross-proyecto (`~/.claude/research/`), compartir manualmente el archivo si el equipo lo necesita.
