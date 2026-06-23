# Integración con skill-creator de Anthropic

`skill-creator` es el plugin oficial de Anthropic para crear skills de Claude Code. Tiene modos Create, Eval, Improve y Benchmark — orienta al autor a través del ciclo completo de un skill.

**Plugin:** `claude.com/plugins/skill-creator`  
**Repo de referencia:** `github.com/anthropics/skills`

## Qué adoptar de skill-creator

Los siguientes principios de `skill-creator` son compatibles con la metodología y están incorporados en `conventions.md`:

| Principio | Descripción | Dónde está en la metodología |
|---|---|---|
| **Imperative form** | Escribir instrucciones en forma imperativa ("To accomplish X, do Y"), no en segunda persona | `conventions.md` §"Cuerpo del SKILL.md" |
| **Pushy descriptions** | La `description` del frontmatter debe ser explícita y directiva para combatir undertriggering | `conventions.md` §"Reglas para description" |
| **Progressive disclosure** | `SKILL.md` lean (< 5k tokens); detalle en archivos hermanos cargados bajo demanda | `conventions.md` §"Progressive disclosure" |
| **Estructura `scripts/` + `references/` + `assets/`** | Patrón canónico Anthropic para agrupar artefactos del skill | Opcional en la metodología (usamos también subdirectorios por dominio) |

## Qué adaptar para la metodología

Aspectos donde la metodología difiere de `skill-creator`:

| Diferencia | Convención del equipo |
|---|---|
| **Distribución** | Los skills se auto-descubren del plugin `neb`. No es instalación individual por dev — el Skill Maintainer hace commit y el equipo hace `claude plugin update` (`/reload-plugins` para tomar cambios sin reiniciar) |
| **Asociación a profiles** | Cada skill se registra en `profiles/<profile>/skills.md` y en el inventario `skills/README.md` |
| **Inventario maestro** | `skills/README.md` como single source of truth del catálogo del equipo |
| **Validación en uso** | El skill se valida al entregar (smoke load + `validation-prompts`); los gaps en uso posterior entran como REQ de patch (Fase 9), sin pendiente de tracking diferido |
| **Restricción de contenido** | La metodología prohíbe signaturas, SQL, números de línea — el código se lee del repo. `skill-creator` no tiene esta restricción explícita |
| **Baselines autogeneradas** | Marcadores `<!-- autogen-start/end -->` gestionados por scripts Python. Solo el Skill Maintainer hace commit |

## Cómo usar skill-creator como andamiaje (opcional)

`skill-creator` puede usarse para generar la estructura base inicial de un skill nuevo:

1. Instalar el plugin (opcional, no requerido por la metodología): abrirlo en `claude.com/plugins/skill-creator`.
2. Usar el modo **Create** para responder las preguntas del wizard: dominio, trigger conditions, archivos hermanos necesarios, scripts si aplica.
3. El wizard genera un directorio con `SKILL.md` y estructura básica.
4. Adaptar las salidas a las convenciones del equipo:
   - Ajustar `description` con los paths/dominios del proyecto y negaciones explícitas.
   - Crear `validation-prompts.md` con al menos 1 caso positivo + 1 negativo.
   - Registrar en `skills/README.md` y en `profiles/<profile>/skills.md`.
   - Revisar restricción de contenido — eliminar cualquier signatura, SQL o número de línea que el wizard haya incluido.

El uso de `skill-creator` es herramienta de conveniencia, no obligatorio. Los skills pueden crearse directamente siguiendo `conventions.md`.
