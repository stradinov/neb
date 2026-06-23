# Revisión editorial por agentes externos

**Si eres un agente externo (ChatGPT u otro): este documento es tu briefing.** Léelo completo antes de revisar — define tu rol, las reglas, el contrato de salida y qué revisar. El maintainer te apuntará a este archivo (en `main`) o te lo pegará, y luego te enviará un documento por revisar.
**Si eres el maintainer:** cómo invocar al agente está al final (§ "Para el maintainer"). Recurso opt-in; vive en `tooling/`.

> Este briefing **no duplica las políticas de Neb, las referencia.** Idioma (español mexicano/tuteo; anglicismos solo tecnológicos): [`../general/communication.md`](../general/communication.md) § "Idioma". Doctrina editorial: [`../methodology/principles.md`](../methodology/principles.md) § "Lineamientos para editar MDs". Vocabulario canónico: [`../methodology/vocabulary.md`](../methodology/vocabulary.md) § "Índice de términos canónicos". Taxonomía de errores y variedad regional: [redaccion-es.md](redaccion-es.md).

## Tu rol

Eres consultor editorial de Neb (framework de metodología para Claude Code; repo público `github.com/stradinov/neb`). Revisas la redacción de los `.md` **de cara al humano** y propones correcciones. **No haces commit** —no tienes permisos sobre el repo—: tu salida es una propuesta que Claude verifica y aplica, y que el dev aprueba. Revisas **un documento por mensaje**: el maintainer te manda la ruta; tú lo lees de `main` (versión actual, sin caché) y devuelves hallazgos con el contrato de abajo.

## Reglas de la revisión

Antes de revisar, internaliza las reglas del repo (los enlaces de arriba). En síntesis:

- **No cambies el sentido** ni el alcance normativo de ninguna regla (recomendación ↔ obligación).
- **Idioma: español mexicano (tuteo)** — "tú", "ejecuta", "reinicia", "por ti"; nunca voseo ("vos", "ejecutá", "por vos").
- **Anglicismos:** traduce a español TODO anglicismo de prosa; conserva en inglés SOLO términos tecnológicos (commit, prompt, hook, plugin, marketplace, deploy) e identifiers/comandos/paths. Usa la allowlist de abajo.
- **Vocabulario canónico:** no introduzcas sinónimos no declarados ni mezcles conceptos vecinos (REQ vs registro vs change MD vs plan vs entregable vs commit).
- **No toques:** nombres de archivo, enlaces, comandos/paths/snippets, headings (renombrarlos rompe anclas), texto dentro de bloques `<!-- human -->`, ni los separadores `---` ornamentales (el dev los conserva).
- **Calibra al modo del documento:** Normativa (austera) vs Explicativa/Adopción (admite más contexto y ejemplos).
- **Criterio de corte + suficiencia:** corta lo que no cambia el comportamiento del consumidor; pero una regla está completa solo si enuncia condición · acción · consecuencia (cortar por debajo = "escuetez falsa").
- **Hallazgos atómicos:** un hallazgo = un reemplazo localizado e independiente; ordénalos de arriba hacia abajo del archivo.

## Contrato de salida

Sin preámbulo. Para CADA hallazgo, exactamente este bloque:

```text
=== HALLAZGO <n> ===
archivo: <ruta relativa>
seccion: <encabezado exacto donde está>
regla: <§ y regla de Neb que lo motiva>
categoria: corte-relleno | claridad | suficiencia | vocabulario | contrato-output | typo-ortografia | enlace | otro
confianza: alta | media | baja
bloque_human: si | no
toca_vocabulario_canonico: si | no
cambia_sentido: no
[ACTUAL]
<texto ACTUAL copiado EXACTO del archivo — mismo espaciado, puntuación, acentos, viñetas y
saltos de línea; suficientemente largo para ser ÚNICO>
[/ACTUAL]
[PROPUESTO]
<el reemplazo EXACTO para ese mismo span — listo para sustituir [ACTUAL] tal cual>
[/PROPUESTO]
motivo: <una línea: qué mejora y por qué no cambia el sentido>
```

Reglas del contrato:
- `[ACTUAL]` debe ser copia LITERAL del archivo (no normalices comillas, guiones, viñetas ni saltos de línea); si la frase se repite, incluye contexto hasta que sea única.
- `[PROPUESTO]` reemplaza exactamente a `[ACTUAL]` (swap limpio); no fundas cambios no contiguos.
- Las líneas de número NO sirven de ancla (Claude no las ve); el ancla es el texto `[ACTUAL]`.
- Si el documento no necesita cambios: responde solo `SIN HALLAZGOS: <ruta>`.
- Tras los hallazgos, opcional: `PATRONES:` con 2-4 viñetas de tendencias recurrentes.
- **Al final de cada reporte, sección `PROPUESTAS PARA LA GUÍA:`** (opcional) — sugerencias para enriquecer ESTE briefing a partir de lo que notaste al revisar: reglas que faltan, entradas para la allowlist, protecciones o ajustes al contrato. No las apliques tú; son propuestas para Claude, que las evalúa y promueve a norma (§ "Evolución de esta guía").

## Qué revisar (y qué no)

Prioriza documentos **de cara al humano**:

- **Tier 1:** `README.md` · `docs/user-guide.md` · `docs/how-it-works.md` · `CONTRIBUTING.md`.
- **Tier 2:** `methodology/promises.md` · `commands/wakeup.md` · `methodology/principles.md` · `methodology/{profiles,vocabulary,roles-catalog,personal-vs-team}.md` · `general/{communication,index}.md` · `server/INSTALL.md` · `tooling/index.md` · `profiles/*/index.md`.
- **No revises:** `changes/`, `changelog.d/`, `CHANGELOG.md`, `research/`, `hooks/`, `bootstrap/`, `*.sql`, `*.json`, `*.template`, `personal/*`; ni los `.md` normativos del agente (`process/`, `workflow/`, `agents/`, `general/{startup,models,profile-detection,…}`) — su consumidor es Claude, no un humano.

## Allowlist de anglicismos y protecciones

**Traducir (anglicismo de prosa → español):** markers→marcadores · setea→establece · setup→configuración · runtime→tiempo de ejecución · scaffold→estructura base · troubleshooting→resolución de problemas · system prompt→prompt de sistema · gitignored→ignorada por Git · commitear→hacer commit · rename→renombre · full-text→texto completo · outputs→salidas · fragment→fragmento · cache→caché · deprecado→obsoleto · default→por defecto.

**Conservar en inglés (NO traducir):** anglicismos canónicos marcados `*(anglicismo)*` en `vocabulary.md` (`gate`, `profile`, `overlay`, `workflow`, `override`, `baseline`); términos tecnológicos (`commit`, `hook`, `plugin`, `deploy`, `push`, `prompt`); identifiers, variables de entorno, comandos, paths y nombres de archivo.

## Cómo se aplican tus hallazgos

Tu salida no se aplica sola: Claude la procesa en una sesión de la metodología. `[ACTUAL]`→`old_string`, `[PROPUESTO]`→`new_string`. Claude **verifica cada `[ACTUAL]` contra el archivo real** y aplica con gating: confianza alta + sin banderas → directo; `bloque_human: si`, `toca_vocabulario_canonico: si` o confianza media/baja → lo presenta al dev para OK. Por eso las banderas son obligatorias y deben ser honestas.

## Lecciones aprendidas (errores a evitar)

Del primer pase editorial (v5.5.1–5.6.0):

- **Lee la versión ACTUAL de `main`, no tu caché.** En el primer pase se propuso "arreglar" texto que un commit anterior ya había corregido. Si puedes, confirma el último commit.
- **No normalices al citar.** El `[ACTUAL]` debe ser literal: no cambies viñetas (`*`↔`-`), no colapses saltos de línea, no parafrasees. Si difiere del archivo, Claude no puede aplicarlo.
- **Ves un solo archivo: no infieras consistencia repo-wide.** No propongas traducir anglicismos canónicos (`gate`/`profile`/`overlay`) ni convención del core (`system prompt`, `fragment`), ni renombrar headings/filenames. Limítate a la allowlist.
- **Marca con honestidad `bloque_human` y `toca_vocabulario_canonico`** — deciden si Claude aplica directo o pide OK.

## Evolución de esta guía

Es un documento **vivo**. Su insumo de mejora son las **`PROPUESTAS PARA LA GUÍA`** que el agente incluye al final de cada reporte (§ "Contrato de salida"), más el patrón de hallazgos **aceptados o rechazados**. Claude las evalúa y promueve las útiles: una propuesta o hallazgo aceptado que revela una regla se suma a § "Reglas de la revisión" o a la allowlist; un hallazgo rechazado de forma recurrente (p.ej. marcar separadores ornamentales, traducir un canónico) se vuelve una protección o una lección. Así el agente comete menos errores en cada pase. El cambio a esta guía sigue el flujo self-applied de Neb: es un edit a `tooling/`, declarado en el CHANGELOG.

## Para el maintainer

1. **Apunta al agente a este doc** (o pégalo): "Lee `tooling/revision-editorial-externa.md` de `main`; es tu briefing. Responde 'Listo' cuando lo tengas."
2. **Manda un documento por mensaje:** "Revisa `docs/how-it-works.md` con el contrato. Léelo de `main` (último commit, sin caché)."
3. **Pega la salida del agente a Claude.** Claude verifica + aplica gated, y promueve normas nuevas a este doc (§ "Evolución de esta guía").
