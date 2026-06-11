# Deployment: skill-authoring

Cómo instalar, distribuir y verificar un skill tras editarlo.

## Fuente y destino

| Artefacto | Path |
|---|---|
| Fuente versionada | `~/.claude/neb/skills/<nombre>/` (este repo) |
| Exposición | Auto-descubierto del plugin (`skills/<nombre>/SKILL.md`) |

## Instalar / actualizar

Bajo el plugin no hay script de instalación: el skill se expone solo por existir en `skills/<nombre>/SKILL.md` (auto-discovery). Tras editar la fuente:

```bash
/reload-plugins
```

O `claude plugin update <plugin>` para tomar la versión publicada. Una sesión nueva ya carga la versión vigente sin pasos extra.

## Verificación post-instalación

### 1. Smoke load

Abrir sesión nueva de Claude Code en un directorio cubierto por el skill. Ejecutar `/skills`. Confirmar que el skill aparece en la lista cargada.

Si no aparece:
- Ver `troubleshooting.md` §"Skill no aparece en /skills".

### 2. Casos de validación

Correr los casos afectados del `validation-prompts.md` del skill. Documentar resultado en la tabla "Registro de resultados" al final del archivo.

Casos mínimos a correr después de cualquier cambio:
- Todos los casos que tocan los archivos modificados.
- Al menos 1 caso negativo (verificar que no overtrigger).

### 3. Registro de resultados

Formato de entrada en la tabla:

| Fecha | Versión skill | Caso | Resultado | Notas |
|---|---|---|---|---|
| 2026-05-14 | 1.0.0 | 1 | ✅ | — |
| 2026-05-14 | 1.0.0 | 3 | ✅ (negativo correcto) | Skill no cargó en un proyecto fuera de su scope |

## Commit y push

Tras verificar smoke load + validation-prompts:

```bash
git add skills/<nombre>/ profiles/ general/ methodology/ process/ tooling/ changelog.d/<version>.md CHANGELOG.md VERSION
git commit -m "skill-authoring: <descripción del cambio>"
git push
```

El Skill Maintainer (asignado en `personal/<usuario>.md`) es quien commitea las **baselines de contenido autogenerado** (`<!-- autogen-start/end -->`). Los demás cambios pueden commitearlos los Skill Authors autorizados.

## Distribución al equipo

El cambio viaja en el plugin. El skill versionado en `neb` llega al resto del equipo cuando:

1. Skill Maintainer commitea + pushea los cambios.
2. Los adoptantes hacen `claude plugin update` (o reinstalan el plugin).
3. `/reload-plugins` para tomar los cambios sin reiniciar la sesión.

Para cambios que afectan la `description` del frontmatter (pueden cambiar el comportamiento de carga), avisar al equipo explícitamente.
