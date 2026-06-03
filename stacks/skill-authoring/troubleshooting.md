# Troubleshooting: skill-authoring

## Skill no aparece en `/skills`

**Síntomas:** El comando `/skills` en una sesión nueva no lista el skill esperado, o el skill no carga aunque el cwd sea cubierto por su `description`.

**Diagnóstico:**

1. Verificar que el skill está instalado en `~/.claude/skills/<nombre>/`:
   ```powershell
   # Windows
   Get-Item "$env:USERPROFILE\.claude\skills\<nombre>"
   ```
   ```bash
   # Linux/WSL
   ls -la ~/.claude/skills/<nombre>
   ```
2. Si no existe → re-correr `bootstrap/install-skills.sh`.
3. Si existe como copia (Windows, sin symlink) y la fuente fue modificada → re-correr el script.
4. Verificar que `SKILL.md` tiene frontmatter YAML válido (`name` + `description` sin syntax errors).
5. Verificar que el frontmatter no tiene tabs en lugar de espacios (YAML es estricto).

---

## Undertriggering: skill carga pero Claude no lo usa

**Síntomas:** `/skills` muestra el skill como cargado, pero Claude no consulta sus archivos hermanos ni menciona el vocabulario del skill al responder un prompt relevante.

**Diagnóstico:**

1. Clasificar si es undertriggering o sub-especificación:
   - **Undertriggering**: el skill está en contexto pero Claude no lo usó. El vocabulario estaba disponible.
   - **Sub-especificación**: el skill cargó pero no contenía la orientación necesaria para el prompt.
   Para distinguirlos: ¿la información estaba en el skill y Claude la ignoró, o simplemente no estaba?

2. Si es **undertriggering**:
   - Revisar el frontmatter `description`. ¿Es suficientemente "pushy"? ¿Menciona explícitamente el path/dominio del prompt?
   - Agregar verbos imperativos más directivos al `description`.
   - Agregar o reforzar negaciones para reducir ambigüedad contextual.
   - **No agregar contenido al skill** — el problema es de activación, no de contenido.

3. Si es **sub-especificación**:
   - Identificar qué vocabulario faltaba.
   - Agregar al archivo hermano correspondiente, siguiendo la restricción de contenido (`conventions.md`).
   - Agregar caso de regresión en `validation-prompts.md`.

---

## Overtriggering: skill carga en contexto equivocado

**Síntomas:** Un skill específico de un stack carga cuando se trabaja en otro proyecto fuera de su scope.

**Solución:**
1. Revisar el frontmatter `description`.
2. Agregar negación explícita: `NO usar para <proyecto> (<tecnología>)`.
3. Ser específico sobre el stack cubierto: indicar versión del framework, rutas de repos.

---

## Conflicto entre dos skills cargados simultáneamente

**Síntomas:** Dos skills dan indicaciones contradictorias, o uno sobreescribe el vocabulario del otro.

**Resolución:**
1. Verificar que los `description` de ambos skills tienen negaciones que los delimitan.
2. Si el conflicto es de contenido (vocabulario duplicado), mover el vocabulario compartido al skill más general y que el más específico lo referencie.
3. Si es inevitable que ambos carguen juntos, documentar la precedencia en el `SKILL.md` del más específico.

---

## Drift: contenido autogenerado desactualizado

**Síntomas:** Las tablas de clases/módulos/controllers del skill no reflejan el estado actual del código.

**Solución:**
1. Correr el script de regeneración:
   ```bash
   python ~/.claude/skills/<nombre>/scripts/regen-maps.py --all
   ```
2. Revisar el diff: solo deben cambiar las secciones entre marcadores `<!-- autogen-start/end -->`.
3. Commitear los baselines actualizados (solo el Skill Maintainer).

Si el script falla, ver los logs del script y verificar que los paths de los repos están correctos en la configuración.

---

## Regeneración falla (regen-maps.py)

**Síntomas:** El script Python lanza errores al intentar regenerar las tablas autogeneradas.

**Diagnóstico común:**
- El path configurado en el script no existe en la máquina local (ej. dev clonó el repo en path diferente al convencional `~/.claude/neb/`).
- Falta dependencia Python (verificar con `python --version` y las importaciones del script).
- El repo del proyecto no está clonado localmente.

**Workaround:** Si el script falla, las secciones autogeneradas pueden quedar marcadas como "(pendiente de regenerar)" temporalmente. El skill sigue funcionando con el contenido manual.
