# Onboarding

Política transversal. Define el comportamiento de Claude al detectar un usuario nuevo y qué ofrece el tour de bienvenida disponible vía `/wakeup`. Los **pasos** del setup (instalar, montar overlay, definir profile) viven en [`../docs/user-guide.md`](../docs/user-guide.md); este archivo define **cuándo** Claude ofrece el tour y **qué opciones** presenta — no los pasos en sí.

## Trigger de oferta pasiva

**Condición**: el profile activo es `self-applied` (el cwd está en el repo de neb) Y el contexto de la sesión no incluye contenido de `personal/<usuario>.md` — sin sección de preferencias personales, atajos ni paths absolutos de la máquina del dev en el contexto cargado.

**Acción**: al cierre del primer turno que cumpla la condición, Claude agrega:

> "Para un tour de Neb (3-5 min), invocá `/wakeup`."

Sin preámbulo, sin interrumpir el trabajo. El tour es opt-in.

**Re-invocación**: `/wakeup` corre el tour completo en cualquier momento y contexto, independientemente de si ya existe `personal/<usuario>.md`.

## Opciones del tour

El tour **no describe los pasos** —esos viven en [`../docs/user-guide.md`](../docs/user-guide.md)— sino que ofrece ejecutarlos. Tras presentar Neb y detectar el estado de la instalación, Claude ofrece las acciones de adopción como opciones numeradas (formato de [`communication.md`](communication.md) § "Tono y forma"):

1. **Montar tu overlay** — la capa propia donde vive lo del adoptante; paso mínimo para usar Neb (ver [user-guide § Montar tu overlay](../docs/user-guide.md)).
2. **Definir tu primer profile** — concreta Neb para el dominio; puede incluir skill de apoyo y agentes revisores (ver [user-guide § Definir tu primer profile](../docs/user-guide.md)).
3. **Versionar la configuración personal** (ver [user-guide § Versionar tu configuración personal](../docs/user-guide.md)).

El detalle del flujo interactivo —cómo Claude ejecuta cada opción, detección de instalación previa— vive en el skill [`wakeup`](../skills/wakeup/SKILL.md).
