# Deployment (profile: profile-authoring)

Hereda de [`profiles/self-applied/deployment.md`](../self-applied/deployment.md): deploy = `git push`, ambiente único (prueba = producción), validación diferida en uso.

## Deploy

```bash
git add profiles/<nombre>/
git commit -m "profiles(<nombre>): <descripción>"
git push
```

En los repos cliente que importan el profile via `@~/.claude/neb/profiles/<nombre>/index.md`: `git pull` en `neb` — el nuevo profile queda disponible en la próxima sesión de Claude.

## Verificación post-creación

Tras crear o modificar un profile:

1. **Detección**: abrir una sesión Claude en un directorio que debería activar el profile y confirmar que el anuncio de profile activo dice `<nombre>` (Claude aplica la heurística de `profiles/index.md`).
2. **Regresión**: confirmar que profiles existentes detectan igual. Probar al menos dos profiles ya soportados con proyectos reales que los activen.
3. **Smoke de sesión**: abrir Claude en cwd dentro del directorio cubierto por el profile y confirmar que el anuncio de profile activo es el correcto.

## Distribución al equipo

1. Maintainer hace `git push` al repo `neb`.
2. Cada dev ejecuta `git pull` en su clon.
3. Si el profile nuevo agrega heurística: basta con que esté en `profiles/index.md` + `general/profile-detection.md`. Bajo el plugin no hace falta re-enganchar proyectos cliente — Claude lee la heurística en runtime; el arranque se inyecta por el hook `SessionStart`.
4. Si el profile nuevo trae subagentes propios: se auto-descubren del plugin; `/reload-plugins` (o sesión nueva) para refrescar.

## Lo que NO hace Claude

- No genera el profile automáticamente sin plan aprobado.
- No toca la heurística de `profiles/index.md` ni `general/profile-detection.md` sin revisar regresión en profiles existentes.
