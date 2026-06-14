# Trazabilidad

Cómo se enlazan los artefactos del workflow para rastrear un requerimiento de extremo a extremo: del plan al commit, y de vuelta. Este documento **consolida y referencia** — los mecanismos detallados de cada artefacto viven en su propio archivo; aquí está el mapa que los une.

## Grafo de artefactos

El **requerimiento (REQ)** es la unidad de trabajo: un cambio lógico coherente con un objetivo, no un documento. El **Change MD** es su **registro** — la proyección documental versionada del REQ, en relación 1↔1. La cadena nominal de artefactos que registran un REQ:

```
Plan aprobado  →  Change MD  →  Confirmación / Entrega
   (opcional)   (registro; eje doc.)   (entregable; en git: commits)
```

El **Change MD** es el **eje documental**: registra al REQ y todo enlace entre artefactos pasa por él. El REQ es la unidad; el Change MD es lo que la registra. Cada artefacto se une al siguiente por un campo concreto:

| Desde | Campo de enlace | Hacia | Doc canónico |
|---|---|---|---|
| Plan aprobado | sección Trazabilidad → `**Plan aprobado:**` | Change MD | [approved-plans.md](approved-plans.md) |
| Change MD | `**Commits:**` (`<hash>` o rango `<a>..<b>`) | git | [changes.md](changes.md) |
| Change MD | `**Pendientes generados:**` (puntero por tag) | `pendings.md` | [pendings.md](pendings.md) |
| Memoria del proyecto | `Draft changes MD:` | Change MD (inverso) | [memory.md](memory.md) |
| Incidente | `Originado por:` | Change MD original (inverso) | [`../general/incidents.md`](../general/incidents.md) |
| Defecto (Fase 9) | tabla Diagnóstico → `REQ derivado` | REQ que lo corrige | [`../process/improvement.md`](../process/improvement.md) |

La estructura de la sección Trazabilidad del Change MD es canónica en [`../templates/change.md.template`](../templates/change.md.template).

### El plan aprobado: persistencia y direccionalidad

**Persistencia.** El artefacto en `~/.claude/approved-plans/` se persiste por **dos vías** (ver [approved-plans.md](approved-plans.md)): el hook `save-approved-plan.sh` al aprobar en plan mode, o un `Write` de Claude al aprobar **conversacionalmente** un plan media/alta. En consecuencia:

- **No opcional en media/alta**: todo plan de esa complejidad deja artefacto (por hook o por Write).
- **Ausente** en REQs **triviales** (una línea/texto, van directo a propuesta), **baja** (solo plan de pruebas) o **no-formales** (sin trigger de formalización) — ahí el campo es `**Plan aprobado:** —`. Ver [`../process/planning.md`](../process/planning.md) § "Cuándo aplica cada aprobación".

**Direccionalidad.** La trazabilidad plan↔Change MD es **unidireccional por diseño**:

- `Change MD → plan` **soportado**: campo `**Plan aprobado:**` (lo deja el hook en plan mode, o Claude en la vía conversacional).
- `plan → Change MD` **no soportado por diseño**: el artefacto del plan no apunta de vuelta. El Change MD es el **eje documental** (todo enlace pasa por él): se parte del Change MD para llegar al plan, no al revés. No es deuda — el hook persiste el plan antes de que el Change MD exista, así que no podría inyectar el enlace inverso, y el slug del plan y el `<nombre>` del Change MD pueden diferir (no se adoptó naming coordinado).

Por eso la **cadena mínima trazable es `Change MD → commits`**: el Change MD es el único eslabón (casi) siempre presente. "Plan aprobado" como *momento* (cuando nace el draft del Change MD, al entrar a Fase 4) es distinto del *artefacto* plan aprobado: el momento siempre ocurre; el artefacto existe en media/alta y se navega desde el Change MD.

## Eslabón Change MD ↔ confirmación del cambio

El último eslabón es la confirmación del cambio (ver [`../process/change-control-gate.md`](../process/change-control-gate.md)). En **profiles versionados con git** (cualquier profile de software/datos y `self-applied`) es el commit, y es bidireccional:

- **REQ → commit**: al cierre (Fase 8), el campo `**Commits:**` del Change MD se completa con el/los hash(es) — un hash único, un rango `<inicial>..<final>`, o una lista cuando los commits no son contiguos.
- **commit → REQ**: el mensaje del commit nombra el tipo y el tema del REQ (`tipo: descripción`, ver [`../process/version-control.md`](../process/version-control.md) "Commits"). Permite ir de un hash suelto al REQ sin partir del Change MD.

El draft del Change MD nace sin hashes (estado `En progreso`); el campo `**Commits:**` se llena cuando los commits ya existen. Mientras tanto, el cross-link inverso `Draft changes MD:` en la memoria del proyecto mantiene la trazabilidad de la sesión en curso.

## Proyecto único

Un Change MD en `<proyecto>/changes/<YYYY-MM-DD>-<nombre>.md`; el campo `**Commits:**` lista los hashes de **ese** repo. Es el caso por defecto.

## Multi-proyecto (cross-repo)

Cuando un requerimiento toca un repo central y/o varios proyectos sincronizados, sigue siendo **un solo REQ con un único Change MD que lo registra, en el repo central** — el registro no se duplica en cada proyecto. Su sección Trazabilidad lista los hashes **por repo**, porque cada proyecto recibe su propio commit (la réplica es un cherry-pick rehecho → hash distinto por repo, no el mismo).

```
- **Commits:**
  - proyecto-a `79c6e417c` · proyecto-b `09ef92bd` · proyecto-c `315fa000` · …
```

Así, `commit → REQ` desde cualquier proyecto se resuelve por el mensaje del commit (que nombra el REQ) y converge al único Change MD del repo central. No se crea un MD por proyecto: a cada requerimiento le corresponde un único Change MD que lo registra (1↔1), también cross-repo.

> La regla operativa de "dónde abrir el Change MD cross-repo" vive en el `CLAUDE.md` del repo central. Este documento es el modelo de trazabilidad que esa regla concreta.

## Trazabilidad por profile

La cadena hasta el commit aplica a profiles versionados con git. Para profiles cuyo entregable no es código (ej. `self-applied`, donde el entregable son archivos markdown de la metodología), el eslabón final no es un commit sino la **Entrega final** del profile en su vocabulario concreto (ver el glosario de [`../methodology/vocabulary.md`](../methodology/vocabulary.md) y `profiles/<profile>/index.md`). El Change MD sigue siendo el eje documental; cambia solo qué representa el último eslabón.

## Casos especiales

- **Incidentes en producción**: trazan al Change MD que originó el cambio vía `Originado por:`, y el Change MD original referencia de vuelta en "Resultado post-entrega" (ver [`../general/incidents.md`](../general/incidents.md)).
- **Defectos (Fase 9)**: la tabla "Diagnóstico de defectos" del Change MD enlaza cada defecto con el REQ derivado que lo corrige (ver [`../process/improvement.md`](../process/improvement.md)).
- **Reconstrucción retrospectiva**: para historia anterior a la adopción de la metodología, los cambios se documentan en `<proyecto>/changes_old/` (un MD por cambio lógico, derivado del historial git). Es un caso excepcional de trazabilidad hacia atrás, no parte del flujo normal.
