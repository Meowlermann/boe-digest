"""Seguimiento de las iniciativas legislativas del Congreso.

Hasta ahora la web solo veía una ley cuando llegaba al BOE, ya aprobada. Lo
que pasa antes —quién la presenta, si se toma en consideración, cuánto dura en
comisión, qué plazos de enmiendas hay abiertos, si se retira— no aparecía, y
por eso buscar un tema de actualidad parlamentaria («acusación popular») no
devolvía nada.

Fuente: los datos abiertos de iniciativas del Congreso
(https://www.congreso.es/es/opendata/iniciativas), que se regeneran cada día:

- ProyectosDeLey, ProposicionesDeLey y PropuestasDeReforma: una fila por
  iniciativa de la legislatura, con su objeto, autor, fechas, situación actual,
  plazos y la tramitación seguida paso a paso.
- IniciativasLegislativasAprobadas: las leyes ya aprobadas, con su número y la
  fecha de publicación en el BOE.

Todo determinista: no se resume ni se interpreta nada, solo se ordena lo que
el Congreso publica. Los nombres de los ficheros llevan la fecha de generación,
así que se leen de la página de datos abiertos, igual que las votaciones.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import unicodedata

import congreso_datos as cd

RAIZ = pathlib.Path(__file__).resolve().parent
ESTADO = RAIZ / "state" / "iniciativas.json"
PAG_INICIATIVAS = f"{cd.CONGRESO}/es/opendata/iniciativas"
FICHEROS = ("ProyectosDeLey", "ProposicionesDeLey", "PropuestasDeReforma")
APROBADAS = "IniciativasLegislativasAprobadas"
FICHA = ("https://www.congreso.es/es/busqueda-de-iniciativas?p_p_id=iniciativas&p_p_lifecycle=0"
         "&p_p_state=normal&p_p_mode=view&_iniciativas_mode=mostrarDetalle"
         "&_iniciativas_legislatura=XV&_iniciativas_id={exp}")
VERSION = 1
MAX_CAMBIOS = 400          # historial de cambios de fase que se guarda
DIAS_NOVEDADES = 30        # «movimiento reciente» en el índice


# ------------------------------------------------------------------ utilidades

def _txt(v) -> str:
    return " ".join(str(v or "").split())


def _fecha(v: str) -> str:
    """«23/12/2025» -> «2025-12-23»; "" si no hay fecha."""
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", v or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def exp_corto(exp: str) -> str:
    """«122/000231/0000» -> «122/000231», que es como lo cita el Congreso."""
    m = re.match(r"(\d{3}/\d{6})", exp or "")
    return m.group(1) if m else (exp or "")


def slug(exp: str) -> str:
    return exp_corto(exp).replace("/", "-")


def url_ficha(exp: str) -> str:
    return FICHA.format(exp=exp_corto(exp).replace("/", "%2F"))


def nucleo(objeto: str) -> str:
    """El tema de la iniciativa sin el tipo delante ni la procedencia detrás:
    «Proposición de Ley Orgánica de garantía y protección de…» -> «de garantía
    y protección de…». Sirve para casar la iniciativa con la ley aprobada y con
    las votaciones, que la citan con otras palabras alrededor."""
    t = _txt(objeto)
    t = re.sub(r"^(Proyecto|Proposición)\s+de\s+Ley(\s+Orgánica)?\s*", "", t, flags=re.I)
    t = re.sub(r"^(Propuesta\s+de\s+reforma\s+del?\s+)", "", t, flags=re.I)
    t = re.sub(r"\s*\(procedente del[^)]*\)\.?\s*$", "", t, flags=re.I)
    return t.rstrip(". ")


def pasos(texto: str) -> list[list[str]]:
    """TRAMITACIONSEGUIDA en pasos [órgano y fase, desde, hasta].

    El campo viene en líneas: una o dos con el órgano y la fase («Comisión de
    Justicia», «Enmiendas») y después «desde dd/mm/aaaa [hasta dd/mm/aaaa]».
    Hay pasos con una sola línea de etiqueta («Senado», «Concluido -
    (Aprobado con modificaciones)»)."""
    salida, etiqueta = [], []
    for linea in (texto or "").splitlines():
        linea = _txt(linea)
        if not linea:
            continue
        m = re.match(r"^desde\s+(\d{2}/\d{2}/\d{4})(?:\s+hasta\s+(\d{2}/\d{2}/\d{4}))?", linea)
        if m:
            salida.append([" · ".join(etiqueta), _fecha(m.group(1)), _fecha(m.group(2) or "")])
            etiqueta = []
        else:
            etiqueta.append(linea)
    if etiqueta:
        salida.append([" · ".join(etiqueta), "", ""])
    return salida


def plazos(texto: str) -> list[list[str]]:
    """«Hasta: 05/10/2026 (18:00) De enmiendas Hasta: …» -> [[fecha, qué]]."""
    t = _txt(texto)
    salida = []
    for m in re.finditer(r"Hasta:\s*(\d{2}/\d{2}/\d{4})(?:\s*\((\d{1,2}:\d{2})\))?\s*(.*?)(?=\s*Hasta:|$)", t):
        salida.append([_fecha(m.group(1)), (m.group(2) or ""), _txt(m.group(3))])
    return salida


def fase(ini: dict) -> str:
    """Una etiqueta corta para agrupar: dónde está ahora."""
    s = ini.get("sit") or ""
    if ini.get("cerrado"):
        return "Cerrada"
    if re.search(r"Senado", s):
        return "En el Senado"
    if re.search(r"Toma en consideración", s):
        return "Pendiente de toma en consideración"
    if re.search(r"Gobierno", s):
        return "Esperando el criterio del Gobierno"
    if re.search(r"Enmiendas|Ponencia|Informe|Dictamen|Debate de totalidad", s):
        return "En comisión"
    if re.search(r"Pleno", s):
        return "En el Pleno"
    return "Otras fases"


ORDEN_FASES = ["Esperando el criterio del Gobierno", "Pendiente de toma en consideración",
               "En comisión", "En el Pleno", "En el Senado", "Otras fases"]


def resultado(ini: dict) -> str:
    """Cómo acabó, si acabó: «Aprobado con modificaciones», «Retirado»…"""
    if ini.get("res"):
        return re.sub(r"\s*\d{2}/\d{2}/\d{4}.*$", "", ini["res"]).strip()
    for p in reversed(ini.get("pasos") or []):
        m = re.search(r"Concluido\s*-\s*\(([^)]+)\)", p[0])
        if m:
            return m.group(1)
    return ""


# ------------------------------------------------------------ de qué trata

# El título oficial no siempre dice de qué va una ley: la que recorta la
# acusación popular se llama «de garantía y protección de los derechos
# fundamentales frente al acoso derivado de acciones judiciales abusivas».
# Para que el buscador la encuentre por el nombre con el que se conoce, se
# leen las expresiones que más se repiten en el texto publicado en el Boletín
# de las Cortes. Sin modelo: solo se cuentan pares de palabras.
_VACIAS = set("""a al ante bajo cabe con contra de del desde durante en entre hacia hasta mediante
para por segun sin so sobre tras y e o u ni que el la los las lo un una unos unas su sus se es son
ser sera seran fue han ha haber hay como mas muy tambien este esta estos estas ese esa esos esas aquel
dicho dicha dichos dichas cual cuales cuyo cuya donde cuando asi otro otra otros otras todo toda todos
todas cada mismo misma mismos mismas sino pero porque pues ya no si le les nos sera podra podran debe
deberan puede pueden sera siendo sido tiene tienen presente presentes primero segundo tercero
articulo articulos apartado apartados parrafo letra disposicion disposiciones adicional transitoria
final derogatoria ley leyes organica proposicion proyecto texto redaccion modifica modificacion
queda quedan redactado redactada siguiente siguientes siguiente numero punto""".split())
_MUERTOS = {"boletin oficial", "cortes generales", "congreso diputados", "grupo parlamentario",
            "mesa camara", "diario sesiones", "oficial estado", "entrada vigor", "boletin cortes",
            "serie proposiciones", "diputados serie", "palacio congreso", "portavoz grupo",
            "reglamento camara", "exposicion motivos", "lengua espanola"}


def terminos(texto: str, maximo: int = 12) -> list[str]:
    """Las expresiones de dos palabras más repetidas del texto, sin las
    fórmulas de cualquier ley («entrada en vigor», «Boletín Oficial»…)."""
    palabras = re.findall(r"[a-záéíóúñü]+", (texto or "").lower())
    utiles = [(w, _norm(w)) for w in palabras]
    utiles = [(w, n) for w, n in utiles if len(n) > 2 and n not in _VACIAS]
    cuenta: dict = {}
    forma: dict = {}
    for (w1, n1), (w2, n2) in zip(utiles, utiles[1:]):
        clave = f"{n1} {n2}"
        if clave in _MUERTOS or n1 == n2:
            continue
        cuenta[clave] = cuenta.get(clave, 0) + 1
        forma.setdefault(clave, f"{w1} {w2}")
    top = sorted((c for c in cuenta.items() if c[1] >= 3), key=lambda x: (-x[1], x[0]))
    return [forma[k] for k, _n in top[:maximo]]


def completar_terminos(e: dict, pdf_text, log, maximo: int = 120) -> int:
    """Lee el primer boletín de cada iniciativa que aún no tenga términos. Por
    tandas: la primera vez son cientos de PDF, y cada edición completa unos
    pocos. Lo más reciente primero, que es lo que se busca."""
    hechas = 0
    pendientes = sorted(((v.get("fp") or "", k) for k, v in (e.get("ini") or {}).items()
                         if v.get("bocg") and v.get("kw_src") != v["bocg"][0]), reverse=True)
    for _f, k in pendientes[:maximo]:
        v = e["ini"][k]
        try:
            texto = pdf_text(v["bocg"][0], max_chars=80_000)
        except Exception as exc:                              # noqa: BLE001
            log(f"iniciativas: no se pudo leer el boletín de {k} ({exc})")
            continue
        if not texto:
            continue
        v["kw"] = terminos(texto)
        v["kw_src"] = v["bocg"][0]
        hechas += 1
    if hechas:
        guardar(e)
    log(f"iniciativas: términos leídos de {hechas} boletines; "
        f"{max(0, len(pendientes) - hechas)} pendientes")
    return hechas


# ---------------------------------------------------------------------- estado

def cargar() -> dict:
    try:
        e = json.loads(ESTADO.read_text(encoding="utf-8"))
        if e.get("version") == VERSION:
            return e
    except Exception:                                         # noqa: BLE001
        pass
    return {"version": VERSION, "ini": {}, "leyes": [], "cambios": [], "actualizado": ""}


def guardar(e: dict) -> None:
    ESTADO.parent.mkdir(exist_ok=True)
    texto = json.dumps(e, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if not ESTADO.exists() or ESTADO.read_text(encoding="utf-8") != texto:
        ESTADO.write_text(texto, encoding="utf-8")


def _lineas(v) -> str:
    """«Comisión de Justicia\nEnmiendas» -> «Comisión de Justicia · Enmiendas»."""
    return " · ".join(_txt(l) for l in str(v or "").splitlines() if _txt(l))


def _registro(x: dict) -> dict:
    sit = _lineas(x.get("SITUACIONACTUAL"))
    ps = pasos(x.get("TRAMITACIONSEGUIDA") or "")
    return {
        "o": _txt(x.get("OBJETO")),
        "t": _txt(x.get("TIPO")),
        "a": _txt(x.get("AUTOR")),
        "fp": _fecha(x.get("FECHAPRESENTACION") or ""),
        "fc": _fecha(x.get("FECHACALIFICACION") or ""),
        "sit": sit,
        "cerrado": sit.startswith("Cerrado") or sit.startswith("Concluido"),
        "res": _txt(x.get("RESULTADOTRAMITACION")),
        "com": _txt(x.get("COMISIONCOMPETENTE")),
        "trt": _txt(x.get("TIPOTRAMITACION")),
        "pon": _txt(x.get("PONENTES")),
        "pasos": ps,
        "plazos": plazos(x.get("PLAZOS") or ""),
        "bocg": [u.split("#")[0] for u in re.findall(r"https?://\S+?\.PDF(?:#page=\d+)?", x.get("ENLACESBOCG") or "", re.I)][:30],
        "rel": sorted(set(re.findall(r"\d{3}/\d{6}", x.get("INICIATIVASRELACIONADAS") or ""))),
    }


def actualizar(get, log) -> dict:
    """Descarga los ficheros del día y actualiza el estado. Guarda también cada
    cambio de situación respecto a la ejecución anterior: es lo que alimenta
    las novedades de «Las Cortes hoy». La primera vez no hay cambios (no se
    sabe qué había antes) y no se inventan."""
    e = cargar()
    r = get(PAG_INICIATIVAS, tries=2)
    if not r:
        log("iniciativas: la página de datos abiertos no responde; se sigue con el estado")
        return e
    urls = cd._urls_json(r.text)
    nuevos: dict = {}
    for nombre in FICHEROS:
        u = cd._elegir(urls, nombre + "__") or cd._elegir(urls, nombre)
        d = get(u, tries=2) if u else None
        try:
            filas = d.json() if d else []
        except Exception as exc:                              # noqa: BLE001
            log(f"iniciativas: {nombre} ilegible ({exc})")
            filas = []
        for x in filas if isinstance(filas, list) else []:
            exp = exp_corto(x.get("NUMEXPEDIENTE") or "")
            if exp:
                nuevos[exp] = _registro(x)
        log(f"iniciativas: {nombre}: {len(filas) if isinstance(filas, list) else 0} filas")
    if not nuevos:
        log("iniciativas: ningún fichero legible; se conserva el estado anterior")
        return e

    u = cd._elegir(urls, APROBADAS)
    d = get(u, tries=2) if u else None
    try:
        leyes = d.json() if d else []
    except Exception:                                         # noqa: BLE001
        leyes = []
    if isinstance(leyes, list) and leyes:
        e["leyes"] = [{"tipo": _txt(l.get("TIPO")), "num": _txt(l.get("NUMERO_LEY")),
                       "titulo": _txt(l.get("TITULO_LEY")), "fl": _fecha(l.get("FECHA_LEY") or ""),
                       "boe": _txt(l.get("NUMERO_BOLETIN")), "fb": _fecha(l.get("FECHA_BOLETIN") or ""),
                       "pdf": _txt(l.get("PDF"))} for l in leyes]

    hoy = dt.date.today().isoformat()
    previos = e.get("ini") or {}
    # Los términos cuestan un PDF cada uno: se conservan mientras el boletín
    # del que salieron sea el mismo.
    for exp, v in nuevos.items():
        antes = previos.get(exp) or {}
        if antes.get("kw_src") and v.get("bocg") and antes["kw_src"] == v["bocg"][0]:
            v["kw"], v["kw_src"] = antes.get("kw") or [], antes["kw_src"]
    if previos:
        for exp, v in nuevos.items():
            antes = previos.get(exp)
            if antes is None:
                e["cambios"].append({"f": hoy, "exp": exp, "de": "", "a": v["sit"] or "Registrada"})
            elif antes.get("sit") != v["sit"]:
                e["cambios"].append({"f": hoy, "exp": exp, "de": antes.get("sit", ""), "a": v["sit"]})
    e["cambios"] = e["cambios"][-MAX_CAMBIOS:]
    e["ini"] = nuevos
    e["actualizado"] = hoy
    guardar(e)
    log(f"iniciativas: {len(nuevos)} en el estado, "
        f"{sum(1 for c in e['cambios'] if c['f'] == hoy)} cambios de fase hoy")
    return e


# ------------------------------------------------------------ relaciones

def ley_de(ini: dict, leyes: list) -> dict | None:
    """La ley aprobada que sale de esta iniciativa, si el título casa."""
    if not ini.get("cerrado") or not re.search(r"Aprobad", resultado(ini)):
        return None
    clave = _norm(nucleo(ini["o"]))[:90]
    if len(clave) < 20:
        return None
    for l in leyes or []:
        if clave in _norm(l.get("titulo")):
            return l
    return None


def votaciones_de(ini: dict, detalle: list) -> list:
    """Votaciones del Pleno que tratan esta iniciativa (por el texto del asunto)."""
    clave = _norm(nucleo(ini["o"]))[:70]
    if len(clave) < 20:
        return []
    return [d for d in detalle or [] if clave in _norm(f'{d.get("t", "")} {d.get("a", "")}')]


def tipo_corto(t: str) -> str:
    t = t or ""
    if t.startswith("Proyecto"):
        return "Proyecto de ley"
    if "Orgánica" in t:
        return "Proposición de ley orgánica"
    if t.startswith("Proposición"):
        return "Proposición de ley"
    if t.startswith("Propuesta"):
        return "Reforma de Estatuto"
    return t or "Iniciativa"


def grupo_corto(autor: str) -> str:
    a = autor or ""
    a = re.sub(r"^Grupo Parlamentario\s+", "", a)
    return a.replace(" en el Congreso", "")


# ---------------------------------------------------------------- «Las Cortes hoy»

def feed(e: dict, hoy: str, fmt_date_es, site_url: str, maximo: int = 8) -> list:
    """Piezas de tramitación para la edición: iniciativas nuevas y cambios de
    fase registrados hoy. Titular por plantilla, sin interpretar."""
    piezas = []
    for c in [c for c in reversed(e.get("cambios") or []) if c["f"] == hoy][:maximo]:
        ini = (e.get("ini") or {}).get(c["exp"])
        if not ini:
            continue
        tema = nucleo(ini["o"])
        tema_corto = tema if len(tema) <= 110 else tema[:110].rsplit(" ", 1)[0] + "…"
        if not c["de"]:
            titular = f"NUEVA {tipo_corto(ini['t']).upper()} DE {grupo_corto(ini['a']).upper()}: {tema_corto.upper()}"
            entradilla = f"Registrada en el Congreso el {fmt_date_es(ini['fp'])}." if ini.get("fp") else "Registrada en el Congreso."
        elif ini.get("cerrado"):
            res = resultado(ini) or "cerrada"
            titular = f"{tipo_corto(ini['t']).upper()} {tema_corto.upper()}: {res.upper()}"
            entradilla = f"Termina la tramitación de la iniciativa de {grupo_corto(ini['a'])}."
        else:
            partes = c["a"].split(" · ")
            destino = (f"FASE DE {partes[-1].upper()} ({' · '.join(partes[:-1]).upper()})"
                       if len(partes) > 1 else c["a"].upper())
            titular = f"{tipo_corto(ini['t']).upper()} {tema_corto.upper()}: ENTRA EN {destino}"
            entradilla = f"Antes estaba en «{c['de']}». Autor: {ini['a']}."
        plazo = next((p for p in ini.get("plazos") or [] if p[0] >= hoy), None)
        cuerpo = [f"{tipo_corto(ini['t'])} {c['exp']}, presentada por {ini['a']}."]
        if plazo:
            cuerpo.append(f"Plazo abierto hasta el {fmt_date_es(plazo[0])}: {plazo[2] or 'sin detalle'}.")
        piezas.append({
            "chamber": "congreso", "type": "Tramitación",
            "date": fmt_date_es(hoy),
            "headline": " ".join(titular.split()),
            "standfirst": entradilla,
            "body": cuerpo,
            "source": {"label": f"Seguimiento de la iniciativa {c['exp']}",
                       "url": f"{site_url}iniciativas/{slug(c['exp'])}.html"},
        })
    return piezas


# ---------------------------------------------------------------------- páginas

def generar_paginas(h: dict) -> list:
    """/iniciativas/: índice, una página por iniciativa, leyes aprobadas, una
    página por autor y la metodología. `h` trae las utilidades de build.py."""
    e = cargar()
    ini = e.get("ini") or {}
    if not ini:
        return []
    esc, attr, fecha = h["esc_html"], h["esc_attr"], h["fmt_date_es"]
    site, plantilla, carpeta = h["site_url"], h["plantilla"], h["carpeta"]
    carpeta.mkdir(exist_ok=True)
    detalle = h.get("detalle") or []
    pag_vot = h.get("pagina_votacion")
    normas = h.get("normas_por_ley") or {}       # «Ley 3/2026» -> ruta normas/...
    hoy = dt.date.today().isoformat()
    salidas = []

    def ultima(v):
        fechas = [p[1] for p in v.get("pasos") or [] if p[1]] + [v.get("fp") or ""]
        return max(fechas) if fechas else ""

    def pagina(nombre, ruta, titulo, desc, h1, kicker, entradilla, ficha, cuerpo, lastmod,
               miga, jsonld, fuente):
        url = f"{site}{ruta}"
        h["pagina_suelta"](plantilla, carpeta, nombre, {
            "TITLE": esc(titulo), "META_DESC": attr(desc[:155]), "CANONICAL": url,
            "JSONLD": h["jsonld_script"](jsonld),
            "EDITION_DATE": esc(f"Datos al {fecha(lastmod or hoy)}"),
            "MIGA": miga, "KICKER": esc(kicker), "HEADLINE": esc(h1),
            "STANDFIRST": esc(entradilla), "FICHA": ficha, "CUERPO": cuerpo, "FUENTE": fuente,
            "RELACIONADAS": "", "RELACIONADAS_HIDDEN": "hidden",
        })
        salidas.append({"url": url, "lastmod": lastmod or hoy})

    fuente = ('Fuente: datos abiertos de iniciativas del Congreso de los Diputados. '
              '<a class="srclink" href="/iniciativas/metodologia.html">Cómo se hace</a>.')

    def fila(exp, v, extra=""):
        return (f'<li><a href="/iniciativas/{attr(slug(exp))}.html">{esc(nucleo(v["o"]) or v["o"])}</a>'
                f'<span class="ref">{esc(tipo_corto(v["t"]))} · {esc(grupo_corto(v["a"]))} · '
                f'{esc(exp)}{extra}</span></li>')

    # ------------------------------------------------------ una por iniciativa
    for exp, v in ini.items():
        lm = ultima(v) or v.get("fp") or hoy
        pasos_html = "".join(
            f'<li><b>{esc(p[0])}</b> <span class="ref">'
            + (f'desde el {esc(fecha(p[1]))}' if p[1] else "")
            + (f' hasta el {esc(fecha(p[2]))}' if p[2] else (" · en curso" if p[1] and not v["cerrado"] and i == len(v["pasos"]) - 1 else ""))
            + '</span></li>' for i, p in enumerate(v.get("pasos") or []))
        plazos_abiertos = [p for p in v.get("plazos") or [] if p[0] >= hoy]
        plazos_html = "".join(
            f'<li>{esc(p[2] or "Plazo")}: hasta el {esc(fecha(p[0]))}{(" a las " + esc(p[1])) if p[1] else ""}'
            + (' <span class="ref">abierto</span>' if p in plazos_abiertos else ' <span class="ref">vencido</span>')
            + '</li>' for p in v.get("plazos") or [])
        vots = votaciones_de(v, detalle)
        vots_html = "".join(
            f'<li><a href="/votaciones/{attr(pag_vot(d))}">{esc(d.get("t") or "Votación")}</a>'
            f'<span class="ref">{esc(fecha(d["f"]))}</span></li>' for d in vots[:20]) if pag_vot else ""
        ley = ley_de(v, e.get("leyes"))
        ley_html = ""
        if ley:
            m = re.match(r"(Ley(?: Orgánica)? \d+/\d{4})", ley["titulo"])
            ruta_norma = normas.get(m.group(1)) if m else None
            ley_html = (f'<h2 class="rotulo">Ley aprobada</h2><p>{esc(ley["titulo"])} '
                        f'<span class="ref">BOE núm. {esc(ley["boe"])} del {esc(fecha(ley["fb"]))}</span></p>'
                        + (f'<p><a class="srclink" href="/{attr(ruta_norma)}">Ficha de la norma en La Tercera Cámara →</a></p>' if ruta_norma else "")
                        + (f'<p><a class="srclink" href="{attr(ley["pdf"])}" target="_blank" rel="noopener">Texto de la ley ↗</a></p>' if ley.get("pdf") else ""))
        relacionadas = "".join(
            f'<li><a href="/iniciativas/{attr(slug(r))}.html">{esc(nucleo(ini[r]["o"]))}</a>'
            f'<span class="ref">{esc(r)}</span></li>' for r in v.get("rel") or [] if r in ini and r != exp)
        bocg = "".join(f'<li><a href="{attr(u)}" target="_blank" rel="noopener">{esc(u.rsplit("/", 1)[-1])}</a></li>'
                       for u in v.get("bocg") or [])
        estado = ("Cerrada" + (f": {resultado(v)}" if resultado(v) else "")) if v["cerrado"] else (v["sit"] or "—")
        cuerpo = (
            f'<h2 class="rotulo">Situación</h2><p><b>{esc(estado)}</b></p>'
            + (f'<h2 class="rotulo">De qué habla el texto</h2><p class="rk-nota">Las expresiones que más '
               f'se repiten en el texto publicado en el Boletín de las Cortes: '
               f'{esc(", ".join(v["kw"]))}.</p>' if v.get("kw") else "")
            + (f'<h2 class="rotulo">Plazos</h2><ul class="indice">{plazos_html}</ul>' if plazos_html else "")
            + f'<h2 class="rotulo">Tramitación</h2><ol class="indice">{pasos_html}</ol>'
            + ley_html
            + (f'<h2 class="rotulo">Votaciones en el Pleno</h2><ul class="indice">{vots_html}</ul>' if vots_html else "")
            + (f'<h2 class="rotulo">Iniciativas relacionadas</h2><ul class="indice">{relacionadas}</ul>' if relacionadas else "")
            + (f'<h2 class="rotulo">Publicaciones en el Boletín de las Cortes</h2><ul class="indice">{bocg}</ul>' if bocg else "")
            + f'<p><a class="srclink" href="{attr(url_ficha(exp))}" target="_blank" rel="noopener">Ficha oficial en el Congreso ↗</a></p>')
        ficha = (f"<dt>Tipo</dt><dd>{esc(v['t'])}</dd><dt>Autor</dt><dd>{esc(v['a'])}</dd>"
                 f"<dt>Expediente</dt><dd>{esc(exp)}</dd>"
                 + (f"<dt>Presentada</dt><dd>{esc(fecha(v['fp']))}</dd>" if v.get("fp") else "")
                 + (f"<dt>Comisión</dt><dd>{esc(v['com'])}</dd>" if v.get("com") else "")
                 + (f"<dt>Tramitación</dt><dd>{esc(v['trt'])}</dd>" if v.get("trt") else "")
                 + (f"<dt>Ponentes</dt><dd>{esc(v['pon'])}</dd>" if v.get("pon") else ""))
        tema = nucleo(v["o"]) or v["o"]
        pagina(f"{slug(exp)}.html", f"iniciativas/{slug(exp)}.html",
               f"{tipo_corto(v['t'])} {tema[:70]}: tramitación | La Tercera Cámara",
               f"{v['o']} Presentada por {v['a']}. Situación: {estado}.",
               v["o"], tipo_corto(v["t"]),
               f"Presentada por {v['a']}" + (f" el {fecha(v['fp'])}" if v.get("fp") else "") + f". {estado}.",
               ficha, cuerpo, lm,
               ('<a href="../">Portada</a> › <a href="./">Leyes en tramitación</a> › '
                f'<span aria-current="page">{esc(exp)}</span>'),
               [{"@type": "Legislation", "name": v["o"], "legislationIdentifier": exp,
                 "url": f"{site}iniciativas/{slug(exp)}.html", "inLanguage": "es-ES",
                 "legislationJurisdiction": "ES",
                 **({"legislationDate": v["fp"]} if v.get("fp") else {})}],
               fuente)

    # ----------------------------------------------------------------- índice
    abiertas = {k: v for k, v in ini.items() if not v["cerrado"]}
    cerradas = {k: v for k, v in ini.items() if v["cerrado"]}
    plazos_ab = sorted(((p[0], k, v, p) for k, v in abiertas.items()
                        for p in v.get("plazos") or [] if p[0] >= hoy), key=lambda x: x[0])
    corte = (dt.date.fromisoformat(hoy) - dt.timedelta(days=DIAS_NOVEDADES)).isoformat()
    recientes = sorted(((ultima(v), k, v) for k, v in ini.items() if ultima(v) >= corte), reverse=True)
    por_fase: dict = {}
    for k, v in abiertas.items():
        por_fase.setdefault(fase(v), []).append((k, v))
    bloques = []
    if plazos_ab:
        vistos = set()
        lis = []
        for f, k, v, p in plazos_ab:
            if k in vistos:
                continue
            vistos.add(k)
            lis.append(fila(k, v, f' · {esc(p[2] or "plazo")} hasta el {esc(fecha(f))}'))
        bloques.append(f'<h2 class="rotulo" id="plazos">Plazos abiertos</h2><ul class="indice">{"".join(lis[:60])}</ul>')
    if recientes:
        bloques.append(f'<h2 class="rotulo" id="novedades">Movimiento en los últimos {DIAS_NOVEDADES} días</h2><ul class="indice">'
                       + "".join(fila(k, v, f' · {esc(fase(v).lower())} · {esc(fecha(f))}') for f, k, v in recientes[:60]) + "</ul>")
    for nombre in ORDEN_FASES:
        lista_f = sorted(por_fase.get(nombre, []), key=lambda x: ultima(x[1]), reverse=True)
        if lista_f:
            bloques.append(f'<h2 class="rotulo">{esc(nombre)} ({len(lista_f)})</h2><ul class="indice">'
                           + "".join(fila(k, v) for k, v in lista_f) + "</ul>")
    autores: dict = {}
    for k, v in ini.items():
        autores.setdefault(v["a"] or "Sin autor", []).append((k, v))
    enlaces_aut = "".join(
        f'<li><a href="autor-{attr(cd._slug(a)[:60])}.html">{esc(grupo_corto(a))}</a><span class="ref">{len(l)}</span></li>'
        for a, l in sorted(autores.items(), key=lambda x: -len(x[1])))
    lm_indice = max((ultima(v) for v in ini.values()), default=hoy) or hoy
    pagina("index.html", "iniciativas/", "Leyes en tramitación en el Congreso | La Tercera Cámara",
           f"Seguimiento de las {len(ini)} iniciativas legislativas de la legislatura: {len(abiertas)} "
           "en tramitación, en qué fase está cada una, plazos de enmiendas y leyes aprobadas.",
           "Leyes en tramitación", "Seguimiento legislativo",
           "Cada proyecto y proposición de ley de la legislatura: en qué fase está, qué plazos "
           "tiene abiertos, qué se ha votado y cómo acaba.",
           (f"<dt>En tramitación</dt><dd>{len(abiertas)}</dd><dt>Cerradas</dt><dd>{len(cerradas)}</dd>"
            f"<dt>Leyes aprobadas</dt><dd>{len(e.get('leyes') or [])}</dd>"),
           (f'<p class="aside-note"><a class="srclink" href="aprobadas.html">Leyes aprobadas</a> · '
            f'<a class="srclink" href="cerradas.html">Cerradas y retiradas</a> · '
            f'<a class="srclink" href="#autores">Por autor</a> · '
            f'<a class="srclink" href="metodologia.html">Cómo se hace</a></p>'
            + "".join(bloques)
            + f'<h2 class="rotulo" id="autores">Por autor</h2><ul class="provincias">{enlaces_aut}</ul>'),
           lm_indice,
           '<a href="../">Portada</a> › <span aria-current="page">Leyes en tramitación</span>',
           [{"@type": "CollectionPage", "name": "Leyes en tramitación en el Congreso",
             "url": f"{site}iniciativas/", "inLanguage": "es-ES", "dateModified": lm_indice}],
           fuente)

    # --------------------------------------------------------------- cerradas
    lis = "".join(fila(k, v, f' · {esc(resultado(v) or "cerrada")} · {esc(fecha(ultima(v)))}')
                  for k, v in sorted(cerradas.items(), key=lambda x: ultima(x[1]), reverse=True))
    pagina("cerradas.html", "iniciativas/cerradas.html",
           "Iniciativas legislativas cerradas: aprobadas, rechazadas y retiradas | La Tercera Cámara",
           f"Las {len(cerradas)} iniciativas legislativas de la legislatura que ya han terminado su "
           "tramitación, con su resultado.",
           "Iniciativas cerradas", "Seguimiento legislativo",
           "Las que ya han terminado: aprobadas, rechazadas, retiradas o decaídas.",
           f"<dt>Cerradas</dt><dd>{len(cerradas)}</dd>",
           f'<ul class="indice">{lis}</ul>', lm_indice,
           '<a href="../">Portada</a> › <a href="./">Leyes en tramitación</a> › <span aria-current="page">Cerradas</span>',
           [{"@type": "CollectionPage", "name": "Iniciativas cerradas", "url": f"{site}iniciativas/cerradas.html"}],
           fuente)

    # --------------------------------------------------------------- aprobadas
    leyes = sorted(e.get("leyes") or [], key=lambda l: l.get("fb") or "", reverse=True)
    por_titulo = {}
    for k, v in cerradas.items():
        l = ley_de(v, leyes)
        if l:
            por_titulo[l["titulo"]] = k
    lis = []
    for l in leyes:
        m = re.match(r"(Ley(?: Orgánica)? \d+/\d{4})", l["titulo"])
        ruta_norma = normas.get(m.group(1)) if m else None
        k = por_titulo.get(l["titulo"])
        destino = (f"/iniciativas/{slug(k)}.html" if k else (f"/{ruta_norma}" if ruta_norma else l.get("pdf") or ""))
        lis.append(f'<li><a href="{attr(destino)}">{esc(l["titulo"])}</a>'
                   f'<span class="ref">BOE núm. {esc(l["boe"])} · {esc(fecha(l["fb"]))}</span></li>')
    pagina("aprobadas.html", "iniciativas/aprobadas.html",
           "Leyes aprobadas en la legislatura | La Tercera Cámara",
           f"Las {len(leyes)} leyes aprobadas por las Cortes en la XV legislatura, con su publicación en el BOE.",
           "Leyes aprobadas", "Seguimiento legislativo",
           "Lo que ha salido de las Cortes convertido en ley, de la más reciente a la más antigua.",
           f"<dt>Leyes</dt><dd>{len(leyes)}</dd>",
           f'<ul class="indice">{"".join(lis)}</ul>', (leyes[0].get("fb") if leyes else hoy) or hoy,
           '<a href="../">Portada</a> › <a href="./">Leyes en tramitación</a> › <span aria-current="page">Aprobadas</span>',
           [{"@type": "CollectionPage", "name": "Leyes aprobadas", "url": f"{site}iniciativas/aprobadas.html"}],
           fuente)

    # ------------------------------------------------------------- por autor
    for a, lista_a in autores.items():
        nombre = f"autor-{cd._slug(a)[:60]}.html"
        ab = [(k, v) for k, v in lista_a if not v["cerrado"]]
        ce = [(k, v) for k, v in lista_a if v["cerrado"]]
        cuerpo = (f'<h2 class="rotulo">En tramitación ({len(ab)})</h2><ul class="indice">'
                  + "".join(fila(k, v, f' · {esc(fase(v).lower())}') for k, v in sorted(ab, key=lambda x: ultima(x[1]), reverse=True))
                  + f'</ul><h2 class="rotulo">Cerradas ({len(ce)})</h2><ul class="indice">'
                  + "".join(fila(k, v, f' · {esc(resultado(v) or "cerrada")}') for k, v in sorted(ce, key=lambda x: ultima(x[1]), reverse=True))
                  + "</ul>")
        pagina(nombre, f"iniciativas/{nombre}",
               f"Iniciativas legislativas de {grupo_corto(a)} | La Tercera Cámara",
               f"Proyectos y proposiciones de ley presentados por {a} en la legislatura: {len(ab)} en tramitación y {len(ce)} cerrados.",
               grupo_corto(a), "Seguimiento legislativo",
               f"Lo que ha presentado {a} y en qué punto está cada iniciativa.",
               f"<dt>En tramitación</dt><dd>{len(ab)}</dd><dt>Cerradas</dt><dd>{len(ce)}</dd>",
               cuerpo, max((ultima(v) for _k, v in lista_a), default=hoy),
               ('<a href="../">Portada</a> › <a href="./">Leyes en tramitación</a> › '
                f'<span aria-current="page">{esc(grupo_corto(a))}</span>'),
               [{"@type": "CollectionPage", "name": f"Iniciativas de {a}", "url": f"{site}iniciativas/{nombre}"}],
               fuente)

    # ------------------------------------------------------------ metodología
    pagina("metodologia.html", "iniciativas/metodologia.html",
           "Seguimiento legislativo: metodología | La Tercera Cámara",
           "De dónde sale el seguimiento de leyes en tramitación, qué incluye y qué limitaciones tiene.",
           "Cómo se hace el seguimiento legislativo", "Metodología",
           "Fuente, alcance y limitaciones.",
           f"<dt>Iniciativas</dt><dd>{len(ini)}</dd><dt>Actualizado</dt><dd>{esc(fecha(e.get('actualizado') or hoy))}</dd>",
           ('<h2 class="rotulo">Fuente</h2><p>Los ficheros de datos abiertos de iniciativas del Congreso de los '
            'Diputados (proyectos de ley, proposiciones de ley, propuestas de reforma de Estatutos y leyes '
            'aprobadas), que el Congreso regenera cada día. Se descargan en cada edición.</p>'
            '<h2 class="rotulo">Qué se muestra</h2><p>Para cada iniciativa de la legislatura: el objeto, el autor, '
            'la situación actual, la tramitación seguida paso a paso con sus fechas, los plazos (de enmiendas, del '
            'criterio del Gobierno…), las publicaciones en el Boletín Oficial de las Cortes, las votaciones del '
            'Pleno cuyo asunto la cita y, si acabó en ley, la ley y su publicación en el BOE.</p>'
            '<h2 class="rotulo">Novedades del día</h2><p>Se comparan la situación de cada iniciativa con la del día '
            'anterior; las nuevas y las que cambian de fase salen en «Las Cortes hoy».</p>'
            '<h2 class="rotulo">Limitaciones</h2><p>Solo el Congreso: la tramitación en el Senado aparece como una '
            'fase más, sin su detalle. Las votaciones se relacionan por el texto del asunto, así que puede faltar '
            'alguna si el Congreso la titula de otra manera. La ley aprobada se casa por el título, y solo se muestra '
            'si coincide. No se resume ni se interpreta el contenido de las iniciativas: el texto está en el '
            'Boletín de las Cortes, enlazado en cada ficha.</p>'),
           e.get("actualizado") or hoy,
           '<a href="../">Portada</a> › <a href="./">Leyes en tramitación</a> › <span aria-current="page">Metodología</span>',
           [{"@type": "WebPage", "name": "Seguimiento legislativo: metodología", "url": f"{site}iniciativas/metodologia.html"}],
           'Fuente: Congreso de los Diputados.')

    h["log"](f"iniciativas/: {len(ini)} fichas, {len(autores)} autores")
    return salidas


def entradas_buscador(entrada, e: dict | None = None) -> list:
    """Filas para el índice del buscador: título, autor y situación."""
    e = e or cargar()
    out = []
    for exp, v in (e.get("ini") or {}).items():
        estado = (resultado(v) or "cerrada") if v["cerrado"] else fase(v)
        fechas = [p[1] for p in v.get("pasos") or [] if p[1]]
        out.append(entrada(v["o"], f"{tipo_corto(v['t'])} · {grupo_corto(v['a'])} · {estado}",
                           f"iniciativas/{slug(exp)}.html", "iniciativa",
                           max(fechas) if fechas else (v.get("fp") or ""),
                           f"{exp} {v['a']} {' '.join(v.get('kw') or [])}", largo=320))
    return out
