# Arquitectura de La Tercera Cámara

Este documento es la puerta de entrada al código. Está pensado para que una
persona o una IA que llega nueva al proyecto sepa, sin leer 12.000 líneas, qué
hace cada pieza, dónde se guarda cada dato y qué reglas no se pueden romper.
Si cambias la arquitectura (un módulo, un fichero de `state/`, una carpeta
publicada, un workflow), actualiza este documento en la misma PR.

Las reglas de trabajo para agentes están en [AGENTS.md](AGENTS.md). El README
explica el proyecto a quien lo usa; esto explica cómo está hecho.

## 1. Qué es, en una frase

Un sitio estático (https://terceracamara.es/, GitHub Pages) que se regenera
solo tres veces al día con lo que publican el BOE y el Congreso. Todo corre en
GitHub Actions: no hay servidor, ni base de datos, ni API propia. La «base de
datos» son ficheros JSON en `state/` y `data/`, versionados en el propio
repositorio.

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
4. **Transparencia de cobertura.** Si una fuente no responde (el Senado, por
   ejemplo), la edición lo dice en la nota de cobertura en lugar de
   disimularlo.
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
                                                          python build.py
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
   ├─ fetch_senado()            (hoy siempre 403, ver §6)
   ├─ redactar_boe() / redactar_cortes()
   └─ fusionar_curado()         curated/ por encima
            │
            ▼
   data/AAAA-MM-DD.json   (la edición del día, fuente de verdad del render)
            │
  renderizar() ─────────────────────────────────────────────────────┐
   ├─ redaccion.aplicar()        titulares Gemini (opcional, con caché)
   ├─ cosechar_congreso()        censo, votaciones → state/congreso.json
   ├─ renderizar_diputados / votaciones / rankings
   ├─ renderizar_preguntas / sesiones / nombramientos / tramitacion
   ├─ renderizar_seguimiento / provincias
   ├─ renderizar_index / ediciones / normas / temas / plazos
   ├─ renderizar_buscador / mapa
   └─ sitemap.xml, feed.xml, indexnow.json
            │
  daily.yml: git add + commit «Edición del AAAA-MM-DD» + push → GitHub Pages
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
| `build.py` | Orquesta todo: CLI, recolección del BOE y del Senado, redacción determinista, render de todas las páginas, sitemap, feed. Es grande (~6.000 líneas) porque es la capa de presentación del sitio entero. | `data/`, `debug/`, `state/ediciones.json` | `/`, `/ediciones/`, `/normas/`, `/temas/`, `/plazos/`, `/diputados/`, `/votaciones/`, `/rankings/`, `/seguimiento/`, `/buscar/`, `/mapa/`, `/datos/` |
| `congreso_datos.py` | Cliente de los datos abiertos del Congreso: censo de diputados, volcado de intervenciones, votaciones (con el histórico por `targetDate`), grupos y colores, URL de fichas. | `state/congreso.json` (vía build) | — |
| `preguntas.py` | Preguntas al Gobierno: orales (volcado) y escritas (buscador de iniciativas, tipo 184). Plazos del art. 190 del Reglamento, pendientes, piezas del feed. | `state/preguntas_escritas.json`, `state/preguntas_orales.json` | `/preguntas/` (solo con el año completo en el estado) |
| `respuestas.py` | Qué contesta el Gobierno. Orales: citas del Diario de Sesiones (contestación, réplica, dúplica). Escritas: cita del PDF de contestación. | `state/respuestas/AAAA.json` | `/sesiones/` |
| `tramitacion.py` | Seguimiento de proyectos y proposiciones de ley: estados, plazos de enmiendas, ampliaciones, ley resultante. | `state/tramitacion.json` | `/tramitacion/` |
| `nombramientos.py` | Nombramientos y ceses de la sección II.A del BOE. | `state/nombramientos.json` | `/personas/`, `/nombramientos/` |
| `provincias.py` | Qué provincias nombra cada disposición (sección I y III) y cada pregunta; páginas por circunscripción. | `state/provincias.json` | `/provincias/` |
| `rankings.py` | Clasificaciones de diputados y grupos sobre `state/congreso.json`. | — | `/rankings/` |
| `nombres.py` | Nombres populares («Verifactu», «ley mordaza») y títulos cortos, desde `curated/nombres_populares.json`. Solo para el buscador y los títulos. | — | — |
| `aes_puro.py` | Descifrado AES en Python puro para que pypdf lea los PDF cifrados sin añadir `cryptography`. Se activa en `build.pdf_text`. | — | — |
| `indices.py` | Componentes HTML comunes de las páginas índice (cifras, filtro, filas). | — | — |
| `reproceso.py` | Reprocesa el histórico del BOE con varios extractores y una descarga por día. Solo toca `state/`. | `state/nombramientos.json`, `state/provincias.json` | — |
| `redaccion.py` | Capa Gemini: propone titular y entradilla, verifica cifras y fechas contra la fuente, cachea. Si no hay clave o cuota, no hace nada. | `state/redaccion.json` | — |
| `senado_local.py` | Recolector del Senado para ejecutar fuera de Actions (ver §6). | `curated/` | — |

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
| Congreso, buscador de iniciativas | `POST filtrarListado` (JSON, 25 por página) y `GET mostrarDetalle` (HTML) | Pausa de `cd.PAUSA_BUSCADOR` entre peticiones y presupuesto por pase. La ficha enlaza el PDF «Contestación» cuando se publica. |
| Congreso, Diario de Sesiones | `ENLACETEXTOINTEGRO` del volcado (HTML) y `ENLACEPDF` (PDF con `#page=N`) | Estructura documentada en `respuestas.py`. Una descarga por sesión. |
| Congreso, contestaciones escritas | PDF `/l15p/e12/e_…_n_000.pdf` | Van cifrados con AES-128 y contraseña de usuario vacía; pypdf solo los abre con `aes_puro.activar()` (sin `cryptography`). Texto tras `RESPUESTA:` hasta `Madrid, dd de mes de aaaa`. El texto extraído parte palabras («cole ctivos»); `reparar_partidas()` las junta solo si la palabra entera está en el vocabulario del sitio y algún trozo no es palabra. Los que tienen texto pero no ese formato (escaneados) se anotan `sin_texto` y solo se reintentan si sube `EXTRACCION`; una descarga fallida se reintenta a los 3 días. |
| Senado | — | Akamai devuelve 403 a las IP de centro de datos, también en los ficheros de datos abiertos (diagnóstico en la PR #8). **No se esquiva el bloqueo**: sin proxies, sin cabeceras falsas y sin relés. La cobertura lo declara. Vías legítimas: `senado_local.py` desde una conexión doméstica, `feed_append` manual o una autorización del Senado. |

## 6. Dónde vive cada dato (`state/`, `data/`, `curated/`)

`data/AAAA-MM-DD.json` es la edición de cada día: todo lo que se pinta de
ella sale de ahí. Las ediciones de archivo (enero a septiembre de 2026) solo
tienen el BOE.

`state/` guarda lo que se acumula entre días:

| Fichero | Contenido | Quién escribe | Tamaño (sep. 2026) | Cómo se contiene |
|---|---|---|---|---|
| `congreso.json` | Censo, contadores por diputado, votaciones con detalle nominal, intervenciones recientes | `build.cosechar_congreso` + `congreso_datos` | ~6 MB | Detalle nominal limitado a `DETALLE_MAX` votaciones; intervenciones por persona limitadas |
| `preguntas_escritas.json` | Un registro compacto por pregunta 184/ (título, autores, fechas, plazo, `cu` = PDF de contestación, `rt` = último intento) | `preguntas`, `respuestas` | ~6 MB | Ventana de 365 días (`VENTANA_DIAS`) |
| `preguntas_orales.json` | Qué sesión salió en qué edición | `preguntas` | < 1 KB | — |
| `respuestas/AAAA.json` | `orales` (por expediente 180/), `sesiones` (por fecha), `escritas` (por expediente 184/) | `respuestas` | ~1 MB/año estimado | Un fichero por año; solo citas, nunca textos completos ni PDF |
| `tramitacion.json` | Iniciativas legislativas, hitos, piezas publicadas | `tramitacion` | ~1,5 MB | Solo la legislatura en curso |
| `nombramientos.json` | Registros de nombramientos y ceses por día | `nombramientos`, `reproceso` | ~0,9 MB | — |
| `provincias.json` | Disposiciones del BOE con provincia asignada | `provincias`, `reproceso` | ~1,5 MB | — |
| `redaccion.json` | Caché de titulares Gemini y uso de cuota | `redaccion` | ~0,2 MB | — |
| `ediciones.json` | Qué fecha de BOE tiene cada edición | `build` | < 10 KB | — |

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
localidades) y `cargos_rankings.json`.

## 7. Tamaño y alojamiento

Límites de GitHub: 1 GB para el sitio de Pages, unos 5 GB recomendados para
el repositorio y 100 MB por fichero. En septiembre de 2026 el sitio publicado
ocupa unos 50 MB y el repositorio, con todo su historial, unos 100 MB.

Lo que más crece no son los datos, sino el historial de git: cada pase hace un
commit y reescribe ficheros de `state/` de varios MB. Por orden, las salidas
cuando haga falta:

1. **Partir por año** lo que se acumula. Ya lo hacen `state/respuestas/` y
   el índice del buscador (`datos/indice-<tipo>[-AAAA[-MM]].json`, en cuanto
   un tipo pasa de 1 MB). Hazlo con cualquier fichero nuevo que acumule.
2. **Separar la web del código**: publicar el HTML generado con un artefacto
   de Pages o una rama `gh-pages`, en vez de commitearlo en `main`. Conviene
   cuando el repositorio pase de ~1 GB.
3. **Llevar fuera los datos pesados** (Cloudflare R2 o Pages, con capa
   gratuita) solo si algún día se guardan textos completos.

## 8. Workflows

`daily.yml` (**Edición diaria**) lanza `python build.py` y publica si hay
cambios. Lo dispara el Worker de `disparador/` por `workflow_dispatch`; sus
cron son de respaldo.

`archivo.yml` (**Archivo histórico**) se lanza a mano y tiene cuatro modos:

- `ediciones`: construye las ediciones del BOE entre `desde` y `hasta`, por
  lotes (`--archivo-desde`, `--lote`).
- `reprocesar`: pasa los extractores (`nombramientos`, `provincias`) sobre
  el histórico (`--reprocesar-desde`, `--extractores`).
- `nombramientos`: alias antiguo de `reprocesar`.
- `repintar`: vuelve a pintar todas las ediciones (`--repintar-ediciones`).
  Úsalo cuando cambie la presentación de las piezas ya publicadas: por
  ejemplo, `arreglar_fuentes()` añade a las preguntas orales antiguas la
  contestación citada.

Los dos workflows comparten el grupo de concurrencia `edicion-diaria`. Solo
puede haber una ejecución pendiente, así que no lances varias seguidas.

Toda carpeta publicada tiene que estar en tres sitios:

- la lista de `mkdir` de `build.main()`;
- las líneas `mkdir -p` y `git add -A` de los dos workflows;
- una constante `*_DIR` en `build.py`.

Si falta en los workflows, `git add` falla.

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
   carpeta en los tres sitios del §8, y enlaces desde `render_nav`,
   `renderizar_mapa` y, si procede, `/seguimiento/`.
6. **Descubrimiento.** Entradas en `llms.txt`. Si tiene que aparecer en el
   buscador, un tipo nuevo en `renderizar_buscador`.
7. **Pruebas.** `tests/test_mi_seccion.py` con fixtures que reproduzcan el
   formato real, sin red.
8. **Documentación.** Una fila en las tablas de este documento.

## 10. Probar sin red

```bash
python -m unittest discover tests          # pruebas unitarias, sin red
```

Para comprobar el render entero sin tocar internet, sustituye `get` y `post`
por funciones que devuelvan `None`:

```python
import sys; sys.argv = ["build.py", "--render"]
import build
build.get = lambda *a, **k: None
build.post = lambda *a, **k: None
build.main()
```

La validación con datos reales se hace lanzando «Edición diaria» sobre la
rama de trabajo (Actions › Run workflow › rama) y leyendo el log y
`debug/last-run.json`. Esa rama se llena de commits del bot, así que la PR sale
de otra rama limpia con solo el código.

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
