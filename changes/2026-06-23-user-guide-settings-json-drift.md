# Corregir drift doc↔script en user-guide (shell profile → settings.json)

**Estado:** Cerrado
**Fecha inicio:** 2026-06-23
**Fecha cierre:** 2026-06-23
**Complejidad estimada:** baja
**Complejidad real:** baja
**Riesgo de regresión:** bajo

## Contexto

Al revisar si el barrido terminológico (5.9.2) podía confundir a Claude Code, el plan-review detectó un drift **preexistente** (ajeno a la traducción): `docs/user-guide.md` § "Configurar el entorno" decía que el script establece las variables en el "shell profile" y que hay que "reiniciar el shell", pero `setup-workspace.sh` (L192, L209) escribe en `~/.claude/settings.json` y declara explícitamente que "el shell profile ya no se edita (settings.json basta)". Si Claude leía la guía para instruir al usuario, daría un paso obsoleto.

## Alcance

### Entra
- **`docs/user-guide.md`** § "Configurar el entorno": ubicación de las variables ("shell profile (con backup)" → "`~/.claude/settings.json` (merge no-destructivo)") y el paso de activación ("Reinicia tu shell" → "Abre una sesión nueva de Claude Code").
- Patch `5.9.2 → 5.9.3` + `changelog.d/5.9.3.md` + `VERSION` + `plugin.json`.

### No entra
- No es un cambio terminológico (el barrido 5.9.2 ya cerró). Aquí solo se corrige el comportamiento documentado.

## Plan de pruebas
- [x] Verificado contra `setup-workspace.sh` (L192 escribe en settings.json vía `set-neb-env.py`; L209 "el shell profile ya no se edita"; L218 "Abrí una sesión nueva de Claude Code").
- [x] grep "shell" en user-guide.md: sin referencias contradictorias remanentes.
- [x] `assemble-changelog.py --check` verde con 5.9.3; `VERSION` == `plugin.json`; scan limpio.

## Reporte de cierre
Drift preexistente detectado como subproducto de la revisión de la traducción; corregido como patch aparte para no mezclarlo con el barrido.
