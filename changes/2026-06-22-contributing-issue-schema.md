# CONTRIBUTING reorientado a issues + esquema de descripción de defecto

**Estado:** En validación
**Fecha inicio:** 2026-06-22
**Fecha cierre:** —
**Complejidad estimada:** baja
**Complejidad real:** —
**Riesgo de regresión:** bajo  <!-- docs + infra de GitHub (issue forms); sin cambio en núcleo de metodología ni imports -->

## Contexto

El `CONTRIBUTING.md` planteaba un esquema de contribución **falso**: describía un flujo fork → rama → registrar en `changelog.d/` → bump SemVer → Pull Request como si lo ejecutara un contribuyente externo. En realidad ese flujo es **ceremonia interna del mantenedor** (el núcleo se mantiene con push directo bajo el profile `self-applied`); Neb no opera con PRs externos. El único punto realista que aplicaba a un externo era "abre un issue".

El dev pidió convertir ese punto en el canal único y que los issues se den de alta en GitHub **cumpliendo un esquema claro de descripción de defecto**.

## Alcance

### Entra
- **`CONTRIBUTING.md`** — reescritura. Elimina fork/rama/`changelog.d`/SemVer/PR del lado del contribuyente. Establece el canal único (abrir un issue), explica el modelo real (núcleo mantenido por el equipo, self-applied, sin PRs externos) y el triage post-issue. Conserva la regla "sin PII/datos de cliente/marcas/rutas absolutas" reubicada en "Qué hace un buen reporte".
- **`.github/ISSUE_TEMPLATE/01-defecto.yml`** — GitHub issue form con el esquema de defecto: resumen (BLUF), componente, versión, entorno, observado (hechos) vs esperado, pasos, evidencia, hipótesis de causa (marcada como tal), severidad/impacto, confirmaciones. Refleja `methodology/principles.md` § "Suposiciones explícitas" (separa hechos de hipótesis). La escala de impacto (Bloqueante/Fricción/Cosmético) está **inspirada** en P1/P2 de `general/incidents.md` y adaptada a tres niveles para triage de issues — no es una correspondencia directa (el nivel "Cosmético" en `incidents.md` iría a backlog normal, no es incidente).
- **`.github/ISSUE_TEMPLATE/02-mejora.yml`** — issue form de propuesta de mejora/fricción/gap.
- **`.github/ISSUE_TEMPLATE/config.yml`** — `blank_issues_enabled: false` + enlaces a docs y discusiones.
- Gobernanza: `changelog.d/5.7.0.md`, bump `VERSION` 5.6.0 → 5.7.0, sync `.claude-plugin/plugin.json`.

### No entra
- `CODE_OF_CONDUCT.md` formal (se mantiene como pendiente declarado en el propio CONTRIBUTING).
- Creación de las labels `defecto` / `mejora` en GitHub (acción del mantenedor en la UI; las plantillas las referencian — si no existen, GitHub simplemente no las aplica).
- (Verificado 2026-06-22) GitHub Discussions está habilitado en `stradinov/neb` (`has_discussions: true`) — el `contact_link` de `config.yml` resuelve; no requiere acción del mantenedor.
- Plantilla de "pregunta/duda" (el dev eligió defecto + mejora; las dudas se canalizan vía Discussions desde `config.yml`).
- Cambios al flujo interno self-applied (no se toca; el CONTRIBUTING solo lo describe).

## Plan de pruebas

- [ ] Sintaxis YAML válida en los 3 archivos de `.github/ISSUE_TEMPLATE/` (estructura de GitHub issue forms: `name`/`description`/`body` con `type` válidos).
- [ ] `CONTRIBUTING.md` no conserva ninguna instrucción de fork/PR/bump/SemVer dirigida al contribuyente.
- [ ] Un defecto de documentación se puede reportar sin inventar versión/entorno (esos campos + pasos son `required: false`); quedan obligatorios solo resumen, componente, observado, esperado, severidad y confirmaciones.
- [ ] Enlaces internos del `CONTRIBUTING.md` resuelven (`README.md`, `docs/user-guide.md`, `CLAUDE.md`).
- [ ] `assemble-changelog.py --check` verde con 5.7.0; `VERSION` == `.claude-plugin/plugin.json`.
- [ ] Revisión de roles (self-applied) sin hallazgos bloqueantes.

> Riesgo bajo → checklist basta.

## Plan de elaboración

| Elemento | Cambio |
|---|---|
| `CONTRIBUTING.md` | Reescritura completa (hecho) |
| `.github/ISSUE_TEMPLATE/01-defecto.yml` | Nuevo (hecho) |
| `.github/ISSUE_TEMPLATE/02-mejora.yml` | Nuevo (hecho) |
| `.github/ISSUE_TEMPLATE/config.yml` | Nuevo (hecho) |
| `changelog.d/5.7.0.md` + `VERSION` + `plugin.json` | Bump Minor (hecho) |

## Trazabilidad

- **Plan aprobado:** conversacional (diagnóstico + menú de 3 decisiones: alcance = defecto+mejora, flujo viejo = eliminar, formato = issue forms).
- **Commits:** pendiente (gate de commit/push con OK del dev).
- **Pendientes generados:** `—` (CODE_OF_CONDUCT ya estaba declarado en el CONTRIBUTING).

## Reporte de cierre

| Señal | Valor |
|---|---|
| Complejidad estimada / real | baja / — |
| Re-entregas | — |
