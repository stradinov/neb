# Correcciones de redacción en docs de adopción (README + user-guide)

**Estado:** Cerrado
**Fecha inicio:** 2026-06-22
**Fecha cierre:** 2026-06-22
**Complejidad estimada:** baja
**Complejidad real:** baja
**Riesgo de regresión:** bajo  <!-- docs modo adopción; sin cambio de sentido ni normativo -->

## Contexto

Primer tramo del pase editorial con ChatGPT (kit [[reference-chatgpt-editorial-neb]]). ChatGPT revisó `README.md` y `docs/user-guide.md` contra las reglas del repo; Claude aplicó los deltas gated tras verificar cada ancla contra el archivo real. El **barrido repo-wide** de tuteo + anglicismos (allowlist) y la **codificación de la política de idioma** quedan como REQ aparte (5.6.0).

## Alcance

### Entra
- **`README.md`** (9 fixes). En el pitch `<!-- human -->` (con OK del dev): comma splice (`incrustada;`), "contexto sobre los cambios", "definición de tus proyectos" + reformulación, orden "aplicaciones web en cierto lenguaje", paralelismo de la enumeración de profiles. Fuera del bloque human: completar "ejecuta" antes de los bloques de comando, "setup"→"configuración inicial", referente "que describe"→"que Neb describe".
- **`docs/user-guide.md`** (23 fixes): gramática/claridad (paso final, "surtan efecto", concordancia "quedan disponibles") + anglicismos de prosa→español (markers→marcadores, runtime→tiempo de ejecución, setea→establece, setup→configuración, reset→restablecimiento, default→por defecto, scaffold→estructura base, troubleshooting→resolución de problemas, system prompt→prompt de sistema, gitignored→ignorada por Git, commitear→hacer commit, rename→renombre, full-text→texto completo, outputs→salidas, fragment→fragmento, cache→caché, deprecado→obsoleto) + "por vos"→"por ti" (tuteo).
- Patch `5.5.0 → 5.5.1` + `changelog.d/5.5.1.md` + `VERSION` + `plugin.json` (sync).

### No entra
- README: 4 separadores ornamentales `---` y H1 ("de la Nebuchadnezzar", válido en español) — decisión del dev.
- Barrido repo-wide de tuteo + anglicismos (allowlist) → REQ 5.6.0.
- Codificación de la política de idioma (mexicano/tuteo + anglicismos solo tecnológicos) → REQ 5.6.0.
- Reverts de anglicismos dudosos: el dev decidió **no revertir ninguno** (se mantienen las traducciones, incl. `system prompt`→`prompt de sistema`).

## Plan de pruebas

- [x] Cada `[ACTUAL]` verificado contra el archivo real (sin drift).
- [x] El bloque `<!-- human -->` del README se editó solo con OK del dev; marcadores intactos.
- [x] Sin cambio de sentido ni de alcance normativo; enlaces/anclas/`*profile*` conservados.
- [x] `assemble-changelog.py --check` verde con 5.5.1; `VERSION` == `plugin.json`; scan de términos vetados limpio.

> Riesgo bajo → checklist basta.

## Trazabilidad

- **Plan aprobado:** conversacional (pase editorial doc-por-doc + menús de selección).
- **Commits:** esta confirmación (repo `neb`).
- **Pendientes generados:** REQ **5.6.0** — barrido repo-wide tuteo + anglicismos (allowlist validada) + codificar la política de idioma en `general/communication.md` (referenciando `tooling/redaccion-es.md`), con las protecciones del plan-review (canónicos de `vocabulary.md`, identifiers/paths/filenames, citas `>`, bloques `<!-- human -->`, exclusión de records/código/`*.template`).

## Reporte de cierre

| Señal | Valor |
|---|---|
| Complejidad estimada / real | baja / baja |
| Re-entregas | 0 |

Pase editorial tramo 1 cerrado: README (9) + user-guide (23). Siguiente: barrido repo-wide (5.6.0).
