---
name: wakeup
description: >
  Cargar cuando el usuario invoca /wakeup, pregunta cómo empezar con Neb, se identifica
  como usuario nuevo, o pide un tour guiado del setup y las capacidades. Corre el tour de
  bienvenida: presenta Neb, usa setup-workspace.sh para detectar/configurar el entorno (montar
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

### 2. Detectar el estado (vía script, no a mano)

Corré `bash "${NEB_HOME:-~/.claude/neb}/bootstrap/setup-workspace.sh" --dry-run` desde la raíz del repo de gobernanza. El script reporta qué hay y qué falta (repo de gobernanza, overlay, `personal/`, `NEB_HOME`, `~/CLAUDE.md`) **sin escribir nada**. Consumí su salida — no re-detectes la estructura por tu cuenta (el script es la fuente de verdad).

- Si el repo aún **no tiene `neb/`** (adoptante nuevo o dev legacy): guiá primero la instalación / `git subtree add` (user-guide § Instalar / Montar overlay), luego volvé a correr el `--dry-run`.
- Si ya está todo montado: pasá a las opciones restantes (no re-configures).

### 3. Ofrecer las opciones (ejecutar, no describir)

Presentar las acciones de adopción como opciones numeradas (formato de [`communication.md`](../../general/communication.md) § "Tono y forma"). Cada opción **ejecuta** los pasos de `user-guide.md` de forma interactiva, sin repetirlos en la conversación:

1. **Montar / configurar tu entorno** — preguntá el nombre del overlay si hay que crear uno (default `overlay`); corré `bash "$NEB_HOME/bootstrap/setup-workspace.sh" [--overlay <nombre>]` (sin `--dry-run`) para crear el scaffolding, setear `NEB_HOME` y verificar `~/CLAUDE.md`. Es el paso mínimo: sin overlay no hay dónde definir un stack. El ajuste de `~/.claude/settings.json` + hooks (`$NEB_HOME/hooks`) es manual — avisalo (ver [user-guide § Montar tu overlay](../../docs/user-guide.md)).
2. **Definir tu primer stack** — preguntar el dominio ("¿Python/ML, PHP/backend, React, iOS…?"), proponer nombre en kebab-case, cambiar a stack `stack-authoring` y guiar `init-stack-subproject.sh` **en el overlay**. Puede incluir skill de apoyo (`skill-authoring`) y agentes revisores.
3. **Versionar tu configuración personal** — seguir [user-guide § Versionar tu configuración personal](../../docs/user-guide.md).

### 4. Cierre

Confirmar lo que quedó montado (overlay, primer stack) y señalar 2 referencias sin abrumar:
- [`general/index.md`](../../general/index.md) — mapa de Neb.
- [`methodology/promises.md`](../../methodology/promises.md) — qué garantiza.

## Restricciones

- No leer ni mostrar archivos extensos durante el tour — solo nombrar paths y seguir user-guide.
- **No duplicar** los pasos de `user-guide.md` en la conversación — ejecutarlos refiriendo a la guía (la guía es la fuente única).
- **Delegá en `setup-workspace.sh`** para detectar y configurar el entorno: corré el script y leé su salida; no re-implementes su lógica de detección en la conversación.
- Mantener el tour conversacional — usar el formato de opciones numeradas de `communication.md`.
- No generar plan estructurado (tabla de archivos, SemVer, change MD) salvo que el usuario pida crear un stack/skill — ahí sí, seguir el flujo de `stack-authoring` o `skill-authoring`.
- Si el usuario quiere saltarse el tour e ir directo al trabajo, dejarlo — el tour es opt-in.
