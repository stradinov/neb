# Notación canónica de cita de pendientes (raíz: `#NNN` huérfano tras migración a `neb.db`)

- **Fecha:** 2026-06-15
- **Profile:** self-applied
- **Versión:** 4.9.0 (minor — nuevo lineamiento de notación + capacidad CLI)
- **Estado:** En validación (dogfooding misma sesión)

## Contexto / síntoma

El dev preguntó "cuáles son 188 y 189"; al resolver con `pendings.py show 188/189` los resultados no correspondían a lo que `MEMORY.md` describe como `#188`/`#189`. Detectado un defecto de comunicación: la notación `#NNN` colisiona entre dos espacios de numeración y me hace resolver mal las referencias.

## Causa raíz

1. La migración del backlog plano a SQLite (REQ `neb-pendings-sqlite`, 2026-06-15) asigna `pending.id` como **autoincrement puro** (rowid). El número `NNN.` del markdown **se parsea pero nunca se persiste** (`migrate-pendings-md.py`: `_ITEM_RE` captura el grupo `num`, no se usa; la idempotencia es por igualdad exacta de `context_origin`). No hay columna `legacy_num` ni mapa.
2. El número viejo sobrevive **solo como texto** embebido en el prefijo `NN.` de `context_origin`.
3. Medición: de 23 `#NNN` únicos citados en `MEMORY.md`, **0 resuelven correctamente** vía `show NNN` (17 → item equivocado, 6 → no encontrado).
4. El `viejo#` **ni siquiera es único**: 22 colisiones en la propia DB (p.ej. `#196` → `site_monitor` id 18 **y** `deployment-gate` id 174). El número markdown no es clave; el `[slug]` sí (estable, preservado en `context_origin`).
5. Vector: `MEMORY.md` (lo inyecta el host de Claude Code cada sesión) + ~18 memorias `project_*.md` cargan ~95–100 refs `#NNN` en la numeración vieja. Ningún documento de Neb definió jamás `#NNN` como notación → convención tribal huérfana entre el `pendings.md` plano (deprecado) y `neb.db` (canónico).

## Decisión (forks aprobados por el dev)

- **Notación canónica = `[slug]`** (anti-colisión, estable). Donde se muestra un número es **siempre** el id de `neb.db`, escrito `PD-<id>`. El bare `#NNN` queda **retirado** como cita de pendiente.
- **Resolución robusta en el CLI**: `pendings.py show` acepta `<id|#id|PD-id|[slug]|slug>`.
- **Limpieza completa** de las ~100 refs `#NNN` en los 19 archivos de memoria (reescritura por slug, no por número a ciegas).

## Cambios

### Código (frente B)
- `hooks/lib/pendings.py`: nueva `resolve_pending_ref(con, ref)` + `cli_show` resuelve por id o por slug (tag exacto `[slug]` → substring), reporta ambigüedad con candidatos, y mensaje claro en "no encontrado" (aclara que el `#NNN` markdown no resuelve).
- `hooks/tests/test_pendings.py`: clase `TestResolvePendingRef` (5 casos: id plano/`#`/`PD-`, slug exacto, ambiguo, no encontrado, "el viejo `153.` no resuelve por id"). Suite completa **77/77 verde**.

### Metodología (frente A)
- `tooling/pendings.md`: nueva sección "Cómo citar un pendiente (notación canónica)".
- `workflow/pendings.md`: nota de deprecación del modelo plano + puntero a la notación canónica.
- `general/communication.md`: al recordar pendientes, citar por `[slug]` (+ `PD-<id>`), nunca `#NNN`.
- `skills/pendings-review/SKILL.md`: el triage cita `[slug]` + `PD-<id>`.

### Limpieza de memoria (frente C)
Fan-out de 19 agentes (uno por archivo) + pase de cierre manual. Resultado:
- **131 refs halladas, 109 reescritas a `[slug]`**, 67 falsos positivos excluidos (colores hex `#235a81`, employee-ids, `run #64`, `finding #10155`, `entry #10`, AWS account-ids, hashes git/md5). **Cero slugs inventados** (lo no resoluble con confianza se dejó intacto).
- **`MEMORY.md` (archivo inyectado cada sesión): 100% limpio** — 21 refs reescritas; las cerradas resueltas desde `pendings.archive-2026-06-15.md` (preserva `NNN. [slug]`) citadas como `[slug] (cerrado)`. En títulos de link markdown se eliminó el número en vez de meter corchetes anidados (no romper el link).
- **4 residuales** dejados intactos por ambigüedad/colisión genuina (documentados, no adivinados): `project_common.md` `#201` (REQ cerrado vs follow-ups), `project_officemax.md` `#189`, `project_site_monitor.md` `#196`, `project_terzab2c.md` `#123` (colisiona: bug `= vs ==` vs `ps_configuration-legacy`).
- Resolución SIEMPRE por descripción/slug, nunca por número (confirmadas 22 colisiones del `old#` en `context_origin`).

## Validación

- `py -m unittest discover -s tests` → 77/77 OK.
- Resolver probado en vivo: id/`#`/`PD-`/slug exacto/ambiguo/no-encontrado.

## Pendientes / follow-ups

- Gaps hermanos hallados en la misma sesión de prueba: infer-objectives no-automático, brújula trivial, skill no registrado en sesión (Windows). Registrados como pendientes aparte.
- El `#186` (encoding cp1252) resultó **falso positivo**: `cli_main` ya hace `reconfigure(utf-8)`; se archiva.
