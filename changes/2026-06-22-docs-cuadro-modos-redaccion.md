# Cuadro pedagógico de modos de redacción en `docs/`

**Estado:** Cerrado
**Fecha inicio:** 2026-06-22
**Fecha cierre:** 2026-06-22
**Complejidad estimada:** baja
**Complejidad real:** baja
**Riesgo de regresión:** bajo  <!-- docs/ aditivo; sin impacto normativo ni anclas -->

## Contexto

REQ-4 (opcional) del roadmap vocabulario+editorial. En REQ-2 el plan-review descartó la tabla de "3 modos" en `principles.md` por ser material explicativo, no normativo, y la difirió a `docs/` (capa de adopción). Este REQ la materializa: un cuadro pedagógico para quien contribuye/edita los MDs de Neb, que **ilustra** el "calibre por consumidor" ya canónico en `principles.md` (no lo duplica como segunda fuente).

## Alcance

### Entra
- `docs/user-guide.md` § "Contribuir al núcleo (mantenedores)": nueva subsección `### Cómo se redactan los MDs (modos de redacción)` con la tabla Normativa/Explicativa/Adopción (consumidor · dónde · calibre), enlazando a `methodology/principles.md` como fuente canónica.
- Minor `5.4.0 → 5.5.0` + `changelog.d/5.5.0.md` + bump `VERSION` y `.claude-plugin/plugin.json` (sync) + assemble.

### No entra
- Archivo nuevo `docs/concepts.md` (descartado por anti-fragmentación; el cuadro cabe en `user-guide.md`).
- Cualquier cambio normativo: la regla "calibre por consumidor" sigue siendo canónica en `principles.md` (REQ-2); aquí solo se ilustra.

## Plan de pruebas

- [x] El cuadro **apunta** a `principles.md` como canónico y no se vuelve 2ª fuente de verdad (ilustra, no re-enuncia la regla).
- [x] Coherente con `principles.md` § "Lineamientos para editar MDs" (REQ-2): mismos 3 consumidores y calibre.
- [x] Ningún heading renombrado; la subsección es aditiva bajo "Contribuir al núcleo".
- [x] `assemble-changelog.py --check` verde con 5.5.0; `VERSION` 5.4.0 → 5.5.0; `plugin.json` == `VERSION`.

> Riesgo bajo → checklist basta (sin tabla `### Resultado`, por `process/planning.md` § "Riesgo de regresión").

## Plan de elaboración

| Elemento | Cambio |
|---|---|
| `docs/user-guide.md` | + subsección "Cómo se redactan los MDs" (tabla de 3 modos, enlace a principles.md) |
| `changelog.d/5.5.0.md` · `VERSION` · `.claude-plugin/plugin.json` | minor 5.5.0 (VERSION + plugin.json sync) |

## Avances realizados

- Cuadro insertado en `user-guide.md`; coherencia con `principles.md` verificada (mismo consumidor/calibre); enlace a fuente canónica.
- Fragment 5.5.0 + bump VERSION + plugin.json + assemble.

## Trazabilidad

- **Plan aprobado:** conversacional (menú "Implementar directo"); complejidad baja.
- **Commits:** esta confirmación (repo `neb`; sin push aún).
- **Pendientes generados:** ninguno. Roadmap vocabulario+editorial **cerrado por completo** (REQ-1/2/3 + REQ-4 opcional).

## Métricas

| Métrica | Valor |
|---|---|
| Turnos — Fase 1-4 | ~2 |
| Complejidad estimada / real | baja / baja |

## Reporte de cierre

| Señal | Valor |
|---|---|
| Turnos total | ~2 |
| Re-entregas | 0 |
| Complejidad estimada / real | baja / baja |

REQ-4 cerrado: cuadro pedagógico de los 3 modos de redacción en `docs/user-guide.md`, ilustrando (no duplicando) el "calibre por consumidor" canónico de `principles.md`. **Roadmap vocabulario+editorial cerrado por completo**: REQ-1 (v5.2.0) + REQ-2 (v5.3.0) + REQ-3 (v5.3.1) + REQ-4 (v5.5.0). Pendiente: `git push` (6 commits locales: ops-capture + REQ-1/2/3 + preprocess + REQ-4).
