# Prueba de títulos (tanda SEO 1 y 1b)

**Fechas:** tanda 1 (#70) el 2026-11-02. Tanda 1b: preparada el 2026-11-03, **pendiente de fusión**; en vigor desde el despliegue tras fusionar (anotar aquí la fecha real).

**Tanda 1b — cambio de URL:** la prueba de provincias pasa de /provincias/X.html a /diputados/provincia-X.html, que es la URL que recibe impresiones y clics en Search Console (línea base del 02-11). Las 7 /provincias/X.html de prueba vuelven a su título, descripción y H1 anteriores a #70, para que no compartan título con la ficha de diputados. Los 9 grupos parlamentarios de #70 siguen igual.

Solo cambian `<title>`, meta description y H1. No cambian canonical, noindex, sitemap, feeds ni el texto visible (la entradilla visible se mantiene; la meta description va aparte). Las cifras salen de las fichas que ya lista la página: número de diputados y reparto por grupo. Con 1 diputado, en singular. Si la descripción supera 155 caracteres, se omite el reparto.

**Prueba:** /diputados/provincia-murcia, asturias, madrid, ceuta, burgos, cantabria, melilla.

**Grupo de control (sin tocar):** /diputados/provincia-barcelona.html, alicante-alacant, navarra, salamanca, valladolid, soria, coruna-a (y sus /provincias/ correspondientes).

**Pendiente tras el despliegue:** comprobar en producción estas URL (título, descripción, H1) y comparar en Search Console prueba frente a control (CTR e impresiones) a las 4–6 semanas desde la fecha de despliegue de la 1b.

## Tanda 1b: /diputados/provincia-X.html

| URL | Campo | Antes | Después |
|---|---|---|---|
| /diputados/provincia-murcia.html | title | Diputados por Murcia — quiénes son y cómo votan \| La Tercera Cámara | Diputados por Murcia (10): quiénes son y cómo votan \| La Tercera Cámara |
| /diputados/provincia-murcia.html | description | Los 10 diputados que representan a Murcia en el Congreso, con su actividad y sus votos. | Murcia tiene 10 diputados en el Congreso: PP 4, PSOE 3, Vox 2 y Mixto 1. Ficha de cada uno, con intervenciones y votos en el Pleno. |
| /diputados/provincia-murcia.html | H1 | Diputados por Murcia | Diputados por Murcia: quiénes son y cómo votan |
| /diputados/provincia-asturias.html | title | Diputados por Asturias — quiénes son y cómo votan \| La Tercera Cámara | Diputados por Asturias (7): quiénes son y cómo votan \| La Tercera Cámara |
| /diputados/provincia-asturias.html | description | Los 7 diputados que representan a Asturias en el Congreso, con su actividad y sus votos. | Asturias tiene 7 diputados en el Congreso: PP 3, PSOE 2, Sumar 1 y Vox 1. Ficha de cada uno, con intervenciones y votos en el Pleno. |
| /diputados/provincia-asturias.html | H1 | Diputados por Asturias | Diputados por Asturias: quiénes son y cómo votan |
| /diputados/provincia-madrid.html | title | Diputados por Madrid — quiénes son y cómo votan \| La Tercera Cámara | Diputados por Madrid (37): quiénes son y cómo votan \| La Tercera Cámara |
| /diputados/provincia-madrid.html | description | Los 37 diputados que representan a Madrid en el Congreso, con su actividad y sus votos. | Madrid tiene 37 diputados en el Congreso: PP 16, PSOE 10, Sumar 5, Vox 4 y Mixto 2. Ficha de cada uno, con intervenciones y votos en el Pleno. |
| /diputados/provincia-madrid.html | H1 | Diputados por Madrid | Diputados por Madrid: quiénes son y cómo votan |
| /diputados/provincia-ceuta.html | title | Diputados por Ceuta — quiénes son y cómo votan \| La Tercera Cámara | Diputado por Ceuta (1): quién es y cómo vota \| La Tercera Cámara |
| /diputados/provincia-ceuta.html | description | Los 1 diputados que representan a Ceuta en el Congreso, con su actividad y sus votos. | Ceuta tiene 1 diputado en el Congreso: PP 1. Su ficha, con intervenciones y votos en el Pleno. |
| /diputados/provincia-ceuta.html | H1 | Diputados por Ceuta | Diputado por Ceuta |
| /diputados/provincia-burgos.html | title | Diputados por Burgos — quiénes son y cómo votan \| La Tercera Cámara | Diputados por Burgos (4): quiénes son y cómo votan \| La Tercera Cámara |
| /diputados/provincia-burgos.html | description | Los 4 diputados que representan a Burgos en el Congreso, con su actividad y sus votos. | Burgos tiene 4 diputados en el Congreso: PP 2 y PSOE 2. Ficha de cada uno, con intervenciones y votos en el Pleno. |
| /diputados/provincia-burgos.html | H1 | Diputados por Burgos | Diputados por Burgos: quiénes son y cómo votan |
| /diputados/provincia-cantabria.html | title | Diputados por Cantabria — quiénes son y cómo votan \| La Tercera Cámara | Diputados por Cantabria (5): quiénes son y cómo votan \| La Tercera Cámara |
| /diputados/provincia-cantabria.html | description | Los 5 diputados que representan a Cantabria en el Congreso, con su actividad y sus votos. | Cantabria tiene 5 diputados en el Congreso: PP 2, PSOE 2 y Vox 1. Ficha de cada uno, con intervenciones y votos en el Pleno. |
| /diputados/provincia-cantabria.html | H1 | Diputados por Cantabria | Diputados por Cantabria: quiénes son y cómo votan |
| /diputados/provincia-melilla.html | title | Diputados por Melilla — quiénes son y cómo votan \| La Tercera Cámara | Diputado por Melilla (1): quién es y cómo vota \| La Tercera Cámara |
| /diputados/provincia-melilla.html | description | Los 1 diputados que representan a Melilla en el Congreso, con su actividad y sus votos. | Melilla tiene 1 diputado en el Congreso: PP 1. Su ficha, con intervenciones y votos en el Pleno. |
| /diputados/provincia-melilla.html | H1 | Diputados por Melilla | Diputado por Melilla |

## Tanda 1b: /provincias/X.html vuelven a su texto anterior a #70

Título «X en las Cortes y en el BOE: diputados, preguntas y votaciones», descripción «X: N diputados, P preguntas al Gobierno que la nombran y D disposiciones del BOE sobre la provincia, con datos oficiales.» y H1 «X» (texto original, igual que el resto de provincias).

## Tanda 1 (#70): grupos parlamentarios (se mantienen)

| URL | Campo | Antes | Después |
|---|---|---|---|
| /diputados/grupo-bildu.html | title | Diputados de EH Bildu — actividad y votos \| La Tercera Cámara | Grupo EH Bildu en el Congreso: sus 6 diputados \| La Tercera Cámara |
| /diputados/grupo-bildu.html | description | Los 6 diputados del Grupo Parlamentario Euskal Herria Bildu, con sus intervenciones y sus votos. | Ficha de cada uno de los 6 diputados del Grupo Parlamentario Euskal Herria Bildu: sus intervenciones y sus votos en el Pleno. |
| /diputados/grupo-bildu.html | H1 | Diputados de EH Bildu | Grupo EH Bildu en el Congreso |
| /diputados/grupo-erc.html | title | Diputados de ERC — actividad y votos \| La Tercera Cámara | Grupo ERC en el Congreso: sus 7 diputados \| La Tercera Cámara |
| /diputados/grupo-erc.html | description | Los 7 diputados del Grupo Parlamentario Republicano, con sus intervenciones y sus votos. | Ficha de cada uno de los 7 diputados del Grupo Parlamentario Republicano: sus intervenciones y sus votos en el Pleno. |
| /diputados/grupo-erc.html | H1 | Diputados de ERC | Grupo ERC en el Congreso |
| /diputados/grupo-junts.html | title | Diputados de Junts — actividad y votos \| La Tercera Cámara | Grupo Junts en el Congreso: sus 7 diputados \| La Tercera Cámara |
| /diputados/grupo-junts.html | description | Los 7 diputados del Grupo Parlamentario Junts per Catalunya, con sus intervenciones y sus votos. | Ficha de cada uno de los 7 diputados del Grupo Parlamentario Junts per Catalunya: sus intervenciones y sus votos en el Pleno. |
| /diputados/grupo-junts.html | H1 | Diputados de Junts | Grupo Junts en el Congreso |
| /diputados/grupo-mixto.html | title | Diputados de Mixto — actividad y votos \| La Tercera Cámara | Grupo Mixto en el Congreso: sus 9 diputados \| La Tercera Cámara |
| /diputados/grupo-mixto.html | description | Los 9 diputados del Grupo Parlamentario Mixto, con sus intervenciones y sus votos. | Ficha de cada uno de los 9 diputados del Grupo Parlamentario Mixto: sus intervenciones y sus votos en el Pleno. |
| /diputados/grupo-mixto.html | H1 | Diputados de Mixto | Grupo Mixto en el Congreso |
| /diputados/grupo-pnv.html | title | Diputados de PNV — actividad y votos \| La Tercera Cámara | Grupo PNV en el Congreso: sus 5 diputados \| La Tercera Cámara |
| /diputados/grupo-pnv.html | description | Los 5 diputados del Grupo Parlamentario Vasco (EAJ-PNV), con sus intervenciones y sus votos. | Ficha de cada uno de los 5 diputados del Grupo Parlamentario Vasco (EAJ-PNV): sus intervenciones y sus votos en el Pleno. |
| /diputados/grupo-pnv.html | H1 | Diputados de PNV | Grupo PNV en el Congreso |
| /diputados/grupo-pp.html | title | Diputados de PP — actividad y votos \| La Tercera Cámara | Grupo PP en el Congreso: sus 137 diputados \| La Tercera Cámara |
| /diputados/grupo-pp.html | description | Los 137 diputados del Grupo Parlamentario Popular en el Congreso, con sus intervenciones y sus votos. | Ficha de cada uno de los 137 diputados del Grupo Parlamentario Popular en el Congreso: sus intervenciones y sus votos en el Pleno. |
| /diputados/grupo-pp.html | H1 | Diputados de PP | Grupo PP en el Congreso |
| /diputados/grupo-psoe.html | title | Diputados de PSOE — actividad y votos \| La Tercera Cámara | Grupo PSOE en el Congreso: sus 121 diputados \| La Tercera Cámara |
| /diputados/grupo-psoe.html | description | Los 121 diputados del Grupo Parlamentario Socialista, con sus intervenciones y sus votos. | Ficha de cada uno de los 121 diputados del Grupo Parlamentario Socialista: sus intervenciones y sus votos en el Pleno. |
| /diputados/grupo-psoe.html | H1 | Diputados de PSOE | Grupo PSOE en el Congreso |
| /diputados/grupo-sumar.html | title | Diputados de Sumar — actividad y votos \| La Tercera Cámara | Grupo Sumar en el Congreso: sus 26 diputados \| La Tercera Cámara |
| /diputados/grupo-sumar.html | description | Los 26 diputados del Grupo Parlamentario Plurinacional SUMAR, con sus intervenciones y sus votos. | Ficha de cada uno de los 26 diputados del Grupo Parlamentario Plurinacional SUMAR: sus intervenciones y sus votos en el Pleno. |
| /diputados/grupo-sumar.html | H1 | Diputados de Sumar | Grupo Sumar en el Congreso |
| /diputados/grupo-vox.html | title | Diputados de Vox — actividad y votos \| La Tercera Cámara | Grupo Vox en el Congreso: sus 32 diputados \| La Tercera Cámara |
| /diputados/grupo-vox.html | description | Los 32 diputados del Grupo Parlamentario VOX, con sus intervenciones y sus votos. | Ficha de cada uno de los 32 diputados del Grupo Parlamentario VOX: sus intervenciones y sus votos en el Pleno. |
| /diputados/grupo-vox.html | H1 | Diputados de Vox | Grupo Vox en el Congreso |
