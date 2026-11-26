# research/

Investigaciones cuyo propósito o hallazgos afectan directamente a **la metodología misma** (stacks, convenciones, lineamientos, principios), versionadas junto a este repo. Útil sobre todo para contribuciones al framework.

Dónde guardar un research según su alcance:

- **Sobre la metodología / el framework** → aquí (`research/`), versionado con el repo.
- **Sobre un proyecto que usa el framework** → `<proyecto>/research/`, versionado en el repo del proyecto.
- **Cross-proyecto o exploratorio sin dueño** → `<datos>/research/` (no versionado, local del dev). `<datos>` es la carpeta de datos de Neb: `NEB_DATA` si es una ruta absoluta; si no, `~/.neb`. Ruta exacta: `neb_paths.py path research` (`hooks/lib/`).

Ver convenciones de formato, trazabilidad y citación en [`profiles/research/conventions.md`](../profiles/research/conventions.md).
