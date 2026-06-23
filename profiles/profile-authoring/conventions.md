# Convenciones (profile: profile-authoring)

## Estructura mínima del directorio

```
profiles/<nombre>/
├── index.md          # Obligatorio
├── deployment.md     # Estándar
├── conventions.md    # Estándar
├── troubleshooting.md # Estándar
├── roles.md          # Estándar
└── skills.md         # Opcional (stub si no hay skills propios)
```

Ver `methodology/profiles.md` "Archivos del profile" para criterios de cuándo omitir archivos estándar.

## Secciones obligatorias de `index.md`

Todo `index.md` de profile debe tener:

1. **Título** — `# Profile: <nombre>` + una línea de descripción.
2. **Cuándo aplica este profile** — condiciones de activación (path, tipo de REQ, regla de conflicto si hay solapamiento).
3. **Glosario del profile** — tabla con los términos del vocabulario abstracto (`methodology/vocabulary.md`) concretizados para este profile.
4. **Fases adaptadas** — tabla con las adaptaciones por fase que divergen del comportamiento genérico.
5. **Archivos clave del profile** — tabla de archivos + propósito (evita repetir la descripción en cada sección).

Secciones adicionales permitidas si el profile las necesita (e.g. "Agregar un profile nuevo", "Flujos críticos").

## Reglas para la heurística de detección

La heurística vive en `profiles/index.md` (single source of truth); `general/profile-detection.md` define cuándo y cómo Claude la aplica en tiempo de ejecución. Ambos deben estar sincronizados.

- **Solo existencia de paths**: existencia de directorios/archivos o match de pattern sobre el path absoluto. Sin leer contenido de archivos (solo si es estrictamente necesario).
- **Idempotente**: aplicar la heurística sobre el mismo directorio N veces → mismo resultado.
- **Prioridad explícita**: los overlays van ANTES que los raíz en `profiles/index.md`. Documentar conflictos potenciales.
- **Pattern para overlays**: `/<nombre-fijo>(/|$)` — el `/` al inicio y `(/|$)` al final evitan falsos positivos (`foobar/reqs/` no activa el overlay de `reqs/`).
- **Actualización sincronizada**: si cambias la heurística en `profiles/index.md`, actualiza `general/profile-detection.md` en el mismo commit.

## Política de imports

| Tipo de referencia | Cómo escribirla |
|---|---|
| Archivo dentro del repo de metodología | Path relativo: `../methodology/profiles.md`, `../../process/delivery.md` |
| Import desde CLAUDE.md de un proyecto cliente | `@~/.claude/neb/profiles/<profile>/index.md` (ruta absoluta convencional) |
| Archivo en otro repo | Nombre + repo: "`server-config.md` en `tu-org/infra-scripts`" |

No usar paths absolutos de la máquina del dev dentro de los MDs del profile (solo en `personal/<usuario>.md`).

## Separación core vs profile

El contenido que es universal a todos los profiles vive en `general/` o `methodology/`/`process/`/`tooling/`. El contenido específico del profile vive en `profiles/<nombre>/`.

Si una regla aplica a todos los profiles → no duplicarla en el profile; referenciar desde `general/` o `methodology/`/`process/`/`tooling/`.

Si una adaptación es específica del profile → documentarla en el profile, sin subir al core.

## Versionado al editar un profile existente

- Edición de contenido (no rompe imports): patch.
- Nuevo archivo en el profile: minor.
- Renombrar archivo importado desde proyectos cliente: major (rompe imports).

Ver tabla completa en `methodology/profiles.md` "Versionado".
