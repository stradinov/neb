@profiles/self-applied/index.md
<!-- El arranque del framework (startup + workflow) lo inyecta el plugin neb (hook SessionStart)
     — no se importa aquí para no cargarlo dos veces. Contribuidor sin plugin: instalalo
     (/plugin marketplace add stradinov/neb + /plugin install neb@neb). -->
# CLAUDE.md (este repo)

Meta-instrucciones para Claude cuando edita la metodología misma.

## Al editar este repo

- **Eres recursivo**: la metodología que editas es la que aplicas. Sigue las fases (clarificación → propuesta → implementación → commit) usando la metodología actual.
- **Cualquier cambio entra al `CHANGELOG.md`** antes del tag. El CHANGELOG se gestiona vía fragments en `changelog.d/<version>.md` ensamblados por `bootstrap/assemble-changelog.py` — ver flujo en [`process/version-control.md`](process/version-control.md) "CHANGELOG fragmentado".
- **Versionado SemVer**:
  - Patch (1.0.0 → 1.0.1): redacción, typos, aclaraciones.
  - Minor (1.0.x → 1.1.0): nuevos lineamientos, profiles, hooks.
  - Major (1.x.y → 2.0.0): rupturas de imports (renombrar archivos importados), cambios incompatibles.

## Convenciones internas

- Archivos: `kebab-case.md`, sin prefijos numéricos.
- Cada carpeta tiene su `index.md` con orden de lectura.
- Imports internos: paths relativos (`../methodology/principles.md`). Los del propio `CLAUDE.md` también son relativos — funcionan en cualquier ubicación del clon.
- Proyectos externos **no importan el framework**: lo inyecta el plugin (hook `SessionStart`).

## Referencias en MDs de este repo

Los MDs no asumen una ruta local fija (cada dev clona donde prefiere).

| Tipo | Cómo escribirla |
|---|---|
| Archivo dentro de este repo | Path relativo: `general/index.md`, `../methodology/principles.md` |
| Archivo en otro repo del equipo | Nombre + repo. Ej: "`proyectos-activos-ambientes.md` en `deployment`" |
| Path local del clon (si necesario) | Etiquetar como convencional. Ej: "convencionalmente `~/.claude/neb/`, ajusta al directorio de tu clon" |
| Paths absolutos de la máquina del dev | **Solo en `personal/*.md`** |

Para localizar un repo en la máquina del dev, consultar primero "Directorio de repos locales" del `personal/<usuario>.md` activo. Si no está, sugerir `git clone` con la URL del repo.

## No editar a mano

- `personal/<usuario>.md` (gitignored, lo gestiona cada dev).
- Archivos generados por hooks.
- Segmentos delimitados por `<!-- human -->` … `<!-- /human -->` dentro de cualquier `.md` — contenido bajo control directo de un humano, cuya voz e intención se preservan intactas; Claude propone deltas inline pero no los edita sin OK. Ver [`methodology/change-control-policy.md`](methodology/change-control-policy.md) § "Ownership de archivos `.md`".

## Agregar un profile nuevo

Correr primero para scaffold inicial: `bash bootstrap/init-profile-subproject.sh <nombre> [--overlay-base self-applied|none]`

El script crea `profiles/<nombre>/` con los 6 archivos mínimos desde templates e imprime la checklist de acoples pendientes. Ver teoría (cuándo crear, tipos, nombramiento) en [`methodology/profiles.md`](methodology/profiles.md) y convenciones de contenido en [`profiles/profile-authoring/conventions.md`](profiles/profile-authoring/conventions.md).

Acoples de roles (todo profile nuevo):
- Definir rol principal en `profiles/<nombre>/roles.md`; decidir herencia de revisores (overlay) o propios.
- Si define revisores propios como subagentes: seguir "Agregar un subagente" abajo.
- Agregar fila en `process/roles-invocation.md` tabla "Default por profile" + matriz "Cobertura mínima por fase".
- Agregar filas en `process/execution.md` y `process/delivery.md` tablas de gate.

Para profiles que viven como **overlays por path** dentro de un repo ya detectado:
- Actualizar la heurística de detección por path en `profiles/index.md` + `general/profile-detection.md` paso 0 (fila prioritaria en `profiles/index.md`).
- Bump **major** si el nuevo profile introduce cambios en el ENUM de estados o vocabulario de `general/`.

Para profiles con **subproyectos anidados** que necesitan init propio:
- Crear `bootstrap/init-<nombre>-subproject.sh` siguiendo el patrón de los scripts de init existentes.

## Agregar un skill nuevo

1. Crear `skills/<nombre>/SKILL.md` con frontmatter `name` + `description` preciso. Bajo el plugin, el skill se expone solo por existir en `skills/<nombre>/SKILL.md` (auto-discovery; no hay registro en un script).
2. Agregar archivos hermanos de contenido y scripts si aplica.
3. Registrar en `skills/README.md` (tabla de skills disponibles).
4. Registrar en `profiles/<profile>/skills.md` del profile correspondiente.
5. Bump minor + nuevo fragment `changelog.d/<version>.md` + correr `py bootstrap/assemble-changelog.py`.

Ver lineamiento completo en `methodology/skills.md`.

Para profiles que viven como **subproyectos anidados** dentro de otro repo:
- Crear también `bootstrap/init-<nombre>-subproject.sh` para inicializar el subproyecto.
- Actualizar la heurística de detección por path en `profiles/index.md` + `general/profile-detection.md` paso 0 (regla de overlay y fila prioritaria en `profiles/index.md`).
- Bump **major** si el nuevo profile introduce cambios en el ENUM de estados o vocabulario de `general/`.

## Agregar un subagente

1. Crear `agents/<nombre>.md` con frontmatter `name`, `description` (cuándo invocarlo) y `tools: [Read, Grep, Glob]` (ampliar solo si el rol necesita una capacidad fuera de ese set — escritura, o lectura de red como `WebFetch` para `fact-check-reviewer` — justificándola en el body). Body = system prompt del rol, que cita o referencia el foco ya definido en `process/roles-invocation.md` o `profiles/<profile>/roles.md` — sin duplicar contenido; la metodología sigue siendo single source of truth. Bajo el plugin, el agente se expone solo por existir en `agents/<nombre>.md` (auto-discovery; no hay registro en un script).
2. En `process/roles-invocation.md` tabla "Resumen de utilidad": cambiar columna "Impl." de `persona` a `**subagente** (\`<nombre>\`)` para el rol correspondiente.
3. En `profiles/<profile>/roles.md` del profile que usa el subagente: anotar `— \`subagente\` (\`agents/<nombre>.md\`)` junto al nombre del rol.
4. Verificar que `process/plan-review.md` paso 2 cubra la lógica de despacho para el nuevo subagente (no debería requerir cambio si el algoritmo ya distingue por presencia de `.md` en `agents/`).
5. Bump minor + nuevo fragment `changelog.d/<version>.md` + correr `py bootstrap/assemble-changelog.py`.

Ver definición técnica del modelo persona/subagente en [`process/roles-invocation.md`](process/roles-invocation.md) sección "Implementación de roles".

## Cambiar paths o nombres de archivos importados

Rompe imports en los `CLAUDE.md` de todos los proyectos. Considerar alias o redirección antes de hacerlo; si no hay forma, justifica un major.
