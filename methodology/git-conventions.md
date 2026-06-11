# Convenciones de commit

Formato y tipos del mensaje de commit. Son invariantes del estilo de commit del equipo; las **operaciones** git (push, gate de confirmación en Fase 4, autonomía sobre `.md`, CHANGELOG fragmentado) viven en [`../process/version-control.md`](../process/version-control.md).

> **Punto de customización**: el formato del mensaje de commit es lo que un adoptante adapta con más frecuencia a su contexto (p. ej. [Conventional Commits](https://www.conventionalcommits.org/) en inglés, scopes obligatorios, gitmoji). Reemplazá esta convención en `personal/<usuario>.md` o `profiles/<profile>/deployment.md` sin tocar las operaciones git del proceso.

## Formato

```
tipo: descripción corta en español   (máx. 72 caracteres)
```

Tipos: `feat` · `fix` · `refactor` · `chore` · `docs`

- Un commit por conjunto lógico, no por archivo.
- Si varios requerimientos deben subirse juntos, agrupar.
- Stagear archivos por nombre, no `git add -A` (evita filtrar `.env`, credenciales, binarios).

## Prohibiciones (no relajables)

- **Nunca** `--no-verify` ni bypass de hooks sin autorización explícita.
- **Nunca** `--force` ni `reset --hard` en rama principal sin autorización explícita.
- Si pre-commit hook falla: el commit NO ocurrió. Arreglar y crear commit NUEVO (no `--amend`).
