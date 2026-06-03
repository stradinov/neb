# Taxonomía completa de errores de redacción en español

Documento de referencia para configurar un agente corrector. Está organizado en dos partes:

1. **Taxonomía** — los errores agrupados por nivel de la lengua, con ejemplos.
2. **Políticas configurables** — los parámetros que el usuario puede ajustar para que el corrector adapte sus criterios al tipo de texto, región, registro y tolerancia deseada. Al final hay una plantilla YAML lista para usar.

---

## Parte 1 — Taxonomía

### 1. Ortografía literal

Afecta las letras que componen una palabra.

- **Confusión de grafemas:** *bender* por vender, *extructura* por estructura, *exhuberante* por exuberante.
- **Confusión b/v, s/c/z, g/j, ll/y, h muda:** *aver* por a ver, *halla/aya/haya*, *vasura* por basura.
- **Omisión o adición de letras:** *transtorno* por trastorno, *aréa* por área.
- **Errores en homófonos:** *a ver* / *haber*, *halla* / *haya* / *allá*, *valla* / *vaya*, *hecho* / *echo*.
- **Errores en grupos consonánticos:** *opción* mal escrito como *obción*, *absorber* como *absorver*.

### 2. Ortografía acentual

Afecta tildes y diéresis.

- **Omisión de tilde obligatoria:** *examen* sin tilde en plural *exámenes*, *facil* por fácil.
- **Tilde de más:** *fué*, *dí*, *vió*, *ti* con tilde, *guión* (hoy monosílabo).
- **Tilde diacrítica mal aplicada:** confundir *sí/si*, *té/te*, *él/el*, *más/mas*, *sólo/solo* (la RAE ya no exige tilde en *solo*, pero el usuario puede configurarlo).
- **Acentuación en mayúsculas:** mito persistente; las mayúsculas **sí** llevan tilde (*ÉXITO*, no *EXITO*).
- **Diéresis omitida:** *pinguino* por pingüino, *verguenza* por vergüenza.
- **Tildes en palabras compuestas y adverbios en -mente:** *fácilmente* (conserva la tilde del adjetivo).

### 3. Ortografía puntual

Afecta el uso de signos de puntuación.

- **Omisión del signo de apertura `¿` o `¡`:** el español exige signo doble por carecer de marcas sintácticas de interrogación al inicio.
- **Coma criminal (*comma splice*):** unir dos oraciones independientes solo con coma. *Llegué tarde, no había nadie* → punto, punto y coma, o conector.
- **Coma entre sujeto y verbo:** *Los estudiantes que vinieron ayer, aprobaron el examen* (la coma sobra).
- **Coma faltante en vocativo, aposición o inciso:** *Juan ven aquí* → *Juan, ven aquí*.
- **Punto y coma mal empleado** o evitado donde es necesario.
- **Dos puntos antes de enumeración indebidos** o ausentes.
- **Puntos suspensivos mal formados** (más de tres, o seguidos de coma redundante).
- **Paréntesis, corchetes y rayas mal pareados** o con espaciado incorrecto.
- **Uso del punto en abreviaturas y siglas:** *EE.UU.* vs *EEUU*, *Sr./Sra.*

### 4. Tipografía

Errores visuales que no afectan el contenido pero sí la calidad del texto.

- **Comillas inglesas `"..."`** en lugar de las españolas `«...»` (primer nivel) o `"..."` (segundo nivel).
- **Confusión guion / raya / signo menos:** `-` (guion, para palabras compuestas), `—` (raya, para incisos y diálogos), `−` (menos, matemático).
- **Espacios dobles, espacios antes de signo de puntuación, falta de espacio tras coma o punto.**
- **Apóstrofos rectos `'` en lugar de tipográficos `'`** (poco usado en español, pero relevante en citas en otros idiomas).
- **Uso incorrecto de cursivas:** los extranjerismos crudos van en cursiva (*software*, *à la carte*); los castellanizados no.
- **Mayúsculas sostenidas (ALL CAPS) como énfasis:** mal estilo en texto formal.
- **Negritas y subrayados excesivos.**

### 5. Morfología

Afecta la formación interna de las palabras.

- **Conjugaciones irregulares mal hechas:** *andé* por anduve, *haiga* por haya, *satisfació* por satisfizo, *forzo* por fuerzo.
- **Plurales inventados:** *sofases*, *cafeses*, *pieses*.
- **Plurales de siglas y extranjerismos:** *los CD* (no *los CDs*), *los currículos* o *los currículums* (no *currícula*).
- **Femeninos y masculinos forzados:** *la chofer* / *la chofera*, *miembra*.
- **Sufijos y prefijos inexistentes o mal usados:** *aperturar* por abrir, *concretizar* por concretar, *recepcionar* por recibir.
- **Diminutivos y aumentativos mal formados** según la región.

### 6. Sintaxis

Afecta la relación entre palabras dentro de la oración.

- **Discordancia de género, número o persona:** *La gente son buena*, *Hubieron problemas* (verbo *haber* impersonal es siempre singular).
- **Dequeísmo:** *Pienso de que es tarde*.
- **Queísmo:** *Estoy seguro que vendrá* (correcto: *seguro de que*).
- **Leísmo, laísmo, loísmo:**
  - Leísmo de persona masculina: *Le vi* por *Lo vi* (aceptado por RAE en España).
  - Leísmo de cosa: *El libro, le leí* (incorrecto en todas las variedades).
  - Laísmo: *La dije que viniera* (incorrecto).
  - Loísmo: *Lo di un beso* (incorrecto).
- **"Se los/las dije" pluralizado por contagio:** *Se los dije a ellos* (incorrecto; *se* no pluraliza, debe ser *se lo dije*). Muy extendido en América.
- **Mala colocación de pronombres clíticos:** *Me se cayó* por *Se me cayó*.
- **Gerundios mal empleados:**
  - De posterioridad: *Salió de casa, llegando tarde* (la llegada es posterior).
  - Especificativo: *Necesito un empleado hablando inglés* → *que hable inglés*.
  - De consecuencia: *Se cayó, rompiéndose la pierna*.
- **Correlación de tiempos verbales errónea:** *Si tendría dinero, lo compraría* → *Si tuviera*.
- **"A" personal mal usada u omitida:** *Vi Juan* (falta la *a*), *Busco a un empleado* (sobra cuando es indeterminado).
- **Voz pasiva calcada del inglés:** *El informe fue elaborado por el equipo* en lugar de *El equipo elaboró el informe* o *Se elaboró el informe*.
- **Anacoluto:** ruptura sintáctica que deja la oración sin terminar lo que prometió.
- **Concordancia ad sensum (silepsis):** *La mayoría de los estudiantes aprobaron* (la RAE acepta ambas concordancias).
- **Calcos sintácticos del inglés:** *aplicar a un trabajo* (postularse), *atender un evento* (asistir), *estoy esperando por ti* (te estoy esperando), *en orden de* (para).
- **Hipérbaton forzado:** orden antinatural sin valor estilístico.

### 7. Semántica

Afecta el significado y la lógica del enunciado.

- **Ambigüedad o anfibología:** *Se vende ropa para niños de lana*; *Vi a Juan paseando por el parque* (¿quién paseaba?).
- **Pleonasmo o redundancia:** *subir arriba*, *prever con antelación*, *cita previa*, *erradicar de raíz*.
- **Impropiedad léxica:** usar una palabra con significado equivocado. *El argumento fue muy severo* (por sólido), *álgido* usado como "acalorado".
- **Falsos amigos:** *eventualmente* como *eventually* (al final) en vez de *posiblemente*; *actualmente* como *actually*; *asumir* como *to assume* (suponer); *realizar* como *to realize* (darse cuenta).
- **Contradicción local o global:** afirmaciones lógicamente incompatibles.
- **Catacresis:** uso forzado o impropio de una metáfora muerta.

### 8. Léxico

Afecta la elección de vocabulario.

- **Barbarismos:** *a grosso modo* (correcto: *grosso modo*), *de motu propio* (correcto: *motu proprio*).
- **Extranjerismos innecesarios:** *hacer un forward*, *un meeting*, *un link*, *un deadline* — cuando hay equivalente claro en español.
- **Cosificación o palabras comodín:** abuso de *cosa*, *algo*, *hacer*, *tener*, *poner*. *Tengo una cosa que decirte*, *Hacer una carta*.
- **Arcaísmos:** *asimesmo*, *maguer*, *otrosí*.
- **Neologismos innecesarios o mal formados:** *aperturar*, *empoderamiento* (aceptado), *clickear*.
- **Vulgarismos y dialectalismos** fuera de contexto.
- **Tecnicismos innecesarios** en texto divulgativo.

### 9. Pragmática y estilo

El texto es gramaticalmente correcto pero falla en adecuación o calidad.

- **Inadecuación del registro:** lenguaje coloquial en texto académico, o pomposo en uno informal.
- **Cacofonía:** repetición desagradable de sonidos. *Juana corre rápido en la pista*; *en relación a la situación de la asignación*.
- **Monotonía o pobreza léxica:** repetir la misma palabra en un párrafo corto.
- **Muletillas y conectores abusados:** *básicamente*, *por lo tanto*, *es decir*, *de hecho* al inicio de cada oración.
- **Adverbios en -mente encadenados:** *rápidamente y eficazmente actuó decididamente*.
- **Verbos comodín y construcciones perifrásticas innecesarias:** *hacer mención de* por *mencionar*, *llevar a cabo* por *realizar*, *dar comienzo a* por *empezar*.
- **Voz pasiva abusiva** donde la activa es más natural.
- **Nominalización excesiva (estilo burocrático):** *la realización de la verificación de los documentos* por *verificar los documentos*.

### 10. Cohesión y coherencia textual

Errores que solo se ven a nivel de párrafo o texto.

- **Conectores que no corresponden a la relación lógica:** *sin embargo* sin oposición real, *por lo tanto* sin causa previa.
- **Saltos temáticos sin transición.**
- **Falta de progresión informativa:** repetir lo dicho sin avanzar.
- **Referencia anafórica ambigua:** pronombres o demostrativos sin antecedente claro.
- **Párrafos kilométricos** sin punto y aparte.
- **Párrafos demasiado cortos** que fragmentan ideas que pertenecen juntas.
- **Inconsistencia en persona o tiempo verbal:** alternar tú/usted, o presente/pretérito sin motivo.
- **Inconsistencia terminológica:** llamar al mismo concepto con nombres distintos sin justificación.

### 11. Formato y convenciones

Errores en la representación de elementos no textuales.

- **Cifras y letras:** mezcla incoherente (*5 personas* vs *cinco personas*); la norma general es escribir con letra del cero al nueve o hasta el veintinueve según manual de estilo.
- **Decimales:** español culto usa coma (*3,14*), no punto.
- **Miles:** punto o espacio fino, no coma. La norma técnica internacional prefiere espacio (*1 000 000*).
- **Unidades de medida:** espacio entre cifra y unidad (*5 kg*, no *5kg*), símbolos sin punto (*kg*, no *kg.*), sin pluralizar (*5 km*, no *5 kms*).
- **Fechas:** orden día-mes-año en español (*17 de mayo de 2026*), mes en minúscula.
- **Horas:** *las 9:30* o *las 9.30*, no *9:30 PM* (anglicismo); preferir *las 9:30 de la noche* o formato de 24 horas.
- **Porcentajes:** espacio entre cifra y símbolo (*25 %*), aunque el uso pegado está extendido.
- **Símbolo de moneda:** posición y espaciado según norma (*$1 000* o *1 000 $* según país).
- **Mayúsculas indebidas:** meses, días, gentilicios, cargos (*el Presidente* → *el presidente*), idiomas, estaciones.
- **Mayúsculas faltantes:** después de punto, en nombres propios, en siglas.
- **Abreviaturas mal formadas:** *etc..*, *Sr* sin punto, *Uds*.

---

## Parte 2 — Políticas configurables

Estas son las perillas que el usuario puede mover para que el corrector se comporte de la manera deseada. Las agrupo por tipo de decisión.

### A. Variedad regional del español

Determina qué se considera estándar.

- `mexico` — Norma mexicana culta. Ustedes para plural, leísmo no aceptado, no voseo.
- `espana` — Norma peninsular. Vosotros aceptado, leísmo de persona masculino aceptado.
- `rioplatense` — Voseo estándar (Argentina, Uruguay). *Vos tenés*.
- `andino` — Variedades andinas (Perú, Bolivia, Ecuador).
- `caribeno` — Variedades caribeñas.
- `neutro` — Español internacional, evitar regionalismos marcados.

### B. Nivel de estrictez

Qué tan exigente es el corrector con la norma académica.

- `purista` — Aplica la RAE al pie de la letra, marca todo lo no recomendado aunque esté aceptado.
- `estandar` — Sigue lo que la RAE considera correcto, acepta lo que la RAE acepta aunque no recomiende.
- `flexible` — Acepta usos asentados aunque la RAE no los registre todavía.
- `descriptivo` — Solo marca errores que dificulten la comprensión o sean claramente agramaticales.

### C. Registro

- `formal_academico` — Texto académico, científico, legal.
- `formal_profesional` — Documentos de trabajo, correos formales.
- `neutro` — Periodístico, divulgación.
- `informal` — Blog, redes sociales, mensajes personales.
- `literario` — Permite licencias estilísticas.
- `tecnico` — Tolera tecnicismos y extranjerismos del campo.

### D. Dominio o género del texto

- `academico`
- `periodistico`
- `juridico`
- `medico`
- `tecnico_software`
- `marketing`
- `narrativa`
- `correspondencia`
- `redes_sociales`

El dominio modula qué se considera apropiado: en software *deployar* puede pasar; en un texto académico de historia no.

### E. Zonas grises (toggles individuales)

Cada uno es booleano. Estos son los casos donde no hay consenso o donde la región pesa.

- `permitir_leismo_persona_masculino` — Aceptar *le vi* referido a varón.
- `permitir_se_los_se_las_pluralizado` — Aceptar *se los dije a ellos*.
- `permitir_concordancia_ad_sensum` — Aceptar *la mayoría aprobaron*.
- `exigir_tilde_solo_adverbio` — Forzar *sólo* cuando es adverbio (contra la RAE actual).
- `exigir_tildes_demostrativos` — Forzar *éste/ése/aquél* (contra la RAE actual).
- `permitir_dequeismo_marginal` — Aceptar dequeísmo en verbos donde la frontera es borrosa.
- `permitir_voseo` — Aceptar formas voseantes.
- `permitir_ustedeo_general` — Convertir todo *tú* a *usted* o viceversa.
- `permitir_inicio_oracion_con_pero_y` — Aceptar *Pero* y *Y* al inicio de oración.
- `permitir_gerundio_simultaneidad_amplia` — Más tolerante con gerundios de simultaneidad.
- `permitir_pasiva_perifrastica` — No marcar la voz pasiva con *ser*.
- `permitir_anglicismo_sintactico_asentado` — Tolerar calcos muy extendidos como *aplicar a*.

### F. Tratamiento de extranjerismos

- `traducir_siempre` — Reemplazar todo extranjerismo que tenga equivalente español.
- `traducir_si_hay_equivalente_claro` — Solo si el equivalente es inequívoco y natural.
- `marcar_pero_no_cambiar` — Señalar pero respetar la elección del autor.
- `respetar_si_estan_en_cursiva` — Aceptar si vienen marcados tipográficamente.
- `respetar_todos` — No intervenir en vocabulario extranjero.

Sublista por categoría: tecnología, gastronomía, moda, deportes, negocios — se puede permitir extranjerismos en una y no en otra.

### G. Convenciones tipográficas y de formato

- `comillas` — `espanolas_angulares` («…»), `espanolas_altas` ("…"), `inglesas` ("…").
- `decimales` — `coma` o `punto`.
- `miles` — `punto`, `espacio_fino`, `coma`, o `ninguno`.
- `formato_hora` — `24h` o `12h_con_palabras`.
- `formato_fecha` — `dd_de_mes_de_aaaa`, `dd/mm/aaaa`, `iso_aaaa-mm-dd`.
- `unidades_pegadas` — `false` por defecto (siempre espacio).
- `porcentaje_espaciado` — `con_espacio` (norma) o `sin_espacio` (uso común).
- `raya_dialogo` — `raya_em` (—) o `guion_largo`.
- `numeros_letra_hasta` — entero; por debajo se escribe con letra, encima con cifra.

### H. Estilo

- `tolerancia_cacofonia` — `alta`, `media`, `baja`.
- `tolerancia_repeticion_lexica` — distancia mínima en palabras entre repeticiones.
- `tolerancia_adverbios_mente_seguidos` — máximo permitido en una frase.
- `longitud_maxima_oracion` — palabras o ninguna.
- `longitud_maxima_parrafo` — oraciones o ninguna.
- `permitir_voz_pasiva` — `siempre`, `con_moderacion`, `nunca`.
- `permitir_nominalizaciones` — `siempre`, `con_moderacion`, `nunca`.
- `preferir_activa_sobre_pasiva` — bool.
- `tono` — `objetivo`, `personal`, `mantener_original`.

### I. Tratamiento del texto original

Determina hasta dónde puede intervenir el corrector.

- `solo_marcar` — Devolver el texto original con anotaciones, sin tocarlo.
- `sugerir` — Devolver original más sugerencias separadas.
- `corregir_obligatorios` — Aplicar correcciones inequívocas; sugerir el resto.
- `corregir_todo` — Aplicar todas las correcciones según las políticas.
- `reescribir` — Permitir reformular oraciones completas si mejora claridad.

Submodificadores:

- `preservar_voz_autor` — bool. Evita reescrituras que cambien el estilo.
- `preservar_extension` — bool. No reducir ni alargar significativamente.
- `preservar_terminologia` — lista de términos intocables.
- `excepciones` — fragmentos marcados que no se deben corregir (citas, código, nombres propios).

### J. Formato de salida

- `texto_corregido_unico` — Solo el resultado final.
- `texto_corregido_mas_lista` — Resultado más lista de cambios.
- `diff` — Mostrar diferencias en formato unificado o con marcas.
- `tabla_de_cambios` — Columnas: original, corregido, categoría, regla aplicada.
- `inline_anotado` — Texto con anotaciones intercaladas tipo [error: ...].
- `idioma_explicaciones` — `es`, `en`, etc.
- `nivel_detalle_explicaciones` — `ninguno`, `breve`, `completo_con_referencia_rae`.

---

## Plantilla de configuración

```yaml
# Configuración del corrector — adapta los valores a tu caso
variedad: mexico              # mexico | espana | rioplatense | andino | caribeno | neutro
estrictez: estandar           # purista | estandar | flexible | descriptivo
registro: formal_profesional  # formal_academico | formal_profesional | neutro | informal | literario | tecnico
dominio: correspondencia      # academico | periodistico | juridico | medico | tecnico_software | marketing | narrativa | correspondencia | redes_sociales

zonas_grises:
  permitir_leismo_persona_masculino: false
  permitir_se_los_se_las_pluralizado: false
  permitir_concordancia_ad_sensum: true
  exigir_tilde_solo_adverbio: false
  exigir_tildes_demostrativos: false
  permitir_voseo: false
  permitir_inicio_oracion_con_pero_y: true
  permitir_gerundio_simultaneidad_amplia: true
  permitir_pasiva_perifrastica: true
  permitir_anglicismo_sintactico_asentado: false

extranjerismos:
  politica: traducir_si_hay_equivalente_claro
  permitir_en_dominios: [tecnico_software]

tipografia:
  comillas: espanolas_angulares
  decimales: coma
  miles: espacio_fino
  formato_hora: 24h
  formato_fecha: dd_de_mes_de_aaaa
  porcentaje_espaciado: con_espacio
  raya_dialogo: raya_em
  numeros_letra_hasta: 29

estilo:
  tolerancia_cacofonia: media
  tolerancia_repeticion_lexica: 15        # palabras de distancia mínima
  tolerancia_adverbios_mente_seguidos: 1
  longitud_maxima_oracion: 35             # palabras; null para sin límite
  longitud_maxima_parrafo: 8              # oraciones; null para sin límite
  permitir_voz_pasiva: con_moderacion
  permitir_nominalizaciones: con_moderacion
  tono: mantener_original

intervencion:
  modo: corregir_obligatorios             # solo_marcar | sugerir | corregir_obligatorios | corregir_todo | reescribir
  preservar_voz_autor: true
  preservar_extension: true
  preservar_terminologia: []
  excepciones: [citas_textuales, codigo, nombres_propios]

salida:
  formato: tabla_de_cambios               # texto_corregido_unico | texto_corregido_mas_lista | diff | tabla_de_cambios | inline_anotado
  idioma_explicaciones: es
  nivel_detalle_explicaciones: breve
```

---

## Notas de uso

- La taxonomía y las políticas están pensadas para alimentar el *system prompt* de un corrector basado en Claude. Puedes pegar este documento entero como referencia o extraer solo las secciones relevantes.
- Las zonas grises son las que más conviene exponer al usuario final, porque son donde dos hablantes cultos pueden discrepar.
- Para un agente de preprocesamiento (que corrige antes de pasar el prompt al modelo principal), conviene `modo: corregir_obligatorios` con `preservar_voz_autor: true` y `salida: texto_corregido_unico`. Para un corrector editorial, conviene `tabla_de_cambios` con `nivel_detalle_explicaciones: completo_con_referencia_rae`.
