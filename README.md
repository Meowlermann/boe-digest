# BOE Digest & Cortes en Directo

Publicación diaria y automática sobre lo que publica el BOE y lo que hacen diputados y
senadores. Se actualiza sola: nadie tiene que tocar nada cada día.

**Web:** https://meowlermann.github.io/boe-digest/

## Cómo funciona

Todo ocurre dentro de GitHub, sin servidores:

1. Cada mañana, un workflow de GitHub Actions (`.github/workflows/daily.yml`) ejecuta
   `build.py`.
2. `build.py` descarga el sumario del BOE del día, las últimas publicaciones oficiales del
   Congreso (BOCG y Diarios de Sesiones) y el último boletín del Senado.
3. Redacta los artículos y guarda la edición en `data/AAAA-MM-DD.json`.
4. Fusiona por encima lo que haya en `curated/` (ver más abajo), regenera `index.html` a
   partir de `template.html` y hace commit. GitHub Pages sirve el resultado.

## Redacción: con modelo o sin él

El pipeline funciona en los dos modos y nunca se queda a medias.

**Sin modelo (por defecto).** Redacción determinista: limpia los títulos oficiales, deduplica,
extrae el identificador `BOE-A-…`, detecta qué hace cada norma y construye el titular a partir
de su objeto, no de su número. Explica además qué es el instrumento jurídico (real decreto,
orden, resolución…). No inventa nada porque no puede.

**Con modelo (opcional).** Sirve cualquier proveedor compatible con la API de OpenAI. Se
configura sin tocar código, en Settings del repositorio:

- `Secrets and variables → Actions → Variables`: `LLM_BASE_URL` (por ejemplo
  `https://api.groq.com/openai/v1`) y `LLM_MODEL`.
- `Secrets and variables → Actions → Secrets`: `LLM_API_KEY`.

Si falta cualquiera de los tres, se usa el modo determinista sin fallar.

> GitHub Models se retiró el 30 de julio de 2026, así que esa vía ya no existe.

## Contenido curado: `curated/`

El regenerador sobrescribe `data/AAAA-MM-DD.json` cada vez que corre. Para que el trabajo
escrito a mano no se pierda, existe `curated/`: cualquier fichero `curated/AAAA-MM-DD.json`
se fusiona **por encima** de lo generado ese día.

Solo hay que incluir las claves que se quieran fijar. Por ejemplo, para quedarse con una
sección de Cortes escrita a mano y dejar que el BOE se regenere solo:

```json
{ "cortes": { "feed": [ ... ], "scoreboard": { ... } } }
```

Para **añadir** artículos sin reemplazar los que se hayan recolectado solos, se usa
`feed_append` (o `stories_append` en la sección del BOE):

```json
{ "cortes": { "feed_append": [ { "headline": "…" } ] } }
```

La edición fusionada queda marcada con `"curated": true`.

## El Senado y el bloqueo de Akamai

El Senado sirve su web detrás de Akamai y deniega en el borde las peticiones que llegan
desde rangos de centro de datos. GitHub Actions recibe siempre un `403 Access Denied`,
tanto en el índice como en los PDF, sin cookie ni challenge que se pueda satisfacer.
No es un problema de cabeceras: desde una conexión doméstica los mismos documentos se
descargan sin más.

Consecuencias prácticas:

- El pipeline detecta el bloqueo, deja de insistir durante esa ejecución (no tiene
  sentido martillear un servidor que ya ha dicho que no) y lo declara en la web, en la
  nota de cobertura del día.
- Para incorporar el Senado hay un recolector que se ejecuta en tu equipo:
  `senado_local.py`. Escribe `curated/AAAA-MM-DD.json` con la clave `feed_append`, que
  se **añade** a los artículos del Congreso en lugar de reemplazarlos.
- En `docs/solicitud-acceso-senado.md` hay un borrador de consulta al Senado por si se
  prefiere resolverlo por la vía formal.

Deliberadamente **no** se usa un runner self-hosted de GitHub Actions: en un
repositorio público, cualquiera que abra un pull request podría lograr ejecución de
código en la máquina que lo aloja.

## SEO e indexación por buscadores e IA

Cada ejecución, además de `index.html`, genera:

- `ediciones/AAAA-MM-DD.html`: una página estática por edición, con URL propia,
  enlace a la anterior/siguiente y su propio `<title>`, descripción y JSON-LD.
  Es lo que hace que cada día pueda encontrarse por separado en un buscador, no
  solo "la portada de hoy".
- `ediciones/index.html`: el índice del archivo. GitHub Pages **no sirve
  listados de directorio**, así que sin esta página `/ediciones/` sería un 404 y
  las ediciones que salen de la ventana de render se quedarían sin ningún enlace
  que las alcance.
- `sitemap.xml`: portada, archivo y **todas** las ediciones publicadas —no solo
  las de la ventana de `MAX_DAYS`— cada una con su fecha de modificación real.
- `feed.xml`: RSS 2.0 con las últimas ediciones.

La portada lleva además el contenido de la edición de hoy ya escrito en el HTML
que se sirve —el JS lo vuelve a pintar igual al cargar, así que para un humano no
cambia nada— porque los rastreadores de los modelos de lenguaje (GPTBot,
ClaudeBot, CCBot, PerplexityBot…) normalmente no ejecutan JavaScript: si el
contenido solo viviera dentro del `<script>` con los datos, verían una página
casi vacía.

`robots.txt` no restringe ningún rastreador y `llms.txt` explica en texto plano,
para agentes automatizados, qué es el sitio, cómo está organizado y cómo citarlo.

### La regla del titular en los datos estructurados

En el JSON-LD de cada norma, `name` es **siempre el título oficial** tal cual lo
publica el BOE, y el titular de la casa va aparte en `alternativeHeadline`.
Publicar el titular —que es editorial, va en mayúsculas y está afilado a
propósito— como nombre de la norma, junto a su identificador `BOE-A-…`, sería
afirmarle a una máquina que la norma se llama así. Es exactamente lo que las
reglas editoriales de más abajo prohíben, y el formato pensado para que las
máquinas ingieran hechos es el peor sitio para saltárselas.

Por lo mismo, `datePublished` usa la fecha del sumario que se leyó de verdad
(`boe.fechaISO`), no la de la edición: `fetch_boe` retrocede hasta tres días si
el BOE del día todavía no está publicado.

### Fechas de modificación

No se usa el mtime del fichero —`actions/checkout` deja todo con la hora del
checkout— ni la fecha de la edición, porque cuando `senado_local.py` añade el
Senado a un día ya publicado vía `curated/`, esa página cambia y hay que
decírselo al buscador. `build.py` compara el HTML recién generado con el que hay
en disco y lleva el registro en `state/ediciones.json`.

### IndexNow

Tras cada publicación con cambios, el workflow avisa por
[IndexNow](https://www.indexnow.org/) a Bing, Yandex, Seznam, Naver, Yep e
Internet Archive de las URLs que han cambiado. No hace falta cuenta en ninguno:
la clave se sirve desde el propio sitio (`<clave>.txt` en la raíz del
repositorio) y su ubicación delimita lo que se puede enviar, que aquí es todo
`/boe-digest/`. Si un buscador no responde, el paso no tumba la edición.

Google no participa en IndexNow y retiró el ping de sitemaps en 2023, así que
ahí hace falta Search Console. El sitio está dado de alta como propiedad de tipo
*prefijo de URL* (`https://meowlermann.github.io/boe-digest/`) y verificado por
dos vías a la vez, a propósito:

- la etiqueta `<meta name="google-site-verification">` en `template.html`, y
- el fichero `googlec4619d97b763e0b5.html` en la raíz.

**Ninguna de las dos se puede borrar.** Si se cae la que esté activa, Google
desverifica la propiedad y deja de reportar; con dos, hace falta perder ambas.

## Diagnóstico: `debug/last-run.json`

Cada ejecución deja ahí el detalle de qué URL se pidió, con qué código de respuesta y cuánto
se descargó. Es el primer sitio donde mirar cuando una fuente deja de responder.

## Reglas editoriales

Están en el `SYSTEM_PROMPT` de `build.py` y son innegociables:

- No se inventa ningún dato, cifra, nombre ni cita. Solo se usa lo que aparece en la
  publicación oficial.
- No se atribuye a nadie una frase que no figure literalmente en el documento.
- La mordacidad se reparte por igual entre todos los grupos políticos. Ningún día puede
  quedar como un ataque desproporcionado a un solo partido.
- Cada pieza de la sección Cortes enlaza al PDF oficial del que sale.
- La sátira va en el titular y en el ángulo, nunca en los hechos.

## Puesta en marcha

1. **Settings → Pages**: origen `Deploy from a branch`, rama `main`, carpeta `/ (root)`.
2. **Settings → Actions → General → Workflow permissions**: `Read and write permissions`.
3. (Opcional) Configurar `LLM_BASE_URL`, `LLM_MODEL` y `LLM_API_KEY` como se indica arriba.
4. **Actions → Edición diaria → Run workflow** para la primera ejecución.

## Ejecutar en local

```bash
pip install -r requirements.txt
python build.py            # recolecta el día de hoy y regenera index.html
python build.py --render   # solo regenera el HTML desde data/
python build.py --date 2026-09-17
```

## Estructura

```
build.py                    pipeline: recolección, redacción, renderizado y SEO
senado_local.py             recolector del Senado para ejecutar en tu equipo
template.html               plantilla de la portada (marcadores __DIGEST_DATA__, __SSR_*__)
template_edicion.html       plantilla de cada página de archivo (ediciones/AAAA-MM-DD.html)
template_archivo.html       plantilla del índice del archivo (ediciones/index.html)
assets/style.css            hoja de estilos compartida por portada y ediciones
data/AAAA-MM-DD.json        una edición por día (regenerable)
curated/AAAA-MM-DD.json     contenido escrito a mano, se fusiona por encima
debug/last-run.json         diagnóstico de la última ejecución
state/senado.json           último boletín del Senado leído, para estimar el siguiente
state/ediciones.json        fecha de última modificación real de cada edición
docs/                       notas del proyecto
index.html                  generado por build.py — no editar a mano
ediciones/AAAA-MM-DD.html   generado por build.py — página propia por edición
ediciones/index.html        generado por build.py — índice del archivo
sitemap.xml                 generado por build.py
feed.xml                    generado por build.py — RSS de las últimas ediciones
llms.txt                    descripción del sitio para agentes/IA (estático, no se regenera)
<clave>.txt                 clave de IndexNow (estático, no tocar ni renombrar)
robots.txt                  sin restricciones para ningún rastreador (estático)
.github/workflows/daily.yml automatización diaria
```
