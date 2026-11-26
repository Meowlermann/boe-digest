"""Resultados oficiales del 29-N (Congreso), solo desde la proclamación de la JEC.

Única fuente: la resolución de la Presidencia de la Junta Electoral Central
«por la que se publica el resumen de los resultados de las elecciones al
Congreso de los Diputados y al Senado» en el BOE (art. 108.6 LOREG). Nada de
escrutinio provisional, de Infoelectoral ni de medios.

- curated/resultados_29n.json es la copia fija. Si no existe, no se pinta nada:
  ni bloque, ni hueco, ni aviso. Este módulo no crea el fichero.
- Votos, escaños y nombres van tal como los escribe el BOE (cadenas: «88.299»,
  «Doña …»). No se calcula nada: ni porcentajes, ni diferencias, ni fechas.
- Una circunscripción que el generador no pueda leer sin dudas (nombre que no
  casa con el real decreto de convocatoria, electos que no suman los escaños,
  una línea que no se entiende) queda fuera, con su motivo en «excluidas», y su
  página sigue como antes.

Formato del BOE (modelo de 2023, BOE-A-2023-18907): los cuadros II y III
(votos y escaños por candidatura y circunscripción) son tablas HTML en el XML;
la relación de diputados proclamados electos es una imagen en el XML y texto en
el PDF, así que se lee con pdftotext (poppler, en local; no es dependencia del
sitio). tools/generar_resultados_29n.py hace las dos lecturas.
"""
from __future__ import annotations

import html as _html
import json
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parent
DATOS = RAIZ / "curated" / "resultados_29n.json"

TITULO_SECCION_ELECTOS = "Relación de Diputados proclamados electos"
# Lo que termina la relación de diputados en el PDF: la parte del Senado o la
# relación de candidatos sin escaño.
FIN_ELECTOS = ("SENADO", "Relación de candidatos que no han obtenido escaño",
               "Relación de Senadores proclamados electos")


def url_boe(ident: str) -> str:
    return f"https://www.boe.es/diario_boe/txt.php?id={ident}"


def _esc(t) -> str:
    return _html.escape(str(t if t is not None else ""), quote=True)


def _limpio(t: str) -> str:
    return " ".join(_html.unescape(re.sub(r"<[^>]+>", " ", t or "")).split())


def nombre_circ(t: str) -> str:
    """«Albacete.» → «Albacete». Solo quita el punto final de las tablas."""
    t = " ".join((t or "").split())
    return t[:-1] if t.endswith(".") else t


# --------------------------------------------------------------- cuadros II/III
def _filas(tabla: str) -> list:
    out = []
    for tr in re.findall(r"<tr\b.*?</tr>", tabla, re.S):
        celdas = []
        for tag, attrs, cont in re.findall(r"<(t[dh])\b([^>]*)>(.*?)</t[dh]>", tr, re.S):
            m = re.search(r'colspan="(\d+)"', attrs)
            celdas.append((tag, int(m.group(1)) if m else 1, _limpio(cont)))
        out.append(celdas)
    return out


def parsear_cuadros(xml: str) -> tuple[dict, list]:
    """Tablas de votos (y escaños) por candidatura y circunscripción.

    Devuelve ({circ: {"escanos": "4" | None, "candidaturas": [...]}}, avisos).
    Cada candidatura: {"nombre", "votos", "escanos" (None si la tabla no lo trae)}.
    Una celda vacía es que la candidatura no se presentaba allí: no se apunta.
    Las filas «Total …» no son circunscripciones y se ignoran.
    """
    texto = xml[xml.find("<texto"):] if "<texto" in xml else xml
    res: dict = {}
    avisos: list = []
    for n, tabla in enumerate(re.findall(r"<table\b.*?</table>", texto, re.S)):
        filas = _filas(tabla)
        if len(filas) < 3:
            continue
        cab, sub = filas[0], filas[1]
        if not all(t == "th" for t, _, _ in cab + sub):
            continue
        # Columnas a partir de la primera (la del nombre de circunscripción).
        # «Total escaños» no tiene subcabecera; cada candidatura ocupa tantas
        # subcabeceras («Votos», «Escaños») como su colspan.
        cols = []           # (candidatura, "Votos" | "Escaños")
        subs = [c for _, _, c in sub]
        if subs and subs[0] == "":
            subs = subs[1:]
        i = 0
        for _, span, nombre in cab[1:]:
            if nombre == "Total escaños":
                cols.append((nombre, "Escaños"))
                continue
            for _ in range(span):
                cols.append((nombre, subs[i] if i < len(subs) else None))
                i += 1
        if i != len(subs) or any(c not in ("Votos", "Escaños") for _, c in cols):
            avisos.append(f"tabla {n}: la cabecera no se entiende; no se usa")
            continue
        for fila in filas[2:]:
            if not fila:
                continue
            circ = nombre_circ(fila[0][2])
            if not circ or circ.lower().startswith("total"):
                continue
            valores = [c for _, _, c in fila[1:]]
            if len(valores) != len(cols):
                avisos.append(f"tabla {n}, {circ}: {len(valores)} celdas para {len(cols)} columnas")
                res.setdefault(circ, {"escanos": None, "candidaturas": []})["_dudosa"] = True
                continue
            d = res.setdefault(circ, {"escanos": None, "candidaturas": []})
            por_nombre = {k["nombre"]: k for k in d["candidaturas"]}
            for (cand, campo), v in zip(cols, valores):
                if cand == "Total escaños":
                    if v:
                        d["escanos"] = v
                    continue
                if not v:
                    continue
                k = por_nombre.get(cand)
                if k is None:
                    k = {"nombre": cand, "votos": None, "escanos": None}
                    d["candidaturas"].append(k)
                    por_nombre[cand] = k
                if campo == "Escaños":
                    k["escanos"] = v
                else:
                    k["votos"] = v
    return res, avisos


# ------------------------------------------------- relación de electos (PDF)
_PIE = re.compile(r"^(BOLETÍN OFICIAL DEL ESTADO|Núm\. \d+\b.*Pág\.|cve: BOE-|Verificable en|D\. L\.|ISSN)")
_PERSONA = re.compile(r"^(Don|Doña|D\.|Dña\.) (\S.*?\S)\s{2,}(\S.*?)$")


def _bloque(texto: str, titulo: str, fin: tuple) -> list:
    lineas = texto.splitlines()
    ini = None
    for i, l in enumerate(lineas):
        if l.strip() == titulo:
            ini = i + 1
    if ini is None:
        return []
    out = []
    for l in lineas[ini:]:
        s = l.strip()
        if s in fin:
            break
        out.append(l)
    return out


def parsear_electos(texto_pdf: str, circs_validas: set, titulo: str = TITULO_SECCION_ELECTOS,
                    fin: tuple = FIN_ELECTOS) -> tuple[dict, dict]:
    """Relación de electos del PDF (pdftotext -layout).

    Una línea es encabezado de circunscripción si su texto es exactamente uno de
    `circs_validas`; es persona si empieza por «Don/Doña» y tiene el nombre y la
    formación separados por dos o más espacios. Cualquier otra línea dentro de
    una circunscripción (nombre partido en dos renglones, una nota) la deja
    fuera. Devuelve ({circ: [{"nombre", "formacion"}]}, {circ: motivo}).
    """
    electos: dict = {}
    dudosas: dict = {}
    actual = None
    for l in _bloque(texto_pdf, titulo, fin):
        s = l.strip()
        if not s or _PIE.match(s) or s.startswith("Elecciones Generales de"):
            continue
        if s in circs_validas:
            actual = s
            electos.setdefault(actual, [])
            continue
        m = _PERSONA.match(s)
        if actual and m:
            electos[actual].append({"nombre": f"{m.group(1)} {m.group(2)}", "formacion": m.group(3).strip()})
            continue
        if actual:
            dudosas.setdefault(actual, f"línea no reconocida: «{s}»")
        else:
            dudosas.setdefault("(antes de la primera circunscripción)", f"línea no reconocida: «{s}»")
    return electos, dudosas


# ---------------------------------------------------------------- construcción
def construir(xml: str, texto_pdf: str, fuente: dict, circs_rd: list) -> dict:
    """Junta cuadros y electos. Solo entra la circunscripción que casa exacta con
    el real decreto de convocatoria y cuyos números cuadran entre sí:
    electos = escaños totales = suma de escaños de las candidaturas."""
    validas = set(circs_rd)
    cuadros, avisos = parsear_cuadros(xml)
    electos, dudosas = parsear_electos(texto_pdf, validas)
    circs, excluidas = {}, {}
    for c in circs_rd:
        d = cuadros.get(c)
        if not d:
            excluidas[c] = "no aparece en los cuadros de votos"
            continue
        if d.get("_dudosa"):
            excluidas[c] = "una fila de los cuadros no cuadra con su cabecera"
            continue
        if c in dudosas:
            excluidas[c] = dudosas[c]
            continue
        e = electos.get(c) or []
        try:
            total = int((d["escanos"] or "").replace(".", ""))
            suma = sum(int((k["escanos"] or "0").replace(".", "")) for k in d["candidaturas"])
        except ValueError:
            excluidas[c] = "escaños no numéricos"
            continue
        if not (total and total == suma == len(e)):
            excluidas[c] = f"escaños {d['escanos']}, suma de candidaturas {suma}, electos {len(e)}"
            continue
        circs[c] = {"escanos": d["escanos"], "candidaturas": d["candidaturas"], "electos": e}
    for c in cuadros:
        if c not in validas:
            excluidas.setdefault(c, "nombre que no casa con el real decreto de convocatoria")
    return {"fuente": fuente, "circunscripciones": circs, "excluidas": excluidas, "avisos": avisos}


def validar(datos) -> list:
    """Errores de forma de la copia fija. Vacío = se puede pintar."""
    err = []
    if not isinstance(datos, dict):
        return ["no es un objeto"]
    f = datos.get("fuente") or {}
    if not re.fullmatch(r"BOE-A-\d{4}-\d+", str(f.get("id") or "")):
        err.append("fuente.id no es un identificador del BOE")
    if not f.get("literal"):
        err.append("falta fuente.literal")
    for c, d in (datos.get("circunscripciones") or {}).items():
        for k in d.get("candidaturas") or []:
            if not (k.get("nombre") and k.get("votos")):
                err.append(f"{c}: candidatura sin nombre o sin votos")
        for e in d.get("electos") or []:
            if not (e.get("nombre") and e.get("formacion")):
                err.append(f"{c}: electo sin nombre o sin formación")
    return err


def cargar(ruta: pathlib.Path = DATOS) -> dict | None:
    """La copia fija, o None si no existe o no es válida (y no se pinta nada)."""
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return datos if not validar(datos) else None


# ------------------------------------------------------------------- render
def bloque_html(datos: dict | None, circ_rd: str, nombre: str) -> str:
    """«Resultados oficiales» de una circunscripción. Vacío si no hay copia fija
    o la circunscripción no está en ella. Sin tarjetas ni subrayados: una tabla
    y una lista, con la fuente al pie."""
    if not datos:
        return ""
    d = (datos.get("circunscripciones") or {}).get(circ_rd)
    if not d:
        return ""
    f = datos["fuente"]
    filas = "".join(
        f'<tr><th scope="row">{_esc(k["nombre"])}</th><td>{_esc(k["votos"])}</td>'
        f'<td>{_esc(k["escanos"] if k.get("escanos") is not None else "—")}</td></tr>'
        for k in d["candidaturas"])
    electos = "".join(f'<li>{_esc(e["nombre"])} <span class="rof-form">{_esc(e["formacion"])}</span></li>'
                      for e in d.get("electos") or [])
    return (
        f'<section class="rof" id="resultados" aria-labelledby="rof-tit">'
        f'<h2 id="rof-tit">Resultados oficiales</h2>'
        f'<p class="rof-intro">Proclamados por la Junta Electoral Central para {_esc(nombre)}: '
        f'{_esc(d["escanos"])} {"escaño" if str(d["escanos"]) == "1" else "escaños"}. '
        f'Cifras y nombres tal como los publica el BOE.</p>'
        f'<div class="rof-tabla"><table><caption>Votos y escaños por candidatura</caption>'
        f'<thead><tr><th scope="col">Candidatura</th><th scope="col">Votos</th>'
        f'<th scope="col">Escaños</th></tr></thead><tbody>{filas}</tbody></table></div>'
        + (f'<h3>Diputados proclamados electos</h3><ol class="rof-electos">{electos}</ol>' if electos else "")
        + f'<p class="rof-fuente">Fuente: <a href="{_esc(url_boe(f["id"]))}">{_esc(f.get("titulo") or f["id"])}</a> '
          f'({_esc(f["literal"])}).</p></section>')
