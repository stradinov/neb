# Correspondencia a terceros

Política transversal: aplica cuando Claude redacta un correo que el dev enviará a otra persona (cliente, colega, proveedor), incluida la respuesta en un hilo. El destinatario no comparte el contexto de la sesión: el correo se sostiene solo frente a ese contexto, sin repetirle lo que él ya sabe. La conversación dev↔Claude se norma en [`communication.md`](communication.md).

## Estructura

El principio rector ([`communication.md`](communication.md) § "Principio rector") medido desde el destinatario:

- El **primer párrafo** tras el saludo dice qué se pide, qué se decidió o qué cambió, y la **acción concreta que se espera del destinatario** (con fecha, si la hay); si el correo solo informa, da la conclusión. Si la conclusión depende de algo sin confirmar, se dice ahí en lenguaje llano («falta confirmar …»), no con los marcadores `[asumido]` / `[dominio sin research]`.
- «No requiere acción de su parte» va solo si el destinatario podría creer que le toca actuar, y nunca junto a una petición ni a una oferta opcional («si quieren verlo antes…»).
- **El correo lleva lo que el destinatario necesita para entender, decidir o actuar**, en orden de relevancia para él; lo demás no entra, y Claude lo reporta en el chat (§ "Formato del cuerpo (HTML)").
  - **Uno a tres párrafos, sin encabezados**: el aviso de que algo quedó corregido, el envío de un archivo, el visto bueno de algo ya aplicado o una sola petición.
  - **La estructura que necesiten**, con encabezados que nombran acción o resultado («Qué pasó», «Qué hicimos», «Estado actual», «Qué necesitamos de ustedes», «Cómo probarlo»): el diagnóstico que el destinatario tiene que entender o transmitir, la propuesta o revisión con decisiones, el instructivo de una acción que el correo pide y el aviso formal.
  - **No entra** la explicación lateral: «Sobre …», una sección «Por qué …» o «Evidencia» que solo explica o prueba.
- **No se le explica lo que ya sabe**: lo que opera a diario, lo que él mismo escribió o ya se le dijo en el hilo, y los datos de sus propios recursos; basta una referencia breve («el mismo CSR del año pasado»). El dato que motiva el correo o que necesita para actuar va aunque lo conozca. Sin evidencia de que lo sabe (en el hilo o en su ficha de destinatario), se explica. Con varios destinatarios, se mide desde quien debe actuar o decidir; si son varios, lo que alguno no sabe se explica; si nadie actúa ni decide, desde los de Para.
- **Un propósito por correo.** Varias peticiones de ese propósito van numeradas (una revisión con varias decisiones, los insumos de un plan, la misma causa en otros casos del destinatario si el correo la diagnostica); una decisión abierta de otro tema no se anexa, ni otros casos en la respuesta a una pregunta puntual: se le reportan al dev. No se vuelve a pedir lo ya decidido o aceptado. Si el correo mezcla tipos, su estructura la fija el propósito: lo que no lo sirve se reduce o sale.
- **Sin índice del contenido** en el primer párrafo («También va …», «Las opciones van al final»). Remitir a una sección que existe («con los pasos de abajo») sí.
- **Sin rótulos de la técnica**: ni el asunto ni el cuerpo nombran la técnica de estructura («BLUF», «TL;DR», «Bottom line») ni rotulan el primer párrafo («Resumen:», «Resumen ejecutivo:», «Conclusión:», «Summary:»); el primer párrafo abre con su contenido. Un rótulo así expone jerga interna al destinatario.
- **Sin jerga del método que el destinatario no usa** (fases, estados, IDs o slugs de pendientes, «REQ», «gate», «Change MD»): se sustituye por su equivalente llano. Las preferencias de presentación del chat declaradas en el overlay o en `personal/<usuario>.md` no se trasladan al cuerpo.

## Idioma y registro

El idioma y el registro los fija el destinatario o el hilo; sin indicación, español.

## Verificación de los hechos

Antes de pasarle al dev un correo, en la forma que sea, cada afirmación de hecho del cuerpo se cruza con su fuente primaria. Afirmación de hecho es lo que el correo da por cierto: el estado o el comportamiento de un sistema, un dato o una cifra, una causa, un evento y su fecha, lo que alguien dijo o hizo; la petición, la propuesta, la recomendación y la cortesía no lo son. Al regenerar el correo se cruzan solo las afirmaciones nuevas o modificadas. Si la redacción se delega, verifica quien le pasa el correo al dev.

- **Fuente primaria** es lo que quedó escrito donde ocurre el hecho, leído en la sesión: el log o la tabla que el sistema escribe en ese momento, el código que produce el valor, el mensaje en que alguien lo dijo, o la salida de una consulta o un script corrido en la sesión sobre ellos.
  - Más estricto que [`../methodology/principles.md`](../methodology/principles.md) § "Suposiciones explícitas antes de afirmar", que acepta la memoria: en un correo no bastan la memoria ni otro texto redactado (un correo anterior, el reporte de un rol delegado), porque registran lo que alguien concluyó y no el hecho.
  - Lo que el dev afirma en el encargo es fuente de lo que él decidió o hizo, no del estado de un sistema.
  - Una fila de la tabla «Hechos verificados» que viene de antes de una compactación o de otra sesión se vuelve a leer.
- **Fuente que discrimina.** Si el dato observado puede salir de más de una causa, la afirmación de una de ellas necesita la fuente que las separa: un campo vacío que el sistema escribe igual con una respuesta vacía que con un error de transporte no sostiene «respondió vacío»; el log del error, sí. Sin esa fuente, el correo dice solo lo que el dato sostiene o plantea las lecturas como hipótesis.
- **Lo que no se verifica** sale del correo, o va como pendiente de confirmar (§ "Estructura") o como hipótesis con la consulta que la resolvería.
- **Revisión adversarial si el correo atribuye una causa** a lo que observó el destinatario o al comportamiento de un sistema: un revisor que no lo redactó coteja cada afirmación de hecho con su fuente y busca otra causa que produzca el mismo dato; al regenerar, vuelve a correr solo si cambia una afirmación que sostiene la causa.
  - **Mecanismo vigente**: el subagente `correspondence-fact-checker`, que no recibe la conversación ni el arranque (supuestos R11 y R12 de [`../methodology/platform-assumptions.md`](../methodology/platform-assumptions.md)): el briefing lleva el cuerpo, las afirmaciones con su fuente y la ruta de la evidencia ya extraída (salidas guardadas en archivos, rutas del código).
- **Traza.** El reporte del chat que acompaña al correo lleva la tabla «Hechos verificados»: afirmación, fuente, qué descarta la otra lectura (`—` si el dato tiene una sola) y si pasó por el revisor. Las afirmaciones de una misma fuente van en una fila; un correo sin afirmaciones de hecho no lleva tabla. La tabla va en el chat, no en el `.html`.

## Formato del cuerpo (HTML)

- El cuerpo se genera como documento `.html` con `<meta charset="utf-8">` cuyo `<body>` contiene **solo el cuerpo del correo**, dentro de un `<div>` contenedor. Destinatarios, CC, asunto y notas para el dev van en la respuesta del chat, no en el `<body>`: ahí se copiarían como texto del cuerpo. Sin la declaración de charset, el visor puede romper los acentos.
- Estilos **inline** en cada elemento; sin `<style>`, `<script>`, atributos `class`/`id` ni recursos externos (hojas de estilo, fuentes, imágenes remotas): el cliente de correo puede descartarlos al pegar y el formato se pierde.
- La copia sale **del render, nunca del código**. Por defecto, Claude **adjunta el `.html` a su respuesta** como archivo que el dev abre renderizado y copia desde esa vista (en la app de escritorio de Claude Code, la tarjeta del archivo abre el render en un panel); si el entorno no muestra adjuntos (terminal), da la ruta del `.html` para abrirlo en el navegador. Cargar el cuerpo al portapapeles en formato HTML es una vía adicional, solo a pedido del dev o si el entorno la declara. El HTML crudo no se ofrece en el chat para copiarse: pegado en un cliente de correo llega como código.
- En el chat se reporta: una línea de qué es el correo o qué cambió, destinatarios/CC/asunto, el archivo adjunto (o su ruta), la tabla «Hechos verificados» (§ "Verificación de los hechos") y, en una línea, lo que se dejó fuera del cuerpo, para que el dev decida si sale y por dónde; el cuerpo no se repite en el chat. Si se usó el portapapeles, se avisa que quedó sustituido. Cada corrección regenera el `.html` y lo vuelve a adjuntar (y recarga el portapapeles, si se usó) en el mismo turno.
- Una respuesta de una o dos líneas sin formato (acuse, confirmación) va como texto en el chat, sin `.html`.
- Si la redacción se delega (subagente, workflow, script generador), el encargo incluye este archivo: el contexto de arranque no se da por heredado.

> **Punto de customización** (promesa 5): el idioma y el registro por defecto (cuando el destinatario o el hilo no los fijan), la vía de copia (adjunto renderizado por defecto; portapapeles o navegador) y la tipografía del contenedor se **sustituyen** desde el overlay (adoptante) o `personal/<usuario>.md` § "Preferencias de comunicación" (individuo); las restricciones del cliente de correo del adoptante (qué descarta al pegar) y las fichas de sus destinatarios (qué conoce cada uno) se **agregan** ahí. El resto del archivo es regla de proceso: un override la estrecha o agrega, nunca la relaja.
