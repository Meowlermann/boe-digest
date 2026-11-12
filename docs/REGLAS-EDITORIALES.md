# Reglas editoriales

Reglas de lo que se publica y de cómo se escribe. No están abiertas a
discusión en cada tarea. Si una PR las cambia, se actualiza este fichero
y [DECISIONES.md](DECISIONES.md) en la misma PR.

El contacto público es contacto@terceracamara.es. En un repositorio
público no se escriben nombres de personas, correos personales, cuentas
ni secretos. Los nombres propios solo salen del boletín oficial y en su
función pública.

## No inventar datos

No se inventa ningún dato, cifra, nombre, fecha ni cita. Solo se usa lo
que aparece en la publicación oficial. No se atribuye a nadie una frase
que no figure literalmente en el documento. Lo que va entre comillas es
literal de la fuente: se puede recortar (con «…» o «[…]») y quitar
acotaciones, pero nunca reescribir.

Si un dato no se puede obtener, se dice. No se rellena ni se estima sin
avisar. Cada pieza enlaza al documento concreto del que sale, no a una
portada.

La sátira, si la hay, va en el titular y en el ángulo, nunca en los hechos.

## La misma mordacidad para todo el arco político

La mordacidad se reparte por igual entre todos los grupos políticos.
Ningún día puede quedar como un ataque desproporcionado a un solo
partido. El mismo criterio vale para todo el arco.

## Lenguaje llano

Se escribe en castellano llano, para un lector que no tiene por qué
conocer la jerga del BOE ni de las Cortes. Si hace falta un término
técnico, se explica junto al dato. Se evitan las siglas opacas y los
rótulos que solo entiende quien ya trabaja con el boletín.

## Publicar solo lo claro

Si una extracción, una clasificación o una frase no está clara, no se
publica como si lo estuviera. En la duda, se omite o se remite a la
fuente oficial. Las herramientas nuevas son deterministas: nada de
modelos ni de APIs de pago.

## Nunca calcular fechas, plazos ni estados en empleo

En empleo no se calculan fechas de cierre, plazos ni estados. El plazo
se muestra en lenguaje llano solo cuando la frase literal del BOE pasa
una regla estricta; si no, se remite a «Consulta el plazo en el BOE».
La fecha de otro diario (autonómico o provincial) solo se cita cuando el
propio BOE la trae completa y sin ambigüedad; no se construye un enlace
ni se infiere el día. El estado de una convocatoria es el que consta,
no el que resultaría de contar días.

## Sin LLM, salvo los titulares de Gemini, con su etiqueta de IA

La única capa con modelo es `redaccion.py` (Gemini), y solo para
titulares y entradillas de piezas que ya tienen texto oficial. Se
publican si pasan la verificación contra la fuente, dentro de la cuota
gratuita o de la suscripción. Van marcados como editoriales (etiqueta
visible y `alternativeHeadline` en el JSON-LD). El resto del sitio —
resúmenes deterministas, archivo histórico, extractores, clasificaciones—
no usa modelos. No se añade un LLM nuevo ni dependencias de pago.

## Evitar tarjetas y subrayados

No se abusa de tarjetas: cuando una lista o una fila tipográfica basta,
se prefiere eso. El diseño no usa subrayados en los enlaces como
recurso visual. Los mockups son solo referencia; en producción solo
entran datos reales.
