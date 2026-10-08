# Arquitectura de La Tercera Cámara

Este documento es la puerta de entrada al código. Está pensado para que una
persona o una IA que llega nueva al proyecto sepa, sin leer 12.000 líneas, qué
hace cada pieza, dónde se guarda cada dato y qué reglas no se pueden romper.
Si cambias la arquitectura (un módulo, un fichero de `state/`, una carpeta
publicada, un workflow), actualiza este documento en la misma PR.

Las reglas de trabajo para agentes están en [AGENTS.md](AGENTS.md). El README
explica el proyecto a quien lo usa; esto explica cómo está hecho.

## 1. Qué es, en una frase

Un sitio estático (https://terceracamara.es/, GitHub Pages, publicado como
artefacto desde Actions) que se regenera solo tres veces al día con lo que
publican el BOE y el Congreso. El Senado
está fuera de la automatización (ver §5). Todo corre en
GitHub Actions: no hay servidor, ni base de datos, ni API propia. La «base de
datos» son ficheros JSON en `state/` y `data/`, versionados en la rama `datos`
del propio repositorio (§8). `main` es el código.

## 2. Principios que explican casi todas las decisiones

1. **El sitio nunca se rompe.** Cada fuente y cada sección van en su propio
   `try/except`. Si algo falla, se registra en el log y en `debug/`, y la
   edición sale sin esa parte. Nunca se publica un día roto ni vacío.
2. **Determinista y verificable.** Titulares y cuerpos salen de plantillas
   sobre datos oficiales. Lo que va entre comillas es literal de la fuente.
   La única capa con modelo es `redaccion.py` (Gemini), que propone
   titulares y entradillas y solo se publican si pasan una verificación
   contra el texto oficial. Las herramientas nuevas no usan modelos.
3. **Cada dato enlaza a su original**, y el enlace lleva al elemento concreto
   (la ficha de la iniciativa, la página del Diario de Sesiones), no a una
   portada genérica.
4. **Transparencia de cobertura.** Si una fuente no responde o no se puede
   usar (el Senado, por ejemplo), la edición lo dice en la nota de cobertura
   en lugar de disimularlo.
5. **Lo curado a mano manda.** `curated/AAAA-MM-DD.json` se fusiona por
   encima de lo generado (`fusionar_curado`).
6. **Sin dependencias nuevas.** `requirements.txt` tiene requests,
   beautifulsoup4 y pypdf. El JavaScript del navegador se compila una vez con
   esbuild y se commitea ya construido.
7. **Ningún fichero crece sin límite.** El estado se poda por ventana
   temporal o se parte por año, y el índice del buscador se parte por tipo
   (ver §7).

## 3. El pase diario, de principio a fin

```
Cloudflare Worker (disparador/)  ──workflow_dispatch──►  .github/workflows/daily.yml
   07:40 · 14:40 · 21:40 (España)                         (cron propios solo de respaldo)
                                                                   │
                                                 publicar.yml: datos.sh traer + python build.py
                                                                   │
  construir_dia(hoy) ───────────────────────────────────────────────┤
   ├─ fetch_boe()               sumario del BOE (API de datos abiertos)
   ├─ capturar_nombramientos()  → nombramientos.py → state/nombramientos.json
   ├─ capturar_provincias()     → provincias.py    → state/provincias.json
   ├─ cortes_congreso()
   │    ├─ congreso_datos.descargar_intervenciones()   (volcado, 1 vez por pase)
   │    ├─ respuestas.actualizar_orales()   → state/respuestas/AAAA.json
   │    ├─ preguntas.feed_orales()          piezas de la sesión de control
   │    ├─ preguntas.actualizar_escritas()  → state/preguntas_escritas.json
   │    ├─ respuestas.actualizar_escritas() → state/respuestas/AAAA.json
   │    ├─ preguntas.feed_escritas()        piezas de contestaciones y pendientes
   │    └─ tramitacion.actualizar() / feed() → state/tramitacion.json
   ├─ fetch_senado()            solo si SENADO_ACTIVO (hoy False, ver §5)
   ├─ redactar_boe() / redactar_cortes()
   ├─ fusionar_curado()         curated/ por encima
   └─ semana.asegurar()         congela las semanas cerradas que falten (§13)
            │
            ▼
   data/AAAA-MM-DD.json   (la edición del día, fuente de verdad del render)
            │
  renderizar() ─────────────────────────────────────────────────────┐
   ├─ redaccion.aplicar()        titulares Gemini (opcional, con caché)
   ├─ cosechar_congreso()        censo, votaciones → state/congreso.json
   ├─ renderizar_feeds()         canales Atom por entidad (antes que las páginas, §13)
   ├─ renderizar_diputados / votaciones / rankings
   ├─ renderizar_preguntas / sesiones / nombramientos / tramitacion
   ├─ renderizar_seguimiento / provincias
   ├─ renderizar_index / ediciones / normas / temas / plazos
   ├─ renderizar_buscador / mapa
   ├─ paginas_fijas              /seguir/, /privacidad.html, /aviso-legal.html
   ├─ renderizar_semana()        /semana/ desde data/semanas/ (congeladas por semana.asegurar)
   └─ sitemap.xml, feed.xml, indexnow.json
            │
  publicar.yml (modo diario, §8):
   tools/verificar.py --modo diario → debug/salud.json (informa, no bloquea)
   tools/datos.sh guardar → commit «Edición del AAAA-MM-DD» en la rama datos
   tools/montar_sitio.py → _site/ → artefacto de GitHub Pages → despliegue
    ├─ incidencia «Salud de la edición» si hay hallazgos graves (§12)
    └─ aviso IndexNow a los buscadores
```

Cada pase rehace la edición del día desde cero. Por eso todo lo que publica
«novedades» (preguntas orales, tramitación, contestaciones) recuerda en su
estado qué ya se publicó y en qué edición. Así un segundo pase el mismo día da
las mismas piezas y el día siguiente no las repite (`piezas_hoy`,
`publicadas`, `vista_c`, `leida`).

## 4. Mapa de módulos

| Módulo | Qué hace | Estado que escribe | Páginas que genera |
|---|---|---|---|
| `build.py` | Orquesta todo: CLI, recolección del BOE (y del Senado si `SENADO_ACTIVO`), redacción determinista, render de todas las páginas, sitemap, feed. Es grande (~6.000 líneas) porque es la capa de presentación del sitio entero. | `data/`, `debug/`, `state/ediciones.json` | `/`, `/ediciones/`, `/normas/`, `/temas/`, `/plazos/`, `/diputados/`, `/votaciones/`, `/rankings/`, `/seguimiento/`, `/buscar/`, `/mapa/`, `/datos/` |
| `congreso_datos.py` | Cliente de los datos abiertos del Congreso: censo de diputados, volcado de intervenciones, votaciones (con el histórico por `targetDate`), grupos y colores, URL de fichas. | `state/congreso.json` (vía build) | — |
| `preguntas.py` | Preguntas al Gobierno: orales (volcado) y escritas (buscador de iniciativas, tipo 184). Plazos del art. 190 del Reglamento, pendientes, piezas del feed. Páginas por ministerio con las preguntas orales que contesta (las escritas no dicen qué ministerio las redacta). | `state/preguntas_escritas.json`, `state/preguntas_orales.json` | `/preguntas/`, `/preguntas/ministerio-<slug>.html` (solo con el año completo en el estado) |
| `respuestas.py` | Qué contesta el Gobierno. Orales: citas del Diario de Sesiones (contestación, réplica, dúplica). Escritas: cita del PDF de contestación. | `state/respuestas/AAAA.json` | `/sesiones/` |
| `tramitacion.py` | Seguimiento de proyectos y proposiciones de ley: estados, plazos de enmiendas, ampliaciones, ley resultante. `situacion()` explica en cada ficha dónde está y qué falta para que avance (incluido el «congelador»: plazo de enmiendas ampliado ≥ `CONGELADOR_AMP` veces durante ≥ `CONGELADOR_DIAS` días). `contenido()` saca del primer BOCG la frase de la exposición de motivos que dice qué hace el texto y los títulos de sus artículos. | `state/tramitacion.json` | `/tramitacion/` |
| `nombramientos.py` | Nombramientos y ceses de la sección II.A del BOE. | `state/nombramientos.json` | `/personas/`, `/nombramientos/` |
| `provincias.py` | Qué provincias nombra cada disposición (sección I y III) y cada pregunta; páginas por circunscripción. | `state/provincias.json` | `/provincias/` |
| `rankings.py` | Clasificaciones de diputados y grupos sobre `state/congreso.json`. | — | `/rankings/` |
| `nombres.py` | Nombres populares («Verifactu», «ley mordaza») y títulos cortos, desde `curated/nombres_populares.json`. Solo para el buscador y los títulos. | — | — |
| `aes_puro.py` | Descifrado AES en Python puro para que pypdf lea los PDF cifrados sin añadir `cryptography`. Se activa en `build.pdf_text`. | — | — |
| `feeds.py` | Canales Atom por entidad (diputado, provincia, materia, iniciativa en tramitación, ministerio): formato, orden, tope de 50 y `id` estables. No importa `build.py`; lo usa `build.renderizar_feeds()` (§13). | — | `/diputados/<slug>.xml`, `/provincias/<slug>.xml`, `/temas/<slug>.xml`, `/tramitacion/<slug>.xml`, `/preguntas/ministerio-<slug>.xml` |
| `semana.py` | Resumen semanal: `construir(semana_iso)` agrega lunes a domingo (leyes y reales decretos, votaciones ajustadas y disidencias, preguntas, tramitación, nombramientos, cifra de la semana); `asegurar()` congela las semanas cerradas; `generar_paginas()` las pinta (§13). | `data/semanas/AAAA-Snn.json` | `/semana/`, `/semana/AAAA-Snn.html`, `/semana/feed.xml` |
| `tools/semana_email.py` | Versión para correo del resumen semanal (HTML con tablas y CSS en línea, 600 px, sin JS, y texto plano) desde el mismo JSON. No envía nada. | — | artefacto `semana-correo` de `publicar.yml` |
| `paginas_fijas.py` | Textos fijos: cómo seguir la web con RSS y las páginas legales, con el marcador `<TITULAR_PENDIENTE>` (§13). | — | `/seguir/`, `/privacidad.html`, `/aviso-legal.html` |
| `indices.py` | Componentes HTML comunes de las páginas índice (cifras, filtro, filas). | — | — |
| `reproceso.py` | Reprocesa el histórico del BOE con varios extractores y una descarga por día. Solo toca `state/`. | `state/nombramientos.json`, `state/provincias.json` | — |
| `redaccion.py` | Capa Gemini: propone titular y entradilla, verifica cifras y fechas contra la fuente, cachea. Si no hay clave o cuota, no hace nada. | `state/redaccion.json` | — |
| `tools/verificar.py` | Comprobaciones de calidad comunes a la integración continua y a la salud diaria (§12). | `debug/salud.json` (modo diario) | — |
| `tools/publicables.txt` | La lista de lo que se publica: el único sitio donde se declara una carpeta publicada (§8). | — | — |
| `tools/montar_sitio.py` | Monta `_site/` con lo de `publicables.txt` y comprueba lo obligatorio, el `CNAME` y el límite de 1 GB (§8). | — | `_site/` |
| `tools/compactar_datos.sh` | Reescribe la rama `datos` como un único commit si su historia pasa de los umbrales (§8). Lo lanza `compactar-datos.yml`. | rama `datos` | — |
| `tools/datos.sh` | Trae y guarda `data/`, `state/` y `debug/` en la rama `datos`. El único sitio que sabe dónde viven los datos (§8). | rama `datos` | — |
| `tools/incidencia_salud.sh` | Abre, comenta o cierra la incidencia «Salud de la edición» con `gh` (§12). | — | — |

Front-end: `template*.html` (plantillas con marcadores `{{…}}`),
`assets/style.css`, `assets/nav.js` (menú y caja de búsqueda), `assets/indices.js`
(filtros de los índices), `assets/votaciones.js`. `app/*.jsx` es el código
fuente de `assets/parlamento.js` (hemiciclo) y `assets/buscar.js` (buscador).
Se compilan con `npm run build` y se commitean.

### El contrato de un módulo de páginas

Los módulos que generan páginas (preguntas, respuestas, tramitación,
nombramientos, provincias) no importan `build.py`. Reciben un diccionario `h`
con las utilidades del sitio y devuelven la lista de URL para el sitemap:

```python
salidas = modulo.generar_paginas({
    "esc_html": esc_html, "esc_attr": esc_attr, "fmt_date_es": fmt_date_es,
    "jsonld_script": jsonld_script, "pagina_suelta": _pagina_suelta,
    "plantilla": TEMPLATE_NORMA.read_text(encoding="utf-8"),
    "site_url": SITE_URL, "carpeta": CARPETA,
})   # -> [{"url": "https://terceracamara.es/…", "lastmod": "AAAA-MM-DD"}]
```

`pagina_suelta(plantilla, carpeta, nombre, frag)` rellena `template_norma.html`
con los marcadores `TITLE`, `META_DESC`, `CANONICAL`, `JSONLD`, `EDITION_DATE`,
`MIGA`, `KICKER`, `HEADLINE`, `STANDFIRST`, `FICHA`, `CUERPO`, `FUENTE`,
`RELACIONADAS` y `RELACIONADAS_HIDDEN`. Solo escribe si el contenido cambia.

## 5. Fuentes externas y sus rarezas

| Fuente | Cómo se lee | A tener en cuenta |
|---|---|---|
| BOE, sumario | API de datos abiertos, JSON por día | No hay BOE los domingos. `fetch_boe` retrocede hasta tres días; si el sumario no es de hoy, la edición va sin BOE (`boe_vacio`) para no duplicarlo. |
| Congreso, datos abiertos | Páginas `/es/opendata/…` que enlazan ficheros con marca de tiempo (`IntervencionesCronologicamente__20260930050130.json`) | La URL cambia cada día: se busca el enlace en la página (`_urls_json`). El volcado de intervenciones pesa decenas de MB y va con días de retraso respecto a la sesión. |
| Congreso, votaciones | Calendario por `targetDate=dd/mm/aaaa` | Es la vía al histórico: no hay listado de directorios. |
| Congreso, censo (`DiputadosActivos`) | Fichero JSON con marca de tiempo, como el resto | Con las Cortes disueltas (desde el 5-10-2026) solo trae a la Diputación Permanente (137 el 7-10-2026). Un censo por debajo de `congreso_datos.CENSO_MINIMO` (300) no sustituye al último completo; el de la XV en la disolución está en `curated/censo_xv.json` (`elegir_censo`). Mientras tanto, los miembros de la Diputación Permanente se guardan en `state/congreso.json` (`diputacion_permanente`) y el hemiciclo de `/diputados/` y de la portada los pinta en color, con el resto atenuado (`hemiciclo_svg(resaltar=…)`). Con un censo completo (nueva legislatura) la clave se borra sola. |
| Congreso, buscador de iniciativas | `POST filtrarListado` (JSON, 25 por página) y `GET mostrarDetalle` (HTML) | Pausa de `cd.PAUSA_BUSCADOR` entre peticiones y presupuesto por pase. La ficha enlaza el PDF «Contestación» cuando se publica. |
| Congreso, Diario de Sesiones | `ENLACETEXTOINTEGRO` del volcado (HTML) y `ENLACEPDF` (PDF con `#page=N`) | Estructura documentada en `respuestas.py`. Una descarga por sesión. |
| Congreso, contestaciones escritas | PDF `/l15p/e12/e_…_n_000.pdf` | Van cifrados con AES-128 y contraseña de usuario vacía; pypdf solo los abre con `aes_puro.activar()` (sin `cryptography`). Texto tras `RESPUESTA:` hasta `Madrid, dd de mes de aaaa`. El texto extraído parte palabras («cole ctivos»); `reparar_partidas()` las junta solo si la palabra entera está en el vocabulario del sitio y algún trozo no es palabra. Los que tienen texto pero no ese formato (escaneados) se anotan `sin_texto` y solo se reintentan si sube `EXTRACCION`; una descarga fallida se reintenta a los 3 días. |
| Senado | **Fuera de la automatización** (`SENADO_ACTIVO = False` en `build.py`) | Akamai devuelve 403 a las IP de centro de datos, también en los ficheros de datos abiertos (diagnóstico en la PR #8), y el Senado respondió que no tiene API ni conexión para la reutilización automatizada (`docs/solicitud-acceso-senado.md`). **No se esquiva el bloqueo**: sin proxies, sin cabeceras falsas y sin relés. Mientras sea `False` no se llama a `fetch_senado()` (que se conserva) y la nota de cobertura dice, fija: «El Senado no ofrece por ahora acceso automatizado a sus datos, así que esta sección cubre solo el Congreso». Una pieza suelta se puede añadir a mano con `feed_append` en `curated/`. |

## 6. Dónde vive cada dato (`state/`, `data/`, `curated/`)

`data/`, `state/` y `debug/` viven en la rama `datos` (§8); los workflows
los traen al árbol de trabajo con `tools/datos.sh` antes de construir.

`data/AAAA-MM-DD.json` es la edición de cada día: todo lo que se pinta de
ella sale de ahí. `data/semanas/AAAA-Snn.json` es el resumen congelado de
cada semana cerrada (§13), la fuente de verdad de `/semana/` y del correo. Las ediciones de archivo (enero a septiembre de 2026) solo
tienen el BOE.

`state/` guarda lo que se acumula entre días:

| Fichero | Contenido | Quién escribe | Tamaño (sep. 2026) | Cómo se contiene |
|---|---|---|---|---|
| `congreso.json` | Censo, contadores por diputado, votaciones con detalle nominal, intervenciones recientes | `build.cosechar_congreso` + `congreso_datos` | ~6 MB | Detalle nominal limitado a `DETALLE_MAX` votaciones; intervenciones por persona limitadas |
| `preguntas_escritas.json` | Un registro compacto por pregunta 184/ (título, autores, fechas, plazo, `cu` = PDF de contestación, `rt` = último intento) | `preguntas`, `respuestas` | ~6 MB | Ventana de 365 días (`VENTANA_DIAS`) |
| `preguntas_orales.json` | Qué sesión salió en qué edición | `preguntas` | < 1 KB | — |
| `respuestas/AAAA.json` | `orales` (por expediente 180/), `sesiones` (por fecha), `escritas` (por expediente 184/) | `respuestas` | ~1 MB/año estimado | Un fichero por año; solo citas, nunca textos completos ni PDF |
| `tramitacion.json` | Iniciativas legislativas, hitos, piezas publicadas; por iniciativa, `cont` (cita de la exposición de motivos y títulos de artículos, versión `cont_v`) y `kw` (términos, solo para el buscador) | `tramitacion` | ~1,5 MB | Solo la legislatura en curso |
| `nombramientos.json` | Registros de nombramientos y ceses por día | `nombramientos`, `reproceso` | ~0,9 MB | — |
| `provincias.json` | Disposiciones del BOE con provincia asignada | `provincias`, `reproceso` | ~1,5 MB | — |
| `redaccion.json` | Caché de titulares Gemini y uso de cuota | `redaccion` | ~0,2 MB | — |
| `ediciones.json` | Fecha de última modificación real de cada edición | `build` | < 10 KB | — |
| `ediciones_huellas.json` | Huella (sha1) del HTML de cada edición, para saber si ha cambiado sin tenerlo en disco | `build` | < 20 KB | — |
| `senado.json` | Último boletín del Senado leído | `build.fetch_senado` | < 1 KB | Sin uso mientras `SENADO_ACTIVO = False` |

Esquema de `state/respuestas/AAAA.json`:

```json
{
  "esquema": 1, "actualizado": "2026-09-30",
  "sesiones": { "2026-09-23": {"n": 17, "con_texto": 17, "leida": "2026-09-30"} },
  "orales": { "180/001178": {
      "s": "2026-09-23", "h": "09:40", "a": "Concepción Gamarra Ruiz-Clavijo", "g": "GP",
      "slug": "…", "t": "¿Cree que puede estar orgullosa de su trabajo, ministra?",
      "gob": "Margarita Robles Fernández", "cargo": "Ministra de Defensa", "quien": "Robles Fernández",
      "c1": "contestación citada", "r": "réplica citada", "c2": "dúplica citada",
      "pdf": "…DSCD-15-PL-207.PDF#page=32", "txt": "…mostrarTextoIntegro…" } },
  "escritas": { "184/041381": {
      "c": "2026-08-27", "pdf": "https://www.congreso.es/l15p/e12/e_0124421_n_000.pdf",
      "leida": "2026-09-30", "v": 2, "cita": "Se informa, en relación con…", "pal": 312 } }
}
```

Una escrita con texto pero sin el formato esperado se guarda con
`"sin_texto": true` en lugar de `cita`/`pal`. `v` es la versión de la lectura
(`respuestas.EXTRACCION`): al subirla, esas se vuelven a intentar.

`curated/` es lo editado a mano: `AAAA-MM-DD.json` (se fusiona sobre la
edición), `nombres_populares.json`, `provincias.json` (variantes y
localidades), `cargos_rankings.json` y `censo_xv.json` (censo de diputados de la XV
Legislatura en su disolución, respaldo de `congreso_datos.elegir_censo`).

## 7. Tamaño y alojamiento

Límites de GitHub: 1 GB para el sitio de Pages, unos 5 GB recomendados para
el repositorio y 100 MB por fichero. En septiembre de 2026 el sitio publicado
ocupa unos 50 MB y el repositorio, con todo su historial, unos 100 MB.

Lo que más crece no son los datos, sino el historial de git: cada pase hace un
commit y reescribe ficheros de `state/` de varios MB. Por orden, las salidas
cuando haga falta:

1. **Partir por año** lo que se acumula. Ya lo hacen `state/respuestas/` y
   el índice del buscador (`datos/indice-<tipo>[-AAAA[-MM[-q1|-q2]]].json`,
   en cuanto un tipo, un año o un mes pasa de 1 MB). Hazlo con cualquier fichero nuevo que acumule.
2. **Separar la web del código** — *aplicada en octubre de 2026* (§8): el
   HTML generado se publica como artefacto de Pages y no se commitea; los
   datos van a la rama `datos`, que se puede compactar sin tocar `main`.
3. **Llevar fuera los datos pesados** (Cloudflare R2 o Pages, con capa
   gratuita) solo si algún día se guardan textos completos.

## 8. Workflows y publicación

Desde la PR «publicacion-artefacto» (octubre de 2026) la web **no se guarda
en ninguna rama**: se construye en Actions y se publica como artefacto de
GitHub Pages. Los datos acumulados viven en la rama huérfana `datos`. El bot
ya no escribe en `main`.

```
                       ┌──────────── main (código) ────────────┐
daily.yml  (diario) ─┐ │                                       │
archivo.yml(archivo) ├─► publicar.yml ── job construir ────────┤
push a main (render)─┘   1. checkout de main                   │
                         2. tools/datos.sh traer  ◄── rama datos (data/ state/ debug/)
                         3. build.py (según el modo)
                         4. tools/verificar.py
                         5. tools/datos.sh guardar ──► rama datos (solo diario/archivo)
                         6. tools/montar_sitio.py → _site/ (tools/publicables.txt)
                         7. upload-pages-artifact
                       job desplegar: deploy-pages → https://terceracamara.es/, IndexNow
```

### `publicar.yml` (**Publicar**)

El único workflow que escribe en `datos` y el único que despliega. Se lanza
con `workflow_call` (desde `daily.yml` y `archivo.yml`), `workflow_dispatch`
o un push a `main`. Input `modo`:

- `render` (por defecto, y siempre en un push de código):
  `python build.py --render --sin-red --sitio-completo`. No descarga nada ni escribe en
  `datos`; repinta la web con el código nuevo. Verifica con `--modo ci`: con
  un grave no despliega.
- `diario`: el pase normal (`python build.py`), salud con `--modo diario`
  (`debug/salud.json`, informa y no bloquea), commit «Edición del
  AAAA-MM-DD» en `datos`, incidencia de salud e IndexNow.
- `archivo`: los modos de `archivo.yml` (`archivo_modo`: `ediciones`,
  `reprocesar`, `nombramientos`, `repintar`, con `desde`, `hasta`, `lote` y
  `extractores`). La salud va a `RUNNER_TEMP`.

Todos los modos llevan `--sitio-completo`: como la web no se guarda en
ninguna rama, cada pase pinta **todas** las ediciones y sus normas desde
`data/` (no solo la ventana de `MAX_DAYS`), en unos 40 s. Fuera de la ventana
no se pide nada a Gemini: solo se aplica la caché. Qué ediciones han cambiado
(para el `lastmod` del sitemap e IndexNow) se decide comparando la huella del
HTML con `state/ediciones_huellas.json`, no con el fichero del disco.

Input `desplegar` (por defecto `true`; en un push solo despliega `main`).
Con `false` construye y sube el artefacto `github-pages` (se puede descargar
desde la ejecución para revisarlo) pero no lo publica.

Permisos: `contents: write` e `issues: write` solo en el job `construir`
(rama `datos` e incidencia); `pages: write` e `id-token: write` solo en
`desplegar`, que usa el entorno `github-pages`. Antes de desplegar comprueba
que Settings › Pages publica desde «GitHub Actions» (`build_type =
workflow`); si no, avisa y no despliega. Después comprueba que
https://terceracamara.es/ responde 200 con su canonical.

Concurrencia: todo lo que escribe en `datos` (modos `diario` y `archivo`, y
la compactación) comparte el grupo `escritura-datos` y va de uno en uno. Los
`render` van en `publicar-render` para que un push de código nunca cancele una
edición pendiente. Los despliegues comparten `pages`.

Fuera de `main` (una prueba lanzada desde otra rama) se escribe en
`datos-pruebas`, que se crea partiendo de `datos` sin tocarla, y no se
despliega (el entorno `github-pages` solo admite `main`).

### `daily.yml`, `archivo.yml` y `ci.yml`

`daily.yml` (**Edición diaria**) llama a `publicar.yml` con `modo: diario`.
Lo dispara el Worker de `disparador/` por `workflow_dispatch`; sus cron son de
respaldo.

`archivo.yml` (**Archivo histórico**) se lanza a mano y llama a
`publicar.yml` con `modo: archivo`. Sus cuatro modos:

- `ediciones`: construye las ediciones del BOE entre `desde` y `hasta`, por
  lotes (`--archivo-desde`, `--lote`).
- `reprocesar`: pasa los extractores (`nombramientos`, `provincias`) sobre
  el histórico (`--reprocesar-desde`, `--extractores`).
- `nombramientos`: alias antiguo de `reprocesar`.
- `repintar`: vuelve a pintar todas las ediciones (`--repintar-ediciones`).
  Úsalo cuando cambie la presentación de las piezas ya publicadas: por
  ejemplo, `arreglar_fuentes()` añade a las preguntas orales antiguas la
  contestación citada.

Solo puede haber una ejecución pendiente por grupo de concurrencia, así que no
lances varias seguidas.

`ci.yml` (**Integración continua**) se lanza en cada PR contra `main` y a mano.
Trae los datos de la rama `datos` para pintar con datos reales y monta `_site`
sin subirlo. Solo lee: nunca hace commit ni push (§12).

### Dónde se declara lo que se publica: `tools/publicables.txt`

Es el **único sitio**. `tools/montar_sitio.py` copia a `_site/` solo lo que
está ahí; lo demás (código, `data/`, `state/`, `debug/`, `tests/`…) no
llega a la web. Una entrada con `!` es obligatoria: si falta, no se despliega.
`montar_sitio.py` además se niega si `CNAME` no es `terceracamara.es` o si
`_site` pasa de 1 GB (límite de Pages).

Al añadir una sección con páginas, añade su carpeta a `tools/publicables.txt`
y nada más. `tools/verificar.py` (comprobación a) da un grave si una carpeta
con HTML, o un fichero de la web de la raíz (HTML, XML, `CNAME`,
`robots.txt`, `llms.txt`, la clave de IndexNow), no está en la lista. La
lista de `mkdir` de `build.main()` sigue creando las carpetas, pero ya no es un
sitio donde haya que declararlas.

### La rama `datos` y `tools/datos.sh`

`datos` es una rama huérfana (sin historia común con `main`, no se fusiona
nunca) con `data/`, `state/`, `debug/` y un README. La crea el primer pase
`diario` o `archivo` que no la encuentra: un commit «Datos iniciales» con lo
que había en `main` y encima el del pase.

`tools/datos.sh` es el **único sitio que sabe dónde están los datos**
(`traer` y `guardar`). `build.py` sigue leyendo y escribiendo `./data`,
`./state` y `./debug`. Cuando en la fase B los datos pasen a almacenamiento
externo, se cambia ese script y nada más. `guardar` hace `pull --rebase` y un
reintento; nunca toca `main`.

### Compactación de la rama `datos`

`datos` recibe tres commits al día y reescribe ficheros de `state/` de varios
MB, así que su historia crece sin parar. `.github/workflows/compactar-datos.yml`
corre los domingos de madrugada (y a mano, con `forzar`) y ejecuta
`tools/compactar_datos.sh`: si la rama pasa de `MAX_COMMITS` commits (300) o de
`MAX_MB` MB de historia (150), la reescribe como **un único commit con el mismo
árbol** que la punta y hace push forzado **solo a `datos`**, con
`--force-with-lease` contra la punta que acaba de medir. Va en el grupo de
concurrencia `escritura-datos`, así que nunca coincide con un pase. El
contenido no cambia; solo se pierde la historia de `datos`. Es la única
excepción a la regla de no forzar push (AGENTS.md).

### Vuelta atrás

`main` ya no contiene la web ni los datos (PR «main-solo-codigo»). El último
commit de `main` que los tenía, con el job antiguo de commit en `main`, es
**`e31e2553d`** (fusión de la PR #19). Si la publicación por artefacto falla y
la web deja de cargar:

1. Abre una PR que revierta la fusión de «main-solo-codigo» (en la PR
   fusionada, botón **Revert**). Eso devuelve a `main` el HTML generado,
   `data/`, `state/`, `debug/` y el job antiguo de `daily.yml` y `archivo.yml`
   tal como estaban en `e31e2553d`. Fusiónala.
2. Settings › Pages › Build and deployment › Source: **Deploy from a branch**,
   rama `main`, carpeta `/ (root)`. En ese momento se sirve la web de
   `e31e2553d` (la del 5 de octubre de 2026).
3. Settings › Secrets and variables › Actions › Variables: crea
   `PUBLICAR_EN_MAIN` con el valor `true`.
4. Actions › Edición diaria › Run workflow (rama `main`). El job antiguo trae
   antes los datos de la rama `datos`, así que no se pierde nada de lo
   publicado por la vía nueva, y deja la edición del día en `main`.

Para volver a la vía nueva: Source «GitHub Actions», borra `PUBLICAR_EN_MAIN`
y vuelve a fusionar «main-solo-codigo» (revirtiendo la reversión).

## 9. Cómo añadir una sección o una fuente

1. **Módulo propio.** Crea `mi_seccion.py`, con un docstring que diga la
   fuente, el formato comprobado (con fecha) y los límites. Pon sus
   constantes de presupuesto arriba.
2. **Recolección.** Una función `actualizar(get, log, …)` llamada desde
   `construir_dia`/`cortes_congreso` dentro de un `try`. Recibe `get`/`post`
   de `build.py`, que ya gestionan reintentos y cabeceras. Nada de sesiones
   HTTP propias.
3. **Estado.** Si acumula, escribe en `state/mi_seccion.json`, o
   `state/mi_seccion/AAAA.json` si crece cada año. Ponle `esquema` y una
   ventana o poda.
4. **Piezas del feed.** Diccionarios con `chamber`, `type`, `date`,
   `headline`, `standfirst`, `body` (lista de frases), `source`
   `{label, url}`, `links` y, opcionalmente, `quote` `{text, author}`.
   Recuerda qué publicaste para no repetir.
5. **Páginas.** `generar_paginas(h)` según el contrato del §4. En `build.py`,
   un `renderizar_mi_seccion()` llamado desde `renderizar()` en su `try`, la
   carpeta en `tools/publicables.txt` (§8), y enlaces desde `render_nav`,
   `renderizar_mapa` y, si procede, `/seguimiento/`.
6. **Descubrimiento.** Entradas en `llms.txt`. Si tiene que aparecer en el
   buscador, un tipo nuevo en `renderizar_buscador`.
7. **Pruebas.** `tests/test_mi_seccion.py` con fixtures que reproduzcan el
   formato real, sin red.
8. **Documentación.** Una fila en las tablas de este documento.

## 10. Probar sin red

```bash
python -m unittest discover tests          # pruebas unitarias, sin red
python build.py --render --sin-red         # el sitio entero desde data/ y state/
python tools/verificar.py --modo ci        # comprobaciones sobre el resultado
```

El modo `--sin-red` se explica en §12.

La validación con datos reales se hace lanzando «Edición diaria» (o
«Publicar» con `modo: diario`) sobre la rama de trabajo (Actions › Run
workflow › rama), una vez que el workflow está en `main`. Fuera de `main` los
datos se escriben en la rama `datos-pruebas` (que parte de `datos` sin
tocarla) y no se despliega nada: se lee el log, el resumen y
`debug/last-run.json` en `datos-pruebas`. La rama de trabajo no recibe
commits del bot.

## 11. Glosario

- **180/**, **184/**: tipos de expediente del Congreso. 180 es la pregunta
  oral en Pleno y 184 la pregunta con respuesta escrita. Un expediente
  completo lleva sufijo (`180/001178/0000`) y aquí se guarda sin él.
- **BOCG**: Boletín Oficial de las Cortes Generales. En el Congreso, la serie
  A son proyectos de ley, la B proposiciones y la D control (preguntas y
  contestaciones).
- **DS / DSCD**: Diario de Sesiones del Congreso de los Diputados, la
  transcripción literal de cada sesión (`DSCD-15-PL-207` es el Pleno número
  207 de la XV Legislatura).
- **Sesión de control**: la parte del Pleno de los miércoles con preguntas
  orales al Gobierno. Cada pregunta tiene formulación, contestación, réplica y
  dúplica.
- **Volcado**: los ficheros JSON de datos abiertos que el Congreso regenera
  cada madrugada.

## 12. Calidad

Dos momentos, un mismo verificador: la **integración continua** detecta los
errores antes de fusionar y la **salud diaria** los que aparecen al publicar.

### `tools/verificar.py`

Un único script, solo con la biblioteca estándar. Cada comprobación es una
función `comprobar_x(raiz, …)` que devuelve hallazgos
`{nivel, comprobacion, detalle, fichero}`; `nivel` es `grave` o `aviso`, y
el detalle de los graves acaba en «Qué hacer: …».

| | Comprobación | Nivel |
|---|---|---|
| a | `carpetas`: cada carpeta de primer nivel con HTML y cada fichero de la web de la raíz están en `tools/publicables.txt` (§8) | grave |
| b | `html`: marcadores sin sustituir (`{{`, `}}`, `__SSR_…__`, `None`, `undefined`, `NaN`, `<EMAIL_DE_CONTACTO>`, fuera de `<script>`), JSON-LD estricto, `<title>`, meta description y canonical de `https://terceracamara.es`, enlaces internos a ficheros inexistentes. `<TITULAR_PENDIENTE>` es solo **aviso**: es un hueco decidido por el mantenedor, no un fallo del código (§13) | grave (titular pendiente: aviso) |
| c | `sitemap`: XML válido, URL del dominio que existen, sin duplicados, ≤ 50.000 por fichero | grave |
| d | `indice`: `datos/indice*.json` válido y < 1 MB | grave |
| e | `titulares` de `data/<fecha>.json` (BOE y Cortes): fin en preposición/artículo/conjunción, nombres de fichero o códigos, «Y N ASUNTOS MÁS», longitud, palabra cortada | grave (muy largo: aviso); en el CI, aviso |
| f | `duplicados`: identificador (referencia del BOE o documento oficial) ya publicado en los 7 días anteriores; titular repetido con otro documento | grave / aviso; en el CI, aviso |
| g | `tamanos`: ficheros de `state/` (aviso 10 MB, grave 25 MB), historia de `main` (aviso 500 MB, grave 900 MB), historia de la rama `datos` (aviso 200 MB, grave 500 MB), número y peso de lo que va a `_site` | aviso / grave |
| h | `feeds`: cada `.xml` publicado (salvo los sitemaps) es Atom 1.0 o RSS 2.0 bien formado, con los campos obligatorios, fechas RFC 3339 (Atom) o RFC 822 (RSS), sin `id`/`guid` repetidos y con 50 entradas como máximo | grave |
| i | `semana` (solo salud diaria): existe `/semana/AAAA-Snn.html` de la semana que terminó el domingo anterior | grave |

Las heurísticas de (e) están en constantes documentadas, cada una con el
fallo real del que sale. Los fragmentos que otra página incrusta
(`datos/votaciones-banner.html`) no se exigen `<title>` ni canonical. Las
piezas que enlazan al propio sitio (el recuento diario de preguntas
pendientes) no cuentan como duplicado.

Los tamaños de historia se miden con `git rev-list --disk-usage --objects`:
`main` en `HEAD` y `datos` en la referencia de `VERIFICAR_REF_DATOS`
(`origin/datos`). `publicar.yml` descarga `main` con la historia completa; en
`ci.yml` el checkout es superficial y se usa `REPO_TAMANO_KB` (el tamaño de
todo el repositorio según la API de GitHub), que es una cota superior.

`SALUD_FORZAR_GRAVE=1` añade un hallazgo grave ficticio: sirve para probar la
incidencia en una rama de pruebas y solo lo lee `verificar.py`.

### Integración continua: `.github/workflows/ci.yml`

En cada PR contra `main` (y a mano): trae los datos de la rama `datos`
(`tools/datos.sh traer`, solo lectura), compila (`compileall`), pasa las
pruebas, regenera el sitio con `python build.py --render --sin-red` y ejecuta
`python tools/verificar.py --modo ci`: (a), (b), (c), (d) y (g) sobre el
resultado y (e) y (f) sobre la edición más reciente de `data/`. Falla con
cualquier grave, salvo los de (e) y (f), que en el CI cuentan como aviso: miran
datos que escribió el pase diario y que ninguna PR puede corregir (la edición
se rehace con el código nuevo solo después de fusionar), así que bloquearían
cualquier PR. En la salud diaria siguen siendo graves y abren la incidencia.
Los avisos van al resumen del job. `permissions: contents: read`, sin secretos, nunca hace commit ni push. Al final monta `_site` con
`tools/montar_sitio.py`, sin subirlo. El render completo (`--sitio-completo`) tarda unos 40 s.

### Salud diaria (`publicar.yml`, modos `diario` y `archivo`)

Después de construir y antes de publicar, `verificar.py --modo diario`
escribe `debug/salud.json`, que se guarda en la rama `datos` (en modo
`archivo`, a `RUNNER_TEMP`, para no dejar commits vacíos) y el resumen del job. **La edición se publica siempre**: la
salud informa, no bloquea, y el paso tiene `continue-on-error`.

Después de publicar, `tools/incidencia_salud.sh` usa `gh` con el
`GITHUB_TOKEN` del workflow (`permissions: issues: write`):

- con graves, abre la incidencia «Salud de la edición» con la etiqueta
  `salud` (la crea si no existe) o, si ya hay una abierta, comenta en ella;
- sin graves y con una abierta, comenta «Resuelto el <fecha>» y la cierra.

GitHub avisa por correo de las incidencias nuevas a quien vigila el
repositorio (Watch › Custom › Issues, activado en octubre de 2026).

### Modo sin red (`--sin-red`)

`build.py --render --sin-red` (o `--repintar-ediciones --sin-red`) regenera el
sitio sin ninguna petición HTTP. `get()`, `post()` y `sesion_para()` lanzan
`SinRed` antes de abrir conexión y, como red de seguridad,
`requests.Session.request` también (por ahí pasan `redaccion.py` y la capa LLM).
Las secciones que dependen de red se saltan con su `log()`, como ante un fallo.

Durante el render había dos sitios que pedían datos: `cosechar_congreso()`
(censo y votaciones) y `redaccion.aplicar()` (Gemini). Con `--sin-red` el
primero trabaja solo con `state/congreso.json` (`sin_red=True`, como en el
archivo) y el segundo solo aplica la caché (`pedir=False`). Sin `--sin-red`
se comportan como siempre.

### Cómo añadir una comprobación

1. Una función `comprobar_x(raiz, …) -> list[dict]` en `tools/verificar.py`,
   con sus umbrales en constantes arriba y, si es una heurística, el ejemplo
   real que la motiva.
2. Su entrada en `ejecutar()`.
3. Casos positivo y negativo en `tests/test_verificar.py`.
4. Una fila en la tabla de arriba.

Si una comprobación da un falso positivo, se corrige la comprobación en una
PR con un test que lo cubra; no se silencia ni se rebaja sin justificarlo.

## 13. Audiencia: analítica, canales, páginas legales

Fase de crear audiencia antes de cobrar (octubre de 2026). Nada de backend
propio ni dependencias nuevas; todo lo nuevo es determinista.

### Analítica sin cookies

Cloudflare Web Analytics, con la baliza en todas las plantillas
(`__SSR_ANALITICA__`, que `_replace_placeholders` sustituye por
`baliza_analitica()`). El token del sitio va en `build.CF_ANALYTICS_TOKEN`: es
**público** (viaja en el HTML de cada página) y lo da el panel de Cloudflare
(Web Analytics › sitio `terceracamara.es` › instalación manual, porque la web
no pasa por el proxy de Cloudflare). Vacío o con forma rara, no se inserta
nada. Sustituye a GoatCounter.

La baliza no usa cookies ni almacenamiento del navegador. Cómo comprobarlo
(hecho en la web publicada al instalarla): abrir una página, esperar a que
cargue `static.cloudflareinsights.com/beacon.min.js` y mirar que
`document.cookie` está vacío y que `localStorage`, `sessionStorage` e
IndexedDB no tienen ninguna clave; en las herramientas de desarrollo,
Application › Cookies no muestra ninguna para `terceracamara.es` ni para
`cloudflareinsights.com`. Como no hay cookies, no hay banner de
consentimiento. Si algún día se añade algo que guarde estado en el
navegador, hay que revisar /privacidad.html y la necesidad de banner.

### Canales por entidad (las «alertas» gratuitas)

`build.renderizar_feeds()` escribe, junto a cada página, su canal Atom con
las mismas reglas (`feeds.py`): 50 entradas como máximo, fecha del hecho
oficial, `id` estable `tag:terceracamara.es,2026:<tipo>:<identificador>`, y el
`updated` del canal es el de su entrada más reciente (sin novedades, el
fichero no cambia).

| Canal | Entradas |
|---|---|
| `/diputados/<slug>.xml` | preguntas escritas (registro y contestación), preguntas orales, últimas intervenciones y votos distintos a los de su grupo |
| `/provincias/<slug>.xml` | disposiciones del BOE que la nombran (`state/provincias.json`) y preguntas escritas cuyo título la cita |
| `/temas/<slug>.xml` | lo publicado en el BOE en esa materia (`agrupar_materias`, la misma lista que /temas/) |
| `/tramitacion/<slug>.xml` | solo iniciativas abiertas (`tramitacion.ABIERTOS`): cada paso con su fecha y cada ampliación del plazo de enmiendas, fechada el día en que vencía el plazo anterior (el Congreso no publica la fecha del acuerdo; la entrada lo dice) |
| `/preguntas/ministerio-<slug>.xml` | preguntas orales de control que contesta ese departamento (deducido del cargo de quien contesta; las escritas no dicen ministerio) |

Se generan antes que las páginas: `FEEDS_PAGINA` registra cada canal y
`_pagina_suelta()` pone en su página el `<link rel="alternate"
type="application/atom+xml">` y el botón «Seguir con RSS». Ningún generador
de páginas tiene que saber nada. Un canal sin entradas no se escribe. La
comprobación (h) de `verificar.py` los valida todos. `/seguir/` explica qué es
RSS, lectores gratuitos y cómo recibir los canales por correo con servicios
gratuitos de terceros.

### Resumen semanal (`semana.py`)

`/semana/AAAA-Snn.html` («La semana en las Cortes y el BOE (del D al D de
mes de AAAA)»), `/semana/index.html` (archivo) y `/semana/feed.xml`. Secciones,
cada una solo si tiene datos y cada elemento con su enlace: leyes y reales
decretos del BOE (con el titular Gemini de la edición diaria, si lo hay,
marcado como editorial), las votaciones más ajustadas y los votos distintos a
los del grupo (sin el Grupo Mixto, como en /rankings/), preguntas (orales
literales, escritas contestadas y pendientes con el plazo superado, con la
redacción prudente de /preguntas/), cambios de tramitación (pasos y
ampliaciones de enmiendas), nombramientos y ceses de real decreto, orden o
acuerdo, y «La cifra de la semana» con reglas fijas (`semana.REGLAS_CIFRA`,
publicadas en cada página). Mismo trato para todos los grupos.

**Cuándo se construye.** El pase diario (`python build.py`, `daily.yml`)
llama a `semana.asegurar()`: congela en `data/semanas/AAAA-Snn.json` las
semanas cerradas que falten. El del lunes construye la que acaba de cerrar;
los demás no hacen nada, así que relanzar el pase no cambia nada
(idempotente). La primera vez construyó todo el archivo desde la semana 1 de
2026. `build.py --render` solo pinta las congeladas. Para rehacerlas todas
tras cambiar las reglas, se sube `semana.VERSION`.

**Por qué congelar.** Una semana publicada no debe cambiar porque luego se
pode el estado (preguntas escritas: 365 días; votaciones con detalle nominal:
las últimas `DETALLE_MAX`). Por lo mismo, una semana solo resume votaciones si
el detalle la cubre entera, y las pendientes al cierre solo se cuentan al
congelar la semana recién cerrada (`DIAS_PENDIENTES`). Los enlaces se
resuelven al pintar: si la página del sitio ya no existe (una votación que
salió del detalle), se enlaza la fuente oficial.

**JSON-LD.** `Report`, no `NewsArticle`: es un informe periódico generado con
reglas fijas sobre datos oficiales, sin autoría periodística ni valoraciones.
Presentarlo como noticia sería afirmar algo que no es, aunque Google solo dé
resultados enriquecidos de artículo a `NewsArticle`.

**Correo.** `tools/semana_email.py` hace la versión para correo (tablas, CSS
en línea, 600 px, sin JS ni recursos remotos, y texto plano) del mismo JSON.
`publicar.yml` la sube en cada pase como artefacto `semana-correo` (30 días)
para revisarla. No envía nada.

### Páginas legales

`/privacidad.html` y `/aviso-legal.html` (`paginas_fijas.py`), enlazadas en el
pie de todas las plantillas. No hay actividad económica y los datos del
titular no se publican: en su lugar va el marcador literal
`<TITULAR_PENDIENTE>`, que `verificar.py` señala como aviso.

**Antes de cualquier actividad económica (suscripción o publicidad), el aviso
legal debe incluir los datos del titular exigidos por la LSSI.**

