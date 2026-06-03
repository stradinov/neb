# Stack: requirements-analysis

Análisis iterativo de requerimientos para cualquier tipo de proyecto. El entregable es un **documento de Clarificación** que el stakeholder valida hasta aprobarlo.

## Cuándo aplica

Cuando el trabajo implica analizar, estimar y documentar requerimientos antes de implementar — independientemente del stack de implementación (web API, mobile, data, scripting, etc.).

**Como overlay**: si el proyecto usa un stack de implementación específico, este stack se activa para el subproyecto de análisis mientras el repo padre retiene su stack original.

## Características

- **Entregable**: documento de Clarificación en Markdown (versionado en git del proyecto).
- **Input**: descripción del stakeholder (texto libre, correo, tícket, notas de reunión).
- **Sin código ejecutable**: no hay build, tests unitarios ni servidor.
- **Receptor de la validación**: el stakeholder/cliente (no el dev).
- **Ciclo de entrega**: iterativo hasta aprobación (ver §"Ciclo iterativo").
- **Subproyecto autocontenido**: propia carpeta `reqs/<nombre>/`, artefactos propios, sin mezcla con el repo padre.

## Modos de operación

| Modo | Conductor | Input | Output |
|---|---|---|---|
| **Asistido** | Claude + BA humano + stakeholder | Descripción del stakeholder | `clar-v1` … `clar-approved` |
| **Autónomo** | Claude solo | Prompt crudo del stakeholder | `clar-v0-auto` (borrador para revisión BA) |

En modo autónomo Claude genera el primer borrador en un turno; el BA lo revisa antes de enviarlo al stakeholder. El borrador lleva siempre supuestos `[S-N]` y preguntas `[Q-N]` etiquetados — nunca se ocultan lagunas.

## Ciclo iterativo

```
clar-v1 → [revisión stakeholder] → clar-v2 → ... → clar-approved
```

Cada vuelta: stakeholder da feedback → BA incorpora y cierra `[Q-N]` → commit + notificación → nueva revisión.

## Glosario del stack

Concretización del [vocabulario abstracto](../../methodology/vocabulary.md):

| Término abstracto | En este stack |
|---|---|
| Entregable / elaboración | Documento de Clarificación (`clarificacion.md`) |
| Elaboración asistida | BA redacta con el stakeholder iterando sesión a sesión |
| Elaboración autónoma | Claude genera `clar-v0-auto` en un turno; BA revisa antes de elevar a `clar-v1` |
| Entrega para revisión | Commit `clar-vN` + notificación al stakeholder |
| Entrega final / aprobación final | Aprobación del stakeholder + commit `clar-approved` |
| Ambiente de revisión | Sesiones de revisión stakeholder↔analista (iterativas, asincrónicas) |
| Estado aprobado | Documento con commit `clar-approved` y aprobación registrada |
| Dependientes | Secciones del documento que referencian un supuesto `[S-N]` o caso de uso `[CU-N]` |
| Flujos críticos | Casos de uso con impacto en auth, pagos, datos sensibles o integraciones externas (prefijo `[crítico]`) |

## Estructura del subproyecto

```
<proyecto>/reqs/<nombre>/
├── CLAUDE.md                  ← imports al stack de análisis
├── clarificacion.md           ← documento vivo (versión actual)
├── preguntas-pendientes.md    ← lista mutable [Q-N]
├── dudas-internas.md          ← hipótesis del equipo sin compartir aún con el stakeholder
├── mockups/                   ← capturas, diagramas (opcional)
└── changes/                   ← meta-trabajo del análisis
```

## Detección

Sin heurística de detección automática — el adoptante importa el stack en el `CLAUDE.md` del subproyecto:

```
@<ruta-al-framework>/stacks/requirements-analysis/index.md
```

**Overlays sobre este base**: un overlay específico de dominio puede extender este stack para concretar la estimación al tipo de artefacto y a las integraciones propias del proyecto.

## Documentos

1. [Conventions](conventions.md) — naming, tags de iteración `[S-N]`/`[Q-N]`/`[CU-N]`, estados.
2. [Clarification template](clarification-template.md) — plantilla canónica del documento (frontmatter + secciones).
3. [Deployment](deployment.md) — ciclo de entrega y aprobación.
4. [Roles](roles.md) — Business Analyst + revisores.
5. [Skills](skills.md) — skills aplicables (candidatos).
6. [Troubleshooting](troubleshooting.md) — problemas comunes.
