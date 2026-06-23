# Profiles

Metodologías específicas por tipo de proyecto. Abstrae lo que NO es universal: comandos de build, paths de deploy, keys SSH, convenciones de framework, resolución de problemas.

## Disponibles

- [profile-authoring](profile-authoring/index.md) — Autoría, mantenimiento y distribución de profiles de la metodología. Overlay sobre `self-applied`.
- [skill-authoring](skill-authoring/index.md) — Autoría, mantenimiento y distribución de skills de Claude Code. Overlay sobre `self-applied`.
- [self-applied](self-applied/index.md) — Proyectos auto-aplicados — la metodología que se edita es la que se aplica (caso canónico: el propio repo `neb`). Validación por **revisión de roles + coherencia**.
- [research](research/index.md) — Investigación multi-LLM: consultar fuentes independientes, sintetizar resultados y producir documentos citables desde cualquier profile o requerimiento. Overlay sobre `self-applied`.

## Pendientes

- `prestashop` — tiendas sobre PrestaShop.
- `react-native` — aplicaciones móviles React Native (Expo).
- `python-poetry` — proyectos Python con Poetry.

## Heurística de detección

Single source of truth — consumida por:

- Claude al iniciar trabajo y al re-evaluar profile durante la sesión (ver [`general/profile-detection.md`](../general/profile-detection.md)).

El consumidor es la detección en tiempo de ejecución de Claude, que aplica esta tabla vía `general/profile-detection.md`. Si la tabla cambia, actualizar `general/profile-detection.md` en el mismo commit.

Inspeccionando el repo, el primer indicador que coincide gana:

| Indicador | Profile |
|---|---|
| **cwd dentro de `*/<neb>/profiles/<nombre>/`** (overlay sobre `self-applied`; `<neb>` = dir del checkout) | `profile-authoring` |
| **cwd dentro de `*/<neb>/skills/<nombre>/`** (overlay sobre `self-applied`) | `skill-authoring` |
| **cwd dentro de `*/<neb>/research/`** (overlay sobre `self-applied`); para investigación en `<proyecto>/research/` o `~/.claude/research/` la activación es **explícita** por el dev | `research` |
| `methodology/principles.md` + `process/plan-review.md` + `general/index.md` con fases canónicas | `self-applied` |
| `app/` + `composer.json` con `prestashop/prestashop` | `prestashop` (futuro) |
| `app.json` + `expo` en deps | `react-native` (futuro) |
| `pyproject.toml` + Poetry | `python-poetry` (futuro) |

Si ningún indicador coincide, Claude continúa genérico o avisa que falta soporte (ver [`general/profile-detection.md`](../general/profile-detection.md) § "Al iniciar trabajo").

(Para agregar un profile nuevo: ver [`CLAUDE.md`](../CLAUDE.md) del repo.)
