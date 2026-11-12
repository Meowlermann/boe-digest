"""Sitemap por secciones con la fecha real de cada página (tanda 8, punto 1).

/sitemap.xml es un índice de sitemaps (la URL que ya conocen robots.txt y
Search Console no cambia) con un fichero por sección:

  sitemap-normas-AAAA-MM.xml   fichas de norma, por el mes de su BOE
  sitemap-ediciones.xml        /ediciones/, páginas de mes y ediciones
  sitemap-diputados.xml        /diputados/
  sitemap-personas.xml         /personas/
  sitemap-votaciones.xml       /votaciones/
  sitemap-tramitacion.xml      /tramitacion/
  sitemap-otros.xml            el resto (portada, /normas/, temas, plazos…)

lastmod nunca es la fecha del pase. Cada generador ya da la fecha real cuando
la tiene (normas: su BOE; ediciones: su manifiesto; tramitación: su último
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


def generar(entradas: list[dict], site_url: str) -> dict[str, str]:
    """{nombre de fichero: XML}. Incluye sitemap.xml (el índice)."""
    vistas, grupos = set(), {}
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
    ficheros["sitemap.xml"] = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                               '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                               + "\n".join(indice) + "\n</sitemapindex>\n")
    return ficheros
