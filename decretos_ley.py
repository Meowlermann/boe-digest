"""Panel «Decretos-ley» de la portada (bloque «Las Cortes hoy»).

Criterio (mecánico, ver docs/DECISIONES.md): todos los reales decretos-leyes de
2026 desde el primero de «¿Quién votó qué en tu provincia?» (votos_rdl), con:

- su número y su BOE (número y fecha), de la ficha oficial del expediente en el
  Congreso o, si el Congreso aún no tiene ficha, de la edición del BOE del sitio;
- su estado en el Congreso tal cual lo publica la ficha del expediente: el campo
  «Resultado tramitación» o, si no lo hay, «Situación actual». Sin ficha o sin
  esos campos, no se pone estado: no se deduce nada;
- el enlace a su votación (la página del sitio si existe, si no el JSON oficial)
  cuando está en curated/votos_rdl.json, y a la ficha del expediente.

Los datos salen de una copia fija, curated/decretos_ley.json, que genera
tools/generar_decretos_ley.py. El build no usa la red ni calcula plazos ni fechas.
"""
from __future__ import annotations

import html
import json
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parent
DATOS = RAIZ / "curated" / "decretos_ley.json"
VISIBLES = 6
RE_NUM = re.compile(r"^Real Decreto-ley (\d+)/(\d{4})")
EXPTE_URL = ("https://www.congreso.es/es/busqueda-de-iniciativas?p_p_id=iniciativas&p_p_lifecycle=0"
             "&p_p_state=normal&p_p_mode=view&_iniciativas_mode=mostrarDetalle"
             "&_iniciativas_legislatura=XV&_iniciativas_id={expte}")
NOTA = ("Los decretos-leyes de 2026 desde el 14/2026, el primero de «¿Quién votó qué en tu provincia?». "
        "El estado es el que publica el Congreso en la ficha de cada expediente, copiado tal cual; "
        "si no hay ficha o no trae estado, no se pone.")


def _esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def cargar(ruta: pathlib.Path = DATOS) -> dict | None:
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def clave(numero: str) -> tuple[int, int]:
    """«Real Decreto-ley 23/2026» -> (2026, 23), para ordenar."""
    m = RE_NUM.match(numero or "")
    return (int(m.group(2)), int(m.group(1))) if m else (0, 0)


def _fila(r: dict, votacion: str, norma: str) -> str:
    partes = [f'<b class="dl-num">{_esc(r["numero"])}</b>']
    if r.get("boe"):
        partes.append(f'<span class="dl-boe">{_esc(r["boe"])}</span>')
    meta = " · ".join(partes)
    estado = (f'<span class="dl-estado">{_esc(r["estado_campo"])}: {_esc(r["estado"])}</span>'
              if r.get("estado") else "")
    organo = (f' <span class="dl-org">({_esc(r["organo"])})</span>' if r.get("estado") and r.get("organo") else "")
    enlaces = []
    if votacion:
        enlaces.append(f'<a href="{_esc(votacion)}">Votación</a>')
    if r.get("expediente"):
        enlaces.append(f'<a href="{_esc(EXPTE_URL.format(expte=r["expediente"]))}">'
                       f'Expediente {_esc(r["expediente"])}</a>')
    if norma:
        enlaces.append(f'<a href="{_esc(norma)}">Ficha de la norma</a>')
    return ('<li class="dl-fila">'
            f'<p class="dl-meta">{meta}</p>'
            f'<p class="dl-tit">{_esc(r["titulo"])}</p>'
            + (f'<p class="dl-est">{estado}{organo}</p>' if estado else
               ('<p class="dl-est dl-sin">Sin ficha de expediente en el Congreso</p>' if not r.get("expediente")
                else '<p class="dl-est dl-sin">La ficha del expediente no trae estado</p>'))
            + (f'<p class="dl-enl">{" · ".join(enlaces)}</p>' if enlaces else "")
            + "</li>")


def panel_html(datos: dict | None, votos: dict | None, votacion_url, norma_url) -> str:
    """El panel. `votacion_url(url_json)` devuelve el enlace a la votación (o
    vacío); `norma_url(id_boe)` el de la ficha de la norma (o vacío)."""
    if not datos or not datos.get("decretos"):
        return ""
    por_num = {}
    for v in (votos or {}).get("votaciones") or []:
        m = RE_NUM.match(v.get("texto") or "")
        if m:
            por_num[m.group(0)] = v
    filas = []
    for r in sorted(datos["decretos"], key=lambda r: clave(r["numero"]), reverse=True):
        v = por_num.get(r["numero"])
        filas.append(_fila(r, votacion_url(v["json"]) if v else "", norma_url(r.get("id_boe") or "")))
    visibles, resto = filas[:VISIBLES], filas[VISIBLES:]
    return ('<div class="dl-panel" id="decretos-ley">'
            '<h3>Decretos-ley: qué ha pasado con cada uno</h3>'
            f'<p class="dl-nota">{_esc(NOTA)} <a href="/diputados/#circunscripciones">'
            '¿Quién votó qué en tu provincia?&nbsp;→</a></p>'
            f'<ul class="dl-lista">{"".join(visibles)}</ul>'
            + (f'<details class="dl-mas"><summary>Los {len(resto)} anteriores</summary>'
               f'<ul class="dl-lista">{"".join(resto)}</ul></details>' if resto else "")
            + "</div>")
