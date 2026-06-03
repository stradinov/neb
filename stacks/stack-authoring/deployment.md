# Deployment (stack: stack-authoring)

Hereda de [`stacks/self-applied/deployment.md`](../self-applied/deployment.md): deploy = `git push`, ambiente único (prueba = producción), validación diferida en uso.

## Deploy

```bash
git add stacks/<nombre>/
git commit -m "stacks(<nombre>): <descripción>"
git push
```

En los repos cliente que importan el stack via `@~/.claude/neb/stacks/<nombre>/index.md`: `git pull` en `neb` — el nuevo stack queda disponible en la próxima sesión de Claude.

## Verificación post-creación

Tras crear o modificar un stack:

1. **detect_stack**: correr `bash bootstrap/link-into-project.sh <proyecto-prueba>` y confirmar que la salida dice `Stack detectado: <nombre>` para un directorio que debería activarlo.
2. **Regresión**: confirmar que stacks existentes detectan igual. Probar al menos dos stacks ya soportados con proyectos reales que los activen.
3. **Smoke de sesión**: abrir Claude en cwd dentro del directorio cubierto por el stack y confirmar que el anuncio de stack activo es el correcto.

## Distribución al equipo

1. Maintainer hace `git push` al repo `neb`.
2. Cada dev ejecuta `git pull` en su clon.
3. Si el stack nuevo agrega heurística en `detect_stack`: cada dev re-corre `bootstrap/link-into-project.sh` en sus proyectos cliente afectados para actualizar el CLAUDE.md.
4. Si el stack nuevo trae subagentes propios: cada dev corre `bootstrap/install-agents.sh` + `/reload-plugins` o inicia sesión nueva.

## Lo que NO hace Claude

- No genera el stack automáticamente sin plan aprobado.
- No toca `bootstrap/link-into-project.sh` ni `stacks/index.md` sin revisar regresión en stacks existentes.
