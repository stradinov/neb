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

## detect_stack retorna `unknown` o nombre incorrecto

**Síntomas**: `bash bootstrap/link-into-project.sh <dir>` imprime `Stack detectado: unknown` o el nombre de otro stack.

**Diagnóstico**:
1. Leer la función `detect_stack` en `bootstrap/link-into-project.sh` — verificar que existe el chequeo para `stack-authoring` (overlay `*/methodology/stacks/<X>/`).
2. Verificar el pattern regex: `grep -qE '/methodology/stacks/[^/]+(/|$)'` — el `[^/]+` asegura al menos un segmento de nombre de stack.
3. Si la heurística está presente pero retorna otro stack, revisar el orden de chequeos — el overlay de `stack-authoring` debe ir antes que la heurística de `self-applied` (`methodology/principles.md + process/plan-review.md`).

**Solución**: actualizar `detect_stack` en `bootstrap/link-into-project.sh` para que el overlay de `stack-authoring` esté en posición 2 (después de `reqs/` y antes de `skills/` y `self-applied`). Ver el orden canónico en `stacks/index.md`.

---

## CLAUDE.md del proyecto cliente no importa el stack tras link-into-project.sh

**Síntomas**: tras correr `bash bootstrap/link-into-project.sh <proyecto>`, el CLAUDE.md del proyecto no tiene `@~/.claude/neb/stacks/stack-authoring/index.md`.

**Diagnóstico**: `link-into-project.sh` genera el import `@.../stacks/$STACK/index.md` donde `$STACK` es el resultado de `detect_stack`. Si `detect_stack` retorna `unknown` o el nombre incorrecto, el import no se agrega.

**Solución**: primero corregir `detect_stack` (ver caso anterior). Luego re-correr `link-into-project.sh` — el script agrega imports faltantes sin sobreescribir el archivo.

---

## Regresión: otro stack deja de detectarse tras agregar stack-authoring

**Síntomas**: tras actualizar `detect_stack`, un proyecto que antes retornaba su stack de dominio ahora retorna `stack-authoring`.

**Diagnóstico**: el pattern del overlay `stack-authoring` es demasiado amplio y captura paths que no son subdirectorios de `methodology/stacks/`. Ejemplo: si el pattern es `/stacks/` en vez de `/methodology/stacks/`, un proyecto cliente con carpeta `/stacks/` activaría el overlay incorrectamente.

**Solución**: usar el path completo del repo en el pattern: `grep -qE '/methodology/stacks/[^/]+(/|$)'`. Probar con al menos dos proyectos cliente para confirmar que no hay regresión.

---

## Divergencia entre stacks/index.md y detect_stack

**Síntomas**: la tabla en `stacks/index.md` tiene la heurística correcta pero `bootstrap/link-into-project.sh` no la implementa (o viceversa).

**Diagnóstico**: cambios en la tabla sin actualizar el script, o actualización del script sin reflejar en la tabla.

**Solución**: actualizar ambos en el mismo commit. `stacks/index.md` es la single source of truth; `detect_stack` es la implementación. Ver nota en `stacks/index.md`: "Si la tabla cambia, actualizar `detect_stack` en el mismo commit."
