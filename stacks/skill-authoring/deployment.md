# Deployment: skill-authoring

Cómo instalar, distribuir y verificar un skill tras editarlo.

## Fuente y destino

| Artefacto | Path |
|---|---|
| Fuente versionada | `~/.claude/neb/skills/<nombre>/` (este repo) |
| Instalación local | `~/.claude/skills/<nombre>/` |
| Script de instalación | `~/.claude/neb/bootstrap/install-skills.sh` |

## Instalar / actualizar

```bash
bash ~/.claude/neb/bootstrap/install-skills.sh
```

El script instala todos los skills registrados. Si solo cambió un skill, el script es idempotente — re-correrlo no rompe los demás.

### Comportamiento por OS

| OS | Comportamiento |
|---|---|
| Linux / WSL | Crea symlink. Los cambios en la fuente se reflejan automáticamente sin re-correr el script |
| Windows (PowerShell admin) | Intenta junction/symlink. Si permisos lo bloquean, cae a copia recursiva |
| Windows sin permisos elevados | Copia recursiva — **re-correr el script después de cada cambio en la fuente** |

Para verificar qué tipo de instalación quedó en Windows:

```powershell
Get-Item "$env:USERPROFILE\.claude\skills\<nombre>" | Select-Object LinkType, Target
```

Si `LinkType` es vacío, es copia. Si es `Junction` o `SymbolicLink`, es link.

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
git add skills/<nombre>/ stacks/ general/ methodology/ process/ tooling/ changelog.d/<version>.md CHANGELOG.md VERSION
git commit -m "skill-authoring: <descripción del cambio>"
git push
```

El Skill Maintainer (asignado en `personal/<usuario>.md`) es quien commitea las **baselines de contenido autogenerado** (`<!-- autogen-start/end -->`). Los demás cambios pueden commitearlos los Skill Authors autorizados.

## Distribución al equipo

El skill versionado en `neb` llega al resto del equipo cuando:

1. Skill Maintainer commitea + pushea los cambios.
2. Cada dev corre `git pull` en su clon de `neb`.
3. Cada dev re-corre `bootstrap/install-skills.sh` para refrescar su instalación local.

Para cambios que afectan la `description` del frontmatter (pueden cambiar el comportamiento de carga), avisar al equipo explícitamente.
