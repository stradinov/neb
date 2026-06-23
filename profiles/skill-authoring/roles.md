# Roles: skill-authoring

## Skill Author

**Rol principal.** Conduce Fases 1–4 del REQ.

**Responsabilidad:**
- Decide qué entra y qué no entra en el skill (aplica restricción de contenido de `conventions.md`).
- Diseña la estructura de archivos hermanos y el frontmatter.
- Escribe el contenido manual (vocabulario, gotchas, desambiguaciones).
- Es responsable de que el skill no replique código del repo.

**Fases activas:** 1 (clarificación), 2 (estimación), 3 (propuesta + plan), 4 (implementación).

**Decisiones exclusivas del Skill Author:**
- Qué contenido entra al skill (vocabulario y orientación sí; signaturas, SQL, números de línea no).
- Cuándo un archivo hermano es necesario vs cuándo el `SKILL.md` es suficiente.
- El frontmatter `description`: cuán "pushy" y qué negaciones incluir.

---

## Skill QA Engineer

**Revisor. Actúa en Fase 5 (Validación).**

**Implementación:** subagente — `agents/skill-qa-engineer.md`

**Responsabilidad:**
- Valida smoke load: confirma que el skill aparece en `/skills` en sesión nueva.
- Corre los casos afectados de `validation-prompts.md` y documenta resultados.
- Audita over-specification: revisa si el skill contiene signaturas, SQL, números de línea u otro contenido que debería eliminarse.
- Verifica que el `SKILL.md` cumple las convenciones de `conventions.md` (frontmatter, progressive disclosure, forma imperativa).

**Criterio de aprobación (Fase 5 passed):**
- Todos los casos de validación positivos pasan.
- Al menos 1 caso negativo pasa (skill no carga en contexto equivocado).
- Sin contenido que viole la restricción de contenido.

**No es su responsabilidad:** decidir el contenido ni el frontmatter — solo auditarlos.

---

## Skill Maintainer

**Revisor periódico.** No es un rol activo en cada REQ — se activa en:

1. **Comando manual en Fase 8**: si el REQ tocó código cubierto por el skill, correr `scripts/regen-maps.py --all` (o el flag pertinente).
2. **Revisión mensual**: revisar diff de autogen, hacer commit de baselines a main.
3. **Distribución**: el cambio viaja en el plugin; los adoptantes hacen `claude plugin update` (o reinstalan); `/reload-plugins` para tomar cambios sin reiniciar.

**Único autorizado** para hacer commit de cambios a las secciones autogeneradas (`<!-- autogen-start/end -->`).

Asignado en `personal/<usuario>.md`.

---

## Default en `process/roles-invocation.md`

| Profile | Rol principal | Revisores default |
|---|---|---|
| `skill-authoring` | Skill Author | Skill QA Engineer (Fase 5) + Skill Maintainer (periódico) |

## Subagentes por fase

| Fase | Subagente | Estado |
|---|---|---|
| 3 Plan-review | `skill-qa-engineer` | ✅ disponible |
| 4 Cierre (gate) | `skill-qa-engineer` — audita frontmatter, over-specification, ambigüedad en SKILL.md | ✅ disponible |
| 5 Validación | `skill-qa-engineer` — smoke load, casos positivos/negativos, restricción de contenido | ✅ disponible |
| 7 Pre-ejecución (gate) | `skill-qa-engineer` — verifica description preciso, ejemplos consistentes con body, pre-merge | ✅ disponible |
| 9 Improvement | `process-improvement-analyst` (universal) | ✅ disponible |
| Incidentes | `process-improvement-analyst` (universal) | ✅ disponible |
