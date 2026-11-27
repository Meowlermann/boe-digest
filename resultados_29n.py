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


def _pagina_inicial(texto: str, titulo: str) -> str | None:
    """Página del BOE en la que empieza la sección: la última cabecera
    «… Pág. N» antes de su título."""
    pag = ultima = None
    for l in texto.splitlines():
        s = l.strip()
        mp = re.search(r"Pág\. (\d+)\s*$", s)
        if mp:
            pag = mp.group(1)
        if s == titulo:
            ultima = pag
    return ultima


def parsear_electos(texto_pdf: str, circs_validas: set, titulo: str = TITULO_SECCION_ELECTOS,
                    fin: tuple = FIN_ELECTOS) -> tuple[dict, dict, dict]:
    """Relación de electos del PDF (pdftotext -layout).

    Una línea es encabezado de circunscripción si su texto es exactamente uno de
    `circs_validas`; es persona si empieza por «Don/Doña» y tiene el nombre y la
    formación separados por dos o más espacios. Cualquier otra línea dentro de
    una circunscripción (nombre partido en dos renglones, una nota) la deja
    fuera. Devuelve ({circ: [{"nombre", "formacion"}]}, {circ: motivo},
    {circ: [páginas del BOE donde está]}); las páginas sirven para curar a mano.
    """
    electos: dict = {}
    dudosas: dict = {}
    paginas: dict = {}
    actual = None
    pag = _pagina_inicial(texto_pdf, titulo)
    for l in _bloque(texto_pdf, titulo, fin):
        s = l.strip()
        mp = re.search(r"Pág\. (\d+)\s*$", s)
        if mp:
            pag = mp.group(1)
        if not s or _PIE.match(s) or s.startswith("Elecciones Generales de"):
            continue
        if s in circs_validas:
            actual = s
            electos.setdefault(actual, [])
        if actual and pag and pag not in paginas.setdefault(actual, []):
            paginas[actual].append(pag)
        if s == actual:
            continue
        m = _PERSONA.match(s)
        if actual and m:
            electos[actual].append({"nombre": f"{m.group(1)} {m.group(2)}", "formacion": m.group(3).strip()})
            continue
        if actual:
            dudosas.setdefault(actual, f"línea no reconocida: «{s}»")
        else:
            dudosas.setdefault("(antes de la primera circunscripción)", f"línea no reconocida: «{s}»")
    return electos, dudosas, paginas


def _cuadra(d: dict) -> str:
    """Vacío si escaños totales = suma de escaños de las candidaturas = electos."""
    try:
        total = int(str(d.get("escanos") or "").replace(".", ""))
        suma = sum(int(str(k.get("escanos") or "0").replace(".", "")) for k in d.get("candidaturas") or [])
    except ValueError:
        return "escaños no numéricos"
    n = len(d.get("electos") or [])
    if not (total and total == suma == n):
        return f"escaños {d.get('escanos')}, suma de candidaturas {suma}, electos {n}"
    return ""


# ---------------------------------------------------------------- construcción
def construir(xml: str, texto_pdf: str, fuente: dict, circs_rd: list) -> dict:
    """Junta cuadros y electos. Solo entra la circunscripción que casa exacta con
    el real decreto de convocatoria y cuyos números cuadran entre sí:
    electos = escaños totales = suma de escaños de las candidaturas.
    «borradores» trae, para cada excluida, lo leído de los cuadros y las
    páginas del BOE de su relación de electos: el punto de partida para curarla
    a mano (curated/resultados_29n_manual.json)."""
    validas = set(circs_rd)
    cuadros, avisos = parsear_cuadros(xml)
    electos, dudosas, paginas = parsear_electos(texto_pdf, validas)
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
        cand = {"escanos": d["escanos"], "candidaturas": d["candidaturas"], "electos": electos.get(c) or []}
        motivo = _cuadra(cand)
        if motivo:
            excluidas[c] = motivo
            continue
        circs[c] = cand
    for c in cuadros:
        if c not in validas:
            excluidas.setdefault(c, "nombre que no casa con el real decreto de convocatoria")
    borradores = {
        c: {"fuente": {"id": fuente.get("id"), "pagina": " y ".join(paginas.get(c) or [])},
            "escanos": (cuadros.get(c) or {}).get("escanos"),
            "candidaturas": (cuadros.get(c) or {}).get("candidaturas") or [],
            "electos": []}
        for c in excluidas if c in validas}
    return {"fuente": fuente, "circunscripciones": circs, "excluidas": excluidas, "avisos": avisos,
            "borradores": borradores}


# ------------------------------------------------------------------- copia fija
# Solo la proclamación de estas elecciones: una copia de otras (por ejemplo, la
# de 2023 que se usa para las capturas de prueba) no pasa la validación y no se
# pinta nunca.
CONVOCATORIA = "Real Decreto 806/2026"
MARCA_PRUEBA = "DATOS DE PRUEBA"
DATOS_MANUAL = RAIZ / "curated" / "resultados_29n_manual.json"


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
    if CONVOCATORIA not in str(f.get("titulo") or ""):
        err.append(f"fuente.titulo no es la proclamación de las elecciones del {CONVOCATORIA}")
    if MARCA_PRUEBA in json.dumps(datos, ensure_ascii=False):
        err.append("lleva la marca de datos de prueba")
    for c, d in (datos.get("circunscripciones") or {}).items():
        for k in d.get("candidaturas") or []:
            if not (k.get("nombre") and k.get("votos")):
                err.append(f"{c}: candidatura sin nombre o sin votos")
        for e in d.get("electos") or []:
            if not (e.get("nombre") and e.get("formacion")):
                err.append(f"{c}: electo sin nombre o sin formación")
        if _cuadra(d):
            err.append(f"{c}: {_cuadra(d)}")
    return err


def validar_manual(circ: str, d, fuente: dict, circs_rd) -> str:
    """Motivo por el que una circunscripción curada a mano no se publica, o vacío.

    Se copia literal del PDF del BOE y lleva como fuente el mismo identificador
    de la proclamación y la página. Tiene que cuadrar igual que la automática."""
    if circs_rd is not None and circ not in circs_rd:
        return "nombre que no casa con el real decreto de convocatoria"
    if not isinstance(d, dict):
        return "no es un objeto"
    fm = d.get("fuente") or {}
    if fm.get("id") != fuente.get("id"):
        return "la fuente no es la misma proclamación"
    if not re.fullmatch(r"\d+(?:(?:, | y |-)\d+)*", str(fm.get("pagina") or "")):
        return "falta la página del BOE"
    for k in d.get("candidaturas") or []:
        if not (k.get("nombre") and k.get("votos")):
            return "candidatura sin nombre o sin votos"
    if not d.get("candidaturas"):
        return "sin candidaturas"
    for e in d.get("electos") or []:
        if not (e.get("nombre") and e.get("formacion")):
            return "electo sin nombre o sin formación"
    if MARCA_PRUEBA in json.dumps(d, ensure_ascii=False):
        return "lleva la marca de datos de prueba"
    return _cuadra(d)


def combinar(datos: dict, manual: dict | None, circs_rd=None) -> dict:
    """Añade las circunscripciones curadas a mano que la automática dejó fuera.
    Si la automática ya la tiene, manda la automática. Si la manual no cuadra,
    no se publica (y se apunta por qué en «manual_descartadas»)."""
    if not manual:
        return datos
    out = {**datos, "circunscripciones": dict(datos.get("circunscripciones") or {}),
           "manual_descartadas": {}}
    for c, d in (manual.get("circunscripciones") or {}).items():
        if c in out["circunscripciones"]:
            out["manual_descartadas"][c] = "ya está en la copia automática"
            continue
        motivo = validar_manual(c, d, datos.get("fuente") or {}, circs_rd)
        if motivo:
            out["manual_descartadas"][c] = motivo
            continue
        out["circunscripciones"][c] = {**d, "manual": True}
    return out


def _circs_rd():
    try:
        import elecciones as el
        return {c["circunscripcion"] for c in el.cargar()["circunscripciones"]}
    except Exception:                                         # noqa: BLE001
        return None


def cargar(ruta: pathlib.Path = DATOS, ruta_manual: pathlib.Path = DATOS_MANUAL) -> dict | None:
    """La copia fija (más las curadas a mano), o None si no existe o no es
    válida: entonces no se pinta nada. Sin copia automática, la manual sola no
    se usa."""
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if validar(datos):
        return None
    try:
        manual = json.loads(ruta_manual.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manual = None
    return combinar(datos, manual, _circs_rd())


# ------------------------------------------------------------------- render
ANCLA = "resultados"


def hay_bloque(datos: dict | None, circ_rd: str) -> bool:
    return bool(datos and (datos.get("circunscripciones") or {}).get(circ_rd))


def _entero(t) -> int:
    """«1.463.183» → 1463183. Solo para ordenar; lo que se pinta es el literal."""
    try:
        return int(str(t or "0").replace(".", ""))
    except ValueError:
        return 0


def escanos(k: dict) -> str:
    """Escaños tal como los da el BOE. Las candidaturas del cuadro de «sin
    escaño» no traen columna de escaños: son 0, el mismo signo que en el
    cuadro de las que tienen escaño en otras circunscripciones (informe 48)."""
    e = k.get("escanos")
    return "0" if e in (None, "") else str(e)


def ordenadas(d: dict) -> list:
    """Candidaturas por escaños (de más a menos) y, a igualdad, por votos (de
    más a menos). A igualdad de las dos cosas, el orden del BOE (orden estable).
    No el orden de columnas de los cuadros (informe 48)."""
    return sorted(d.get("candidaturas") or [],
                  key=lambda k: (-_entero(escanos(k)), -_entero(k.get("votos"))))


def sigla(nombre: str) -> str:
    """La sigla que el BOE pone entre paréntesis al final del nombre
    («Partido Popular (PP)» → «PP»); si no hay, el nombre entero."""
    m = re.search(r"\(([^()]+)\)\s*$", nombre or "")
    return m.group(1).strip() if m else (nombre or "").strip()


def reparto_texto(d: dict) -> str:
    """«PP 16, PSOE 10, SUMAR 6, VOX 5»: solo las candidaturas con escaño, en el
    orden de la tabla, con la sigla y los escaños tal cual del BOE. Las que no
    tienen escaño no salen: el resumen dice quién entra (están en la tabla)."""
    return ", ".join(f"{sigla(k['nombre'])} {escanos(k)}" for k in ordenadas(d) if _entero(escanos(k)) > 0)


def _reparto_html(d: dict) -> str:
    """El reparto, con cada sigla pegada a sus escaños (espacio duro): a 360 px
    la línea parte entre candidaturas, nunca entre «PP» y «16». El texto es el
    mismo que reparto_texto()."""
    trozos = [f"{_esc(sigla(k['nombre']))}&nbsp;{_esc(escanos(k))}"
              for k in ordenadas(d) if _entero(escanos(k)) > 0]
    return f'<span class="rof-reparto">Escaños: {", ".join(trozos)}</span>' if trozos else ""


def salto_html(datos: dict | None, circ_rd: str, junto: str = "") -> str:
    """Arriba del todo, solo si hay bloque: el enlace al bloque y, debajo, el
    reparto de escaños, para que a 375 px se vea en el primer pantallazo.
    `junto`: otro enlace de salto en la misma línea («Tus senadores ↓»), que
    sale solo aunque no haya resultados."""
    if not hay_bloque(datos, circ_rd):
        return f'<p class="rof-salto">{junto}</p>' if junto else ""
    return (f'<p class="rof-salto"><a href="#{ANCLA}">Resultados oficiales&nbsp;↓</a>'
            + (f' <span class="rof-sep" aria-hidden="true">·</span> {junto}' if junto else "")
            + f'{_reparto_html(datos["circunscripciones"][circ_rd])}</p>')


def bloque_html(datos: dict | None, circ_rd: str, nombre: str) -> str:
    """«Resultados oficiales» de una circunscripción. Vacío si no hay copia fija
    o la circunscripción no está en ella. Sin tarjetas ni subrayados: una tabla
    y una lista, con la fuente al pie."""
    if not hay_bloque(datos, circ_rd):
        return ""
    d = datos["circunscripciones"][circ_rd]
    f = datos["fuente"]
    filas = "".join(
        f'<tr><th scope="row">{_esc(k["nombre"])}</th><td>{_esc(k["votos"])}</td>'
        f'<td>{_esc(escanos(k))}</td></tr>'
        for k in ordenadas(d))
    electos = "".join(
        f'<li>{_esc(e["nombre"])}'
        + (f' <span class="rof-nota">{_esc(e["nota"])}</span>' if e.get("nota") else "")
        + f' <span class="rof-form">{_esc(e["formacion"])}</span></li>'
        for e in d.get("electos") or [])
    pagina = ""
    if d.get("manual"):
        pg = str((d.get("fuente") or {}).get("pagina") or "")
        pagina = f", {'páginas' if re.search(r'[ ,-]', pg) else 'página'} {_esc(pg)}"
    return (
        f'<section class="rof" id="{ANCLA}" aria-labelledby="rof-tit">'
        f'<h2 id="rof-tit">Resultados oficiales</h2>'
        f'<p class="rof-intro">Proclamados por la Junta Electoral Central para {_esc(nombre)}: '
        f'{_esc(d["escanos"])} {"escaño" if str(d["escanos"]) == "1" else "escaños"}. '
        f'Cifras y nombres tal como los publica el BOE.</p>'
        + (f'<p class="rof-resumen">{_reparto_html(d)}</p>' if reparto_texto(d) else "")
        + f'<div class="rof-tabla"><table><caption>Votos y escaños por candidatura</caption>'
        f'<thead><tr><th scope="col">Candidatura</th><th scope="col">Votos</th>'
        f'<th scope="col">Escaños</th></tr></thead><tbody>{filas}</tbody></table></div>'
        + (f'<h3>Diputados proclamados electos</h3><ol class="rof-electos">{electos}</ol>' if electos else "")
        + f'<p class="rof-fuente">Fuente: <a href="{_esc(url_boe(f["id"]))}">{_esc(f.get("titulo") or f["id"])}</a> '
          f'({_esc(f["literal"])}{pagina}).</p></section>')
