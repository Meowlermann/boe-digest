"""Página /correcciones/ y aviso de corrección en cada pieza corregida (TC-017).

El registro vive en el repositorio, en editorial/correcciones.json, y se edita
a mano con una PR (main es código y texto editorial; no lo escribe el bot).
Cada entrada genera un apartado con ancla en /correcciones/#c-<id> y, en la
página corregida, un aviso bajo el titular que enlaza a ese apartado. Nada de
LLM ni de red: el texto sale tal cual del registro.

Texto neutro, sin nombre de persona: el único contacto es
contacto@terceracamara.es.
"""

from __future__ import annotations

import json
import pathlib
import re

REGISTRO = pathlib.Path(__file__).resolve().parent / "editorial" / "correcciones.json"
CONTACTO = "contacto@terceracamara.es"
REVISION = "2026-10-27"
SITIO = "https://terceracamara.es"
RE_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
CAMPOS = ("id", "fecha", "url", "pieza", "dice", "debe_decir", "motivo")


def cargar(registro: pathlib.Path | None = None) -> list[dict]:
    """Entradas válidas del registro, de la más reciente a la más antigua.

    Una entrada mal formada lanza ValueError: es un fichero hecho a mano y el
    CI tiene que pararlo antes de publicar."""
    registro = registro or REGISTRO
    if not registro.exists():
        return []
    datos = json.loads(registro.read_text(encoding="utf-8"))
    entradas = datos.get("correcciones", [])
    vistos = set()
    for e in entradas:
        faltan = [c for c in CAMPOS if not str(e.get(c, "")).strip()]
        if faltan:
            raise ValueError(f"corrección {e.get('id', '?')}: faltan {', '.join(faltan)}")
        if not RE_ID.match(e["id"]) or e["id"] in vistos:
            raise ValueError(f"corrección {e['id']}: id inválido o repetido")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", e["fecha"]) or not e["url"].startswith("/"):
            raise ValueError(f"corrección {e['id']}: fecha o url inválidas")
        vistos.add(e["id"])
    return sorted(entradas, key=lambda e: (e["fecha"], e["id"]), reverse=True)


def ruta_de_canonical(canonical: str) -> str:
    ruta = canonical[len(SITIO):] if canonical.startswith(SITIO) else canonical
    return re.split(r"[?#]", ruta or "/", maxsplit=1)[0]


def por_pagina(entradas: list[dict]) -> dict[str, list[dict]]:
    mapa: dict[str, list[dict]] = {}
    for e in entradas:
        mapa.setdefault(ruta_de_canonical(e["url"]), []).append(e)
    return mapa


def aviso(entradas: list[dict], esc, fmt_fecha) -> str:
    """Aviso que va bajo el titular de la página corregida."""
    enlaces = "; ".join(
        f'<a href="/correcciones/#c-{esc(e["id"])}">corregido el {esc(fmt_fecha(e["fecha"]))}: '
        f'{esc(e["pieza"])}</a>' for e in entradas)
    return f'<p class="correccion" role="note"><b>Corrección.</b> {enlaces}.</p>'


def marcar(html: str, entradas: list[dict], esc, fmt_fecha) -> str:
    """Inserta el aviso tras el primer <h1 class="display…">…</h1>; si no lo hay, no toca nada."""
    m = re.search(r'<h1 class="display[^"]*"[^>]*>.*?</h1>', html, re.S)
    if not m or 'class="correccion"' in html:
        return html
    return html[:m.end()] + "\n    " + aviso(entradas, esc, fmt_fecha) + html[m.end():]


def cuerpo(entradas: list[dict], esc, fmt_fecha) -> str:
    partes = [f"""
<p>Cuando un dato publicado aquí es erróneo, lo corregimos en la propia página y lo anotamos en
esta lista: qué decía, qué dice ahora y por qué. Cada página corregida lleva un aviso bajo el
titular que enlaza a su entrada. No se borra ninguna corrección.</p>
<p>Lo que va entre comillas en esta web es literal de la fuente oficial. Si el error está en la
fuente (el BOE o las Cortes), lo señalamos aquí con el enlace a la rectificación oficial cuando
exista.</p>
<p>Para comunicar un error, escribe a <a href="mailto:{CONTACTO}">{CONTACTO}</a> con el enlace a la
página y, si puedes, a la fuente oficial.</p>
<h2 class="rotulo">Correcciones publicadas</h2>"""]
    if not entradas:
        partes.append("<p>Por ahora no hay correcciones publicadas.</p>")
    for e in entradas:
        partes.append(f"""
<section class="correccion-item" id="c-{esc(e['id'])}">
<h3>{esc(fmt_fecha(e['fecha']))} · <a href="{esc(e['url'])}">{esc(e['pieza'])}</a></h3>
<p><b>Decía:</b> {esc(e['dice'])}</p>
<p><b>Dice ahora:</b> {esc(e['debe_decir'])}</p>
<p><b>Motivo:</b> {esc(e['motivo'])}</p>
</section>""")
    return "\n".join(partes)


def generar_pagina(h: dict, entradas: list[dict]) -> list:
    """/correcciones/index.html con la plantilla de ficha. Devuelve la URL para el sitemap."""
    esc, site = h["esc_html"], h["site_url"]
    url = site + "correcciones/"
    lastmod = max([REVISION] + [e["fecha"] for e in entradas])
    h["pagina_suelta"](h["plantilla"], h["raiz"] / "correcciones", "index.html", {
        "TITLE": esc("Correcciones | La Tercera Cámara"),
        "META_DESC": h["esc_attr"]("Errores corregidos en La Tercera Cámara: qué decía cada página, "
                                   "qué dice ahora y por qué. Cómo comunicar un error."),
        "CANONICAL": url,
        "JSONLD": h["jsonld_script"]([{"@type": "WebPage", "url": url, "name": "Correcciones",
                                       "inLanguage": "es-ES", "dateModified": lastmod}]),
        "EDITION_DATE": esc(f"Actualizado el {h['fmt_date_es'](lastmod)}"),
        "MIGA": '<a href="/">Portada</a> › <span aria-current="page">Correcciones</span>',
        "KICKER": esc("Política editorial"),
        "HEADLINE": esc("Correcciones"),
        "STANDFIRST": esc("Lo que hemos corregido, con lo que decía antes y el motivo."),
        "FICHA": "",
        "CUERPO": cuerpo(entradas, esc, h["fmt_date_es"]),
        "FUENTE": f'Contacto: <a class="srclink" href="mailto:{CONTACTO}">{CONTACTO}</a>.',
        "RELACIONADAS": "", "RELACIONADAS_HIDDEN": "hidden",
    })
    return [{"url": url, "lastmod": lastmod}]
