"""Páginas de texto fijo: /seguir/ (canales RSS), /privacidad.html y
/aviso-legal.html.

Son texto redactado a mano, sin datos que cambien. Siguen el contrato de los
módulos de páginas (ARQUITECTURA.md §4): reciben `h` y devuelven las URL para
el sitemap. La fecha de modificación es la de la última revisión del texto
(REVISION), no la del pase: así no cambian ni un byte si nadie las toca.

Titular (TC-002, versión mínima, octubre de 2026): no se publican nombre, NIF
ni domicilio. Las páginas legales describen el proyecto de forma neutra, con un
único contacto (contacto@terceracamara.es), y declaran que se actualizarán
antes de abrir un boletín o cualquier cobro. tools/verificar.py falla (grave)
si el HTML publicado contiene una dirección @gmail.com o el nombre del
mantenedor. La descripción de Cloudflare Web Analytics se ciñe a lo que dice
su documentación oficial (developers.cloudflare.com/web-analytics/about/ y
/web-analytics/data-metrics/data-origin-and-collection/, revisadas el
27-10-2026); no se afirma nada que no esté ahí.

Servicios de terceros citados en /seguir/: comprobados en octubre de 2026 en
sus propias webs; solo se citan los que tienen uso gratuito.
"""

from __future__ import annotations

REVISION = "2026-10-27"
CONTACTO = "contacto@terceracamara.es"


SEGUIR = f"""
<h2 class="rotulo">Qué es RSS</h2>
<p>RSS (y su primo Atom, que es el formato que usamos) es una forma abierta y gratuita de
seguir una web sin depender de una red social ni de un algoritmo. Cada página que se puede
seguir publica al lado un fichero, el <b>canal</b>, con sus últimas novedades. Un programa
lector de canales lo consulta por ti cada cierto tiempo y te enseña lo nuevo. No hace falta
darnos el correo ni crear una cuenta en esta web: nosotros no sabemos quién sigue qué.</p>

<h2 class="rotulo">Qué se puede seguir aquí</h2>
<ul class="indice">
<li><a href="/diputados/">Cada diputado</a><span class="ref">sus preguntas al Gobierno, sus intervenciones y las votaciones en las que se apartó de su grupo</span></li>
<li><a href="/provincias/">Cada provincia</a><span class="ref">lo que el BOE publica nombrándola y las preguntas escritas que la citan</span></li>
<li><a href="/temas/">Cada materia</a><span class="ref">lo que publica el BOE en subvenciones, fiscal, laboral y el resto de materias</span></li>
<li><a href="/tramitacion/">Cada iniciativa en tramitación</a><span class="ref">sus cambios de estado y las ampliaciones del plazo de enmiendas</span></li>
<li><a href="/preguntas/#ministerios">Cada ministerio</a><span class="ref">las preguntas orales de la sesión de control que contesta</span></li>
<li><a href="/feed.xml">La edición diaria</a><span class="ref">una entrada por edición</span></li>
</ul>
<p>En cada una de esas páginas verás el enlace <b>Seguir con RSS</b> debajo de la entradilla.
Cada canal guarda las 50 novedades más recientes, con la fecha real del hecho (la de su
publicación oficial, la de la sesión o la del registro), no la del día en que lo recogimos.</p>

<h2 class="rotulo">Cómo usarlo, en tres pasos</h2>
<ol>
<li>Instala o abre un lector de canales (abajo hay varios gratuitos).</li>
<li>En la página que quieras seguir, pulsa <b>Seguir con RSS</b> con el botón derecho y copia
la dirección del enlace. También vale pegar en el lector la dirección de la página: casi todos
encuentran el canal solos.</li>
<li>Pega esa dirección en el lector, en la opción «Añadir», «Suscribirse» o «+».</li>
</ol>

<h2 class="rotulo">Lectores recomendados</h2>
<p>Todos tienen uso gratuito. Algunos ofrecen además planes de pago que no hacen falta para
seguir esta web.</p>
<ul class="indice">
<li><a href="https://netnewswire.com/" rel="noopener" target="_blank">NetNewsWire</a><span class="ref">Mac, iPhone y iPad · gratuito y de código abierto</span></li>
<li><a href="https://github.com/spacecowboy/Feeder" rel="noopener" target="_blank">Feeder</a><span class="ref">Android · gratuito y de código abierto, también en F-Droid</span></li>
<li><a href="https://www.thunderbird.net/" rel="noopener" target="_blank">Thunderbird</a><span class="ref">Windows, Mac y Linux · el cliente de correo de Mozilla lee canales: Archivo › Nuevo › Cuenta de canales</span></li>
<li><a href="https://feedly.com/" rel="noopener" target="_blank">Feedly</a> e <a href="https://www.inoreader.com/" rel="noopener" target="_blank">Inoreader</a><span class="ref">en el navegador y en el móvil · con plan gratuito</span></li>
</ul>

<h2 class="rotulo">Recibirlo por correo electrónico</h2>
<p>Si prefieres el correo, hay servicios de terceros que convierten cualquier canal en avisos
por email. No tienen relación con esta web: les das tu dirección a ellos, no a nosotros, así
que lee su política de privacidad antes. Con uso gratuito:</p>
<ul class="indice">
<li><a href="https://blogtrottr.com/" rel="noopener" target="_blank">Blogtrottr</a><span class="ref">pegas la dirección del canal y tu correo; puedes elegir recibirlo al momento o en un resumen diario. El plan gratuito incluye publicidad en los correos</span></li>
<li><a href="https://follow.it/" rel="noopener" target="_blank">follow.it</a><span class="ref">permite seguir una web o un canal por correo con una cuenta gratuita</span></li>
<li><span>Tu propio lector</span><span class="ref">Thunderbird, arriba, deja los canales junto a tu correo sin intermediarios</span></li>
</ul>
<p>Comprobado en octubre de 2026. Las condiciones de servicios ajenos pueden cambiar.</p>

<h2 class="rotulo">Y algún día, nuestro propio correo</h2>
<p>Estamos preparando un boletín semanal propio. Cuando exista, se anunciará aquí y en la
portada, siempre con suscripción voluntaria y doble confirmación. Mientras tanto, el resumen de
la semana se puede leer en la web.</p>
"""


PRIVACIDAD = f"""
<h2 class="rotulo">Quién responde</h2>
<p>La Tercera Cámara es un proyecto editorial independiente de fiscalización ciudadana basado
en datos públicos del BOE y de las Cortes Generales. Contacto único para cualquier cuestión
sobre datos personales: <a href="mailto:{CONTACTO}">{CONTACTO}</a>.</p>

<h2 class="rotulo">Datos que recoge esta web</h2>
<p>Esta web no recoge datos personales de quien la visita: no tiene formularios, cuentas de
usuario, comentarios, boletín por correo, publicidad ni cobros.</p>

<h2 class="rotulo">Medición de visitas</h2>
<p>Contamos visitas con <b>Cloudflare Web Analytics</b>. Según su documentación oficial, es una
analítica «privacy-first» que no recoge ni usa datos personales de los visitantes, recoge la
cantidad mínima de información (métricas de tiempos de carga) y Cloudflare no sigue a usuarios
individuales entre las webs de sus clientes. Funciona con un pequeño script que se carga desde
<i>static.cloudflareinsights.com</i> y usa la Performance API del navegador para medir páginas
vistas y rendimiento de carga. Con eso vemos cifras agregadas. Documentación:
<a href="https://developers.cloudflare.com/web-analytics/about/" rel="noopener" target="_blank">About</a> y
<a href="https://developers.cloudflare.com/web-analytics/data-metrics/data-origin-and-collection/" rel="noopener" target="_blank">Data origin and collection</a>.
Política de privacidad de Cloudflare:
<a href="https://www.cloudflare.com/privacypolicy/" rel="noopener" target="_blank">cloudflare.com/privacypolicy</a>.</p>

<h2 class="rotulo">Otros servicios que intervienen al cargar la página</h2>
<ul>
<li><b>Alojamiento y entrega</b>: la web la aloja GitHub Pages (GitHub, Inc.) y se entrega a
través de la red de Cloudflare. Como cualquier servidor, reciben tu dirección IP para
entregarte la página. <a href="https://docs.github.com/es/site-policy/privacy-policies/github-general-privacy-statement" rel="noopener" target="_blank">Declaración de privacidad de GitHub</a>.</li>
<li><b>Tipografías</b>: las fuentes de letra se cargan desde Google Fonts, que recibe tu IP al
descargarlas. <a href="https://policies.google.com/privacy?hl=es" rel="noopener" target="_blank">Política de privacidad de Google</a>.</li>
</ul>

<h2 class="rotulo">Datos de cargos públicos</h2>
<p>La web publica nombres y actividad de diputados, miembros del Gobierno y personas
nombradas o cesadas en el BOE, tal como aparecen en las publicaciones oficiales del BOE y de las
Cortes, para informar sobre la actividad pública. El criterio es el mismo para todos los grupos
y partidos.</p>

<h2 class="rotulo">Correcciones y derechos</h2>
<p>Para pedir una corrección o ejercer los derechos que te reconozca la normativa de protección
de datos (por ejemplo, acceso, rectificación o supresión), escribe a
<a href="mailto:{CONTACTO}">{CONTACTO}</a> indicando qué pides. También puedes dirigirte a la
Agencia Española de Protección de Datos (<a href="https://www.aepd.es/" rel="noopener" target="_blank">aepd.es</a>).</p>

<h2 class="rotulo">Cambios en este texto</h2>
<p>Este texto describe la web tal como funciona hoy. Se actualizará antes de abrir un boletín
por correo o cualquier forma de cobro, y antes de cualquier otro cambio en los datos que se
tratan.</p>
"""


AVISO_LEGAL = f"""
<h2 class="rotulo">Quién está detrás</h2>
<p>terceracamara.es es un proyecto editorial independiente de fiscalización ciudadana basado en
datos públicos del BOE y de las Cortes Generales. Contacto único:
<a href="mailto:{CONTACTO}">{CONTACTO}</a>.</p>

<h2 class="rotulo">Qué es este proyecto</h2>
<p>La Tercera Cámara resume y ordena lo que publican el Boletín Oficial del Estado y el Congreso
de los Diputados, con el mismo criterio para todo el arco político. No tiene actividad
económica: no cobra suscripciones, no vende nada, no lleva publicidad y no tiene boletín por
correo. No está vinculado a ninguna administración, partido ni grupo parlamentario.</p>
<h2 class="rotulo">No es una fuente oficial</h2>
<p>Lo que publicamos es un resumen. <b>Solo tiene validez oficial el texto publicado por cada
institución</b>: el BOE en <a href="https://www.boe.es/" rel="noopener" target="_blank">boe.es</a>
y el Congreso en <a href="https://www.congreso.es/" rel="noopener" target="_blank">congreso.es</a>.
Cada pieza enlaza al documento oficial del que sale. Lo que va entre comillas es literal de la
fuente; el resto son plantillas sobre datos oficiales y, en la edición diaria, titulares y
entradillas redactados con ayuda de IA y verificados de forma automática, que van marcados como
editoriales. Puede haber errores: si encuentras uno, escríbenos. Nada de lo publicado es
asesoramiento jurídico, fiscal ni de ningún otro tipo.</p>

<h2 class="rotulo">Fuentes y condiciones de reutilización</h2>
<ul>
<li><b>Boletín Oficial del Estado</b>: documentos de la sede electrónica de la Agencia Estatal
Boletín Oficial del Estado, reutilizados conforme a sus
<a href="https://www.boe.es/informacion/aviso_legal/index.php" rel="noopener" target="_blank">condiciones de reutilización</a>
(licencia tipo aprobada por Resolución de la Agencia de 27 de junio de 2024): se cita la fuente con
enlace a <a href="https://www.boe.es" rel="noopener" target="_blank">www.boe.es</a> («Basado en datos de la
Agencia Estatal Boletín Oficial del Estado»; «Fuente de los datos: Agencia Estatal Boletín Oficial del
Estado» en las citas literales), no se desnaturaliza el sentido de la información, se indica la fecha de
publicación de cada documento y lo que es elaboración propia se distingue de lo literal, que va entre
comillas. Solo tienen carácter oficial y auténtico los textos publicados en la edición electrónica del
BOE; los textos de legislación consolidada que se citen tienen carácter meramente informativo. No se
insertan páginas del BOE dentro de esta web.</li>
<li><b>Congreso de los Diputados</b>: datos abiertos, buscador de iniciativas, Diario de
Sesiones y Boletín Oficial de las Cortes Generales de congreso.es, reutilizados con las mismas
condiciones: cita de la fuente, sin desnaturalizar el sentido de la información y con la fecha
de la última actualización.</li>
<li><b>Senado</b>: no ofrece por ahora acceso automatizado a sus datos y no se recoge.</li>
</ul>
<p>Este es un medio no oficial, sin relación con la Agencia Estatal Boletín Oficial del Estado ni con
las Cortes Generales. Ninguna de estas instituciones participa en este proyecto, lo patrocina ni lo respalda.</p>

<h2 class="rotulo">Responsabilidad y enlaces</h2>
<p>Ponemos cuidado en que la información sea fiel a la fuente y se corrige en cuanto se detecta
un error, pero no se garantiza que esté libre de ellos ni actualizada al minuto. Los enlaces a
webs de terceros se ofrecen para consultar la fuente o un servicio útil; no somos responsables
de su contenido.</p>

<h2 class="rotulo">Correcciones</h2>
<p>Si encuentras un error o quieres pedir una rectificación, escribe a
<a href="mailto:{CONTACTO}">{CONTACTO}</a>.</p>

<h2 class="rotulo">Privacidad</h2>
<p>Qué se mide y qué datos se tratan está en la <a href="/privacidad.html">política de privacidad</a>.</p>

<h2 class="rotulo">Cambios en este aviso</h2>
<p>Este aviso se actualizará antes de abrir un boletín por correo o cualquier forma de cobro.</p>
"""


def generar_paginas(h: dict) -> list:
    """/seguir/index.html, /privacidad.html y /aviso-legal.html."""
    esc, attr = h["esc_html"], h["esc_attr"]
    site, raiz, plantilla = h["site_url"], h["raiz"], h["plantilla"]
    fecha = h["fmt_date_es"](REVISION)
    salidas = []

    def pagina(carpeta, nombre, ruta_url, titulo, desc, kicker, h1, entradilla, cuerpo, tipo):
        url = site + ruta_url
        h["pagina_suelta"](plantilla, carpeta, nombre, {
            "TITLE": esc(f"{titulo} | La Tercera Cámara"),
            "META_DESC": attr(desc),
            "CANONICAL": url,
            "JSONLD": h["jsonld_script"]([{"@type": tipo, "url": url, "name": titulo,
                                           "inLanguage": "es-ES", "dateModified": REVISION}]),
            "EDITION_DATE": esc(f"Revisado el {fecha}"),
            "MIGA": f'<a href="/">Portada</a> › <span aria-current="page">{esc(h1)}</span>',
            "KICKER": esc(kicker),
            "HEADLINE": esc(h1),
            "STANDFIRST": esc(entradilla),
            "FICHA": "",
            "CUERPO": cuerpo,
            "FUENTE": f'Contacto: <a class="srclink" href="mailto:{CONTACTO}">{CONTACTO}</a>.',
            "RELACIONADAS": "", "RELACIONADAS_HIDDEN": "hidden",
        })
        salidas.append({"url": url, "lastmod": REVISION})

    pagina(raiz / "seguir", "index.html", "seguir/", "Seguir La Tercera Cámara con RSS",
           "Cómo seguir a cada diputado, provincia, materia, iniciativa o ministerio con RSS, "
           "qué lectores usar y cómo recibir los avisos por correo gratis.",
           "Alertas gratuitas", "Síguelo con RSS",
           "Sin cuentas, sin correo y sin algoritmo: elige qué seguir y tu lector te avisa.",
           SEGUIR, "WebPage")
    pagina(raiz, "privacidad.html", "privacidad.html", "Política de privacidad",
           "Qué mide La Tercera Cámara (Cloudflare Web Analytics), qué servicios intervienen "
           "y cómo pedir correcciones o ejercer tus derechos.",
           "Información legal", "Política de privacidad",
           "Esta web no recoge datos personales. Esto es lo que se mide y quién interviene.",
           PRIVACIDAD, "WebPage")
    pagina(raiz, "aviso-legal.html", "aviso-legal.html", "Aviso legal",
           "Naturaleza del proyecto La Tercera Cámara, fuentes oficiales y condiciones de "
           "reutilización. No es una fuente oficial.",
           "Información legal", "Aviso legal",
           "Quién está detrás, de dónde salen los datos y qué valor tienen.",
           AVISO_LEGAL, "WebPage")
    return salidas
