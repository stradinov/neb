# Research — Empaquetado del plugin neb (spike F2.0)

**Fecha:** 2026-06-09
**REQ:** `neb-plugin-empaquetado` (REQ-2)
**Tipo:** spike de empaquetado (gate menor)
**Veredicto:** **GO** — estructura resuelta (`source: github`); una decisión revertida (`autoUpdate` no es del autor).

## Validado con `claude plugin validate` + `claude --plugin-dir` (CLI 2.1.153)

| # | Punto | Resultado |
|---|---|---|
| 1 | **Estructura marketplace + plugin** | `source: "."` (plugin en la raíz) → **INVÁLIDO** ("Invalid input"). Válidos: (a) subdir `source: "./plugin"` (requeriría mover todo neb a un subdir); (b) **`source: {"source":"github","repo":"stradinov/neb"}`** → **VÁLIDO**. neb usa (b): el repo raíz lleva `.claude-plugin/{plugin.json, marketplace.json}` y el marketplace apunta al propio repo en GitHub. Sin reestructurar. |
| 2 | **`autoUpdate` en marketplace.json** | **Campo DESCONOCIDO** — warning "Unknown field 'autoUpdate'. Claude Code ignores it at load time." → **el autor NO puede forzar auto-update**; lo controla el usuario (`/plugin`, terceros vienen OFF). **Revierte la decisión "autoUpdate ON por defecto".** Se documenta cómo el usuario lo activa. |
| 3 | **`userConfig` → hook** | `userConfig.username` valida en `plugin.json`. Con `CLAUDE_PLUGIN_OPTION_USERNAME=testuser` el hook leyó `username=testuser`; sin la env, `<none>`. El mecanismo username→env→hook funciona (la captura interactiva en `/plugin install` no se prueba headless, pero el acceso sí). |
| 4 | **`${CLAUDE_PLUGIN_ROOT}`** | Disponible en el hook (= ruta del plugin). ✓ |
| 5 | **additionalContext** | stdout crudo del hook se inyecta (validado en F0). ✓ |
| 6 | **`claude plugin validate`** | Gate de empaquetado: valida `plugin.json` (incl. `userConfig`) y `marketplace.json` (incl. `source`). Útil en verificación/CI. |

## Implicaciones para REQ-2

- **plugin.json + marketplace.json en la raíz de neb**; `marketplace.json.plugins[0].source = {"source":"github","repo":"stradinov/neb"}`.
- **Flujo del adoptante**: `/plugin marketplace add stradinov/neb` → `/plugin install neb@neb-marketplace` → `/reload-plugins`. (Clona el repo para el marketplace y otra vez para el plugin desde GitHub — redundancia aceptable; evita reestructurar.)
- **auto-update**: no forzable por el autor → el user-guide documenta que el adoptante lo activa desde `/plugin` si lo desea.
- **username**: `userConfig.username` en `plugin.json`; wakeup lee `CLAUDE_PLUGIN_OPTION_USERNAME` para `personal/<username>.md`.

> Reproducibilidad: plugin de prueba en un dir scratch fuera del workspace (borrado). `claude plugin validate <dir>` para los manifests; `CLAUDE_PLUGIN_OPTION_X=val claude -p "..." --plugin-dir <dir> --setting-sources project` para confirmar que la env var llega al hook.
