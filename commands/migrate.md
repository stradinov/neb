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

Lee `guiados.pendientes` (cada fila: `id` `<versión>:<paso>`, `titulo`, `clase` `solo` o `dev`, `exclusivo`, `error`), `guiados.omitidos` y `guiados.errores_de_carga`. Si `guiados.error_omitidos` no es nulo, repórtalo y termina: no se sabe qué omitió el dev, y el menú le volvería a ofrecer lo que ya rechazó. Sin pendientes, dilo en una línea (con los omitidos, si los hay, y que se piden con `apply --include <id>`) y termina. Un error de carga o de detección se reporta tal cual y no detiene lo demás: esos pasos no corren hasta que una versión de neb lo corrija. Un paso cuya detección falla (fila con `error`) entra en el menú del paso 4 solo con «No aplicarlo» y «Después», para que el dev pueda dejar de verlo en el aviso.

## 2. El prompt de cada versión

Por cada versión con pasos pendientes, en orden de versión, lee `"$NEB_SRC/migrations/<versión>.md"` y síguelo: el orden de los pasos, qué decirle al dev y cómo verificar lo salen de ahí. Lo que ese prompt pida no relaja nada de este comando.

## 3. Pasos que corren solos

Nunca pidas al dev cerrar las demás sesiones, tampoco por un paso `exclusivo`: una versión nueva no puede pedir que se cierren las sesiones abiertas. Un exclusivo comprueba solo, en el momento, que ninguna otra conexión tenga la base abierta; si alguna la tiene, no hace nada y queda pendiente, y se reintenta en la siguiente corrida de este comando. Sin menú:

```bash
py "$NEB_SRC/bootstrap/neb-migrate.py" apply --guiados
```

Corre los pasos de base y los pasos guiados que dejan con qué deshacerlos; ninguno más. Sin `--guiados`, `apply` solo corre los pasos de base. Un exclusivo cuya condición no se cumple queda en `guiados.pendientes` con su motivo: repórtalo en una línea (queda para la siguiente corrida) sin pedirle nada al dev. `--sin-exclusivos` sigue existiendo para correrlo a mano; este comando no lo usa. Si la salida trae `guiados.error`, no corrió ningún paso guiado: repórtalo y termina. Si no trae `guiados` (la base no abrió: `motivo`, `accion`), tampoco corrió ningún paso guiado: reporta `detalle` y `accion` y termina.

## 4. Pasos que piden al dev

Los pendientes con `clase: dev` (y los de detección fallida, sin «Aplicarlo») no dejan con qué deshacerlos (quitar un secreto o una variable de usuario, un paso libre sin respaldo). Van todos en **un solo menú**: la herramienta de preguntas al usuario, con una pregunta por paso (hasta cuatro por llamada `[asumido: límite de la herramienta, sin fila de supuesto de plataforma]`; si son más, la siguiente llamada sigue el mismo menú). Cada pregunta nombra el paso (`titulo` e `id`) y lo que el prompt de su versión diga de él; opciones, en este orden:

- **«Aplicarlo»** — *Claude lo corre; no deja respaldo.*
- **«No aplicarlo»** — *Claude guarda tu «no» y deja de ofrecerlo; se pide después con `apply --include`.* En una fila con `error` (detección fallida), en su lugar: *Claude guarda tu «no»: aunque una versión de neb corrija la detección, este paso no se vuelve a ofrecer; se pide con `apply --include <id>`.*
- **«Después»** — *queda pendiente y el arranque lo vuelve a avisar.*

Ninguna va marcada «(Recomendado)»: decide el dev.

Sin la herramienta de preguntas (sesión sin interfaz, tarea programada), estos pasos quedan pendientes: no corras `apply --include` ni `skip`, y dilo en el reporte.

Con las respuestas, y solo con ellas:

```bash
py "$NEB_SRC/bootstrap/neb-migrate.py" apply --include <id> [<id> …]   # los «Aplicarlo»
py "$NEB_SRC/bootstrap/neb-migrate.py" skip <id>                       # uno por cada «No aplicarlo»
```

`skip` se niega sin base, con la base sin migrar o con una base de una versión de neb más nueva (`motivo`): el paso sigue pendiente; díselo al dev. Un paso que responde `manual` (una variable a nivel de máquina, o fuera de Windows) sigue pendiente hasta que el dev la quite a mano: díselo y ofrécele «No aplicarlo» para que el arranque deje de avisar. Si un paso `manual` ya no figura en `guiados.pendientes` (p. ej. `7.0.0:renombrar-base` cuando una sesión anterior escribió en `neb-logbook.db` después del cambio de nombre), no ofrezcas «No aplicarlo»: reporta su `detalle`.

Nunca corras `restore`, ni `apply --include` o `skip` de un paso que el dev no eligió en el menú de esta sesión.

## 5. Verificación y reporte

Vuelve a correr `status --json`: lo aplicado ya no figura en `guiados.pendientes`. Una variable de entorno se verifica por su presencia (la detección del paso), nunca leyendo ni imprimiendo su valor.

Reporta, conclusión primero:

- lo aplicado, con el respaldo que dejó cada paso (`respaldo` en la salida de `apply`);
- lo que queda pendiente y por qué (un exclusivo con otra sesión usando la base en ese momento, que se reintenta en la siguiente corrida; «Después»; sin menú);
- lo `manual`, con la instrucción que trae su `detalle` (una variable a nivel de máquina, fuera de Windows);
- los fallos, con su `detalle`, y `guiados.errores_de_carga` (esos pasos no corrieron); y `guiados.omision_sin_borrar` (pasos aplicados cuyo «no» no se pudo borrar: siguen como omitidos);
- si se quitó alguna variable de entorno: las sesiones y terminales ya abiertas la conservan hasta reiniciarse.
