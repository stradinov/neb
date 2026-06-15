# Gate de autorización del cambio (Fase 4)

Gate de autorización antes de confirmar cambios durante la implementación. La política de ownership de `.md`, acciones destructivas y punto de restauración vive en [`../methodology/change-control-policy.md`](../methodology/change-control-policy.md).

Términos abstractos usados aquí ("Confirmación del cambio", "Punto de restauración"): ver [`../methodology/vocabulary.md`](../methodology/vocabulary.md).

## Autorización de la confirmación del cambio (Fase 4)

Confirmar un cambio = hacerlo permanente y recuperable en el mecanismo del profile. Antes de cada confirmación que toque el entregable del proyecto destino durante la implementación, Claude espera **OK explícito** del dev. El mecanismo de revisión (diff, IDE externo, listado de cambios) queda a criterio del dev — el lineamiento prescribe solo el OK.

- **Granularidad**: un OK por confirmación separada. Si el REQ replica a N destinos, el OK aplica a cada confirmación individual — un OK global al inicio del REQ no autoriza las siguientes.
- **Excepción — artefactos que Neb genera / solo-`.md`**: ver § "Ownership de archivos `.md`" en [`../methodology/change-control-policy.md`](../methodology/change-control-policy.md).
- **Excepción — validación diferida** (profile `self-applied`): tras plan aprobado + Fase 4 cerrada, Claude confirma sin OK (ver `profiles/self-applied/deployment.md`). La excepción cubre confirmar el **entregable**; el **registro del requerimiento** (change MD — ver [`../methodology/vocabulary.md`](../methodology/vocabulary.md) § "Registro del requerimiento"), por ser `.md`-only, además puede confirmarse y **entregarse** temprano cuando el entorno de validación es compartido (ver [`../workflow/changes.md`](../workflow/changes.md) § "Ciclo de vida del draft" y [`version-control.md`](version-control.md) § Push).
- **Excepción — autonomía declarada por proyecto**: cuando `personal/<usuario>.md` o la memoria del dev declara autonomía explícita para un proyecto (caso típico: una herramienta interna de bajo riesgo, de uso propio), Claude confirma sin pedir OK en ese proyecto.

Las exclusiones propias del mecanismo git (artefactos de gobernanza del REQ: VERSION, CHANGELOG, fragments) viven en [`version-control.md`](version-control.md).
