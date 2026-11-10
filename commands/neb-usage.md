---
name: neb-usage
description: Gasto de tokens por REQ o por ventana de días, con subagentes, leído de los transcripts de Claude Code.
---

# /neb-usage — gasto de tokens

El usuario invocó `/neb-usage` (opcionalmente con argumentos). Corre el reporte del medidor de Neb y preséntalo.

Argumentos (`$ARGUMENTS`), los de `hooks/lib/usage-tracker.py report`:

- sin argumentos — los últimos 14 días, con el gasto por REQ;
- `--days N` — otra ventana;
- `--req <slug>` — solo el REQ `<slug>` (nombre de su change MD sin la fecha);
- `--write <change MD>` — además escribe el bloque de uso entre `<!-- usage-tracker-start -->` y `<!-- usage-tracker-end -->` del change MD (el slug sale de su nombre). Es el paso del Reporte de cierre ([`workflow/metrics.md`](../workflow/metrics.md) § "Tokens, costo y breakdown por modelo").

Resuelve el módulo (el clon de `NEB_HOME` si lo hay; si no, la raíz del plugin, que Claude Code sustituye al cargar este comando) y corre:

```bash
NEB_SRC="${NEB_HOME:-}"
case "$NEB_SRC" in ""|*/plugins/cache/*|*\\plugins\\cache\\*) NEB_SRC="${CLAUDE_PLUGIN_ROOT}" ;; esac
[ -f "$NEB_SRC/VERSION" ] || echo "Neb: no hay VERSION en '$NEB_SRC'. Si la ruta es la de NEB_HOME, corrígela; si quedó vacía, actualiza Claude Code (sustitución de CLAUDE_PLUGIN_ROOT en skills)" >&2
py "$NEB_SRC/hooks/lib/usage-tracker.py" report $ARGUMENTS   # o python / python3
```

Presenta la salida tal cual (ya es Markdown). Los USD son a precio de API, no el consumo del plan. Si el reporte dice que el total es parcial, nombra los modelos sin precio en `hooks/pricing.yml`.
