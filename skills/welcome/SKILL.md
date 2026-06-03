---
name: welcome
description: >
  Cargar cuando el usuario invoca /welcome, pregunta cómo empezar con el framework, se identifica
  como usuario nuevo, o pide un tour guiado de las fases y capacidades. Corre el tour de bienvenida:
  presenta el framework, ayuda a elegir nivel de adopción (L1/L2/L3) y ofrece crear el primer stack
  o skill. NO cargar para preguntas técnicas concretas, tareas de implementación, ni cuando el
  usuario ya está trabajando en una tarea específica.
---

# Skill: welcome

Guía de bienvenida para nuevos adoptantes del framework. Objetivo: que el usuario entienda qué tiene en sus manos en 3-5 minutos, elija cómo adoptarlo y, si quiere, cree sus primeras capacidades propias.

## Flujo del tour

### 1. Presentar (empezar directo, sin preguntar permiso)

Abrir con 2-3 oraciones:
- **El framework** es un sistema de trabajo con Claude que formaliza fases (clarificación → propuesta → implementación → validación) y genera artefactos trazables — no un generador de código autónomo.
- **Garantiza** comportamiento explícito (el agente no se salta fases), customizable (adaptar defaults vía `personal/<usuario>.md` sin forkear el núcleo) y expandible (agregar stacks y skills propios sin tocar el núcleo). Ver [`methodology/promises.md`](../../methodology/promises.md) para las 11 promesas.
- **No requiere** configuración inicial — L1 funciona out-of-the-box.

### 2. Elegir nivel de adopción

Preguntar el contexto y proponer el nivel adecuado:

| Nivel | Incluye | Para quién |
|---|---|---|
| L1 — Arranque rápido | Clarificación → Propuesta → Implementación → Validación | Solo-dev, primera semana |
| L2 — Gates | L1 + revisores por dimensión + criterios de done | Código en producción, equipo pequeño |
| L3 — Completo | L2 + métricas, pendings, change MDs, versioning, Fase 9 | Equipo, múltiples proyectos |

Recomendar L1 explícitamente si el usuario es nuevo al framework. Al elegir:
1. Confirmar con 1 oración qué activa ese nivel.
2. Ofrecer crear `personal/<usuario>.md` con el nivel bajo `## Nivel de adopción` — persiste entre sesiones.

### 3. Crear el primer stack o skill (opcional)

Preguntar: "¿Cuál es tu stack principal? Por ejemplo: Python/ML, PHP/backend, React, iOS, etc."

**Dominio descrito** → proponer nombre en kebab-case → ofrecer `bash bootstrap/init-stack-subproject.sh <nombre>` → si acepta, cambiar a stack `stack-authoring` y guiar la creación.

**Skill específico** → proponer nombre → cambiar a `skill-authoring` → guiar creación de `skills/<nombre>/SKILL.md`.

**Explorar primero** → señalar 3 archivos sin abrumar:
- [`general/index.md`](../../general/index.md) — mapa del framework
- [`methodology/promises.md`](../../methodology/promises.md) — qué garantiza
- [`stacks/self-applied/index.md`](../../stacks/self-applied/index.md) — ejemplo real de uso

### 4. Cierre — adopción incremental

Terminar con 4 bullets:
1. Usá **L1** en tu próxima tarea — funciona sin config adicional.
2. Creá **`personal/<usuario>.md`** cuando quieras personalizar (ver [`templates/personal.md.template`](../../templates/personal.md.template)).
3. Subí a **L2/L3** cuando el proyecto crezca.
4. Creá **stacks y skills** cuando identifiques gaps repetitivos en tu dominio.

## Restricciones

- No leer ni mostrar archivos extensos durante el tour — solo nombrar paths.
- No generar plan estructurado (tabla de archivos, SemVer, change MD) a menos que el usuario pida crear un stack/skill — ahí sí, seguir el flujo de `stack-authoring` o `skill-authoring`.
- Mantener el tour conversacional — sin tablas pesadas salvo la de niveles de adopción.
- Si el usuario quiere saltarse el tour e ir directo al trabajo, dejarlo — el tour es opt-in.
