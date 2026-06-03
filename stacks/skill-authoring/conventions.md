# Convenciones: skill-authoring

Cómo escribir y estructurar un skill de Claude Code bajo la metodología.

## Estructura del directorio

```
skills/<nombre>/
├── SKILL.md                  # Requerido — orquestador, < 5k tokens
├── validation-prompts.md     # Requerido — casos de prueba
├── <archivo-hermano>.md      # Contenido detallado, cargado bajo demanda
└── scripts/                  # Scripts de regen si aplica
    └── regen-maps.py
```

Variante con subdominios (ej. un skill que cubre varios módulos de un framework):

```
skills/<nombre>/
├── SKILL.md
├── validation-prompts.md
├── glossary.md
├── references/               # Subdirectorio por dominio (convención skill-creator: referencias técnicas)
├── common/
├── projects/
└── scripts/
```

Ambas variantes son válidas. Usar subdirectorios cuando el skill cubre dominios claramente separados que no siempre se cargan juntos.

## Frontmatter requerido

```yaml
---
name: <nombre-en-kebab-case>
description: <descripción precisa>
---
```

### Reglas para `description`

La `description` es el contrato de invocación — governa cuándo Claude carga el skill.

1. **Verbos imperativos**: "Cargar ANTES de planear...", "Usar al editar...".
2. **Paths y dominios explícitos**: nombrar los paths, proyectos o tecnologías cubiertos.
3. **Fases de aplicación**: indicar en qué fase(s) del workflow aplica (Planning, Execution, etc.).
4. **Negaciones explícitas**: incluir "NO usar para X" para reducir falsos positivos (overtriggering).

Ejemplo (skill filtrado de un stack de un framework):
> Cargar ANTES de planear o editar archivos en `<repo>/src/`, `<repo>/lib/` o `<repo>/plugins/` del proyecto. Sirve durante Planning (Fases 1-3) y Execution (Fase 4) cuando se toca código del framework. NO usar para la app móvil, los scripts de datos ni un proyecto sobre otro framework.

**Pushy descriptions**: Claude tiende a no cargar skills aunque sean relevantes (undertriggering). La description debe ser explícita y directiva — no minimalista.

## Cuerpo del `SKILL.md`

### Forma imperativa

Escribir en forma imperativa/infinitiva, no en segunda persona:

- ✅ "To find the canonical class, open `references/classes-map.md`."
- ✅ "Cargar `projects/<proyecto>.md` para customizaciones específicas del proyecto."
- ❌ "You should open references/classes-map.md to find the class."
- ❌ "Se recomienda revisar projects/<proyecto>.md."

### Progressive disclosure

El `SKILL.md` es el orquestador de bajo costo. No contiene el contenido detallado — lo indexa.

- **Objetivo**: `SKILL.md` < 5k tokens (el scanner de Claude procesa ~100 tokens por skill para decidir si cargarlo; el cuerpo completo carga solo si es relevante).
- **Contenido del SKILL.md**: tabla "cuándo abrir cada archivo hermano", glosario rápido (5-10 términos clave), sección "ver también".
- **Contenido detallado**: en archivos hermanos, cargados bajo demanda cuando Claude los lee explícitamente.

### Restricción de contenido

El skill entrega **vocabulario y orientación**; el código vive en el repo y Claude lo lee al momento.

**No incluir en un skill:**
- Signaturas completas de funciones o métodos.
- SQL o snippets de código extensos.
- Números de línea (`ClaseEjemplo.php:117-137`).
- Gaps de implementación ("no existe método X, créalo") — eso es trabajo de proyecto.
- Schemas completos de tablas cuando el `install.sql` / migration está a una lectura de distancia.
- Listas de constantes/ENUMs cuando el código fuente es la fuente de verdad.

**Sí incluir:**
- Vocabulario y desambiguación (qué significan los términos del dominio).
- Puntos de entrada: nombre de la clase / módulo / archivo, sin signaturas internas.
- Reglas y gotchas no derivables del código (managed files, propagación, decisiones de diseño, restricciones de negocio).
- Tablas de mapeo de conceptos (ej. códigos de un sistema externo ↔ significado de negocio).

**Regla práctica**: si una línea del skill tiene un número de línea, una signatura completa o un bloque SQL, probablemente sobra. Caso de referencia: un skill que copió signaturas y bloques SQL literales tuvo que revertirse porque cada cambio menor en el código fuente lo dejaba desactualizado.

## Política de contenido autogenerado vs manual

Dos tipos de contenido dentro de los archivos hermanos:

- **Autogenerado** (entre marcadores `<!-- autogen-start: <id> -->` y `<!-- autogen-end: <id> -->`): tablas de clases, módulos, controllers, índices de proyectos. El script `scripts/regen-maps.py` los reescribe idempotentemente. El texto fuera de los marcadores se conserva entre regeneraciones.
- **Manual**: gotchas, decisiones de diseño, vocabulario del dominio, desambiguaciones, reglas de negocio. Este es el valor diferencial del skill. No se sobreescribe en regen.

Al editar un archivo hermano, identificar si la sección es autogen o manual antes de modificarla.

## Asociación con stacks

Cada skill debe registrarse en dos lugares:

1. `skills/README.md` — inventario maestro (ver `methodology/skills.md`).
2. `stacks/<stack>/skills.md` del stack donde aplica — tabla de cuándo cargarlo dentro del workflow del stack.

Un skill puede asociarse a múltiples stacks si el dominio cruza proyectos de tipos distintos.
