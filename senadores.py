"""«Tus senadores» en cada ficha de provincia, solo desde la proclamación de la JEC.

Única fuente: la relación de «Senadores proclamados electos» de la resolución
de la Presidencia de la Junta Electoral Central que publica en el BOE el
resumen de los resultados de las elecciones convocadas por el Real Decreto
806/2026 (art. 108.6 LOREG). Nunca senado.es ni otra web.

- curated/senadores_29n.json es la copia fija. Si no existe, no se pinta nada.
  Este módulo no crea el fichero.
- Nombre, formación y votos van tal como los escribe el BOE. No se calcula nada.
- Si una provincia no está clara, no se publica: encabezado que no casa con el
  real decreto de convocatoria, una línea que no se entiende (nombre partido en
  dos renglones, una nota de renuncia), una isla desconocida o un número de
  senadores distinto del que fija el artículo 165 de la LOREG. Su ficha sigue
  como antes. No se publica una provincia a medias.
- Solo los senadores elegidos en la provincia. Los que designan los
  parlamentos autonómicos no están en esa resolución y no se mencionan con
  nombre.

Formato del BOE (modelo de 2023, BOE-A-2023-18907): la relación es una imagen
en el XML y texto en el PDF; se lee con pdftotext -layout (poppler, en local).
Las provincias insulares llevan un encabezado por isla: «Balears (Illes):
MALLORCA». tools/generar_senadores.py hace la lectura.
"""
from __future__ import annotations

import html as _html
import json
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parent
DATOS = RAIZ / "curated" / "senadores_29n.json"

TITULO_SECCION = "Relación de Senadores proclamados electos"
FIN = ("SENADO", "Relación de candidatos que no han obtenido escaño")

# Artículo 165 de la LOREG: cuatro por provincia; tres en Gran Canaria, Mallorca
# y Tenerife; uno en cada una de las demás islas o agrupaciones; dos en Ceuta y
# dos en Melilla. Solo sirve para comprobar la lectura, no se publica.
SENADORES_PROVINCIA = 4
SENADORES_CIUDAD = {"Ceuta": 2, "Melilla": 2}
ISLAS = {
    "Balears (Illes)": {"MALLORCA": 3, "MENORCA": 1, "EIVISSA-FORMENTERA": 1},
    "Palmas (Las)": {"GRAN CANARIA": 3, "FUERTEVENTURA": 1, "LANZAROTE": 1},
    "Santa Cruz de Tenerife": {"TENERIFE": 3, "LA PALMA": 1, "LA GOMERA": 1, "EL HIERRO": 1},
}

_PIE = re.compile(r"^(BOLETÍN OFICIAL DEL ESTADO|Núm\. \d+\b.*Pág\.|cve: BOE-|Verificable en|D\. L\.|ISSN)")
_PERSONA = re.compile(r"^(Don|Doña) (\S.*?\S)\s{2,}(\S.*?\S)\s{2,}(\d{1,3}(?:\.\d{3})*)$")


def url_boe(ident: str) -> str:
    return f"https://www.boe.es/diario_boe/txt.php?id={ident}"


def _esc(t) -> str:
    return _html.escape(str(t if t is not None else ""), quote=True)


def _bloque(texto: str) -> list:
    lineas = texto.splitlines()
    ini = None
    for i, l in enumerate(lineas):
        if l.strip() == TITULO_SECCION:
            ini = i + 1
    if ini is None:
        return []
    out = []
    for l in lineas[ini:]:
        if l.strip() in FIN:
            break
        out.append(l)
    return out


def parsear(texto_pdf: str, provincias_rd: list) -> tuple[dict, dict]:
    """Relación de senadores electos del PDF.

    Devuelve ({provincia: [{"isla": str | None, "senadores": [{"nombre",
    "formacion", "votos"}]}]}, {provincia: motivo}) solo con las provincias
    claras. Las claves son los nombres del real decreto de convocatoria."""
    validas = set(provincias_rd)
    lectura: dict = {}
    dudosas: dict = {}
    actual = None                       # (provincia, isla)
    for l in _bloque(texto_pdf):
        s = l.strip()
        if not s or _PIE.match(s) or s == "Votos" or s.startswith("Elecciones Generales de"):
            continue
        m = _PERSONA.match(s)
        if m:
            if actual is None:
                dudosas.setdefault("(antes del primer encabezado)", f"línea sin provincia: «{s}»")
                continue
            prov, isla = actual
            grupos = lectura.setdefault(prov, [])
            if not grupos or grupos[-1]["isla"] != isla:
                grupos.append({"isla": isla, "senadores": []})
            grupos[-1]["senadores"].append({"nombre": f"{m.group(1)} {m.group(2)}",
                                            "formacion": m.group(3).strip(), "votos": m.group(4)})
            continue
        prov, _, isla = (p.strip() for p in s.partition(":"))
        if prov in validas and not re.search(r"\s{2,}", s):
            actual = (prov, isla or None)
            lectura.setdefault(prov, [])
            if isla and prov not in ISLAS:
                dudosas.setdefault(prov, f"isla en una provincia no insular: «{s}»")
            continue
        if actual:
            dudosas.setdefault(actual[0], f"línea no reconocida: «{s}»")
        else:
            dudosas.setdefault("(antes del primer encabezado)", f"línea no reconocida: «{s}»")
    claras = {}
    for prov in provincias_rd:
        grupos = lectura.get(prov)
        if not grupos:
            dudosas.setdefault(prov, "no aparece en la relación")
            continue
        if prov in dudosas:
            continue
        motivo = _comprobar(prov, grupos)
        if motivo:
            dudosas[prov] = motivo
            continue
        claras[prov] = grupos
    return claras, dudosas


def _comprobar(prov: str, grupos: list) -> str:
    if prov in ISLAS:
        esperado = ISLAS[prov]
        vistas = [g["isla"] for g in grupos]
        if sorted(vistas) != sorted(esperado) or len(set(vistas)) != len(vistas):
            return f"islas leídas {vistas}, esperadas {sorted(esperado)}"
        for g in grupos:
            if len(g["senadores"]) != esperado[g["isla"]]:
                return f"{g['isla']}: {len(g['senadores'])} senadores, esperados {esperado[g['isla']]}"
        return ""
    if len(grupos) != 1 or grupos[0]["isla"] is not None:
        return "encabezados repetidos o con isla"
    n = SENADORES_CIUDAD.get(prov, SENADORES_PROVINCIA)
    if len(grupos[0]["senadores"]) != n:
        return f"{len(grupos[0]['senadores'])} senadores, esperados {n}"
    return ""


def validar(datos) -> list:
    err = []
    if not isinstance(datos, dict):
        return ["no es un objeto"]
    f = datos.get("fuente") or {}
    if not re.fullmatch(r"BOE-A-\d{4}-\d+", str(f.get("id") or "")):
        err.append("fuente.id no es un identificador del BOE")
    if not f.get("literal"):
        err.append("falta fuente.literal")
    for prov, grupos in (datos.get("provincias") or {}).items():
        if _comprobar(prov, grupos):
            err.append(f"{prov}: {_comprobar(prov, grupos)}")
        for g in grupos:
            for s in g.get("senadores") or []:
                if not (s.get("nombre") and s.get("formacion") and s.get("votos")):
                    err.append(f"{prov}: senador sin nombre, formación o votos")
    return err


def cargar(ruta: pathlib.Path = DATOS) -> dict | None:
    """La copia fija, o None si no existe o no es válida (y no se pinta nada)."""
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return datos if not validar(datos) else None


def bloque_html(datos: dict | None, prov_rd: str, nombre: str) -> str:
    """«Tus senadores» de una provincia. Vacío si no hay copia fija o la
    provincia no está en ella. Lista simple, sin tarjetas ni subrayados."""
    if not datos or not prov_rd:
        return ""
    grupos = (datos.get("provincias") or {}).get(prov_rd)
    if not grupos:
        return ""
    f = datos["fuente"]

    def lista(ss):
        return ('<ul class="sen-lista">' + "".join(
            f'<li>{_esc(s["nombre"])}<span class="sen-det">{_esc(s["formacion"])} · '
            f'{_esc(s["votos"])} votos</span></li>' for s in ss) + "</ul>")
    cuerpo = "".join(
        (f'<h3>{_esc(g["isla"])}</h3>' if g["isla"] else "") + lista(g["senadores"]) for g in grupos)
    return (
        f'<section class="sen-29n" id="tus-senadores" aria-labelledby="sen-tit">'
        f'<h2 id="sen-tit">Tus senadores</h2>'
        f'<p class="sen-intro">Senadores proclamados electos por {_esc(nombre)} en las elecciones '
        f'generales del 29-N, tal como los publica la Junta Electoral Central en el BOE. No incluye '
        f'a los senadores que designan los parlamentos autonómicos.</p>'
        + cuerpo
        + f'<p class="sen-fuente">Fuente: <a href="{_esc(url_boe(f["id"]))}">{_esc(f.get("titulo") or f["id"])}</a> '
          f'({_esc(f["literal"])}).</p></section>')
