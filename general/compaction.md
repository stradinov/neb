# Compact instructions

Al compactar una sesión de Neb, el resumen conserva con su valor literal:

- el REQ activo: su `active_<proyecto>_<slug>.md`, su change MD, la fase y el estado;
- cada OK del dev a un plan o a un gate (qué aprobó) y lo que sigue esperando OK;
- las decisiones del dev, con su motivo.

## Tras compactar

- El detalle se recupera del `active_*.md` y del change MD del REQ; del transcript, solo con búsquedas puntuales, nunca leyéndolo completo.
- Un OK que el resumen no registra no se da por dado: se vuelve a pedir.

Hoy lo cumple la compactación de Claude Code: esta sección le llega con el arranque (supuesto R22 de [`platform-assumptions.md`](../methodology/platform-assumptions.md)), y el tope de contexto que la dispara lo fija `autoCompactWindow` (R23).
