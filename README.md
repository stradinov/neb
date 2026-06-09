<!-- human -->
# Neb

> Un framework metodológico para Claude Code.

El nombre proviene de la [Nebuchadnezzar](https://matrix.fandom.com/wiki/Nebuchadnezzar), la nave desde la cual los personajes de Matrix operan en el mundo real.
Trabajar con Claude Code es como pilotar una nave: tú defines el rumbo y tomas las decisiones; Neb es la estructura que evita que la nave improvise.

---

## El problema que resuelve

Claude Code no ofrece una metodología incrustada. Sin ella, el agente improvisa, omite pasos de validación, pierde contexto entre sesiones y aplica criterios sin reglas explícitas. El resultado son cambios sin trazabilidad, decisiones sin registro y falta de contexto de cambios entre miembros del equipo.

Neb resuelve este problema ajustando el comportamiento de Claude a un mismo flujo de trabajo y administrando sus artefactos de manera abstracta, delegándote la definición tus proyecto en *stacks*.

En la práctica, defines un *stack* para cada tipo de proyecto: uno para el desarrollo de aplicaciones en web cierto lenguaje, otro para procesos de generación de documentos o un *stack* para el análisis y levantamiento de requerimientos en un dominio específico.


---
<!-- /human -->

## Cómo empezar

En Claude Code, agrega el marketplace e instala el plugin:

```
/plugin marketplace add stradinov/neb
/plugin install neb@neb
```

Reinicia Claude Code (o `/reload-plugins`) para activar el hook de arranque. Luego `/wakeup` monta tu *workspace* (tu overlay + configuración personal) y lo conecta.

> El hook `SessionStart` del plugin inyecta el arranque de Neb en cada sesión; no necesitas clonar el repo ni correr instaladores.

---

## Qué te da

* **Comportamiento explícito** — Claude sigue lineamientos predefinidos.
* **Aprobación en puntos críticos** — Ningún cambio relevante avanza sin tu validación explícita.
* **Consistencia entre sesiones y desarrolladores** — El método no varía según quién haya trabajado en la sesión anterior.
* **Adaptable al stack del proyecto** — Las reglas genéricas aplican a cualquier proyecto; las específicas del equipo se incorporan sin modificar el núcleo.
* **Adopción guiada** — El tour inicial (`/wakeup`) te lleva por el setup: montar tu capa propia y definir tu primer stack.
* **Trazabilidad completa** — Cada decisión queda documentada para auditorías, incorporación de nuevos integrantes o revisiones futuras.
* **Reflexivo** — Neb se aplica a sí mismo; cada modificación al framework ha seguido el mismo método que describe.

---



[Cómo funciona por dentro](docs/how-it-works.md) · [Guía del usuario](docs/user-guide.md) · [Contribuir](CONTRIBUTING.md) · [Licencia MIT](LICENSE)
