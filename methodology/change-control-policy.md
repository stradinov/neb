# Política de control de cambios

Política transversal **agnóstica del mecanismo**: ownership de archivos `.md`, acciones destructivas, punto de restauración y contrato del mecanismo de versionamiento. La concretización para git (comandos, formato de commits, ramas, CHANGELOG) vive en [`../process/version-control.md`](../process/version-control.md); el gate de autorización en Fase 4 vive en [`../process/change-control-gate.md`](../process/change-control-gate.md).

Términos abstractos usados aquí ("Confirmación del cambio", "Punto de restauración"): ver [vocabulary.md](vocabulary.md).

## Ownership de archivos `.md`

Claude es **dueño operativo** de los **artefactos que Neb genera y administra** —[registros del requerimiento](vocabulary.md#registro-del-requerimiento) (change/incident MD), `pendings`, planes aprobados, métricas— por su **rol** (metadata del proceso que Neb produce, no entregable del proyecto); el dev los consulta para diagnóstico, no los redacta. De forma **derivada**, la autonomía cubre **cualquier archivo `.md`** del repo: su naturaleza documental los hace de bajo riesgo y revisables en diff. En consecuencia, las confirmaciones que tocan **exclusivamente** esos artefactos —o, en general, solo `.md`— no requieren OK del dev en ninguna fase (1–9) ni profile.

> Criterio: el discriminador primario es el **rol/función** (lo que Neb genera), no la extensión — `.md` es el rasgo **derivado**, no el definitorio (ver [vocabulary.md](vocabulary.md) § "Discriminador registro vs entregable: el rol, no la extensión"). La frontera de lo autónomo coincide con el criterio `.md`-only previo (todo artefacto que Neb genera es hoy `.md`); el encuadre por rol nombra *por qué* esos artefactos son de Claude y resiste casos futuros donde un artefacto de proceso no sea `.md`.

- **No aplica a**:
  - Confirmaciones **mixtas** `.md` + entregable no-documental — piden OK por la parte más restrictiva; la autonomía sobre `.md` no contagia al resto.
  - Memorias personales del dev (`~/.claude/projects/.../memory/*.md`) — Claude propone deltas inline; el dev los aplica.
  - `.md` de upstream en forks de proyectos externos — la autonomía cubre solo los `.md` agregados por el equipo.
  - **Segmentos de contenido humano** delimitados por `<!-- human -->` … `<!-- /human -->` dentro de un `.md` — marcan contenido que un humano redacta y mantiene bajo su control directo (voz de autor, prefacio, narrativa de marca). El propósito del marcador es **preservar esa voz e intención intactas frente a la edición autónoma del agente**: Claude lo lee como contexto y puede **proponer** deltas inline, pero **no edita** el contenido entre los marcadores sin OK explícito del dev (mismo trato que las memorias personales). El resto del archivo sigue bajo la autonomía normal.

La materialización en operaciones del VCS (qué cubre, límites sobre historia compartida y tags publicados) vive en [`../process/version-control.md`](../process/version-control.md) § "Autonomía de Claude sobre archivos `.md`".

Uso canónico de esta autonomía — **entrega temprana del registro del requerimiento**: el registro (change MD — ver [`vocabulary.md`](vocabulary.md) § "Registro del requerimiento") es `.md`, así que confirmarlo y entregarlo (en git: commit + push) cae bajo esta autonomía sin OK del dev cuando el delta es solo-`.md`, desacoplado de la entrega del entregable. Aplica cuando el entorno de validación es compartido (señal determinista: el `work` se publica a una bitácora compartida); fuera de ese caso el registro se confirma/entrega en el cierre. No redefine el ownership: solo lo aplica al registro. La **validación del entregable** (cuando el entregable es `.md`, p. ej. la metodología misma) sigue su propio gate — son `.md` distintos. Condición y momento: [`../workflow/changes.md`](../workflow/changes.md) § "Ciclo de vida del draft"; operaciones git: [`../process/version-control.md`](../process/version-control.md) § Push.

## Acciones destructivas

Ninguna acción que **reescriba historia o destruya estado recuperable** del entregable se ejecuta sin OK explícito del dev. La autorización contextual (ej. restaurar un archivo durante el rollback de un incidente) no la viola. Los comandos concretos que caen en esta categoría dependen del mecanismo y se enumeran en [`../process/version-control.md`](../process/version-control.md).

## Punto de restauración

Antes de la entrega final debe existir un **punto de restauración** — un estado previo recuperable que habilite rollback rápido. Sin punto de restauración no hay rollback (ver [`../general/incidents.md`](../general/incidents.md)).

Concretización por naturaleza del entregable: confirmación previa (entregables con control de versiones) · versión anterior etiquetada (documentos) · backup explícito (datos).

## Mecanismo de versionamiento por profile

Cada profile declara su mecanismo en `profiles/<profile>/deployment.md`. Sea cual sea, debe proveer **confirmación del cambio** (hacer permanente y recuperable) y **punto de restauración** (rollback).

Hoy todos los profiles usan **git** (los versionados con git se enumeran en [`../workflow/traceability.md`](../workflow/traceability.md); un profile de análisis de requerimientos versiona en el git del proyecto al que sirve); su concretización vive en [`../process/version-control.md`](../process/version-control.md). Un profile futuro sin git instancia el mismo contrato con otro medio —versiones etiquetadas, snapshot/backup, o entrega directa con backup previo como punto de restauración— declarándolo en su `deployment.md` sin necesitar git.
