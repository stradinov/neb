# Troubleshooting (stack: stack-authoring)

## cwd en `stacks/` (raíz) activa `self-applied` en vez de `stack-authoring`

**Síntomas**: Claude anuncia `[stack: none → self-applied]` al hacer `cd stacks/` desde la raíz del repo.

**Por qué ocurre**: el pattern del overlay es `*/methodology/stacks/[^/]+(/|$)` — requiere al menos un segmento de nombre de stack (`[^/]+`). El directorio `stacks/` sin subdirectorio no matchea la fila de `stack-authoring` y cae a la heurística estructural de `self-applied`.

**¿Es un error?** No — al estar en la raíz de `stacks/`, no estás editando un stack específico. `self-applied` es el stack correcto para esa posición.

**Solución si se quería `stack-authoring`**: hacer `cd stacks/<nombre>` para entrar al directorio del stack concreto.

---

## Stack no se detecta en sesión Claude

**Síntomas**: Claude no anuncia `[stack: none → stack-authoring]` al entrar a `stacks/<nombre>/`.

**Diagnóstico**:
1. Verificar que la fila existe en `stacks/index.md` tabla "Heurística de detección".
2. Verificar que la fila de `stack-authoring` está ANTES que la de `self-applied` en la tabla (primer match gana).
3. Verificar que el cwd real incluye el segmento `/stacks/<nombre>/` en el path — si el cwd es la raíz del repo, activa `self-applied`, no `stack-authoring`.

**Solución**: mover la fila de `stack-authoring` antes de `self-applied` en `stacks/index.md` si está mal ordenada. Si el cwd es la raíz del repo, hacer `cd stacks/<nombre>` para activar el overlay.

---

## El stack activo es incorrecto o `none` en un directorio cubierto

**Síntomas**: al abrir una sesión Claude en `stacks/<nombre>/`, el stack activo anunciado es otro o `none`.

**Diagnóstico**:
1. Verificar que existe la fila para `stack-authoring` (overlay `*/methodology/stacks/<X>/`) en la tabla "Heurística de detección" de `stacks/index.md`.
2. Verificar el pattern regex: `/methodology/stacks/[^/]+(/|$)` — el `[^/]+` asegura al menos un segmento de nombre de stack.
3. Si la heurística está presente pero activa otro stack, revisar el orden — el overlay de `stack-authoring` debe ir antes que la heurística de `self-applied` (`methodology/principles.md + process/plan-review.md`).

**Solución**: corregir la heurística en `stacks/index.md` + `general/stack-detection.md` (Claude la lee en runtime) para que el overlay de `stack-authoring` esté en posición 2 (después de `reqs/` y antes de `skills/` y `self-applied`). Ver el orden canónico en `stacks/index.md`.

---

## Regresión: otro stack deja de detectarse tras agregar stack-authoring

**Síntomas**: tras actualizar la heurística, un proyecto que antes activaba su stack de dominio ahora activa `stack-authoring`.

**Diagnóstico**: el pattern del overlay `stack-authoring` es demasiado amplio y captura paths que no son subdirectorios de `methodology/stacks/`. Ejemplo: si el pattern es `/stacks/` en vez de `/methodology/stacks/`, un proyecto cliente con carpeta `/stacks/` activaría el overlay incorrectamente.

**Solución**: usar el path completo del repo en el pattern: `/methodology/stacks/[^/]+(/|$)`. Probar con al menos dos proyectos cliente para confirmar que no hay regresión.

---

## Divergencia entre stacks/index.md y general/stack-detection.md

**Síntomas**: la tabla en `stacks/index.md` tiene la heurística correcta pero `general/stack-detection.md` no la refleja (o viceversa).

**Diagnóstico**: cambios en la tabla sin actualizar la política de detección runtime, o viceversa.

**Solución**: actualizar ambos en el mismo commit. `stacks/index.md` es la single source of truth de la heurística; `general/stack-detection.md` define cuándo y cómo Claude la aplica en runtime. Ver nota en `stacks/index.md`.
