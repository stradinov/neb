---
name: neb-usage
description: Gasto de tokens por REQ o por ventana de días, con subagentes; con `plugins`, audita los plugins activos (peso contra uso) y, con OK, los apaga o pasa sus skills a name-only.
---

# /neb-usage — gasto de tokens y auditoría de plugins

El usuario invocó `/neb-usage` (opcionalmente con argumentos). Si el primer argumento es `plugins`, sigue § "Modo `plugins`"; si no, § "Modo `report`".

Resuelve el módulo (el clon de `NEB_HOME` si lo hay; si no, la raíz del plugin, que Claude Code sustituye al cargar este comando):

```bash
NEB_SRC="${NEB_HOME:-}"
case "$NEB_SRC" in ""|*/plugins/cache/*|*\\plugins\\cache\\*) NEB_SRC="${CLAUDE_PLUGIN_ROOT}" ;; esac
[ -f "$NEB_SRC/VERSION" ] || echo "Neb: no hay VERSION en '$NEB_SRC'. Si la ruta es la de NEB_HOME, corrígela; si quedó vacía, actualiza Claude Code (sustitución de CLAUDE_PLUGIN_ROOT en skills)" >&2
```

## Modo `report`

Argumentos (`$ARGUMENTS`), los de `hooks/lib/usage-tracker.py report`:

- sin argumentos — los últimos 14 días, con el gasto por REQ;
- `--days N` — otra ventana;
- `--req <slug>` — solo el REQ `<slug>` (nombre de su change MD sin la fecha);
- `--write <change MD>` — además escribe el bloque de uso entre `<!-- usage-tracker-start -->` y `<!-- usage-tracker-end -->` del change MD (el slug sale de su nombre). Es el paso del Reporte de cierre ([`workflow/metrics.md`](../workflow/metrics.md) § "Tokens, costo y breakdown por modelo").

```bash
py "$NEB_SRC/hooks/lib/usage-tracker.py" report $ARGUMENTS   # o python / python3
```

Presenta la salida tal cual (ya es Markdown). Los USD son a precio de API, no el consumo del plan. Si el reporte dice que el total es parcial, nombra los modelos sin precio en `hooks/pricing.yml`.

## Modo `plugins`

Argumentos tras `plugins`: `--days N` (por defecto 90), `--settings <archivo>` (por defecto el `settings.json` del dir de config: `CLAUDE_CONFIG_DIR` o `~/.claude`) y `--projects <dir>` (los transcripts).

```bash
py "$NEB_SRC/hooks/lib/usage-tracker.py" plugins $REST   # $REST = los argumentos después de `plugins`; o python / python3
```

Es de solo lectura. Presenta la tabla y los candidatos tal cual. Sin candidatos, termina ahí.

Con candidatos, ofrece un menú de selección por candidato (§ "Elecciones" de `general/communication.md`), en el orden del reporte. Cada menú lleva una línea de premisa con lo medido (peso, usos y último uso en la ventana); si los avisos de la salida dicen que un settings de proyecto del cwd declara ese plugin, la premisa lo dice también, porque ese valor gana y el cambio no rige en este proyecto. Las opciones, la que coincide con el veredicto primero y marcada «(Recomendado)»:

- **«Desactivarlo»** — *Claude pone `enabledPlugins.<id>` en `false`. Se va todo el plugin: sus skills, agentes y comandos y, si el reporte los nombra, sus MCP, hooks y LSP (p. ej. los hooks de seguridad `PreToolUse` de aws-core). Se revierte volviendo la clave a `true`.*
- **«Pasar sus skills a name-only»** — *solo si el plugin tiene skills. Claude pone `skillOverrides["<plugin>:<skill>"] = "name-only"` por cada skill. MCP, agentes, comandos y hooks siguen; los skills se listan sin descripción, así que dejan de cargarse solos por su descripción (siguen por nombre). Libera lugar en el listado de skills; baja tokens solo si el total del listado queda bajo el tope que aplica Claude Code (`[asumido]`: el tope y el recorte no tienen fila en los supuestos). Que `skillOverrides` reconozca el nombre calificado está sin verificar (supuesto R24): se comprueba en la sesión siguiente. Se revierte borrando esas claves.*
- **«Dejarlo»** — *no cambia nada.*

Las etiquetas son la respuesta del dev; la descripción nombra a Claude como quien escribe el settings. Si el veredicto es «desactivar», la recomendada es «Desactivarlo»; si es «name-only», «Pasar sus skills a name-only». La razón de la recomendada va en su descripción, con el dato medido («cero usos en 90 días», «99 usos MCP y cero cargas de skill»).

Con la opción elegida (y solo con ella; «Dejarlo» no corre nada), con el mismo `--settings` que se le dio a `plugins`, si se dio:

```bash
py "$NEB_SRC/hooks/lib/usage-tracker.py" apply <id> disable [--settings <archivo>]     # o: apply <id> name-only; o python / python3
```

`apply` es la única escritura: relee el settings justo antes, cambia solo esas claves y deja igual el contenido ajeno (reescribe el formato con la sangría detectada); rechaza `neb@*` y los plugins que no están en `true`. Tras aplicar, avisa en una línea que rige al abrir una sesión nueva (supuesto R25 de [`methodology/platform-assumptions.md`](../methodology/platform-assumptions.md)) y, si la salida lo trae, que un settings de proyecto del cwd declara ese plugin y su valor gana al de usuario.
