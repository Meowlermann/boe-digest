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
build.py                    pipeline: recolección, redacción y renderizado
senado_local.py             recolector del Senado para ejecutar en tu equipo
template.html               plantilla del sitio (marcador __DIGEST_DATA__)
data/AAAA-MM-DD.json        una edición por día (regenerable)
curated/AAAA-MM-DD.json     contenido escrito a mano, se fusiona por encima
debug/last-run.json         diagnóstico de la última ejecución
state/senado.json           último boletín del Senado leído, para estimar el siguiente
docs/                       notas del proyecto
index.html                  generado por build.py — no editar a mano
.github/workflows/daily.yml automatización diaria
```
