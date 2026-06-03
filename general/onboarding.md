# Onboarding / Adopción guiada

Política transversal. Define el comportamiento de Claude al detectar un usuario nuevo y la estructura del tour de bienvenida disponible vía `/welcome`.

## Trigger de oferta pasiva

**Condición**: el stack activo es `self-applied` (el cwd está en el repo del framework) Y el contexto de la sesión no incluye contenido de `personal/<usuario>.md` — sin sección de preferencias personales, atajos ni paths absolutos de la máquina del dev en el contexto cargado.

**Acción**: al cierre del primer turno que cumpla la condición, Claude agrega:

> "Para un tour del framework (3-5 min), invocá `/welcome`."

Sin preámbulo, sin interrumpir el trabajo. El tour es opt-in.

**Re-invocación**: `/welcome` corre el tour completo en cualquier momento y contexto, independientemente de si ya existe `personal/<usuario>.md`.

## Tour de bienvenida

Estructura que Claude sigue cuando corre el tour (vía `/welcome` o a pedido explícito).

### Paso 1 — Presentación

Describir el framework en 2-3 oraciones:
- **Qué es**: sistema de trabajo con Claude que formaliza fases (clarificación → propuesta → implementación → validación) y genera artefactos trazables (change MDs, plans, métricas).
- **Qué garantiza**: comportamiento explícito (todo vive en archivos versionables), customizable (adaptar defaults vía `personal/<usuario>.md` sin forkear el núcleo), expandible (stacks y skills propios sin tocar el núcleo), anti-desviación (Claude no se salta fases por falta de contexto). Lista completa en [`methodology/promises.md`](../methodology/promises.md).
- **Qué no es**: no un generador de código autónomo — es un framework de colaboración estructurada.

No pedir permiso para empezar. Presentar directo.

### Paso 2 — Nivel de adopción

Preguntar el contexto del usuario y proponer el nivel apropiado:

| Nivel | Qué activa | Cuándo elegirlo |
|---|---|---|
| **L1 — Arranque rápido** | Clarificación → Propuesta → Implementación → Validación | Solo-dev, proyectos personales, primera semana |
| **L2 — Gates** | L1 + revisores por dimensión + criterios de done | Código que va a producción, equipo pequeño |
| **L3 — Completo** | L2 + métricas, pendings, change MDs, versioning, Fase 9 | Equipo con múltiples proyectos activos |

Recomendar **L1 si el usuario es nuevo**. Al elegir un nivel:
1. Confirmar con 1 oración qué activa.
2. Ofrecer crear `personal/<usuario>.md` con el nivel bajo `## Nivel de adopción` — persiste la elección entre sesiones.

### Paso 3 — Primer stack o skill (opcional)

Preguntar: "¿Cuál es tu stack principal? Por ejemplo: Python/ML, PHP/backend, React, iOS, etc."

**Dominio descrito** → proponer nombre de stack en kebab-case → ofrecer `bash bootstrap/init-stack-subproject.sh <nombre>` → si acepta, cambiar stack activo a `stack-authoring` y guiar la creación (ver [`stacks/stack-authoring/index.md`](../stacks/stack-authoring/index.md)).

**Skill específico pedido** → proponer nombre → cambiar a `skill-authoring` → guiar creación de `skills/<nombre>/SKILL.md` (ver [`stacks/skill-authoring/index.md`](../stacks/skill-authoring/index.md)).

**Explorar primero** → señalar 3 archivos sin abrumar:
- [`general/index.md`](index.md) — mapa del framework
- [`methodology/promises.md`](../methodology/promises.md) — qué garantiza
- [`stacks/self-applied/index.md`](../stacks/self-applied/index.md) — ejemplo real de uso

Terminar el tour ahí y recordar que `/welcome` está disponible cuando quiera crear capacidades.

## Adopción incremental — ruta sugerida

Comunicar al finalizar el tour. No presionar a adoptar todo de una vez:

1. **L1** — el flujo básico funciona sin configuración adicional.
2. **`personal/<usuario>.md`** — para personalizar comportamientos (ver [`templates/personal.md.template`](../templates/personal.md.template)).
3. **L2/L3** — cuando el proyecto crezca o el equipo se incorpore.
4. **Stacks y skills** — cuando se identifiquen gaps repetitivos en el dominio.
