# Convenciones (stack: stack-authoring)

## Estructura mínima del directorio

```
stacks/<nombre>/
├── index.md          # Obligatorio
├── deployment.md     # Estándar
├── conventions.md    # Estándar
├── troubleshooting.md # Estándar
├── roles.md          # Estándar
└── skills.md         # Opcional (stub si no hay skills propios)
```

Ver `methodology/stacks.md` "Archivos del stack" para criterios de cuándo omitir archivos estándar.

## Secciones obligatorias de `index.md`

Todo `index.md` de stack debe tener:

1. **Título** — `# Stack: <nombre>` + una línea de descripción.
2. **Cuándo aplica este stack** — condiciones de activación (path, tipo de REQ, regla de conflicto si hay solapamiento).
3. **Glosario del stack** — tabla con los términos del vocabulario abstracto (`methodology/vocabulary.md`) concretizados para este stack.
4. **Fases adaptadas** — tabla con las adaptaciones por fase que divergen del comportamiento genérico.
5. **Archivos clave del stack** — tabla de archivos + propósito (evita repetir la descripción en cada sección).

Secciones adicionales permitidas si el stack las necesita (e.g. "Agregar un stack nuevo", "Flujos críticos").

## Reglas para la heurística de detección

La heurística vive en `stacks/index.md` (single source of truth); `general/stack-detection.md` define cuándo y cómo Claude la aplica en runtime. Ambos deben estar sincronizados.

- **Solo existencia de paths**: existencia de directorios/archivos o match de pattern sobre el path absoluto. Sin leer contenido de archivos (solo si es estrictamente necesario).
- **Idempotente**: aplicar la heurística sobre el mismo directorio N veces → mismo resultado.
- **Prioridad explícita**: los overlays van ANTES que los raíz en `stacks/index.md`. Documentar conflictos potenciales.
- **Pattern para overlays**: `/<nombre-fijo>(/|$)` — el `/` al inicio y `(/|$)` al final evitan falsos positivos (`foobar/reqs/` no activa el overlay de `reqs/`).
- **Actualización sincronizada**: si cambias la heurística en `stacks/index.md`, actualiza `general/stack-detection.md` en el mismo commit.

## Política de imports

| Tipo de referencia | Cómo escribirla |
|---|---|
| Archivo dentro del repo de metodología | Path relativo: `../methodology/stacks.md`, `../../process/delivery.md` |
| Import desde CLAUDE.md de un proyecto cliente | `@~/.claude/neb/stacks/<stack>/index.md` (ruta absoluta convencional) |
| Archivo en otro repo | Nombre + repo: "`server-config.md` en `tu-org/infra-scripts`" |

No usar paths absolutos de la máquina del dev dentro de los MDs del stack (solo en `personal/<usuario>.md`).

## Separación core vs stack

El contenido que es universal a todos los stacks vive en `general/` o `methodology/`/`process/`/`tooling/`. El contenido específico del stack vive en `stacks/<nombre>/`.

Si una regla aplica a todos los stacks → no duplicarla en el stack; referenciar desde `general/` o `methodology/`/`process/`/`tooling/`.

Si una adaptación es específica del stack → documentarla en el stack, sin subir al core.

## Versionado al editar un stack existente

- Edición de contenido (no rompe imports): patch.
- Nuevo archivo en el stack: minor.
- Renombrar archivo importado desde proyectos cliente: major (rompe imports).

Ver tabla completa en `methodology/stacks.md` "Versionado".
