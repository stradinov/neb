# Migraciones guiadas

Una versión de Neb que pide algo más que pasos de base (configurar la máquina, un paso que necesita al dev) trae aquí dos archivos con el nombre de su versión. Qué es una migración guiada, qué corre solo y qué pide al dev: [`../tooling/migrations.md`](../tooling/migrations.md) § "Migración guiada". Cuándo una versión la trae: [`../process/version-control.md`](../process/version-control.md) § "Flujo al cerrar REQ".

## Índice

| Versión | Pasos guiados | Qué hace |
|---|---|---|
| [7.3.0](7.3.0.md) | `compas-proyectos`, `vacuum-neb-db` | Pasa `compas.md` al eje proyecto y sin roadmap (`Clientes:` → `Proyectos:`, sin `Roadmap:`, `version: 3`) y compacta `neb.db` (`VACUUM`): se ofrece cada vez que la base acumula páginas libres (más de una cuarta parte y más de 1 MB) y conserva solo la copia previa más reciente |
| [7.4.0](7.4.0.md) | `compas-tema-proyecto` | Cambia en «- **Temas:**» de `compas.md` la cita `proyecto` por el slug al que el paso de base 3 movió ese tema (desde 7.4.0 el paso resuelve el choque de slug solo) |
| [8.0.0](8.0.0.md) | `mover-base`, `mover-respaldos`, `mover-compas`, `mover-planes`, `mover-research`, `mover-estado`, `mover-requisitos`, `fusionar-config` | Muda a la carpeta de datos (`NEB_DATA` o `~/.neb`) lo que Neb guardaba en `~/.claude`: la base (con respaldo, y deja en su lugar la base testigo), los respaldos, `compas.md`, los planes aprobados, `research/`, el estado del preproceso, el caché de sonidos y el «No volver a ofrecer» de la oferta de Python; junta los tres JSON de configuración en `config.json`. Corre todo solo |

## Formato

### `<X.Y.Z>.md` — el prompt

Lo lee Claude cuando sigue `/neb:migrate`: al correr el comando o por el encargo del aviso de migración del inicio de sesión. Dice qué cambia, en qué orden van los pasos, qué se le dice al dev (lo que el dev debe saber antes de elegir en el menú), cómo se verifica y qué se reporta. No relaja lo que fija `commands/migrate.md`.

### `<X.Y.Z>.py` — los pasos guiados

Define `STEPS`, una lista de `GuidedStep` (de `hooks/lib/_guided.py`, que el registro deja importable). El nombre del archivo es la versión semántica; otro nombre se ignora. Un archivo que falla al cargar se reporta y no detiene a los demás ni al inicio de sesión.

```python
from _guided import GuidedStep

STEPS = [
    # De catálogo: el paso es un dato (operación de hooks/lib/_machine.py y sus argumentos).
    GuidedStep("quitar-ejemplo-settings", "Quitar NEB_EJEMPLO de settings.json",
               op="settings_env_remove", args={"claves": ["NEB_EJEMPLO"], "secretas": []}),
    GuidedStep("quitar-ejemplo-entorno", "Quitar la variable de usuario NEB_EJEMPLO",
               op="user_env_remove", args={"nombre": "NEB_EJEMPLO"}),
    # Libre: detectar (solo lee) y aplicar propios. respaldo=True si aplicar deja con qué deshacerlo
    # y devuelve {"respaldo": <ruta>}; exclusivo=True si solo corre sin otra conexión a la base
    # (si no, queda pendiente y se reintenta; nunca se pide al dev cerrar sesiones).
    GuidedStep("renombrar-algo", "Renombrar algo", detectar=detectar, aplicar=aplicar,
               respaldo=True, exclusivo=True),
]
```

- `id`: minúsculas, dígitos y guiones, único en la versión. El id completo es `<X.Y.Z>:<id>`. Los argumentos de un paso de catálogo se validan al cargar.
- Un paso libre: `detectar(ctx)` solo lee y no llama a nada que escriba; `aplicar(ctx)` devuelve `{"respaldo": ruta, "detalle": texto}` o `{"estado": "sin-cambio" | "pendiente" | "manual" | "fallo", "detalle": texto}`. El respaldo que declara es un archivo nuevo, creado por `aplicar`, directamente en `~/.claude` o en la carpeta de respaldos (`<datos>/backups/`, que el paso recibe en `ctx.backups_dir`); si es una base SQLite, en `journal_mode=DELETE` (reglas completas en [`../tooling/migrations.md`](../tooling/migrations.md) § "Qué corre solo y qué pide al dev"). Un paso `exclusivo` vuelve a comprobar su condición con `ctx.exclusivo_ok()` (None si se cumple) justo antes de la acción que no se deshace. La condición por omisión mira `neb.db`; un paso que actúa sobre otro archivo declara la suya con `condicion=f(ctx)` (motivo o None).
- Las rutas, de `ctx` (`claude_dir`, `config_dir`, `legacy_dir`, `data_dir`, `db_path`, `backups_dir`), nunca armadas a mano: [`../tooling/migrations.md`](../tooling/migrations.md) § "Migración guiada".
- El mensaje de una excepción de un paso libre no se reporta (puede traer valores): `detalle` lleva solo su tipo. Un paso libre que quiera explicar un fallo devuelve `{"estado": "fallo", "detalle": …}` sin valores.
- Pruebas: la migración se prueba con su falla sembrada antes del gate de Fase 4 de su versión. Quién revisa en ese gate: `profiles/self-applied/roles.md` § "Subagentes por fase".
