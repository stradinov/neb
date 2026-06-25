# Personal vs equipo

## Punto de extensión (promesa 5 — Customizable)

Este archivo define el contrato de customización de Neb. Para adaptar defaults y reglas a tu contexto sin forkear el núcleo, crea `personal/<usuario>.md` a partir de [`templates/personal.md.template`](../templates/personal.md.template).

Pasos:

1. Importa el archivo al final de tu `~/CLAUDE.md` — ver §"Orden de carga".
2. Cada override en `personal/<usuario>.md` estrecha o agrega sobre `general/`; nunca lo relaja — ver §"Regla central".
3. Puntos de customización preconfigurados —con bloque listo; subconjunto materializado de [principles.md](principles.md) § "Puntos de customización"—: [coding-standards.md](coding-standards.md), [git-conventions.md](git-conventions.md), [done-criteria.md](done-criteria.md), [communication.md § Idioma](../general/communication.md).

Criterio verificable: un override en `personal/<usuario>.md` cambia un comportamiento sin editar ningún archivo bajo `general/` ni `methodology/`.

## Regla central

> Las reglas de `general/` son **baseline del equipo**. Un override personal puede **estrechar** o **agregar**, **nunca relajar**.

| Caso | ¿Permitido? |
|------|-------------|
| Personal: "siempre commit con `--signoff`" | ✅ Estrecha |
| Personal: "agrega revisión de accesibilidad antes de validación" | ✅ Agrega |
| Personal: "no necesito plan de pruebas en complejidad baja" | ❌ Relaja |
| Personal: "puedo usar `--no-verify` si el hook molesta" | ❌ Relaja |

## Puntos de customización vs reglas de proceso

La "Regla central" (estrechar/agregar/nunca relajar) gobierna las **reglas de proceso** — las que tienen un eje de severidad (gates, plan de pruebas, firma de commits, revisión). Un **punto de customización** (idioma/variedad/registro, formato de salida, alias) no tiene eje de severidad: el override lo **sustituye**, no lo estrecha.

| Tipo | Override personal | Ejemplos |
|------|-------------------|----------|
| **Regla de proceso** (tiene eje de severidad) | Estrecha o agrega, **nunca relaja** | gates, plan de pruebas, firma de commits, revisión |
| **Punto de customización** (sin eje de severidad) | **Sustituye** el default | idioma/variedad/registro, formato de salida, alias |

Por eso `permitir_voseo: true` en un `personal.md` es legítimo aunque el default del equipo sea no-voseo — sustituye una preferencia, no relaja un control.

## Detección de contradicciones

Si una instrucción del `personal.md` contradice una regla general, Claude avisa antes de aplicarla:

> "Tu personal.md dice X, pero la regla general dice Y. ¿Confirmas que quieres aplicar tu regla personal en este caso?"

Si el conflicto es recurrente, proponer cambio a la regla general (loop de refinamiento) en lugar de mantener el override.

## Orden de carga

En el `~/CLAUDE.md` del dev:

```
@~/.claude/neb/general/startup.md
@~/.claude/neb/workflow/index.md
@~/.claude/neb/personal/<usuario>.md   ← último
```

`~/.claude/neb` es la ruta convencional; ajustar al directorio real del clon.

Override solo para un proyecto: `<proyecto>/.claude/personal.md` (ignorada por Git, importado al final del `CLAUDE.md` del proyecto).

## Qué va en el personal

- Atajos personales (alias mentales, formatos de salida).
- Preferencias de comunicación (idioma, variedad, registro, formato): sustituyen el default del equipo.
- Convenciones individuales (firma de commits, herramientas).
- Notas privadas.

## Qué NO va

- Reglas que beneficiarían al equipo → propongan cambio a `general/`.
- Convenciones de un proyecto → `CLAUDE.md` del proyecto.
- Datos sensibles (credenciales, paths confidenciales).
