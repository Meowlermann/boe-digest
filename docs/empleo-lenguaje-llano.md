# Empleo público en lenguaje llano

## Lugar de los órganos locales
`lugar()` ya no inventa «de»: se respeta la forma literal del título
(p. ej. BOE-A-2026-22813 → «Consorcio Provincial…»). Revisados 6 casos que
cambiaban. El estado guardado conserva los valores antiguos; la localidad se
recalcula al pintar, sin tocar LECTURA ni el estado.

## Nombres de organismo en mayúsculas
Regla determinista (`empleo.nombre_dept`): solo se convierte un nombre
íntegramente en mayúsculas; si no, se deja el original. Palabras menores en
minúscula (de, del, la, y…), siglas conocidas y palabras sin vocales se
mantienen; las partes con guion o barra se tratan por separado. En la duda,
el original. Universidades: nombre extraído del título o «Universidades».
Administración local: «Ayuntamiento/Concello/Ajuntament de X», el lugar, o
«Administración Local».

## Plazo
`MOSTRAR_PLAZO_LLANO = False`: todas las tarjetas muestran «Consulta el plazo
en el BOE». Nunca se calculan fechas de cierre. Con la flag en True se muestra
el plazo en llano solo si la frase pasa la regla estricta de
`plazo_llano_motivo`. Activarla exige OK expreso en una PR/commit aparte.

Motivo: en la revisión manual (68 plazos: 22 de la maqueta + 46 nuevos) hubo
1 error, BOE-A-2026-21686 («desde el BOE o el DOGC, la posterior»): la frase
guardada estaba truncada tras «Estado» [...]. Se añadió la regla «frase
truncada tras el BOE», que manda a «Consulta» 68 frases del estado, 43 de
ellas antes clasificadas como claras (algunas correctas, p. ej. 21380). Se
aceptan como «Consulta».

Medición sobre el estado entero (convocatoria + provisión, sin no_oferta):
529 claros y 273 «Consulta» si la flag se activase (antes de la corrección,
572 claros).
