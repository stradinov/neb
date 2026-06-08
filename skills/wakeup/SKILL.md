---
name: wakeup
description: >
  Cargar cuando el usuario invoca /wakeup, pregunta cómo empezar con Neb, se identifica
  como usuario nuevo, o pide un tour guiado del setup y las capacidades. Corre el tour de
  bienvenida: presenta Neb, detecta el estado de la instalación y guía el setup (montar
  overlay, definir el primer stack). NO cargar para preguntas técnicas concretas, tareas de
  implementación, ni cuando el usuario ya está trabajando en una tarea específica.
---

# Skill: wakeup

Guía de bienvenida para nuevos adoptantes de Neb. Objetivo: que el usuario entienda qué tiene en sus manos y deje montado el setup mínimo (overlay + primer stack) para trabajar. Los pasos canónicos viven en [`docs/user-guide.md`](../../docs/user-guide.md); este skill los **ejecuta de forma interactiva** — no los repite.

## Flujo del tour

### 1. Presentar (empezar directo, sin preguntar permiso)

Abrir con 2-3 oraciones:
- **Neb** es un sistema de trabajo con Claude Code que formaliza fases (clarificación → propuesta → implementación → validación) y genera artefactos trazables — no un generador de código autónomo.
- **Garantiza** comportamiento explícito (el agente no se salta fases), customizable (adaptar defaults vía `personal/<usuario>.md` sin forkear el núcleo) y expandible (agregar stacks y skills propios sin tocar el núcleo). Ver [`methodology/promises.md`](../../methodology/promises.md) para las promesas de Neb.

### 2. Detectar el estado de la instalación

Antes de proponer pasos, verificar el estado y adaptar:
- **¿neb instalado?** (existe el clon + `~/CLAUDE.md` con los imports). Si no, guiar la instalación (user-guide § Instalar).
- **¿overlay montado?** (existe el repo de gobernanza con `neb/` como subtree + overlay). Si ya existe, no proponer montarlo de nuevo — saltar a las opciones restantes.
- **Instalación previa detectada** → ofrecer reinstalar/actualizar, o continuar con lo que falte.

### 3. Ofrecer las opciones (ejecutar, no describir)

Presentar las acciones de adopción como opciones numeradas (formato de [`communication.md`](../../general/communication.md) § "Tono y forma"). Cada opción **ejecuta** los pasos de `user-guide.md` de forma interactiva, sin repetirlos en la conversación:

1. **Montar tu overlay** — seguir [user-guide § Montar tu overlay](../../docs/user-guide.md). Es el paso mínimo: sin overlay no hay dónde definir un stack.
2. **Definir tu primer stack** — preguntar el dominio ("¿Python/ML, PHP/backend, React, iOS…?"), proponer nombre en kebab-case, cambiar a stack `stack-authoring` y guiar `init-stack-subproject.sh` **en el overlay**. Puede incluir skill de apoyo (`skill-authoring`) y agentes revisores.
3. **Versionar tu configuración personal** — seguir [user-guide § Versionar tu configuración personal](../../docs/user-guide.md).

### 4. Cierre

Confirmar lo que quedó montado (overlay, primer stack) y señalar 2 referencias sin abrumar:
- [`general/index.md`](../../general/index.md) — mapa de Neb.
- [`methodology/promises.md`](../../methodology/promises.md) — qué garantiza.

## Restricciones

- No leer ni mostrar archivos extensos durante el tour — solo nombrar paths y seguir user-guide.
- **No duplicar** los pasos de `user-guide.md` en la conversación — ejecutarlos refiriendo a la guía (la guía es la fuente única).
- Mantener el tour conversacional — usar el formato de opciones numeradas de `communication.md`.
- No generar plan estructurado (tabla de archivos, SemVer, change MD) salvo que el usuario pida crear un stack/skill — ahí sí, seguir el flujo de `stack-authoring` o `skill-authoring`.
- Si el usuario quiere saltarse el tour e ir directo al trabajo, dejarlo — el tour es opt-in.
