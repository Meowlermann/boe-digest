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
  cuando consta, y listas sin tarjetas en las fichas de provincia
  (#38, #65, #67, #92, #93, #94, #96).
- SEO de base: canonicales, migas, JSON-LD, alias del feed, sitemap por
  secciones con `lastmod` real (#101), comprobación de huérfanas, prueba
  de títulos en una muestra (#70, #75).
- Salud de la edición, observabilidad de producción, vigilante de
  despliegues y correcciones públicas (#16, #25, #33, #36, #103).
- Páginas legales, analítica sin cookies y etiqueta de titulares con IA
  (#23, #68, #97, #99).
- El Senado, fuera de la automatización, con la nota de cobertura a la
  vista (#16).

## En curso

- **#102 «SEO: enlazado interno»**, sin fusionar. El listado de los 350
  diputados pasa a `/diputados/todos/`; `/diputados/` se queda con un
  enlace a esa página. En PRs posteriores del mismo frente: ediciones
  por mes, `/normas/` por meses y `/personas/` de la A a la Z.
- **#104 «Senado: limpieza del residuo»**, sin fusionar. Ya no se generan
  páginas de estado con cero iniciativas; nota de caducidad de las
  proposiciones del Senado al disolverse las Cortes; el pie dice «el BOE
  y el Congreso bajo control ciudadano», sin mención al Senado.
- **#106 «Empleo: página general sin tarjetas»**, sin fusionar. La
  página general `/empleo/` usa las filas compactas de las fichas de
  provincia, sin tocar el `noindex`, el title, la description ni el
  canonical. El peso se valida antes de quitar el `noindex`.
- **#107 «Docs: traspaso»**, sin fusionar (`OPERACION.md`, `DECISIONES.md`,
  `REGLAS-EDITORIALES.md`, `HOJA-DE-RUTA.md`) y la regla de
  mantenerlos al día en cada PR.
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
- **#110 «Elecciones: enlaces al hub»**, apilada sobre #109, sin fusionar:
  redirección de `/elecciones/`, enlaces desde el menú y `/diputados/`.
- **#109 «Elecciones: bloque 29-N y hub /elecciones/2026/»** (tanda E2),
  sin fusionar. Siguientes de la tanda E, en PR aparte: reparto por partido
  y FAQ en las fichas (E3), `ItemList` y `Event` (E4), imagen OG y «¿Quién
  votó qué en tu provincia?» (E5), H1 de normas y 404 propia (E6), prueba de
  descarga de resultados del Ministerio del Interior (E7), sitemaps
  prioritario y de noticias (E8) y revisión de 4xx y canonicales (E9). El
  Senado sigue fuera.

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
