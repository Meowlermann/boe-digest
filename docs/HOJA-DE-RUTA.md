# Hoja de ruta

Qué está hecho, qué está en curso y qué está aparcado, con el motivo.
Se actualiza en la misma PR que cambie el estado de un frente.

## Hecho

- Edición diaria del BOE y de la actividad del Congreso, tres pases al
  día, con archivo histórico determinista.
- Publicación por artefacto de GitHub Pages y rama `datos`; `main` solo
  lleva código (#19, #20).
- Preguntas, respuestas, votaciones, tramitación, nombramientos,
  provincias, rankings y resumen semanal.
- Empleo público a partir de la sección II.B: extractor, fichas de
  provincia, lenguaje llano, plazo literal, cita del diario autonómico
  cuando consta, y listas sin tarjetas en las fichas de provincia y en la
  página general (#38, #65, #67, #92, #93, #94, #96, #106).
- SEO de base: canonicales, migas, JSON-LD, alias del feed, sitemap por
  secciones con `lastmod` real (#101), comprobación de huérfanas, prueba
  de títulos en una muestra (#70, #75), y enlazado interno con el listado
  de los 350 diputados en `/diputados/todos/` (#102).
- Salud de la edición, observabilidad de producción, vigilante de
  despliegues y correcciones públicas (#16, #25, #33, #36, #103).
- Páginas legales, analítica sin cookies y etiqueta de titulares con IA
  (#23, #68, #97, #99).
- El Senado, fuera de la automatización, con la nota de cobertura a la
  vista (#16), y limpieza del residuo: sin páginas de estado vacías y sin
  mención al Senado en el pie (#104).
- Documentos de traspaso en `docs/` y la regla de mantenerlos al día en
  cada PR (#107).

## En curso

- **#108 «Empleo: quitar el noindex de /empleo/»** (tanda E1), fusionada
  el 13 de noviembre de 2026. La página general `/empleo/` pasa a
  `index, follow` y entra en el sitemap; las fichas por organismo siguen en
  `noindex`. Pendiente: pedir la indexación en Search Console.
- **Enlazado interno, siguientes pasos** (tras #102): ediciones por mes y
  `/normas/` por meses, con menos prioridad que la tanda E. `/personas/`
  de la A a la Z sale de este frente porque choca con la poda prevista.
- **Tanda 9 (Fable):** clasificador de interés público y extractor de
  valor añadido, todavía en la rama `seo/interes-publico-y-valor-anadido`,
  sin conectar a `build.py` y sin tocar robots, sitemap ni metas. Pendiente
  subir y revisar esa rama, el noindex previsto, guardar sección y
  epígrafe en las fichas de `data/`, que el clasificador priorice las
  index en el tope diario de disposiciones, y una tercera muestra de unas
  60 normas (fuera de las 100 ya revisadas).
- **Tanda 4 (normas)** y **tanda 5 (jerga)**, en ese orden aprobado
  tras el enlazado interno y la página general de empleo: «Qué cambia»
  primero en las fichas de norma (solo puntos verificados, sin LLM) y,
  después, explicar la jerga junto al dato con `<details>` nativo, más un
  resumen visible de los filtros de empleo.
- La prueba de títulos, description y canonical de #75 sigue en marcha
  hasta mediados de diciembre: esas etiquetas no se tocan.
- **#112 «SEO: datos estructurados de provincias y elecciones»** (tanda
  E4), fusionada el 16 de noviembre de 2026: `ItemList` en las fichas de provincia y `Event` en el
  hub y en las páginas por circunscripción.
- **#111 «Elecciones: fichas de provincia completas»** (tanda E3),
  fusionada el 16 de noviembre de 2026: reparto de escaños por formación y preguntas frecuentes. La
  comparación por partido con 2019, la asistencia y las rebeldías quedan
  fuera porque no salen limpias (ver DECISIONES). Retoques del informe 34
  en la misma PR: en «¿Qué diputados… se presentan de nuevo?» van aparte
  los que eran diputados por otra provincia (Madrid: 22 de los 37, y 2 de
  Málaga y Pontevedra; Sevilla: 1 de Córdoba), el Mixto en la pregunta del
  reparto, preguntas sin versales, pie que dice que se cruzan BOE y
  Congreso, grupos sin partirse a 375 y enlace al reparto desde cada
  página `/elecciones/2026/<provincia>.html`.
- **#110 «Elecciones: enlaces al hub»**, fusionada el 16 de noviembre de 2026 (también corrige el orden de render: votaciones antes que diputados, para que `/diputados/` no incruste el bloque de votaciones de la pasada anterior):
  redirección de `/elecciones/`, enlace en el panel «Parlamento», línea en
  la portada y enlace desde `/diputados/`.
- **#113 «Portada: sin subrayados»**, fusionada el 16 de noviembre de 2026 (tras #110):
  ningún enlace de la portada subrayado, en ningún estado (pistas por color,
  peso, fondo tenue con hover y contorno con el teclado),
  filetes de la línea de elecciones con contraste y flechas que no se quedan
  solas en una línea.
- **Tras el escrutinio del 29-N:** poner `CAMPANA_29N = False` en `build.py`
  y regenerar. Así se quitan la línea de la portada y el enlace del panel
  «Parlamento», donde vuelve «Los 350 diputados».
- **#109 «Elecciones: bloque 29-N y hub /elecciones/2026/»** (tanda E2),
  fusionada el 13 de noviembre de 2026. Siguientes de la tanda E, en PR aparte: reparto por partido
  y FAQ en las fichas (E3), `ItemList` y `Event` (E4), imagen OG y «¿Quién
  votó qué en tu provincia?» (E5), H1 de normas y 404 propia (E6), prueba de
  descarga de resultados del Ministerio del Interior (E7), sitemaps
  prioritario y de noticias (E8) y revisión de 4xx y canonicales (E9). El
  Senado sigue fuera.

- **«Sitio: página 404 propia»** (E6, PR abierta el 27 de noviembre de 2026, sin fusionar):
  `/404.html` generada por `paginas_fijas.generar_404`, con la cabecera, el
  pie y el estilo de la web, el buscador de `/buscar/` y enlaces a las
  secciones principales; `noindex`, fuera de los sitemaps y con rutas
  absolutas. GitHub Pages la sirve sola, con código 404. Tras fusionar,
  comprobar con `curl -I https://terceracamara.es/no-existe/` que da 404 y
  la página propia (la caché de Cloudflare guarda la 404 actual hasta 10
  minutos). El H1 de normas (la otra mitad de E6) sigue congelado por la
  prueba de #75.

- **E7, descarga de resultados de Interior: no hay feed público.** El
  repositorio de la noche electoral es solo para medios acreditados (plazo
  cerrado) y Infoelectoral responde con un desafío de Cloudflare a la box y
  a los runners (run 45029633641). Los xlsx de resultados definitivos de
  `descargas.interior.gob.es` sí se descargan (llegan hasta 2023).
- **#116 «Elecciones: aviso para la noche del 29-N»**, fusionada y
  publicada el 22 de noviembre de 2026 (`54d5dad9`). Aviso fijo en el
  hub y en las 52 páginas por circunscripción, con Infoelectoral y la
  aplicación oficial de Interior, sin nombrarla (hay apps no oficiales con
  nombres parecidos). Si Interior publica una página de descarga, se puede
  enlazar. Tras el escrutinio hay que quitarlo (`elecciones.AVISO_29N`),
  a la vez que se pone `CAMPANA_29N = False`.
- **Siguiente, aprobado: bloque «Resultados oficiales» por provincia.**
  Copiado tal cual de la proclamación de la Junta Electoral Central en el
  BOE (o del xlsx de Interior cuando incluya 2026), sin porcentajes ni
  proyecciones, en los pases diarios que ya existen. Si la descarga falla,
  el bloque no se muestra y se mantiene la última versión buena. Tiene que
  estar listo antes de que se publique la proclamación.
  Código preparado en la rama `elecciones/resultados-oficiales` (sin datos):
  `resultados_29n.py` pinta el bloque en `/elecciones/2026/<slug>.html` solo
  si existe `curated/resultados_29n.json`, que genera a mano
  `tools/generar_resultados_29n.py --id BOE-A-…` cuando el BOE publique la
  resolución de la JEC. La copia fija es la «última versión buena»: si una
  regeneración falla, no se escribe. Las circunscripciones que el generador
  deje fuera se curan a mano en `curated/resultados_29n_manual.json`.
  Tabla ordenada por escaños y votos, con el reparto encima y bajo el
  enlace de arriba (informe 48).
  Falta la proclamación real.
- **«Tus senadores» en cada ficha de provincia.** Código preparado en la rama
  `provincias/tus-senadores` (sin datos): `senadores.py` pinta el bloque en
  `/diputados/provincia-*.html` solo si existe `curated/senadores_29n.json`,
  que genera a mano `tools/generar_senadores.py --id BOE-A-…` con la
  relación de senadores electos de la misma resolución de la JEC. Nunca desde
  senado.es. Las dudosas se curan a mano en `curated/senadores_29n_manual.json`;
  la que siga sin estar clara no se publica. Falta la proclamación real.
- **#115 «Elecciones: imagen para redes por provincia»** (tanda E5, parte
  OG), fusionada y publicada el 22 de noviembre de 2026 (`4eb4d5d6`): un PNG por circunscripción en `og:image` y
  `twitter:image` de `/elecciones/2026/<slug>.html` y de
  `/diputados/provincia-*.html`. Si cambia `curated/elecciones_2026.json`,
  hay que volver a ejecutar `python tools/generar_og.py --elecciones` y
  commitear los PNG; el test avisa. «¿Quién votó qué en tu provincia?»
  (el resto de E5) queda para después de E8, si da tiempo.
- **#117 «SEO: sitemap prioritario y de noticias»** (tanda E8), fusionada
  y publicada el 22 de noviembre de 2026 (`618bee6e`): `sitemap-prioritario.xml` y `sitemap-noticias.xml` (Google
  News, 48 horas) en el índice `/sitemap.xml`. Tras fusionar: enviar de nuevo
  el índice en Search Console y mirar que lea los dos ficheros nuevos.
- **#118 «Diputados: ¿quién votó qué en tu provincia?»** (E5), fusionada
  y publicada el 22 de noviembre de 2026 (`5c499acb`). En las 52 fichas `/diputados/provincia-*`, el voto de cada
  diputado en las 10 últimas convalidaciones o derogaciones de reales
  decretos-leyes, con enlace al JSON oficial, al PDF y al expediente. La copia
  fija `curated/votos_rdl.json` solo cambia al regenerarla con
  `tools/generar_votos_rdl.py` (ver OPERACION).
- **#119 «Parlamento: fuera el Senado, panel de decretos-ley»**, abierta
  y sin fusionar. Sin Senado en el lema, la ficha de cámara y la nota de
  cobertura; desde el BOE del RD 806/2026, un párrafo sobre la disolución
  y la Diputación Permanente en vez de la ficha de la XV Legislatura; y en
  la portada, la lista de decretos-leyes de 2026 desde el 14/2026 con su
  estado en llano (de la ficha del Congreso o, si aún no la hay, de la
  resolución del BOE) y el texto oficial debajo. La copia fija
  `curated/decretos_ley.json` solo cambia al regenerarla con
  `tools/generar_decretos_ley.py` (ver OPERACION). Pendiente de decidir:
  si se regenera sola, lo que exigiría tocar los crons o la extracción.

## Tanda F (empleo)

Aprobada por Dirección el 22 de noviembre de 2026.

- **Empleo por organismo:** pasar las 48 fichas a `index, follow` y
  añadirlas al sitemap, empezando por las de ministerios y comunidades.
  Motivo: hoy hay 96 convocatorias de 90 días que solo aparecen en esas
  fichas, por el tope de 300 del listado general.
- **Convocatorias de la comunidad en las fichas de provincia:** cada ficha
  de provincia muestra también las convocatorias de su comunidad
  autónoma, con la etiqueta «de tu comunidad» y sin cálculos.

## Aparcado

- **Senado en automático.** El WAF de Akamai devuelve 403 desde la box
  y desde los runners de GitHub, también a los datos abiertos.
  `SENADO_ACTIVO = False`. La PR #8 (diagnóstico) se cerró sin fusionar.
  La PR #105 «Senado: prueba de descarga» se cerró el 12 de noviembre de
  2026 sin fusionar: 13 de 13 URLs devolvieron 403. Se repetirá la prueba
  cuando se constituya el Senado nuevo. No se esquiva el bloqueo.
- **Boletín por correo y cobro.** Aplazados. Faltan el titular de las
  páginas legales, el dominio de envío y otras decisiones. `/seguir/`
  se quedó en RSS (#32).
- **Plan B de Cloudflare Pages.** Documentado el 10 de noviembre de
  2026, no activado: no hay proyecto, ni secretos, ni cambio de DNS.
- **Transición a la XVI legislatura** (TC-015) y el seguimiento
  parlamentario que depende de ella (TC-016): a la espera de que se
  constituyan las Cortes.
- Del debate de UX del 7 de noviembre de 2026, aparcados de forma
  expresa: Pagefind (pesa y ya existe `/buscar/`), speculation rules,
  view transitions, gráficos SVG salvo que respondan a una pregunta
  concreta, código postal a diputados (no hay una tabla pública
  versionada) y personalización con `localStorage`.
