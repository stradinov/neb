# Validation prompts — skill: pendings-review

Casos de validación del skill. Cada caso trae el prompt, lo esperado y cómo se monta.

Montaje común: sesión con `NEB_HOME` apuntando al árbol bajo prueba. Ningún caso abre la base real del dev ni su `compas.md`: cada llamada al CLI lleva `HOME` y `USERPROFILE` apuntando a un directorio temporal `T` (en Windows la ruta sale de `USERPROFILE`), fijados solo en el entorno de esa llamada. La sesión no se lanza con esas variables, porque romperían la configuración y la autenticación de Claude Code. Antes del prompt, la sesión recibe esta instrucción: «en cada llamada a `PD`, antepón `HOME='<T>' USERPROFILE='<T>'`, solo a esa llamada». `T` va en forma Windows (`C:\...`). Esa instrucción es parte del montaje, no del prompt que se evalúa.

`T/.claude/neb.db` se siembra con nombres genéricos del núcleo, nunca con clientes reales: tres pendientes creados con `PD create` y curados con `bootstrap/seed-pendings-taxonomy.py --apply --db <T>/.claude/neb.db`, con un catálogo `{"proyecto": [alpha, beta], "topico": [seguridad, tooling]}`. Uno queda en `alpha` · `seguridad`, otro en `alpha` · `tooling` y otro en `beta` · `seguridad`. Se agrega un cuarto pendiente sin curar, para que el pase tenga algo que proponer. El aislamiento se comprueba por el contenido: el JSON de `PD triage` trae solo los ids sembrados en `T` y su `catalog` es exactamente el genérico.

## Positivos (deben disparar el skill)

1. «qué tengo pendiente»
   - **Esperado:** carga el skill y corre `PD triage`, sin filtros. Muestra cada pendiente con su cita `[slug]` (`PD-<id>`), proyecto, tópico, banda y origen, con los enums traducidos al español. Propone la curaduría del cuarto pendiente en una sola `AskUserQuestion` y no cura nada sin el OK. No usa `PD list` ni `PD show` como sustituto del pase.
   - **Montaje:** el común.

2. «qué tengo de alpha»
   - **Esperado:** carga el skill y corre `PD triage --proyecto alpha`. La respuesta trae solo los dos pendientes de `alpha`; el de `beta` no aparece. No filtra a mano sobre el JSON completo.
   - **Montaje:** el común.

3. «pendientes de seguridad»
   - **Esperado:** carga el skill y corre `PD triage --topico seguridad`. La respuesta trae el pendiente de `alpha` · `seguridad` y el de `beta` · `seguridad`, y no el de `tooling`.
   - **Montaje:** el común.

4. «rankéame los pendientes según lo que bloquea a otros equipos»
   - **Esperado:** carga el skill y corre `PD rank "lo que bloquea a otros equipos"`. Presenta el orden con las citas que salen de `slugs` y aclara que el criterio es efímero: no persiste bandas ni llama a `PD curate`.
   - **Montaje:** el común. Al final, comprobar que las bandas de `T/.claude/neb.db` no cambiaron.

## Negativos (NO deben disparar el skill)

5. «implementa la validación de entrada en el proyecto beta»
   - **Esperado:** no carga `pendings-review` ni corre `PD`. Mencionar un proyecto del catálogo no basta para disparar el skill: es implementación normal y sigue el flujo formal.
   - **Montaje:** el común.

6. «agrega una prueba unitaria al módulo de exportación de este proyecto»
   - **Esperado:** no carga `pendings-review`. La palabra «proyecto» por sí sola no lo dispara; se trata como tarea de implementación.
   - **Montaje:** ninguno.
