"""Páginas de texto fijo: /seguir/ (canales RSS), /privacidad.html y
/aviso-legal.html.

Son texto redactado a mano, sin datos que cambien. Siguen el contrato de los
módulos de páginas (ARQUITECTURA.md §4): reciben `h` y devuelven las URL para
el sitemap. La fecha de modificación es la de la última revisión del texto
(REVISION), no la del pase: así no cambian ni un byte si nadie las toca.

Datos del titular: todavía no hay actividad económica y no se publican. En su
lugar va el marcador literal <TITULAR_PENDIENTE> (en el HTML, escapado para
que se vea). tools/verificar.py lo señala como AVISO, no como grave: es una
decisión del mantenedor, no un fallo del código. Antes de cualquier actividad
económica (suscripción de pago o publicidad), la LSSI (art. 10) exige el
nombre o denominación, el NIF y los datos de contacto del titular en el aviso
legal: entonces se sustituye el marcador y el aviso desaparece.

Servicios de terceros citados en /seguir/: comprobados en octubre de 2026 en
sus propias webs; solo se citan los que tienen uso gratuito.
"""

from __future__ import annotations

REVISION = "2026-10-08"
CONTACTO = "datos@terceracamara.es"
TITULAR = "&lt;TITULAR_PENDIENTE&gt;"


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
<h2 class="rotulo">Responsable</h2>
<p>Titular del sitio: {TITULAR}. Contacto para cualquier cuestión sobre datos personales:
<a href="mailto:{CONTACTO}">{CONTACTO}</a>.</p>

<h2 class="rotulo">Qué medimos de tu visita</h2>
<p>Contamos visitas con <b>Cloudflare Web Analytics</b>. No usa cookies ni guarda nada en tu
navegador (ni <i>localStorage</i>, ni <i>sessionStorage</i>, ni identificadores), no crea un
perfil tuyo y no te sigue entre webs. Por eso no ves ningún aviso de cookies: no hay ninguna
que aceptar. Lo comprobamos en la web publicada al instalarlo.</p>
<p>Cada vez que abres una página, un pequeño script envía a Cloudflare la dirección de la
página, la de procedencia (si llegas desde otra web), el tipo de navegador, sistema operativo y
dispositivo, el país (deducido de la conexión) y medidas de velocidad de carga. Con eso vemos
cifras agregadas: cuántas visitas tiene cada página y de dónde llegan. Cloudflare, Inc. actúa
como encargado del tratamiento; su política está en
<a href="https://www.cloudflare.com/privacypolicy/" rel="noopener" target="_blank">cloudflare.com/privacypolicy</a>.
Base jurídica: el interés legítimo en saber qué páginas se leen para mejorarlas (art. 6.1.f
RGPD), con una medición diseñada para no identificar a nadie.</p>

<h2 class="rotulo">Otros servicios que intervienen al cargar la página</h2>
<ul>
<li><b>Alojamiento</b>: la web la sirve GitHub Pages (GitHub, Inc.). Como cualquier servidor,
recibe tu dirección IP para entregarte la página y puede conservarla en registros técnicos y de
seguridad. <a href="https://docs.github.com/es/site-policy/privacy-policies/github-general-privacy-statement" rel="noopener" target="_blank">Declaración de privacidad de GitHub</a>.</li>
<li><b>Tipografías</b>: las fuentes de letra se cargan desde Google Fonts, que recibe tu IP al
descargarlas. <a href="https://policies.google.com/privacy?hl=es" rel="noopener" target="_blank">Política de privacidad de Google</a>.</li>
</ul>
<p>Esta web no tiene formularios que envíen datos, cuentas de usuario ni comentarios, y no usa publicidad.</p>

<h2 class="rotulo">Si te suscribes al boletín (cuando exista)</h2>
<p>Estamos preparando un boletín semanal por correo. Cuando se abra la suscripción, se tratarán
estos datos y solo estos:</p>
<ul>
<li><b>Tu correo electrónico</b>, para enviarte el boletín.</li>
<li><b>La prueba de tu consentimiento</b>: fecha y hora de la suscripción y de la confirmación,
y la dirección IP desde la que confirmaste. La suscripción tendrá <b>doble confirmación</b>: no
recibirás nada hasta pulsar el enlace del correo de confirmación.</li>
<li><b>Estadísticas de envío</b> que genere el proveedor (entregas, rebotes, bajas).</li>
</ul>
<p>Base jurídica: tu consentimiento (art. 6.1.a RGPD), que puedes retirar en cualquier momento
con el enlace de baja que llevará cada envío. Los datos se conservarán mientras sigas suscrito y
se borrarán al darte de baja, salvo la prueba del consentimiento y de la baja durante el plazo
en que se pudieran exigir responsabilidades. El <b>encargado del tratamiento</b> será el
proveedor de envío de correo, que se identificará aquí, con su ubicación y su política, antes de
abrir la suscripción. Nunca se venderán ni cederán las direcciones a nadie.</p>

<h2 class="rotulo">Datos de cargos públicos</h2>
<p>La web publica nombres y actividad de diputados, miembros del Gobierno y personas nombradas o
cesadas en el BOE, tal como aparecen en las publicaciones oficiales del Congreso y del BOE, para
informar sobre la actividad pública. Si apareces en ellas y quieres ejercer tus derechos, escribe
a la dirección de contacto.</p>

<h2 class="rotulo">Tus derechos</h2>
<p>Puedes pedir acceso a tus datos, su rectificación o supresión, la limitación u oposición a su
tratamiento y su portabilidad escribiendo a <a href="mailto:{CONTACTO}">{CONTACTO}</a>, indicando
qué derecho ejerces. Contestaremos en el plazo de un mes. Si no quedas conforme, puedes reclamar
ante la Agencia Española de Protección de Datos
(<a href="https://www.aepd.es/" rel="noopener" target="_blank">aepd.es</a>).</p>
"""


AVISO_LEGAL = f"""
<h2 class="rotulo">Titular</h2>
<p>Titular del sitio terceracamara.es: {TITULAR} (nombre y NIF: {TITULAR}).
Contacto: <a href="mailto:{CONTACTO}">{CONTACTO}</a>.</p>

<h2 class="rotulo">Qué es este proyecto</h2>
<p>La Tercera Cámara es un proyecto ciudadano e independiente que resume y ordena lo que
publican el Boletín Oficial del Estado y el Congreso de los Diputados. No tiene actividad
económica: no cobra suscripciones, no vende nada y no lleva publicidad. No está vinculado a
ninguna administración, partido ni grupo parlamentario.</p>

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
<li><b>Boletín Oficial del Estado</b>: datos abiertos y textos de boe.es, reutilizados conforme
a la Ley 37/2007, sobre reutilización de la información del sector público, y a las condiciones
de reutilización del propio BOE: se cita la fuente, no se altera el contenido de lo que se
presenta como oficial y se indica la fecha de la información.</li>
<li><b>Congreso de los Diputados</b>: datos abiertos, buscador de iniciativas, Diario de
Sesiones y Boletín Oficial de las Cortes Generales de congreso.es, reutilizados con las mismas
condiciones: cita de la fuente, sin desnaturalizar el sentido de la información y con la fecha
de la última actualización.</li>
<li><b>Senado</b>: no ofrece por ahora acceso automatizado a sus datos y no se recoge.</li>
</ul>
<p>Ninguna de estas instituciones patrocina ni respalda este proyecto.</p>

<h2 class="rotulo">Responsabilidad y enlaces</h2>
<p>Ponemos cuidado en que la información sea fiel a la fuente y se corrige en cuanto se detecta
un error, pero no se garantiza que esté libre de ellos ni actualizada al minuto. Los enlaces a
webs de terceros se ofrecen para consultar la fuente o un servicio útil; no somos responsables
de su contenido.</p>

<h2 class="rotulo">Privacidad</h2>
<p>Qué se mide y qué datos se tratan está en la <a href="/privacidad.html">política de privacidad</a>.</p>
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
           "Qué mide La Tercera Cámara (Cloudflare Web Analytics, sin cookies), qué datos se "
           "tratarán en el boletín y cómo ejercer tus derechos.",
           "Información legal", "Política de privacidad",
           "Sin cookies, sin perfiles y sin publicidad. Esto es lo que se mide y lo que se tratará.",
           PRIVACIDAD, "WebPage")
    pagina(raiz, "aviso-legal.html", "aviso-legal.html", "Aviso legal",
           "Naturaleza del proyecto La Tercera Cámara, fuentes oficiales y condiciones de "
           "reutilización. No es una fuente oficial.",
           "Información legal", "Aviso legal",
           "Quién está detrás, de dónde salen los datos y qué valor tienen.",
           AVISO_LEGAL, "WebPage")
    return salidas
