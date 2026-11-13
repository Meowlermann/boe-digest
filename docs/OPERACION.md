# Operación de La Tercera Cámara

Cómo se publica el sitio, cuándo corren las pasadas y qué hacer con
los modos que no pintan una edición completa. La arquitectura detallada
está en [ARQUITECTURA.md](../ARQUITECTURA.md). Este documento se actualiza
en la misma PR que cambie la operación.

El repositorio es público. El único correo que debe aparecer en el sitio
y en estos documentos es contacto@terceracamara.es. Nada de nombres de
personas, correos personales, cuentas, identificadores de cuenta ni secretos.

## Horarios de las pasadas

Todos los cron (el Worker de Cloudflare y GitHub Actions) están en **UTC
fijo** y no siguen el cambio de hora. La hora de Madrid se mueve una hora
entre verano (UTC+2) e invierno (UTC+1). Nunca se dispara después de las
22:00 UTC: `build.py` fecha la edición con el día UTC del runner, y un pase
tardío abriría la edición del día siguiente.

Los pases los lanza el Worker `disparador/` (`terceracamara-disparador`) con
`workflow_dispatch` sobre `daily.yml`. Los cron de `daily.yml` son solo
respaldo, porque GitHub no garantiza la puntualidad de los cron (se han
medido retrasos de casi cinco horas).

| Origen | Cron (UTC) | Madrid, invierno (UTC+1) | Madrid, verano (UTC+2) | Para qué |
|---|---|---|---|---|
| Worker | `40 5 * * *` | 06:40 | 07:40 | El BOE del día |
| Worker | `40 6 * * *` | 07:40 | 08:40 | Segundo intento si falla el primero |
| Worker | `40 12 * * *` | 13:40 | 14:40 | Mediodía: preguntas y tramitación |
| Worker | `40 19 * * *` | 20:40 | 21:40 | Noche: votaciones del pleno de la tarde |
| `daily.yml` (respaldo) | `37 5 * * *` | 06:37 | 07:37 | Red de seguridad del pase de la mañana |
| `daily.yml` (respaldo) | `23 8 * * *` | 09:23 | 10:23 | Si el primero se retrasa |
| `daily.yml` (respaldo) | `7 13 * * *` | 14:07 | 15:07 | Red de seguridad del pase de mediodía |

El pase de la noche no tiene cron de respaldo a propósito: con un retraso
grande caería pasada la medianoche UTC.

Otros cron que no publican la edición:

- Vigilante de despliegues (`vigilante.yml`): `40 7,14,21 * * *` UTC.
- Observabilidad de producción (`observabilidad.yml`): `50 9 * * *` UTC.
- Lighthouse CI (`lighthouse.yml`): `15 10 * * 1` UTC (lunes).
- Compactación de la rama `datos` (`compactar-datos.yml`): `17 3 * * 0` UTC
  (domingos de madrugada).

### Ventanas en las que no se hace push

Para no cruzarse con una pasada, no se hace push ni se lanza un workflow si
`gh run list --status in_progress` o `--status queued` no están vacíos, y no
se relanza nada que haya dado timeout. En hora de Madrid, evitar empujar
alrededor de las pasadas; de forma fija, no hay push entre las 20:10 y las
21:10 (pase de las 20:40 en invierno) ni en la ventana de mediodía
(13:10–14:50 en invierno, alrededor del pase de las 13:40).

## Cómo publicar

`publicar.yml` es el único workflow que escribe en la rama `datos` y el
único que despliega la web. `main` solo lleva código. El HTML generado no se
guarda en ninguna rama.

Se lanza de tres maneras:

1. **Pase diario** (`daily.yml`, modo `diario`): lo dispara el Worker o el
   cron de respaldo, o un `workflow_dispatch` a mano. Ejecuta `python build.py`,
   guarda `data/`, `state/` y `debug/` en la rama `datos` y avisa a IndexNow.
2. **Push de código a `main`** (modo `render`): `python build.py --render --sin-red --sitio-completo`.
   No descarga nada y no escribe en `datos`; repinta la web con el código
   nuevo y los datos ya guardados. Un hallazgo grave en `verificar.py` impide
   el despliegue.
3. **Archivo** (`archivo.yml`, modo `archivo`): a mano, por tramos. Véanse
   los modos más abajo.

El job `construir` monta `_site/` con `tools/montar_sitio.py` (solo lo
listado en `tools/publicables.txt`), sube el artefacto de Pages y el job
`desplegar` llama a `actions/deploy-pages@v4`. Después comprueba que
https://terceracamara.es/ responde 200 con su canonical. Input `desplegar=false`
construye y sube el artefacto sin publicarlo.

Concurrencia: lo que escribe en `datos` (diario, archivo y compactación) va
en el grupo `escritura-datos`, de uno en uno. Los render van en
`publicar-render`, para que un push de código no cancele una edición. Los
despliegues comparten el grupo `pages`.

Una prueba lanzada desde otra rama escribe en `datos-pruebas` (parte de
`datos` sin tocarla) y no se despliega.

Antes de fusionar una PR: la integración continua (`ci.yml`) tiene que estar
en verde. En la práctica del proyecto, además hace falta el OK explícito del
mantenedor, con sus propias palabras. No se fusiona con el CI en rojo ni
desactivándolo. La fusión, cuando se autorice, es `gh pr merge N --squash`.
Después hay que esperar a que el workflow **Publicar** de `main` salga en
verde y comprobar la web con `curl`.

## Reproceso de empleo con `archivo.yml`

Para releer convocatorias ya guardadas (por ejemplo, tras un cambio del
extractor de empleo) se lanza **Archivo histórico** a mano, con:

- modo `reprocesar`
- `extractores=empleo` (o la lista que corresponda)
- `desde` y, si aplica, `hasta`

El reproceso actualiza `state/` (en empleo, `state/empleo.json`) y
`publicar.yml` guarda esos datos en la rama `datos`. **No pinta una edición
completa**, así que el paso «Montar `_site`» falla: faltan páginas
obligatorias y no hay despliegue. Es el fallo esperado. Los datos ya se han
guardado antes de ese paso.

Para que el cambio se vea en la web hace falta un **render posterior**
(un push de código a `main`, o un `workflow_dispatch` de `publicar.yml` en
modo `render` desde `main`).

Desde la PR #103, en modo `reprocesar` o `nombramientos` no se corre el
chequeo de salud ni se abre la incidencia «Salud de la edición». Esos modos
no construyen una edición completa y el chequeo producía graves que no
correspondían (falsa alarma #100). En diario, render, `ediciones` y
`repintar` el comportamiento no cambia.

## Elecciones del 29-N: regenerar las candidaturas

`/elecciones/2026/` y el bloque «Elecciones 29-N» de las fichas de provincia
salen de `curated/elecciones_2026.json`, una copia fija del BOE que se
versiona en `main` (como `curated/censo_xv.json`). El render no pide nada a la
red. Si el BOE publica otra corrección de las candidaturas:

1. Añadir su identificador en `elecciones.py` y en `tools/elecciones_2026.py`.
2. `python tools/elecciones_2026.py` (descarga por `txt.php` los cuatro documentos:
   RD 806/2026, candidaturas, corrección y RD 400/2023 para el reparto de 2023,
   respetando el `robots.txt` del BOE) y revisar lo que imprime: correcciones
   aplicadas y avisos. Si una corrección no encaja exactamente, el script
   para con error y no escribe nada.
3. Abrir una PR con el JSON regenerado y los tests al día.

## Timeouts de Pages en el primer despliegue de un SHA

El 10 de noviembre de 2026, varios despliegues fallaron en el paso
`actions/deploy-pages@v4` (timeout por defecto de 10 minutos). La
construcción y la subida del artefacto habían terminado bien. La acción
creaba el despliegue de Pages y se quedaba en `syncing_files` o
`deployment_queued` hasta el timeout; entonces cancelaba el despliegue. El
identificador del despliegue de Pages es el SHA del commit
(`pages_build_version`).

Fallaron, entre otros, el SHA `c7b38243` (varias ejecuciones, incluido un
relanzamiento) y un commit vacío posterior, `2a398ecc`, creado precisamente
para forzar un identificador nuevo. Un artefacto casi idéntico se había
desplegado bien esa misma mañana en unos 5–7 segundos.

Ese síntoma coincide con la incidencia upstream
[actions/deploy-pages#406](https://github.com/actions/deploy-pages/issues/406)
(el despliegue se crea y se queda en `syncing_files` o `deployment_queued`
hasta el timeout). También se revisó
[actions/deploy-pages#383](https://github.com/actions/deploy-pages/issues/383):
el identificador es el `GITHUB_SHA` y se reutiliza en `workflow_dispatch` y
`schedule`; el caso que describe #383 es, sobre todo, que un despliegue
posterior del mismo SHA puede reportar éxito y servir un artefacto antiguo.
En el incidente del 10 de noviembre los runs no llegaron a éxito, y un SHA
nuevo también agotó el tiempo, así que #383 no parece la causa de aquellos
timeouts. #383 sigue siendo la referencia si un render con el mismo SHA no
se sirve o deja un artefacto viejo.

Si vuelve a ocurrir un timeout de `deploy-pages`: no relanzar en bucle. El
sitio sigue sirviendo el último despliegue que sí terminó. Documentar el SHA
y la ejecución, y avisar. No se cambia el timeout de la acción ni se toca el
DNS sin autorización.

## Plan B de Cloudflare Pages

Hay un plan B documentado (10 de noviembre de 2026) por si GitHub Pages deja
de aceptar despliegues: servir el mismo `_site` que ya construye Actions, en
el plan gratuito de Cloudflare, por Direct Upload de Pages
(`wrangler pages deploy`) o por Workers Static Assets, que es lo que
Cloudflare recomienda hoy para proyectos nuevos. No se ha creado ningún
proyecto, ni token, ni secreto, ni se ha tocado el DNS.

El corte de dominio (apuntar `terceracamara.es` a ese origen) solo se hace
cuando lo autorice el mantenedor, después de validar una previsualización
(`*.pages.dev` o `*.workers.dev`): mismos canonical, title y description,
muestra de fichas, `/empleo/`, `/ediciones/`, 404 y barra final. Hay que
replicar el 301 de `www` al apex (ruta y consulta) antes o en el mismo
momento, porque hoy lo emite GitHub Pages. La vuelta atrás es restaurar los
registros que apuntan a GitHub Pages.

Este plan no se activa solo. No se tocan nameservers, correo ni el Worker
de disparador.

## Salud de la edición y falsas alarmas

En modo `diario` (y en archivo `ediciones` o `repintar`), `verificar.py --modo diario`
escribe un informe de salud. **La edición se publica igual**: la salud
informa, no bloquea (`continue-on-error`). Si hay hallazgos graves,
`tools/incidencia_salud.sh` abre o actualiza la incidencia «Salud de la
edición» (etiqueta `salud`). Sin graves, cierra la que estuviera abierta.

El 12 de noviembre de 2026, la incidencia #100 fue una falsa alarma: un
reproceso de archivo no pinta una edición completa y el chequeo abrió graves
que no correspondían. La PR #103 evita que vuelva a pasar, saltándose la
verificación y la incidencia en modos `reprocesar` y `nombramientos`.

La observabilidad de producción (`observabilidad.yml`) mira lo que sirve
https://terceracamara.es/, no lo construido en el runner, y puede abrir
«Edición ausente en producción».

## Rama `datos`

Rama huérfana, solo datos, escrita únicamente por `publicar.yml` de `main`
(modos `diario` y `archivo`) a través de `tools/datos.sh`. No se edita a
mano, no se fusiona con `main` y no se usa como base de una PR. Las pruebas
desde otra rama escriben en `datos-pruebas`.

Contiene:

- `data/AAAA-MM-DD.json`: una edición por día (fuente de verdad del render).
  `data/semanas/AAAA-Snn.json`: resumen congelado de cada semana cerrada.
- `state/`: lo que se acumula entre días. Hoy: `congreso.json`,
  `preguntas_escritas.json`, `preguntas_orales.json`, `respuestas/`,
  `tramitacion.json`, `nombramientos.json`, `provincias.json`,
  `empleo.json`, `redaccion.json`, `ediciones.json`,
  `ediciones_huellas.json`, `sitemap_lastmod.json` y `senado.json` (este
  último sin uso mientras `SENADO_ACTIVO = False`).
- `debug/`: diagnóstico de la última ejecución y, en el pase diario,
  `salud.json`.

`sitemap_lastmod.json` guarda la huella y el `lastmod` de las páginas sin
fecha clara, para el sitemap por secciones. Un render no escribe en
`datos`; esa huella se actualiza en una pasada diaria.

Los domingos, si la historia de `datos` pasa de 300 commits o de 150 MB,
`compactar-datos.yml` la reescribe como un único commit con el mismo árbol
y hace `push --force-with-lease` **solo a esa rama**. Es la única excepción
a la regla de no forzar un push (AGENTS.md). El contenido no cambia; solo
se pierde la historia de `datos`.
