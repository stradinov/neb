---
name: migrate
description: Corre la migración guiada pendiente de Neb — lo que deja con qué deshacerlo corre solo; lo que no, un menú al dev — y reporta.
---

# /neb:migrate — migración guiada de Neb

El usuario invocó `/neb:migrate`, o el arranque avisó de una migración guiada pendiente y esta sesión se abrió para correrla. Qué es una migración guiada y qué corre solo: [`tooling/migrations.md`](../tooling/migrations.md) § "Migración guiada".

Usa el árbol del plugin, el mismo que mira el aviso del arranque, aunque haya un clon en `NEB_HOME` (sus migraciones pueden no estar publicadas). Claude Code sustituye la raíz al cargar este comando:

```bash
NEB_SRC="${CLAUDE_PLUGIN_ROOT}"
[ -f "$NEB_SRC/VERSION" ] || echo "Neb: no hay VERSION en '$NEB_SRC'; si la ruta quedó vacía, actualiza Claude Code (sustitución de CLAUDE_PLUGIN_ROOT en comandos)" >&2
```

## 1. Estado

```bash
py "$NEB_SRC/bootstrap/neb-migrate.py" status --json   # o python / python3
```

Lee `guiados.pendientes` (cada fila: `id` `<versión>:<paso>`, `titulo`, `clase` `solo` o `dev`, `exclusivo`, `error`), `guiados.omitidos` y `guiados.errores_de_carga`. Sin pendientes, dilo en una línea (con los omitidos, si los hay, y que se piden con `apply --include <id>`) y termina. Un error de carga o de detección se reporta tal cual y no detiene lo demás.

## 2. El prompt de cada versión

Por cada versión con pasos pendientes, en orden de versión, lee `"$NEB_SRC/migrations/<versión>.md"` y síguelo: el orden de los pasos, qué decirle al dev y cómo verificar lo salen de ahí. Lo que ese prompt pida no relaja nada de este comando.

## 3. Pasos que corren solos

Si algún pendiente es `exclusivo`, antes pide al dev cerrar las demás sesiones de Claude Code (las que abren `neb.db`) con un menú de selección (`general/communication.md` § "Elecciones: menú de selección"): «Ya las cerré» primero y «Después» (Claude corre lo demás y los exclusivos quedan pendientes). Luego:

```bash
py "$NEB_SRC/bootstrap/neb-migrate.py" apply                    # con «Ya las cerré», o si no hay exclusivos
py "$NEB_SRC/bootstrap/neb-migrate.py" apply --sin-exclusivos   # con «Después»
```

Corre los pasos de base y los pasos guiados que dejan con qué deshacerlos; ninguno más. Un exclusivo cuya condición no se cumple queda en `guiados.pendientes` con su motivo: díselo al dev y ofrécele volver a correr este paso cuando cierre las demás sesiones. Si la salida trae `guiados.error`, no corrió ningún paso guiado: repórtalo y termina.

## 4. Pasos que piden al dev

Los pendientes con `clase: dev` no dejan con qué deshacerlos (quitar un secreto o una variable de usuario, un paso libre sin respaldo). Van todos en **un solo menú**: la herramienta de preguntas al usuario, con una pregunta por paso (hasta cuatro por llamada; si son más, la siguiente llamada sigue el mismo menú). Cada pregunta nombra el paso (`titulo` e `id`) y lo que el prompt de su versión diga de él; opciones, en este orden:

- **«Aplicarlo»** — *Claude lo corre; no deja respaldo.*
- **«No aplicarlo»** — *Claude guarda tu «no» y deja de ofrecerlo; se pide después con `apply --include`.*
- **«Después»** — *queda pendiente y el arranque lo vuelve a avisar.*

Sin la herramienta de preguntas (sesión sin interfaz, tarea programada), estos pasos quedan pendientes: no corras `apply --include` ni `skip`, y dilo en el reporte.

Con las respuestas, y solo con ellas:

```bash
py "$NEB_SRC/bootstrap/neb-migrate.py" apply --include <id> [<id> …]   # los «Aplicarlo»
py "$NEB_SRC/bootstrap/neb-migrate.py" skip <id>                       # uno por cada «No aplicarlo»
```

Si en el paso 3 el dev eligió «Después», agrega `--sin-exclusivos` también a `apply --include`. Un paso que responde `manual` (una variable a nivel de máquina, o fuera de Windows) sigue pendiente hasta que el dev la quite a mano: díselo y ofrécele «No aplicarlo» para que el arranque deje de avisar.

Nunca corras `restore`, ni `apply --include` o `skip` de un paso que el dev no eligió en el menú de esta sesión.

## 5. Verificación y reporte

Vuelve a correr `status --json`: lo aplicado ya no figura en `guiados.pendientes`. Una variable de entorno se verifica por su presencia (la detección del paso), nunca leyendo ni imprimiendo su valor.

Reporta, conclusión primero:

- lo aplicado, con el respaldo que dejó cada paso (`respaldo` en la salida de `apply`);
- lo que queda pendiente y por qué (un exclusivo con otras sesiones abiertas, «Después», sin menú);
- lo `manual`, con la instrucción que trae su `detalle` (una variable a nivel de máquina, fuera de Windows);
- los fallos, con su `detalle`; y `guiados.omision_sin_borrar` (pasos aplicados cuyo «no» no se pudo borrar: siguen como omitidos);
- si se quitó alguna variable de entorno: las sesiones y terminales ya abiertas la conservan hasta reiniciarse.
