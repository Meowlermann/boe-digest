"""Sitemap por secciones con la fecha real de cada página (tanda 8, punto 1).

/sitemap.xml es un índice de sitemaps (la URL que ya conocen robots.txt y
Search Console no cambia) con un fichero por sección:

  sitemap-normas-AAAA-MM.xml   fichas de norma, por el mes de su BOE
  sitemap-ediciones.xml        /ediciones/, páginas de mes y ediciones
  sitemap-diputados.xml        /diputados/
  sitemap-personas.xml         /personas/
  sitemap-votaciones.xml       /votaciones/
  sitemap-tramitacion.xml      /tramitacion/
  sitemap-otros.xml            el resto (/normas/, temas, plazos…)
  sitemap-prioritario.xml      las páginas clave (tanda E8): portada, /empleo/,
                               /diputados/, el hub /elecciones/2026/ y sus 52
                               páginas, y las 52 fichas /diputados/provincia-*
  sitemap-noticias.xml         formato Google News (news:news): ediciones y
                               normas publicadas en las últimas 48 horas, según
                               el datePublished de su propio NewsArticle; el
                               título es su og:title sin el nombre del sitio

Cada URL va en un solo sitemap (verificar.py lo exige). Si es noticia, va en el
de noticias; si no, si es clave, en el prioritario; si no, en el de su sección.
Una noticia que pasa de las 48 horas vuelve sola al sitemap de su sección.

lastmod nunca es la fecha del pase. Cada generador ya da la fecha real cuando
la tiene (normas: su BOE; ediciones: la fecha de la edición; tramitación: su último
hito…). Las páginas cuyo generador solo sabe decir «hoy» (diputados, índices,
buscador…) pasan por `estabilizar`: se guarda una huella del contenido
principal (sin cabecera, pie, JSON-LD, ?v= ni «hace N días») en
state/sitemap_lastmod.json y se conserva la fecha anterior mientras la huella
no cambie. La primera vez, la fecha es la más reciente que aparece en la propia
página (sus actos, votaciones…), si la hay.

Qué URLs entran no se decide aquí: son exactamente las que ya devolvían los
generadores (solo indexables; las noindex no llegan).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from xml.sax.saxutils import escape

MAX_URLS = 45_000
SECCIONES = ("ediciones", "diputados", "personas", "votaciones", "tramitacion")

# Páginas clave (informe SEO, tanda E8): rutas relativas a la raíz del sitio.
# Las fichas de provincia son lo único que hoy trae clics; el 29-N, el hub y
# las páginas por circunscripción. Qué URL existen no se decide aquí: solo se
# reparten las que ya llegan (indexables y con su lastmod real).
RE_PRIORITARIA = re.compile(
    r"^(?:|empleo/|diputados/|elecciones/2026/|elecciones/2026/[a-z0-9-]+\.html|"
    r"diputados/provincia-[a-z0-9-]+\.html)$")

# Google News: solo artículos de los dos últimos días, como mucho 1.000 por
# fichero. https://developers.google.com/search/docs/crawling-indexing/sitemaps/news-sitemap
NOTICIAS_HORAS = 48
MAX_NOTICIAS = 1000
NOTICIAS_NOMBRE = "La Tercera Cámara"
NOTICIAS_IDIOMA = "es"
NS_NEWS = "http://www.google.com/schemas/sitemap-news/0.9"
# news:title: el og:title de la página (su <title>), sin el nombre del sitio.
# Los titulares editoriales (headline del JSON-LD y H1) van en mayúsculas en
# el propio dato; el og:title es el título oficial del BOE en caja normal. No
# se convierte nada de mayúsculas a minúsculas: si no hay og:title, va el headline.
_RE_OG_TITLE = re.compile(r'<meta\s+property="og:title"\s+content="([^"]*)"', re.I)
_RE_SUFIJO = re.compile(r"\s+[|—–]\s+La Tercera Cámara\s*$")
_RE_JSONLD = re.compile(r"<script\b[^>]*application/ld\+json[^>]*>(.*?)</script>", re.S | re.I)

_RE_FUERA = [
    re.compile(r"<header\b.*?</header>", re.S | re.I),
    re.compile(r"<footer\b.*?</footer>", re.S | re.I),
    re.compile(r"<script\b[^>]*application/ld\+json[^>]*>.*?</script>", re.S | re.I),
    re.compile(r"<span class=\"em-hace\">.*?</span>", re.S),
    re.compile(r"\(hace [^)]{1,20}\)"),
    re.compile(r"\?v=[0-9a-f]{6,}"),
    # «Actualizado el jueves, 12 de noviembre de 2026»: la fecha del pase
    # aparece en el cuerpo de algunos índices; sola no es un cambio real.
    re.compile(r"(lunes|martes|miércoles|jueves|viernes|sábado|domingo), \d{1,2} de [a-z]+ de \d{4}"),
]
_RE_ISO = re.compile(r'datetime="(\d{4}-\d{2}-\d{2})')
_RE_DMY = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre")
_RE_LARGA = re.compile(r"\b(\d{1,2}) de (" + "|".join(_MESES) + r") de (\d{4})\b")


def huella(html: str) -> str:
    """Hash del contenido principal, estable entre pases si nada cambia."""
    for r in _RE_FUERA:
        html = r.sub("", html)
    return hashlib.sha256(html.encode("utf-8")).hexdigest()[:20]


def fecha_en_pagina(html: str, hoy: str) -> str:
    """Fecha más reciente (no futura) que la página muestra, o ''."""
    for r in _RE_FUERA[:3]:
        html = r.sub("", html)
    fechas = set(_RE_ISO.findall(html))
    fechas.update(f"{a}-{m}-{d}" for d, m, a in _RE_DMY.findall(html))
    fechas.update(f"{a}-{_MESES.index(m) + 1:02d}-{int(d):02d}" for d, m, a in _RE_LARGA.findall(html))
    validas = []
    for f in fechas:
        try:
            dt.date.fromisoformat(f)
        except ValueError:
            continue
        if "2000-01-01" <= f <= hoy:
            validas.append(f)
    return max(validas, default="")


def estabilizar(entradas: list[dict], hoy: str, leer, estado: dict) -> tuple[list[dict], dict]:
    """Cambia lastmod == hoy por la fecha del último cambio real del contenido.

    `leer(url)` devuelve el HTML publicado o None. `estado` es
    {url: {"h": huella, "f": fecha}} del pase anterior. Devuelve las entradas
    y el estado nuevo (solo de las URLs que pasan por aquí)."""
    salida, nuevo = [], {}
    for e in entradas:
        if e.get("lastmod") != hoy:
            salida.append(e)
            continue
        html = leer(e["url"])
        if html is None:
            salida.append(e)
            continue
        h = huella(html)
        previo = estado.get(e["url"]) or {}
        if previo.get("h") == h and previo.get("f"):
            fecha = previo["f"]
        elif previo.get("h"):
            fecha = hoy                       # el contenido ha cambiado hoy
        else:
            fecha = fecha_en_pagina(html, hoy) or hoy
        nuevo[e["url"]] = {"h": h, "f": fecha}
        salida.append({**e, "lastmod": fecha})
    return salida, nuevo


def seccion(url: str, lastmod: str, site_url: str) -> str:
    ruta = url[len(site_url):] if url.startswith(site_url) else url
    if url.startswith(site_url) and RE_PRIORITARIA.match(ruta):
        return "prioritario"
    primero = ruta.split("/", 1)[0] if "/" in ruta else ""
    if primero == "normas" and ruta not in ("normas/", "normas/index.html"):
        return "normas-" + (lastmod[:7] if re.fullmatch(r"\d{4}-\d{2}.*", lastmod or "") else "sin-fecha")
    return primero if primero in SECCIONES else "otros"


def _urlset(filas: list[dict]) -> str:
    cuerpo = "\n".join(
        f"  <url>\n    <loc>{escape(f['url'])}</loc>\n    <lastmod>{f['lastmod']}</lastmod>\n  </url>"
        for f in filas)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + cuerpo + "\n</urlset>\n")


def articulo_propio(html: str, url: str) -> dict | None:
    """{"titulo", "fecha", "oficial"} del NewsArticle cuya url es la de la
    propia página (una edición también lleva los de sus normas), o None. La
    fecha es su datePublished tal cual (ISO 8601 con zona), sin recalcular
    nada. «oficial» es el título oficial completo de la norma (about.name del
    Legislation, tal cual viene del BOE) o vacío si la página no es una norma."""
    import json
    for bloque in _RE_JSONLD.findall(html or ""):
        try:
            datos = json.loads(bloque)
        except ValueError:
            continue
        pila = datos if isinstance(datos, list) else [datos]
        while pila:
            x = pila.pop(0)
            if isinstance(x, list):
                pila.extend(x)
                continue
            if not isinstance(x, dict):
                continue
            pila.extend(x.get("@graph", []) if isinstance(x.get("@graph"), list) else [])
            if x.get("@type") == "NewsArticle" and x.get("url") == url \
                    and x.get("headline") and x.get("datePublished"):
                ab = x.get("about") if isinstance(x.get("about"), dict) else {}
                oficial = (str(ab.get("name") or "").strip()
                           if ab.get("@type") == "Legislation" else "")
                return {"titulo": str(x["headline"]), "fecha": str(x["datePublished"]),
                        "oficial": oficial}
    return None


def titulo_noticia(html: str, headline: str, oficial: str = "") -> str:
    """news:title: el título oficial completo de la norma, tal cual y sin
    recortar (el og:title de las normas va recortado para el <title>, que no se
    toca por la prueba de #75, y a veces queda a media frase). Si la página no
    trae título oficial (ediciones), el og:title sin « | La Tercera Cámara»; y
    si tampoco, el headline tal cual. No se convierte ninguna mayúscula."""
    import html as h
    if oficial:
        return " ".join(oficial.split())
    m = _RE_OG_TITLE.search(html or "")
    t = _RE_SUFIJO.sub("", h.unescape(m.group(1))).strip() if m else ""
    return t or headline


def noticias(candidatas: list[str], ahora: dt.datetime, leer) -> list[dict]:
    """Las URL publicadas en las últimas NOTICIAS_HORAS respecto a `ahora`
    (aware), según el datePublished de su NewsArticle. Nada futuro ni sin
    fecha. Devuelve [{"url", "titulo", "fecha"}], de la más reciente a la más
    antigua, como mucho MAX_NOTICIAS."""
    desde = ahora - dt.timedelta(hours=NOTICIAS_HORAS)
    out = []
    for url in dict.fromkeys(candidatas):
        html = leer(url)
        a = articulo_propio(html, url)
        if not a:
            continue
        a = {"titulo": titulo_noticia(html, a["titulo"], a.get("oficial", "")), "fecha": a["fecha"]}
        try:
            f = dt.datetime.fromisoformat(a["fecha"])
        except ValueError:
            continue
        if f.tzinfo is None or not (desde <= f <= ahora):
            continue
        out.append({"url": url, **a, "_t": f})
    out.sort(key=lambda x: (x["_t"], x["url"]), reverse=True)
    return [{k: v for k, v in x.items() if k != "_t"} for x in out[:MAX_NOTICIAS]]


def _newsset(items: list[dict]) -> str:
    cuerpo = "\n".join(
        f"  <url>\n    <loc>{escape(n['url'])}</loc>\n    <news:news>\n"
        f"      <news:publication>\n        <news:name>{escape(NOTICIAS_NOMBRE)}</news:name>\n"
        f"        <news:language>{NOTICIAS_IDIOMA}</news:language>\n      </news:publication>\n"
        f"      <news:publication_date>{escape(n['fecha'])}</news:publication_date>\n"
        f"      <news:title>{escape(n['titulo'])}</news:title>\n    </news:news>\n  </url>"
        for n in items)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            f'xmlns:news="{NS_NEWS}">\n' + (cuerpo + "\n" if cuerpo else "") + "</urlset>\n")


def generar(entradas: list[dict], site_url: str, noticias: list[dict] | None = None) -> dict[str, str]:
    """{nombre de fichero: XML}. Incluye sitemap.xml (el índice). Con
    `noticias` (aunque esté vacía) añade sitemap-noticias.xml y esas URL salen
    de su sitemap de sección."""
    son_noticia = {n["url"] for n in noticias or []}
    vistas, grupos = set(son_noticia), {}
    for e in entradas:
        if e["url"] in vistas:
            continue
        vistas.add(e["url"])
        grupos.setdefault(seccion(e["url"], e["lastmod"], site_url), []).append(e)
    ficheros, indice = {}, []
    for nombre in sorted(grupos):
        filas = sorted(grupos[nombre], key=lambda x: (x["lastmod"], x["url"]), reverse=True)
        trozos = [filas[i:i + MAX_URLS] for i in range(0, len(filas), MAX_URLS)]
        for n, trozo in enumerate(trozos, 1):
            fichero = f"sitemap-{nombre}.xml" if len(trozos) == 1 else f"sitemap-{nombre}-{n}.xml"
            ficheros[fichero] = _urlset(trozo)
            indice.append(f"  <sitemap>\n    <loc>{site_url}{fichero}</loc>\n"
                          f"    <lastmod>{max(f['lastmod'] for f in trozo)}</lastmod>\n  </sitemap>")
    if noticias is not None:
        ficheros["sitemap-noticias.xml"] = _newsset(noticias)
        # lastmod del índice: la publicación más reciente; sin noticias, sin lastmod.
        ult = max((n["fecha"][:10] for n in noticias), default="")
        indice.append(f"  <sitemap>\n    <loc>{site_url}sitemap-noticias.xml</loc>\n"
                      + (f"    <lastmod>{ult}</lastmod>\n" if ult else "") + "  </sitemap>")
    ficheros["sitemap.xml"] = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                               '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                               + "\n".join(indice) + "\n</sitemapindex>\n")
    return ficheros
