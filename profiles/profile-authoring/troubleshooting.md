# Troubleshooting (profile: profile-authoring)

## cwd en `profiles/` (raíz) activa `self-applied` en vez de `profile-authoring`

**Síntomas**: Claude anuncia `[profile: none → self-applied]` al hacer `cd profiles/` desde la raíz del repo.

**Por qué ocurre**: el pattern del overlay es `*/methodology/profiles/[^/]+(/|$)` — requiere al menos un segmento de nombre de profile (`[^/]+`). El directorio `profiles/` sin subdirectorio no matchea la fila de `profile-authoring` y cae a la heurística estructural de `self-applied`.

**¿Es un error?** No — al estar en la raíz de `profiles/`, no estás editando un profile específico. `self-applied` es el profile correcto para esa posición.

**Solución si se quería `profile-authoring`**: hacer `cd profiles/<nombre>` para entrar al directorio del profile concreto.

---

## Profile no se detecta en sesión Claude

**Síntomas**: Claude no anuncia `[profile: none → profile-authoring]` al entrar a `profiles/<nombre>/`.

**Diagnóstico**:
1. Verificar que la fila existe en `profiles/index.md` tabla "Heurística de detección".
2. Verificar que la fila de `profile-authoring` está ANTES que la de `self-applied` en la tabla (primer match gana).
3. Verificar que el cwd real incluye el segmento `/profiles/<nombre>/` en el path — si el cwd es la raíz del repo, activa `self-applied`, no `profile-authoring`.

**Solución**: mover la fila de `profile-authoring` antes de `self-applied` en `profiles/index.md` si está mal ordenada. Si el cwd es la raíz del repo, hacer `cd profiles/<nombre>` para activar el overlay.

---

## El profile activo es incorrecto o `none` en un directorio cubierto

**Síntomas**: al abrir una sesión Claude en `profiles/<nombre>/`, el profile activo anunciado es otro o `none`.

**Diagnóstico**:
1. Verificar que existe la fila para `profile-authoring` (overlay `*/methodology/profiles/<X>/`) en la tabla "Heurística de detección" de `profiles/index.md`.
2. Verificar el pattern regex: `/methodology/profiles/[^/]+(/|$)` — el `[^/]+` asegura al menos un segmento de nombre de profile.
3. Si la heurística está presente pero activa otro profile, revisar el orden — el overlay de `profile-authoring` debe ir antes que la heurística de `self-applied` (`methodology/principles.md + process/plan-review.md`).

**Solución**: corregir la heurística en `profiles/index.md` + `general/profile-detection.md` (Claude la lee en tiempo de ejecución) para que el overlay de `profile-authoring` esté en posición 2 (después de `reqs/` y antes de `skills/` y `self-applied`). Ver el orden canónico en `profiles/index.md`.

---

## Regresión: otro profile deja de detectarse tras agregar profile-authoring

**Síntomas**: tras actualizar la heurística, un proyecto que antes activaba su profile de dominio ahora activa `profile-authoring`.

**Diagnóstico**: el pattern del overlay `profile-authoring` es demasiado amplio y captura paths que no son subdirectorios de `methodology/profiles/`. Ejemplo: si el pattern es `/profiles/` en vez de `/methodology/profiles/`, un proyecto cliente con carpeta `/profiles/` activaría el overlay incorrectamente.

**Solución**: usar el path completo del repo en el pattern: `/methodology/profiles/[^/]+(/|$)`. Probar con al menos dos proyectos cliente para confirmar que no hay regresión.

---

## Divergencia entre profiles/index.md y general/profile-detection.md

**Síntomas**: la tabla en `profiles/index.md` tiene la heurística correcta pero `general/profile-detection.md` no la refleja (o viceversa).

**Diagnóstico**: cambios en la tabla sin actualizar la política de detección runtime, o viceversa.

**Solución**: actualizar ambos en el mismo commit. `profiles/index.md` es la single source of truth de la heurística; `general/profile-detection.md` define cuándo y cómo Claude la aplica en tiempo de ejecución. Ver nota en `profiles/index.md`.
