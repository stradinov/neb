# Arranque

Punto de entrada de la metodología. Reúne vía `@import` las reglas operativas que Claude aplica **desde el primer prompt**, independientes de fase. Esas reglas están completas en el contexto antes de la primera respuesta de cada sesión. Hoy las entrega el hook `SessionStart` del plugin, en partes que caben en el tope de salida de la plataforma (supuesto R1 de [`platform-assumptions.md`](../methodology/platform-assumptions.md)). Reemplaza la antigua sección declarativa "lectura obligatoria al iniciar sesión".

@communication.md
@correspondence.md
@profile-detection.md
@../process/phase-transitions.md
@onboarding.md
@../workflow/index.md

---

Mapa de la metodología (orden de lectura, capas del repo, flujo de fases): ver [`index.md`](index.md) — referencia de navegación on-demand, no se carga al arranque.
