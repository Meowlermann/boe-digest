"""«¿Quién votó qué en tu provincia?»: el voto de cada diputado de la
circunscripción en las últimas convalidaciones o derogaciones de reales
decretos-leyes.

Criterio (mecánico e igual para todas las provincias, ver docs/DECISIONES.md):
las 10 votaciones más recientes del Pleno de la XV Legislatura cuyo título
oficial es «Convalidación o derogación de Reales Decretos-leyes.», sin las de
«Tramitación como Proyecto de Ley…».

Los datos salen de una copia fija, curated/votos_rdl.json, que genera
tools/generar_votos_rdl.py a partir de state/congreso.json (el detalle nominal
de los datos abiertos del Congreso). El build no usa la red ni cambia la copia:
el bloque solo se actualiza cuando se vuelve a generar la copia y se commitea.

No se calcula nada: ni porcentajes ni el resultado. Si el RDL quedó convalidado
o derogado se pone solo cuando la ficha oficial del expediente lo trae (campo
«Resultado tramitación», copiado tal cual en la copia fija); si no, no se pone. Si un diputado no aparece en el
listado oficial de una votación, se dice «sin dato».
"""
from __future__ import annotations

import html
import json
import pathlib
import re
import unicodedata

RAIZ = pathlib.Path(__file__).resolve().parent
DATOS = RAIZ / "curated" / "votos_rdl.json"

N_VOTACIONES = 10
TITULO = "Convalidación o derogación de Reales Decretos-leyes."
EXCLUIR = "Tramitación como Proyecto de Ley"
LEGISLATURA = "/Leg15/"
CRITERIO = ("Las 10 votaciones más recientes del Pleno de la XV Legislatura con el título "
            "oficial «Convalidación o derogación de Reales Decretos-leyes», sin las de "
            "tramitación como proyecto de ley.")
NOTA = ("Las 10 últimas votaciones del Pleno sobre la convalidación o derogación de un real "
        "decreto-ley (XV Legislatura), con el voto de cada diputado tal como lo publica el Congreso.")
SIN_DATO = "Sin dato"
SIN_DATO_EXPLICA = "no aparece en el listado oficial de esta votación"

VOTO_TXT = {"S": "Sí", "N": "No", "A": "Abstención", "X": "No vota"}
ORDEN = "SNAX"
RE_RDL = re.compile(r"^(Real Decreto-ley \d+/\d{4})")
DIA_URL = ("https://www.congreso.es/es/opendata/votaciones?p_p_id=votaciones&p_p_lifecycle=0"
           "&p_p_state=normal&p_p_mode=view&targetLegislatura=XV&targetDate={fecha}")
EXPTE_URL = ("https://www.congreso.es/es/busqueda-de-iniciativas?p_p_id=iniciativas&p_p_lifecycle=0"
             "&p_p_state=normal&p_p_mode=view&_iniciativas_mode=mostrarDetalle"
             "&_iniciativas_legislatura=XV&_iniciativas_id={expte}")


def fecha_fuente(iso: str) -> str:
    """«2026-09-23» -> «23/9/2026», el formato de informacion.fecha del JSON oficial."""
    a, m, d = iso.split("-")
    return f"{int(d)}/{int(m)}/{a}"


def fecha_dia(iso: str) -> str:
    """«2026-09-23» -> «23/09/2026», el formato de targetDate en congreso.es."""
    a, m, d = iso.split("-")
    return f"{d}/{m}/{a}"


def seleccionar(estado: dict) -> list:
    """[(url, detalle)] de las votaciones que cumplen el criterio, de la más
    reciente a la más antigua (fecha, sesión y número de votación)."""
    out = [(u, d) for u, d in (estado.get("detalle") or {}).items()
           if LEGISLATURA in u and (d.get("t") or "").strip() == TITULO
           and not (d.get("a") or "").startswith(EXCLUIR)]
    out.sort(key=lambda p: (p[1]["f"], p[1].get("s") or 0, p[1].get("n") or 0), reverse=True)
    return out[:N_VOTACIONES]


def votos_de(d: dict, nombres: list) -> dict:
    """{clave del diputado: letra S/N/A/X}. Quien no figura en el listado no entra."""
    v = d.get("v") or ""
    return {nombres[i]: c for i, c in enumerate(v) if c in ORDEN and i < len(nombres)}


def cargar(ruta: pathlib.Path = DATOS) -> dict | None:
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def rdl_html(texto: str) -> str:
    """El texto oficial tal cual; solo el número del RDL va en negrita."""
    m = RE_RDL.match(texto or "")
    if not m:
        return _esc(texto)
    return f"<b>{_esc(m.group(1))}</b>{_esc(texto[m.end():])}"


def bloque_html(datos: dict | None, gente: list, nombre: str) -> str:
    """La sección de la ficha /diputados/provincia-*.html. Vacía si no hay copia."""
    if not datos or not datos.get("votaciones") or not gente:
        return ""
    orden = sorted(gente, key=lambda f: _clave_orden(f.get("nombre") or f.get("natural") or ""))
    partes = []
    for vot in datos["votaciones"]:
        votos = vot.get("votos") or {}
        grupos = {k: [] for k in ORDEN}
        sin = []
        for f in orden:
            c = votos.get(f.get("clave"))
            (grupos[c] if c in grupos else sin).append(f)
        lis = []
        for k in ORDEN:
            if grupos[k]:
                lis.append(f'<li><span class="pv-v">{VOTO_TXT[k]}:</span> '
                           + ", ".join(_enlace(f) for f in grupos[k]) + "</li>")
        if sin:
            lis.append(f'<li class="pv-sin"><span class="pv-v">{SIN_DATO}</span> ({SIN_DATO_EXPLICA}): '
                       + ", ".join(_enlace(f) + (f' (alta en el Congreso: {_esc(f["alta"])})'
                                                 if f.get("alta") else "") for f in sin) + "</li>")
        fuentes = [f'<a href="{_esc(vot["json"])}">JSON oficial</a>']
        if vot.get("pdf"):
            fuentes.append(f'<a href="{_esc(vot["pdf"])}">PDF</a>')
        if vot.get("dia"):
            fuentes.append(f'<a href="{_esc(vot["dia"])}">votaciones del día</a>')
        if vot.get("expediente"):
            fuentes.append(f'<a href="{_esc(EXPTE_URL.format(expte=vot["expediente"]))}">'
                           f'expediente {_esc(vot["expediente"])}</a>')
        partes.append(
            '<div class="pv-vot">'
            f'<h3 class="pv-tit"><span class="pv-fecha">{_esc(vot["fecha"])}</span> '
            f'{rdl_html(vot["texto"])}</h3>'
            + (f'<p class="pv-res">Resultado, según el expediente del Congreso: '
               f'{_esc(vot["resultado"])}.</p>' if vot.get("resultado") else "")
            + f'<ul class="pv-votos">{"".join(lis)}</ul>'
            f'<p class="pv-fuente">Fuente: {" · ".join(fuentes)}</p></div>')
    return ('<section class="prov-votos" aria-labelledby="prov-votos">'
            f'<h2 id="prov-votos">¿Quién votó qué en {_esc(nombre)}?</h2>'
            f'<p class="elec-nota">{_esc(NOTA)}</p>'
            + "".join(partes) + "</section>")


def _clave_orden(nombre: str) -> str:
    """Orden alfabético de apellidos sin que las tildes manden al final («Álvarez»)."""
    n = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    return n.lower()


def _enlace(f: dict) -> str:
    return f'<a href="{_esc(f["slug"])}.html">{_esc(f["natural"])}</a>'
