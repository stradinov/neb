# Migraciones guiadas

Una versión de Neb que pide algo más que pasos de base (configurar la máquina, un paso que necesita al dev) trae aquí dos archivos con el nombre de su versión. Qué es una migración guiada, qué corre solo y qué pide al dev: [`../tooling/migrations.md`](../tooling/migrations.md) § "Migración guiada". Cuándo una versión la trae: [`../process/version-control.md`](../process/version-control.md) § "Flujo al cerrar REQ".

## Índice

| Versión | Pasos guiados | Qué hace |
|---|---|---|
| — | — | Ninguna todavía (6.49.0 trae el mecanismo; la primera es la de 7.0.0) |

## Formato

### `<X.Y.Z>.md` — el prompt

Lo lee Claude en la sesión que corre `/neb:migrate`. Dice qué cambia, en qué orden van los pasos, qué se le dice al dev (lo que el dev debe saber antes de elegir en el menú), cómo se verifica y qué se reporta. No relaja lo que fija `commands/migrate.md`.

### `<X.Y.Z>.py` — los pasos guiados

Define `STEPS`, una lista de `GuidedStep` (de `hooks/lib/_guided.py`, que el registro deja importable). El nombre del archivo es la versión semántica; otro nombre se ignora. Un archivo que falla al cargar se reporta y no detiene a los demás ni al arranque.

```python
from _guided import GuidedStep

STEPS = [
    # De catálogo: el paso es un dato (operación de hooks/lib/_machine.py y sus argumentos).
    GuidedStep("quitar-ejemplo-settings", "Quitar NEB_EJEMPLO de settings.json",
               op="settings_env_remove", args={"claves": ["NEB_EJEMPLO"], "secretas": []}),
    GuidedStep("quitar-ejemplo-entorno", "Quitar la variable de usuario NEB_EJEMPLO",
               op="user_env_remove", args={"nombre": "NEB_EJEMPLO"}),
    # Libre: detectar (solo lee) y aplicar propios. respaldo=True si aplicar deja con qué deshacerlo
    # y devuelve {"respaldo": <ruta>}; exclusivo=True si pide las demás sesiones cerradas.
    GuidedStep("renombrar-algo", "Renombrar algo", detectar=detectar, aplicar=aplicar,
               respaldo=True, exclusivo=True),
]
```

- `id`: minúsculas, dígitos y guiones, único en la versión. El id completo es `<X.Y.Z>:<id>`. Los argumentos de un paso de catálogo se validan al cargar.
- Un paso libre: `detectar(ctx)` solo lee y no llama a nada que escriba; `aplicar(ctx)` devuelve `{"respaldo": ruta, "detalle": texto}` o `{"estado": "pendiente" | "manual" | "fallo", "detalle": texto}`. El respaldo que declara es un archivo nuevo, creado por `aplicar`, directamente en `~/.claude` o en `neb-backups/`; si es una base SQLite, en `journal_mode=DELETE` (reglas completas en [`../tooling/migrations.md`](../tooling/migrations.md) § "Qué corre solo y qué pide al dev"). Un paso `exclusivo` vuelve a comprobar su condición con `ctx.exclusivo_ok()` (None si se cumple) justo antes de la acción que no se deshace.
- El mensaje de una excepción de un paso libre no se reporta (puede traer valores): `detalle` lleva solo su tipo. Un paso libre que quiera explicar un fallo devuelve `{"estado": "fallo", "detalle": …}` sin valores.
- Pruebas: la migración se prueba con su falla sembrada antes del gate de Fase 4 de su versión. Quién revisa en ese gate: `profiles/self-applied/roles.md` § "Subagentes por fase".
