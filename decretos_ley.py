"""Panel «Decretos-ley» de la portada (bloque «Las Cortes hoy»).

Qué ha pasado en el Congreso con cada real decreto-ley de 2026 desde el
14/2026 (el primero de «¿Quién votó qué en tu provincia?»).

Estado, por este orden de fuentes (nada se deduce):
1. La ficha del expediente en el Congreso: campo «Resultado tramitación» o, si
   no está, «Situación actual», y el órgano («Pleno» o «Diputación
   Permanente»).
2. Si no hay ficha, la resolución del Congreso publicada en el BOE que ordena
   publicar el acuerdo de convalidación o derogación (la frase de la parte
   dispositiva: quién «acordó convalidar» o «acordó derogar»). Se cita y enlaza.
3. Si no hay ni una ni otra: «Aún sin votación publicada».

La etiqueta en llano sale de una correspondencia fija (ETIQUETAS_EXPEDIENTE y
ETIQUETAS_RESOLUCION) desde el texto oficial; lo que no esté en ella se muestra
literal (y un test lo avisa). El texto oficial va debajo, como detalle.

Los datos salen de una copia fija, curated/decretos_ley.json, que genera
tools/generar_decretos_ley.py. Al pintar, sin red, se completa con las
resoluciones de convalidación o derogación que traigan las ediciones del sitio
(data/*.json), solo para los decretos-leyes que la copia deja sin estado.
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
BOE_URL = "https://www.boe.es/diario_boe/txt.php?id={id}"

# Resolución del BOE: título y frase de la parte dispositiva.
RE_RESOLUCION = re.compile(r"^Resolución de .+?, del Congreso de los Diputados, por la que se ordena la "
                           r"publicación del Acuerdo de (convalidación|derogación) del (Real Decreto-ley \d+/\d{4})")
RE_ACUERDO = re.compile(r"((?:la Diputación Permanente del Congreso de los Diputados|el Congreso de los Diputados)"
                        r", en su sesión del día de hoy, acordó (?:convalidar|derogar)) (el (Real Decreto-ley \d+/\d{4}))")

# Correspondencia fija: (texto oficial del campo, órgano) -> etiqueta en llano.
ETIQUETAS_EXPEDIENTE = {
    ("Convalidado", "Pleno"): "Convalidado por el Pleno",
    ("Convalidado", "Diputación Permanente"): "Convalidado por la Diputación Permanente",
    ("Derogado", "Pleno"): "Derogado por el Pleno",
    ("Derogado", "Diputación Permanente"): "Derogado por la Diputación Permanente",
    ("Convalidado y tramitado como proyecto de ley", "Pleno"):
        "Convalidado por el Pleno y tramitado como proyecto de ley",
    ("Convalidado y tramitado como proyecto de ley", "Diputación Permanente"):
        "Convalidado por la Diputación Permanente y tramitado como proyecto de ley",
    ("Concluido - (Convalidado)", "Pleno"): "Convalidado por el Pleno",
    ("Concluido - (Convalidado)", "Diputación Permanente"): "Convalidado por la Diputación Permanente",
    ("Concluido - (Derogado)", "Pleno"): "Derogado por el Pleno",
    ("Concluido - (Derogado)", "Diputación Permanente"): "Derogado por la Diputación Permanente",
}
# Frase de la resolución del BOE -> etiqueta en llano.
ETIQUETAS_RESOLUCION = {
    "la Diputación Permanente del Congreso de los Diputados, en su sesión del día de hoy, acordó convalidar":
        "Convalidado por la Diputación Permanente",
    "la Diputación Permanente del Congreso de los Diputados, en su sesión del día de hoy, acordó derogar":
        "Derogado por la Diputación Permanente",
    "el Congreso de los Diputados, en su sesión del día de hoy, acordó convalidar": "Convalidado por el Congreso",
    "el Congreso de los Diputados, en su sesión del día de hoy, acordó derogar": "Derogado por el Congreso",
}
SIN_VOTACION = "Aún sin votación publicada"

ENTRADILLA = ("Qué ha pasado con cada decreto-ley que el Gobierno aprueba sin pasar antes por las Cortes: "
              "el Congreso (con las Cortes disueltas, su Diputación Permanente) tiene que convalidarlo o "
              "derogarlo. Desde el 14/2026 hasta el más reciente. El estado sale de la ficha del expediente "
              "en el Congreso o, si aún no la hay, de la resolución publicada en el BOE; si no hay ninguna "
              "de las dos, se dice.")


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


def resolucion_de_texto(titulo: str, cuerpo: str) -> dict | None:
    """Del título y la parte dispositiva de una resolución del BOE: el RDL y la
    frase literal del acuerdo. None si no es una de esas resoluciones."""
    t = RE_RESOLUCION.match(" ".join((titulo or "").split()))
    a = RE_ACUERDO.search(" ".join((cuerpo or "").split()))
    if not t or not a or a.group(3) != t.group(2):
        return None
    return {"numero": t.group(2), "acuerdo": a.group(1), "objeto": a.group(2)}


def etiqueta(r: dict) -> tuple[str, str]:
    """(etiqueta en llano, fuente): fuente es «expediente», «resolucion» o ""."""
    if r.get("estado"):
        return ETIQUETAS_EXPEDIENTE.get((r["estado"], r.get("organo") or ""), r["estado"]), "expediente"
    res = r.get("resolucion") or {}
    if res.get("acuerdo"):
        return ETIQUETAS_RESOLUCION.get(res["acuerdo"], res["acuerdo"]), "resolucion"
    return SIN_VOTACION, ""


def sin_correspondencia(datos: dict | None) -> list[str]:
    """Textos oficiales de la copia que no están en la correspondencia."""
    fuera = []
    for r in (datos or {}).get("decretos") or []:
        if r.get("estado") and (r["estado"], r.get("organo") or "") not in ETIQUETAS_EXPEDIENTE:
            fuera.append(f'{r["numero"]}: {r["estado"]} ({r.get("organo") or "sin órgano"})')
        res = r.get("resolucion") or {}
        if not r.get("estado") and res.get("acuerdo") and res["acuerdo"] not in ETIQUETAS_RESOLUCION:
            fuera.append(f'{r["numero"]}: {res["acuerdo"]}')
    return fuera


def completar_con_ediciones(datos: dict | None, dias: list[dict]) -> dict | None:
    """Sin red: si una edición del sitio trae la resolución del BOE de un
    decreto-ley que la copia deja sin estado, se usa. No toca nada más."""
    if not datos:
        return datos
    sin = {r["numero"]: r for r in datos.get("decretos") or []
           if not r.get("estado") and not (r.get("resolucion") or {}).get("acuerdo")}
    if not sin:
        return datos
    nuevas = {}
    for d in dias or []:
        b = d.get("boe") or {}
        for s in b.get("stories") or []:
            res = resolucion_de_texto(s.get("titulo_oficial") or "", s.get("materia") or "")
            if not res or res["numero"] not in sin or not re.fullmatch(r"BOE-A-\d{4}-\d+", s.get("ref") or ""):
                continue
            fecha = b.get("fechaISO") or ""
            boe = ""
            if b.get("numero") and re.fullmatch(r"\d{4}-\d{2}-\d{2}", fecha):
                a, m, dd = fecha.split("-")
                boe = f"BOE núm. {b['numero']}, de {dd}/{m}/{a}"
            nuevas[res["numero"]] = {"id": s["ref"], "boe": boe, "acuerdo": res["acuerdo"],
                                     "objeto": res["objeto"], "fuente": "edición del sitio"}
    if not nuevas:
        return datos
    out = dict(datos)
    out["decretos"] = [dict(r, resolucion=nuevas[r["numero"]]) if r["numero"] in nuevas else r
                       for r in datos.get("decretos") or []]
    return out


def _detalle(r: dict, fuente: str) -> str:
    """El texto oficial, literal, como detalle secundario."""
    if fuente == "expediente":
        return (f'Ficha del expediente {_esc(r["expediente"])} en el Congreso: '
                f'«{_esc(r["estado_campo"])}: {_esc(r["estado"])}»'
                + (f' · {_esc(r["organo"])}' if r.get("organo") else ""))
    if fuente == "resolucion":
        res = r["resolucion"]
        return (f'Resolución del Congreso en el BOE ({_esc(res["id"])}'
                + (f', {_esc(res["boe"])}' if res.get("boe") else "")
                + f'): «{_esc(res["acuerdo"])} {_esc(res["objeto"])}»')
    return "Ni ficha de expediente en el Congreso ni resolución en el BOE en la última consulta."


def _fila(r: dict, votacion: str, norma: str) -> str:
    texto, fuente = etiqueta(r)
    if votacion:
        destino = votacion
    elif fuente == "expediente":
        destino = EXPTE_URL.format(expte=r["expediente"])
    elif fuente == "resolucion":
        destino = BOE_URL.format(id=r["resolucion"]["id"])
    else:
        destino = ""
    estado = (f'<a class="dl-estado" href="{_esc(destino)}">{_esc(texto)}</a>' if destino
              else f'<span class="dl-estado dl-sin">{_esc(texto)}</span>')
    titulo = (f'<a href="{_esc(norma)}">{_esc(r["titulo"])}</a>' if norma else _esc(r["titulo"]))
    meta = f'<b class="dl-num">{_esc(r["numero"])}</b>'
    if r.get("boe"):
        meta += f' · <span class="dl-boe">{_esc(r["boe"])}</span>'
    return ('<li class="dl-fila">'
            f'<p class="dl-meta">{meta}</p>'
            f'<p class="dl-est">{estado}</p>'
            f'<p class="dl-tit">{titulo}</p>'
            f'<p class="dl-lit">{_detalle(r, fuente)}</p>'
            "</li>")


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
            f'<p class="dl-nota">{_esc(ENTRADILLA)} Cómo votó cada diputado de tu provincia: '
            '<a href="/diputados/#circunscripciones">¿Quién votó qué en tu provincia?&nbsp;→</a></p>'
            f'<ul class="dl-lista">{"".join(visibles)}</ul>'
            + (f'<details class="dl-mas"><summary>Los {len(resto)} anteriores</summary>'
               f'<ul class="dl-lista">{"".join(resto)}</ul></details>' if resto else "")
            + "</div>")
