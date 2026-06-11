# Estándares de código

Criterios de calidad que el implementador aplica al producir código. El proceso los consulta en Fase 4 (ver [`../process/execution.md`](../process/execution.md)); cada profile los concreta en `profiles/<profile>/conventions.md`.

> **Punto de customización**: estos estándares son el baseline genérico. Un adoptante los adapta a su lenguaje y a los artefactos que ya maneja (linters, formatters, convenciones de su framework) declarando los específicos en `profiles/<profile>/conventions.md` o `personal/<usuario>.md`. Esta capa define el *qué*; el profile define el *cómo* para su tecnología.

## Baseline

- **Sin comentarios** salvo que el WHY sea no obvio (workaround, invariante oculta, comportamiento sorprendente).
- **Sanitizar en fronteras del sistema**: validar y escapar inputs externos según las convenciones del profile (ver `profiles/<profile>/conventions.md`).
- **Sin features ni refactors no pedidos**.
- **Sin backwards-compat innecesario** (vars renombradas con `_`, re-exports, comentarios "// removed").
