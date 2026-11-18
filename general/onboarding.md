# Onboarding

Política transversal, fuera del arranque. Define qué ofrece el recorrido de bienvenida; el flujo que lo ejecuta lo lleva el skill `wakeup`. Los **pasos** de la configuración (instalar, montar overlay, definir profile) viven en [`../docs/user-guide.md`](../docs/user-guide.md); este archivo define **qué opciones** presenta el recorrido — no los pasos en sí.

## Trigger de oferta pasiva

El disparador (condición, acción y cita) vive en [`profile-detection.md`](profile-detection.md) § "Oferta pasiva del recorrido (onboarding)", que se carga al arranque.

**Re-invocación**: `/wakeup` corre el recorrido completo en cualquier momento y contexto, independientemente de si ya existe `personal/<usuario>.md`.

## Opciones del recorrido

El recorrido **no describe los pasos** —esos viven en [`../docs/user-guide.md`](../docs/user-guide.md)— sino que ofrece ejecutarlos. Tras presentar Neb y detectar el estado de la instalación, Claude ofrece las acciones de adopción como **menú de selección** (formato de [`communication.md`](communication.md) § "Elecciones: menú de selección"):

1. **Montar el overlay** — la capa propia donde vive lo del adoptante; paso mínimo para usar Neb (ver [user-guide § Montar tu overlay](../docs/user-guide.md)).
2. **Definir el primer profile** — concreta Neb para el dominio; puede incluir skill de apoyo y agentes revisores (ver [user-guide § Definir tu primer profile](../docs/user-guide.md)).
3. **Versionar la configuración personal** (ver [user-guide § Versionar tu configuración personal](../docs/user-guide.md)).

El detalle del flujo interactivo —cómo Claude ejecuta cada opción, detección de instalación previa— vive en el skill [`wakeup`](../skills/wakeup/SKILL.md).
