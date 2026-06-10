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

1. **Detección**: abrir una sesión Claude en un directorio que debería activar el stack y confirmar que el anuncio de stack activo dice `<nombre>` (Claude aplica la heurística de `stacks/index.md`).
2. **Regresión**: confirmar que stacks existentes detectan igual. Probar al menos dos stacks ya soportados con proyectos reales que los activen.
3. **Smoke de sesión**: abrir Claude en cwd dentro del directorio cubierto por el stack y confirmar que el anuncio de stack activo es el correcto.

## Distribución al equipo

1. Maintainer hace `git push` al repo `neb`.
2. Cada dev ejecuta `git pull` en su clon.
3. Si el stack nuevo agrega heurística: basta con que esté en `stacks/index.md` + `general/stack-detection.md`. Bajo el plugin no hace falta re-enganchar proyectos cliente — Claude lee la heurística en runtime; el arranque se inyecta por el hook `SessionStart`.
4. Si el stack nuevo trae subagentes propios: se auto-descubren del plugin; `/reload-plugins` (o sesión nueva) para refrescar.

## Lo que NO hace Claude

- No genera el stack automáticamente sin plan aprobado.
- No toca la heurística de `stacks/index.md` ni `general/stack-detection.md` sin revisar regresión en stacks existentes.
