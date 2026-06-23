# Skills

Lineamiento meta-organizacional: cuándo crear un skill, qué nivel de detalle poner y cómo mantenerlo a lo largo del ciclo de vida de la metodología. Para el "cómo" concreto (estructura, frontmatter, distribución), ver `profiles/skill-authoring/`.

## ¿Qué es un skill?

Un skill es un archivo Markdown con frontmatter YAML ubicado en `~/.claude/skills/<nombre>/SKILL.md`. Claude lo carga selectivamente cuando el `description` del frontmatter encaja con el contexto del prompt. Los archivos hermanos (en el mismo directorio) se referencian explícitamente desde el cuerpo y se leen bajo demanda — el `SKILL.md` raíz actúa como orquestador de bajo token cost.

## Skill vs alternativas

Antes de crear un skill, descartar alternativas más simples:

| ¿El conocimiento es...? | Va en |
|---|---|
| Específico de un proyecto, estable | `CLAUDE.md` del proyecto |
| Convención del profile, aplica a todos sus proyectos | `profiles/<profile>/conventions.md` |
| Decisión de un REQ puntual, histórica | Change MD del REQ |
| Override del dev, no del equipo | `personal/<usuario>.md` |
| Mapa/índice cross-proyecto, demasiado voluminoso para CLAUDE.md, estable | **Skill** |
| Vocabulario de dominio compartido entre proyectos, no derivable del código en una sesión | **Skill** |

Solo crear un skill cuando ninguna alternativa encaja.

## Restricción de contenido

El skill entrega **vocabulario y orientación**; el código vive en el repo y Claude lo lee al momento.

No incluir: signaturas de funciones, SQL, números de línea, gaps de implementación ("no existe método X"), schemas completos cuando el `install.sql` está a una lectura de distancia.

Sí incluir: vocabulario, desambiguación, puntos de entrada (nombre de clase/módulo), gotchas no derivables del código, tablas de mapeo de conceptos.

   Regla práctica: si una línea del skill tiene un número de línea, una signatura completa o un bloque SQL, probablemente sobra.

Ver detalle de convenciones en `profiles/skill-authoring/conventions.md`.

## Asociación con profiles e inventario

Cada skill se registra en dos lugares:

1. `skills/README.md` — inventario maestro (single source of truth del catálogo del equipo).
2. `profiles/<profile>/skills.md` del profile donde aplica.

Un skill puede asociarse a múltiples profiles.

## Validación al entregar y gaps en uso

El skill se valida **al entregar** (Fase 5): smoke load + `validation-prompts.md` — cubre los casos previstos al escribirlo. Con eso el REQ **cierra**.

Los gaps que aparecen en sesiones reales posteriores (no previstos al escribir) son **retroalimentación de Fase 9**, no un gate que difiera el cierre: cada uno entra como REQ de patch (ver § siguiente). No se mantiene un pendiente de "validación en uso" abierto indefinidamente.

### Procesamiento de un gap detectado en uso

1. **Clasificar**: ¿fue sub-especificación o undertriggering?
   - **Sub-especificación**: el skill cargó pero no tenía el vocabulario/orientación necesario.
   - **Undertriggering**: el skill estaba cargado pero Claude no lo usó.
2. **Sub-especificación** → REQ de patch. Agregar lo mínimo que cierra el gap, siguiendo restricción de contenido. No extrapolar.
3. **Undertriggering** → ajustar `description` del frontmatter (más pushy, paths explícitos, negaciones). **No agregar contenido** — el problema es de activación, no de vocabulario.
4. Agregar caso de regresión en `validation-prompts.md` con el prompt fallado y el esperado.

## Desambiguación de colisiones de nombres

Cuando el dominio cubierto por el skill usa strings que también son nombres de proyectos u otras entidades (ej. un código corto que es tanto un valor en el código como el nombre de un proyecto), el skill debe incluir desambiguación explícita en dos lugares:

1. **El archivo del dominio compartido** (`common/`, `references/`, u otro): bloque "Desambiguación" visible al inicio de la sección correspondiente.
2. **`glossary.md`**: tabla con ambos significados y pista de interpretación contextual.

Indicador de que se necesita: el mismo string aparece en el nombre de un proyecto **y** como literal en código compartido (constante, valor de columna ENUM, código de mensaje de un sistema externo, etc.).

Caso de referencia: un código corto que es a la vez el nombre de un proyecto y un valor literal en el código compartido (constante, valor de columna ENUM, código de mensaje).

## Mantenimiento general

El skill no se actualiza automáticamente. Tres triggers:

1. **Comando manual en Fase 8**: si el REQ tocó código cubierto por el skill, correr `scripts/regen-maps.py --all`.
2. **Regla en metodología**: si el REQ agrega un proyecto al common o cambia `projects.json`, regenerar el skill en Fase 8.
3. **Revisión mensual**: el Skill Maintainer (asignado en `personal/<usuario>.md`) regenera, revisa diff, hace commit de baselines.

Ver procedimiento completo en `profiles/skill-authoring/deployment.md`.
