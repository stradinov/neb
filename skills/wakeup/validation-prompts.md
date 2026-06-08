# Validation prompts — skill: wakeup

## Positivos (deben disparar el skill)

1. `/wakeup` — invocación directa; debe iniciar el tour sin preámbulo.
2. "¿Cómo empiezo con Neb?" — pregunta de usuario nuevo.
3. "Nunca usé esta metodología. ¿Qué tengo que hacer primero?"
4. "Dame un tour rápido de cómo funciona esto."
5. "Quiero montar mi overlay / crear mi primer stack. ¿Cómo lo hago?" — entrada directa a una opción del tour.
6. "Acabo de instalar Neb. ¿Por dónde arranco?"

## Negativos (NO deben disparar el skill)

1. "Agrega una función X al módulo Y" — tarea de implementación concreta; el flujo formal aplica.
2. "¿Qué hace `stack-detection.md`?" — pregunta técnica específica; leer y responder directo.
3. "Hola" — saludo; responder con pendientes activos según `communication.md`.
4. "¿Cuál es el criterio de cierre de la Fase 5?" — pregunta sobre la metodología; consultar el archivo correspondiente.
5. "Ayudame a revisar este PR" — tarea concreta; usar el workflow formal.
6. "¿Cuándo uso un skill vs un lineamiento?" — pregunta de diseño; responder desde `methodology/skills.md`.
