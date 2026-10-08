"""Canales Atom por entidad: las «alertas» gratuitas de La Tercera Cámara.

Cada página de entidad (un diputado, una provincia, una materia, una iniciativa
en tramitación, un ministerio) tiene al lado su canal, con la misma ruta y
extensión .xml:

    /diputados/<slug>.xml            sus preguntas, intervenciones y votos distintos a su grupo
    /provincias/<slug>.xml           el BOE que la nombra y las preguntas escritas que la citan
    /temas/<slug>.xml                lo publicado en el BOE en esa materia
    /tramitacion/<slug>.xml          los cambios de estado de la iniciativa y sus plazos de enmiendas
    /preguntas/ministerio-<slug>.xml las preguntas orales de control que contesta ese departamento

Formato: Atom 1.0 (RFC 4287). Se eligió Atom y no RSS 2.0 porque exige un
identificador estable (`id`) y una fecha (`updated`) en cada entrada y tiene
un único formato de fecha (RFC 3339); son justo las tres cosas que comprueba
tools/verificar.py.

Reglas:
- como máximo MAX_ENTRADAS entradas, de la más reciente a la más antigua;
- la fecha de cada entrada es la del hecho oficial (publicación en el BOE,
  sesión, registro, hito de tramitación), nunca la del pase;
- el `id` es una URN `tag:` construida con el identificador oficial y el tipo
  de hecho: no cambia entre pases ni si cambia la redacción del título;
- el `updated` del canal es el de su entrada más reciente, así que un canal
  sin novedades no cambia ni un byte entre pases;
- un canal sin entradas no se escribe (y su página no lo anuncia).

Este módulo no importa build.py: recibe los datos ya cargados y devuelve
texto. build.renderizar_feeds() los recoge, los escribe y anuncia cada canal
en su página (<link rel="alternate"> y el botón «Seguir con RSS»).
"""

from __future__ import annotations

import re
import unicodedata
from xml.sax.saxutils import escape as _esc

MAX_ENTRADAS = 50
ATOM_NS = "http://www.w3.org/2005/Atom"
TAG = "tag:terceracamara.es,2026:"
AUTOR = "La Tercera Cámara"
TIPO = "application/atom+xml"


def _attr(s: str) -> str:
    return _esc(s or "", {'"': "&quot;"})


def fecha_rfc3339(iso: str) -> str:
    """«2026-10-07» -> «2026-10-07T00:00:00Z». Sin hora oficial, medianoche UTC:
    es estable y no inventa una hora que la fuente no da."""
    iso = (iso or "")[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso):
        raise ValueError(f"fecha no ISO: {iso!r}")
    return f"{iso}T00:00:00Z"


def ddmmaaaa_a_iso(f: str) -> str:
    """«17/09/2026» -> «2026-09-17» ('' si no encaja)."""
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", f or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def entrada(ident: str, titulo: str, fecha: str, enlace: str, resumen: str = "") -> dict | None:
    """Una entrada normalizada, o None si le falta algo obligatorio."""
    fecha = (fecha or "")[:10]
    if not (ident and titulo and enlace and re.fullmatch(r"\d{4}-\d{2}-\d{2}", fecha)):
        return None
    return {"id": TAG + ident, "titulo": re.sub(r"\s+", " ", titulo).strip(),
            "fecha": fecha, "enlace": enlace, "resumen": re.sub(r"\s+", " ", resumen or "").strip()}


def ordenar(entradas: list) -> list:
    """Sin vacías ni duplicados (se queda la primera aparición de cada id), de
    la más reciente a la más antigua, con desempate estable por id, y con el
    tope de MAX_ENTRADAS."""
    vistos, salida = set(), []
    for e in entradas:
        if not e or e["id"] in vistos:
            continue
        vistos.add(e["id"])
        salida.append(e)
    salida.sort(key=lambda e: (e["fecha"], e["id"]), reverse=True)
    return salida[:MAX_ENTRADAS]


def atom(titulo: str, subtitulo: str, url_feed: str, url_pagina: str, entradas: list) -> str:
    """El documento Atom. `entradas` ya ordenadas (ordenar()). Vacío -> ''."""
    if not entradas:
        return ""
    partes = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<feed xmlns="{ATOM_NS}" xml:lang="es">',
        f"  <id>{_esc(url_feed)}</id>",
        f"  <title>{_esc(titulo)}</title>",
        f"  <subtitle>{_esc(subtitulo)}</subtitle>",
        f'  <link rel="self" type="{TIPO}" href="{_attr(url_feed)}"/>',
        f'  <link rel="alternate" type="text/html" href="{_attr(url_pagina)}"/>',
        f"  <updated>{fecha_rfc3339(entradas[0]['fecha'])}</updated>",
        f"  <author><name>{AUTOR}</name></author>",
        "  <generator>build.py</generator>",
    ]
    for e in entradas:
        partes += [
            "  <entry>",
            f"    <id>{_esc(e['id'])}</id>",
            f"    <title>{_esc(e['titulo'])}</title>",
            f'    <link rel="alternate" type="text/html" href="{_attr(e["enlace"])}"/>',
            f"    <updated>{fecha_rfc3339(e['fecha'])}</updated>",
        ]
        if e.get("resumen"):
            partes.append(f"    <summary>{_esc(e['resumen'])}</summary>")
        partes.append("  </entry>")
    partes.append("</feed>")
    return "\n".join(partes) + "\n"


def enlace_alternate(href: str, titulo: str) -> str:
    return f'<link rel="alternate" type="{TIPO}" title="{_attr(titulo)}" href="{_attr(href)}">'


def boton(href: str) -> str:
    """El botón discreto de las fichas. Lleva a la explicación la primera vez
    que alguien no sepa qué es RSS."""
    return (f'<p class="seguir-rss"><a class="srclink" href="{_attr(href)}" type="{TIPO}">'
            f'Seguir con RSS</a> <a class="seguir-que" href="/seguir/">¿Qué es?</a></p>')


# ------------------------------------------------------------- ministerios

# Variantes del mismo departamento en el dato oficial (erratas, cambios de
# denominación sin cambio de cartera). Comprobado en state/respuestas/ en
# octubre de 2026.
_ALIAS_DEPARTAMENTO = {
    "Educación, Formación Profesional y Deportes": "Educación, Formación Profesional y Deporte",
    "Hacienda y Función Pública": "Hacienda",
}


def departamento(cargo: str) -> str:
    """«Vicepresidenta Primera del Gobierno y Ministra de Hacienda» -> «Hacienda».
    «Presidente del Gobierno» -> «Presidencia del Gobierno». '' si no se reconoce."""
    c = re.sub(r"\s+", " ", cargo or "").strip()
    if re.fullmatch(r"(?i)president[ea] del gobierno", c):
        return "Presidencia del Gobierno"
    m = re.search(r"(?i)\bministr[oa]\s+(?:del?|para)?\s*(.+)$", c)
    if not m:
        return ""
    d = re.sub(r"^(?:la|el|los|las)\s+", "", m.group(1).strip(), flags=re.I)
    d = d[:1].upper() + d[1:]
    return _ALIAS_DEPARTAMENTO.get(d, d)


def etiqueta_departamento(cargo: str) -> str:
    """El nombre del departamento con su preposición, sacado del propio cargo:
    «Ministro del Interior» -> «Ministerio del Interior»."""
    c = re.sub(r"\s+", " ", cargo or "").strip()
    if re.fullmatch(r"(?i)president[ea] del gobierno", c):
        return "Presidencia del Gobierno"
    m = re.search(r"(?i)\bministr[oa]\s+(.+)$", c)
    return f"Ministerio {m.group(1)}" if m else ""


def slug(t: str) -> str:
    base = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")[:60] or "sin-nombre"


def ministerios(orales: dict) -> dict:
    """{slug: {"nombre", "regs": [(exp, reg)]}} a partir de los registros de
    preguntas orales (state/respuestas/*.json, clave «orales»)."""
    salida: dict = {}
    for exp, r in orales.items():
        d = departamento(r.get("cargo") or "")
        if not d:
            continue
        s = salida.setdefault(slug(d), {"nombre": d, "regs": []})
        s["regs"].append((exp, r))
    for s in salida.values():
        s["regs"].sort(key=lambda x: (x[1].get("s") or "", x[0]), reverse=True)
        # El nombre visible sale del cargo más repetido (las erratas sueltas
        # del dato oficial, como «Ministro del Hacienda», no ganan).
        cargos: dict = {}
        for _exp, r in s["regs"]:
            cargos[r.get("cargo") or ""] = cargos.get(r.get("cargo") or "", 0) + 1
        mas = max(sorted(cargos), key=lambda c: cargos[c])
        s["nombre"] = etiqueta_departamento(mas) or s["nombre"]
    return salida
