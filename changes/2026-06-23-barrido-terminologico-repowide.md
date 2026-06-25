# Barrido terminológico repo-wide (workspace / opt-in / tour / dry-run)

**Estado:** Cerrado
**Fecha inicio:** 2026-06-23
**Fecha cierre:** 2026-06-23
**Complejidad estimada:** media
**Complejidad real:** media
**Riesgo de regresión:** bajo

## Contexto

En v5.9.1 (revisión editorial de `commands/wakeup.md`) el dev decidió traducir 4 anglicismos pervasivos que estaban en la allowlist pero diferidos por su alcance (`workspace`, `opt-in`, `tour`, `dry-run`). Este REQ ejecuta ese barrido en los docs de cara al humano, de forma coherente cross-doc (no doc por doc).

## Clarificación (Fase 1)
- **Alcance:** solo docs de cara al humano (no agent-normativos). Excluidos `process/`, `workflow/`, `general/profile-detection`, `profiles/self-applied/deployment`, `hooks/`, `bootstrap/`, `CHANGELOG`/`changelog.d`/`changes`/`research`, `*.py/*.sh/*.json/*.template`.
- **Output del script:** se conservan las comillas que citan el output literal de `setup-workspace.sh` ("Workspace existente detectado…") — no se toca el script.

## Inventario + plan-review (Fases 2-3)
- Inventario clasificado vía workflow (4 agentes, uno por término): occurrencias marcadas translate / conserve-identifier / conserve-filename / conserve-flag-or-code / conserve-output-quote / conserve-meta-guide / out-of-scope.
- **Plan-review (2 revisores adversariales)** refinó el plan:
  1. **`opt-in` no es uniforme** → mapeo desdoblado: standalone/personal → "opcional"; "opt-in por proyecto/perfil" (activación afirmativa, contrasta con opt-out) → "de activación voluntaria por proyecto/perfil".
  2. **Conservar el frontmatter `description:` + `name:`** de `commands/wakeup.md` y `skills/wakeup/SKILL.md` (metadata de dispatch/auto-discovery) → mantiene el cambio como Patch limpio.
  3. Ediciones **quirúrgicas intra-línea** donde conviven identifier/output/dir/código con prosa.
- Verificado: ningún enlace por anchor apunta a los headings traducidos (sin ruptura de anclas).

## Alcance ejecutado (Fase 4)
- **18 docs** traducidos: `README`, `docs/{user-guide,how-it-works}`, `commands/wakeup`, `general/{onboarding,index}`, `skills/wakeup/{SKILL,validation-prompts}`, `skills/pendings-review/SKILL`, `profiles/self-applied/skills`, `server/INSTALL`, `tooling/{index,logbook,notify-on-stop,notify-on-permission,prompt-preprocessing}`, `methodology/{principles,vocabulary}`.
- **`tooling/revision-editorial-externa.md`**: nota de barrido "pendiente" → "ejecutado en v5.9.2" + traducción de su prosa incidental "Recurso opt-in"→"Recurso opcional" (las líneas de mapeo META se conservan).
- Patch `5.9.1 → 5.9.2` + `changelog.d/5.9.2.md` + `VERSION` + `plugin.json`.

## Plan de pruebas (Fase 5)
- [x] grep de los 4 términos en cada dir in-scope (docs, commands, general, skills, tooling, server, README, methodology, profiles): los residuos restantes son **todos** de conservación (NEB_WORKSPACE, setup-workspace.sh, neb_workspace/, --dry-run, comillas de output, frontmatter, fixture "Dame un tour rápido", mapeo META de la guía) o fuera de alcance (profile-detection, deployment).
- [x] `assemble-changelog.py --check` verde con 5.9.2; `VERSION` == `plugin.json`; scan de términos vetados limpio.

## Trazabilidad
- **Commits:** esta confirmación.
- **Pendientes / follow-ups:**
  - `skills/wakeup/SKILL.md` conserva otros anglicismos del allowlist no revisados editorialmente (`customizable`, `fallback`, `refiriendo`) — pase editorial aparte, fuera del alcance de los 4 términos.
  - Los docs agent-normativos retienen el inglés por decisión de alcance; un REQ futuro podría extender el barrido a ellos para consistencia total repo-wide.

## Reporte de cierre
Barrido coherente cross-doc de los 4 términos en la superficie de cara al humano. El plan-review evitó dos errores (mapeo plano de opt-in; traducir metadata de dispatch). Conservación verificada por grep dir por dir. Los agent-normativos quedan en inglés por alcance, registrado como follow-up.
