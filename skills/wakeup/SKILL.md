---
name: wakeup
description: >
  Cargar cuando el usuario invoca /wakeup, pregunta cómo empezar con Neb, se identifica
  como usuario nuevo, o pide un tour guiado del setup y las capacidades. Corre el tour de
  bienvenida: presenta Neb, usa setup-workspace.sh para detectar/configurar el entorno (montar
  overlay, definir el primer profile). NO cargar para preguntas técnicas concretas, tareas de
  implementación, ni cuando el usuario ya está trabajando en una tarea específica.
---

# Skill: wakeup

Guía de bienvenida para nuevos adoptantes de Neb. Objetivo: que el usuario entienda qué tiene en sus manos y deje montado el setup mínimo (overlay + primer profile) para trabajar. Los pasos canónicos viven en [`docs/user-guide.md`](../../docs/user-guide.md); este skill los **ejecuta de forma interactiva** — no los repite.

## Flujo del tour

### 1. Presentar (empezar directo, sin preguntar permiso)

Abrir con 2-3 oraciones:
- **Neb** es un sistema de trabajo con Claude Code que formaliza fases (clarificación → propuesta → implementación → validación) y genera artefactos trazables — no un generador de código autónomo.
- **Garantiza** comportamiento explícito (el agente no se salta fases), customizable (adaptar defaults vía `personal/<usuario>.md` sin forkear el núcleo) y expandible (agregar profiles y skills propios sin tocar el núcleo). Ver [`methodology/promises.md`](../../methodology/promises.md) para las promesas de Neb.

### 2. Detectar el estado (vía script, no a mano)

Resolvé el script con fallback (un miembro recién instalado no tiene `NEB_HOME`) y corré el dry-run:

```bash
NEB_SRC="${NEB_HOME:-${CLAUDE_PLUGIN_ROOT:-$(ls -d "$HOME"/.claude/plugins/cache/neb/neb/*/ 2>/dev/null | sort -V | tail -1)}}"
bash "$NEB_SRC/bootstrap/setup-workspace.sh" --dry-run
```

El script aplica la **cascada de detección** y reporta **sin escribir nada**. Consumí su salida — no re-detectes la estructura por tu cuenta (el script es la fuente de verdad):

- **Ya conectado** (`NEB_WORKSPACE` configurado y válido): confirmalo en una línea y pasá a las opciones restantes (no re-configures).
- **"Workspace existente detectado en `<dir>`"** (caso típico: el usuario clonó el repo workspace de su equipo y corre `/wakeup` desde el clon): ofrecé **"Conectar este workspace"** como opción primera — corre `--existing "<dir>"`: setea `NEB_WORKSPACE` y crea su `personal/<usuario>.md` si falta, sin tocar la estructura existente.
- **"Workspace(s) existente(s) encontrado(s) bajo `$HOME`"** (el cwd no era workspace; el script barrió `$HOME` con el mismo marker): con 1 resultado, ofrecé conectarlo; con varios, lista numerada para que el usuario elija — nadie teclea paths a mano.
- **Sin workspace** (ni en cwd ni en el barrido): preguntá si tiene uno en otra ruta (`--existing <ruta>`) o creá uno nuevo (opción 1 de abajo).

### 3. Ofrecer las opciones (ejecutar, no describir)

Presentar las acciones de adopción como opciones numeradas (formato de [`communication.md`](../../general/communication.md) § "Tono y forma"). Cada opción **ejecuta** los pasos de `user-guide.md` de forma interactiva, sin repetirlos en la conversación:

1. **Conectar / montar tu entorno** — si el paso 2 detectó un workspace existente, la acción es **conectarlo** (`--existing "<dir>"`). Si no, preguntá **dónde** crear el workspace: (default) `neb_workspace/` en el dir actual; `--base <dir>` para otra ubicación. Corré `bash "$NEB_SRC/bootstrap/setup-workspace.sh" [--base <dir> | --existing <dir>] [--overlay <nombre>]` (sin `--dry-run`): crea/conecta el scaffolding (overlay + `overlay/startup.md` + `personal/` + `changes/`), `personal/<username>.md` (username del SO) y **setea `NEB_WORKSPACE` en `~/.claude/settings.json` automáticamente** (merge no-destructivo, vía `set-neb-env.py`; `NEB_HOME` solo se persiste cuando no resuelve al cache del plugin). Bajo plugin los hooks ya vienen registrados; no hay que tocar settings.json a mano. Es el paso mínimo (ver [user-guide § Montar tu overlay](../../docs/user-guide.md)).
2. **Definir tu primer profile** — preguntar el dominio ("¿Python/ML, PHP/backend, React, iOS…?"), proponer nombre en kebab-case, cambiar a profile `profile-authoring` y guiar `init-profile-subproject.sh` **en el overlay**. Puede incluir skill de apoyo (`skill-authoring`) y agentes revisores.
3. **Versionar tu configuración personal** — seguir [user-guide § Versionar tu configuración personal](../../docs/user-guide.md).

### 4. Cierre

Confirmar lo que quedó montado/conectado (workspace, overlay, primer profile), recordar abrir una **sesión nueva** para que el hook tome el workspace, y señalar 2 referencias sin abrumar:
- [`general/index.md`](../../general/index.md) — mapa de Neb.
- [`methodology/promises.md`](../../methodology/promises.md) — qué garantiza.

## Restricciones

- No leer ni mostrar archivos extensos durante el tour — solo nombrar paths y seguir user-guide.
- **No duplicar** los pasos de `user-guide.md` en la conversación — ejecutarlos refiriendo a la guía (la guía es la fuente única).
- **Delegá en `setup-workspace.sh`** para detectar y configurar el entorno: corré el script y leé su salida; no re-implementes su lógica de detección en la conversación.
- Mantener el tour conversacional — usar el formato de opciones numeradas de `communication.md`.
- No generar plan estructurado (tabla de archivos, SemVer, change MD) salvo que el usuario pida crear un profile/skill — ahí sí, seguir el flujo de `profile-authoring` o `skill-authoring`.
- Si el usuario quiere saltarse el tour e ir directo al trabajo, dejarlo — el tour es opt-in.
