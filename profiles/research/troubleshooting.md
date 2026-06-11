# Troubleshooting (profile: research)

## Divergencia material entre fuentes

**Síntomas**: dos o más fuentes entregan claims contradictorios en una dimensión central de la investigación.

**Diagnóstico**: identificar exactamente el claim en disputa. Clasificar: ¿diferencia de versión/fecha? ¿sesgo de la fuente o de entrenamiento (si es voz LLM)? ¿ambigüedad en el prompt?

**Solución**:
1. Invocar `fact-check-reviewer` en Fase 4 (divergencia material es trigger independiente del propósito declarado — aplica también en `exploratorio`).
2. En la síntesis, documentar la divergencia explícitamente en la tabla "Dimensiones investigadas" columna "Discrepancias".
3. Si la divergencia afecta una dimensión `[crítico]`: no cerrar la investigación hasta resolver con una fuente adicional (doc oficial, benchmark, paper).

---

## Ninguna fuente convergió en un claim útil

**Síntomas**: todas las fuentes responden con vaguedad, se contradicen o no aportan.

**Diagnóstico**: el tema puede ser demasiado reciente, demasiado específico (dominio interno), o el prompt fue ambiguo.

**Solución**:
1. Re-formular el prompt con más contexto y re-consultar.
2. Si sigue sin convergencia: documentar en la síntesis "No se obtuvo consenso — fuente adicional recomendada" y marcar `propósito = exploratorio` aunque se había declarado `decisión`. Escalar al dev.
3. Añadir a Fase 9: el tema no se beneficia de multi-fuente ni de la voz externa — candidato a restricción en conventions.md.

---

## Sospecha de alucinación

**Síntomas**: una fuente cita URLs, versiones, fechas o estadísticas que no pueden verificarse.

**Diagnóstico**: intentar verificar el claim con una búsqueda directa o fuente oficial. Si no se puede confirmar en ≤2 intentos, considerar alucinación probable.

**Solución**:
1. No incluir el claim en la síntesis sin verificación.
2. Si el claim es central: invocar `fact-check-reviewer` antes de continuar.
3. Documentar en el anexo: "Claim de `<fuente>` sobre `<tema>` no verificable — omitido de síntesis".

---

## Fuente no disponible o acceso bloqueado

**Síntomas**: la fuente, el motor o la URL a consultar no responde, está bloqueado, o requiere autenticación de pago.

**Diagnóstico**: verificar si hay alternativa equivalente disponible (ver jerarquía de motor en [conventions.md](conventions.md) §Mecanismo recomendado — p. ej. degradar de `deep-research` al piso `WebSearch`/`WebFetch`).

**Solución**: sustituir por la alternativa disponible. Documentar en el frontmatter `llms_consultados` qué se usó en reemplazo y por qué.

---

## Research obsoleto citado desde otro documento

**Síntomas**: un archivo cita un research con `status: superseded` o `status: deprecated`.

**Diagnóstico**: verificar si el research nuevo (`superseded_by`) resuelve la necesidad del citador.

**Solución**: actualizar la cita en el documento consumidor para apuntar al research nuevo. Anotar en Fase 9 del REQ que lo detectó.
