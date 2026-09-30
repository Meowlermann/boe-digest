"""Lo que contesta el Gobierno a las preguntas parlamentarias del Congreso.

preguntas.py cuenta qué se pregunta y cuándo se contesta; este módulo guarda
QUÉ se contesta, siempre con citas literales cortas y el enlace al original.
Determinista: sin modelo, sin APIs de pago y sin dependencias nuevas (pypdf
ya estaba en requirements.txt).

(A) Orales, en la sesión de control del Pleno. Cada fila del volcado de
    intervenciones (IntervencionesCronologicamente) trae ENLACETEXTOINTEGRO:
    el Diario de Sesiones de esa sesión en HTML, en el buscador de
    intervenciones del Congreso. Una descarga por sesión (unos 450 KB) basta
    para todas sus preguntas. Estructura comprobada en las 64 sesiones de
    control de la XV Legislatura (diciembre de 2023 a septiembre de 2026):
      - párrafos separados por <br><br>;
      - cada pregunta empieza con un rótulo en mayúsculas que termina en
        «(Número de expediente 180/001178).»; el sumario del principio repite
        los rótulos en minúsculas, así que se busca el que va en mayúsculas;
      - cada turno de palabra empieza por «La señora GAMARRA RUIZ-CLAVIJO:» o
        «La señora MINISTRA DE DEFENSA (Robles Fernández):»; los párrafos sin
        rótulo siguen el turno anterior;
      - «Página 33» sueltos marcan el salto de página del PDF.
    Resultado: 1.081 de 1.089 preguntas con contestación localizada. Las ocho
    restantes son preguntas acumuladas con otro rótulo o con el ministro
    ausente; se guardan sin cita, no se inventa nada.

(B) Escritas (184/…). Cuando la contestación se publica, la ficha de la
    pregunta en el buscador de iniciativas enlaza un PDF propio
    («Contestación», /l15p/e12/e_…_n_000.pdf) con la respuesta del Gobierno:
    una cabecera («RESPUESTA DEL GOBIERNO», expediente, autores), el texto
    tras «RESPUESTA:» y el cierre «Madrid, 27 de agosto de 2026». Suele
    aparecer dos o tres semanas después de que la ficha registre la fecha de
    contestación, así que se reintenta cada pocos días.

Qué se guarda: solo citas (unos 400 caracteres por turno), autor, fecha y
enlaces. Nunca el texto completo ni los PDF: el original está a un clic y el
repositorio no crece sin control.

Dónde: state/respuestas/AAAA.json, un fichero por año (de la sesión o de la
contestación). Así ningún fichero crece sin límite y el histórico de un año
cerrado deja de reescribirse. Esquema en ARQUITECTURA.md.
"""

from __future__ import annotations

import datetime as dt
import html as html_mod
import json
import pathlib
import re
import time

import congreso_datos as cd

ROOT = pathlib.Path(__file__).parent
DIR = ROOT / "state" / "respuestas"
ESQUEMA = 1

# Presupuesto por ejecución (la edición corre tres veces al día).
MAX_SESIONES = 4            # Diarios de Sesiones descargados por ejecución
MAX_PETICIONES_ESCRITAS = 80  # fichas + PDF de contestación
REINTENTO_DIAS = 3          # días entre intentos de una contestación sin PDF
LARGO_CITA = 400            # caracteres por cita oral
LARGO_CITA_ESCRITA = 500
# Una contestación que llega meses tarde no es noticia de portada: va a las
# páginas, no al feed.
NOTICIA_DIAS = 45


# --------------------------------------------------------------- almacén

_CACHE: dict = {}


def _ruta(anio: str) -> pathlib.Path:
    return DIR / f"{anio}.json"


def cargar(anio: str) -> dict:
    """El fichero de un año, con la forma completa aunque no exista."""
    if anio in _CACHE:
        return _CACHE[anio]
    try:
        d = json.loads(_ruta(anio).read_text(encoding="utf-8"))
    except Exception:                                          # noqa: BLE001
        d = {}
    d.setdefault("esquema", ESQUEMA)
    d.setdefault("orales", {})
    d.setdefault("sesiones", {})
    d.setdefault("escritas", {})
    _CACHE[anio] = d
    return d


def anios() -> list:
    """Años con fichero, del más reciente al más antiguo."""
    en_disco = {p.stem for p in DIR.glob("*.json") if re.fullmatch(r"\d{4}", p.stem)}
    return sorted(en_disco | set(_CACHE), reverse=True)


def guardar(anio: str) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    d = cargar(anio)
    d["actualizado"] = dt.date.today().isoformat()
    _ruta(anio).write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":"),
                                      sort_keys=True), encoding="utf-8")


def oral(exp: str) -> dict | None:
    """La contestación guardada de una pregunta oral, o None."""
    exp = _exp10(exp)
    for a in anios():
        r = cargar(a)["orales"].get(exp)
        if r:
            return r
    return None


def escrita(exp: str) -> dict | None:
    for a in anios():
        r = cargar(a)["escritas"].get(exp)
        if r:
            return r
    return None


def _exp10(exp: str) -> str:
    """«180/001178/0000» -> «180/001178»."""
    m = re.match(r"\s*(\d{3}/\d{6})", exp or "")
    return m.group(1) if m else (exp or "").strip()


# ------------------------------------------------------------ texto y citas

# Acotaciones del Diario de Sesiones: no son palabras de quien habla. Se
# quitan de las citas (y la metodología lo dice).
ACOTACION = re.compile(
    r"\s*\((?:Aplaus|Rumor|Protest|Risa|Pausa|Un señor|Una señora|Varios|Varias|"
    r"El señor|La señora|El orador|La oradora|Muestra|Denegaci|Asentimiento|"
    r"Continúa|Fuertes|Prolongad|Grandes|Golpes|Palmas|Pronuncia|Pite|Abuche)"
    r"[^()]{0,200}\)(\.?)")
CORTESIA = re.compile(
    r"^(?:(?:Muchas|Muchísimas)\s+)?gracias(?:,?\s+(?:señora|señor)?\s*"
    r"(?:presidenta|presidente))?\s*[.,!;]\s*", re.I)
FIN_FRASE = re.compile(r"(?<=[.!?…»])\s+(?=[¿¡«\"“A-ZÁÉÍÓÚÑ])")


def limpiar(texto: str) -> str:
    """Sin acotaciones, sin marcas de página y con los espacios normalizados.
    Si la acotación cerraba la frase («…justicia (Aplausos). Ya…»), el punto
    se conserva."""
    def _quitar(m):
        antes = texto[:m.start()].rstrip()
        return "." if m.group(1) and antes and antes[-1] not in ".!?…:;," else " "
    t = ACOTACION.sub(_quitar, texto)
    t = re.sub(r"\(P[áa]gina\s*\d+\)", " ", t)
    t = re.sub(r"\s+([.,;:])", r"\1", t)
    return " ".join(t.split())


def cita(texto: str, largo: int = LARGO_CITA) -> str:
    """Las primeras frases enteras hasta `largo` caracteres, sin el «Gracias,
    señora presidenta» del principio. Si la primera frase ya es más larga, se
    corta en una palabra y se marca con «…». Literal: no se reescribe nada."""
    t = limpiar(texto)
    for _ in range(2):
        t2 = CORTESIA.sub("", t, count=1)
        if t2 == t:
            break
        t = t2
    if not t:
        return ""
    t = t[0].upper() + t[1:]
    frases = FIN_FRASE.split(t)
    salida = ""
    for f in frases:
        if len(salida) + len(f) + 1 > largo:
            break
        salida = f"{salida} {f}".strip()
    if not salida:
        salida = t[:largo].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    elif len(salida) < len(t):
        salida += " […]"
    return salida


# ----------------------------------------------------------- (A) orales

ROTULO = re.compile(r"^(?:el|la)\s+señora?\s+([^:]{2,200}?):\s*", re.I)


def parrafos(html: str) -> list:
    """Los párrafos del texto íntegro, en orden, sin marcas de página."""
    trozos = re.split(r"<br\s*/?>\s*<br\s*/?>", html or "", flags=re.I)
    salida = []
    for t in trozos:
        t = html_mod.unescape(re.sub(r"<[^>]+>", " ", t))
        t = " ".join(t.split())
        if t and not re.fullmatch(r"P[áa]gina\s*\d+", t):
            salida.append(t)
    return salida


def _es_rotulo_pregunta(p: str) -> bool:
    """«- DE LA DIPUTADA DOÑA … (Número de expediente 180/001178).»: lo de
    antes del paréntesis va en mayúsculas. En el sumario, no."""
    antes = p.split("(Número")[0]
    return len(antes) > 15 and antes == antes.upper() and not ROTULO.match(p)


def turnos(pars: list, exp: str) -> list:
    """[(rótulo, texto)] de la pregunta `exp`, desde su rótulo hasta el
    siguiente. Vacío si no se encuentra el rótulo."""
    exp = _exp10(exp)
    inicio = None
    for i, p in enumerate(pars):
        if f"expediente {exp})" in p and _es_rotulo_pregunta(p):
            inicio = i
    if inicio is None:
        return []
    salida: list = []
    for p in pars[inicio + 1:]:
        if _es_rotulo_pregunta(p):
            break
        m = ROTULO.match(p)
        if m:
            salida.append([" ".join(m.group(1).split()), p[m.end():]])
        elif salida:
            salida[-1][1] += " " + p
    return [tuple(t) for t in salida]


def es_gobierno(rotulo: str) -> bool:
    """«MINISTRA DE DEFENSA (Robles Fernández)», «PRESIDENTE DEL GOBIERNO
    (Sánchez Pérez-Castejón)». La presidencia de la Cámara («PRESIDENTA»,
    «VICEPRESIDENTA (Gil Lázaro)») no lleva GOBIERNO ni MINISTR."""
    return "(" in rotulo and bool(re.search(r"MINISTR|GOBIERNO", rotulo))


def es_presidencia(rotulo: str) -> bool:
    return bool(re.match(r"(?:VICE)?PRESIDENT[AE]\b", rotulo)) and not es_gobierno(rotulo)


def intercambio(ts: list) -> dict:
    """De los turnos, las tres citas que cuentan la pregunta: la contestación
    del Gobierno (c1), la réplica de quien pregunta (r) y la dúplica del
    Gobierno (c2). La primera intervención del diputado es la formulación, que
    ya se publica literal desde el volcado."""
    gob = [(r, t) for r, t in ts if es_gobierno(r)]
    dip = [(r, t) for r, t in ts if not es_gobierno(r) and not es_presidencia(r)]
    d: dict = {}
    if gob:
        d["c1"] = cita(gob[0][1])
        m = re.search(r"\(([^)]+)\)", gob[0][0])
        d["quien"] = m.group(1).strip() if m else ""
        if len(gob) > 1:
            d["c2"] = cita(gob[-1][1])
    if len(dip) > 1:
        d["r"] = cita(dip[1][1])
    return {k: v for k, v in d.items() if v}


def sesiones_en_volcado(filas: list) -> list:
    """Fechas (AAAA-MM-DD) de las sesiones de control del Pleno que trae el
    volcado, de la más reciente a la más antigua."""
    fechas = {cd._fecha_ddmmaaaa(f.get("SESION", "")) for f in filas
              if (f.get("TIPOINICIATIVA") or "").startswith("Pregunta oral en Pleno")
              and (f.get("ORGANO") or "").strip() == "Pleno"}
    return sorted(fechas - {""}, reverse=True)


def leer_sesion(ses: dict, get, log) -> dict | None:
    """{exp: registro} de una sesión ya agrupada por cd.preguntas_orales().
    None si el Diario de Sesiones no se pudo descargar."""
    url = next((p.get("txt") for p in ses["preguntas"] if p.get("txt")), "")
    if not url:
        return None
    r = get(url.split("#")[0], tries=1)
    if not r:
        log(f"  respuestas orales: sin texto íntegro del {ses['fecha']}")
        return None
    pars = parrafos(r.text)
    salida = {}
    for p in ses["preguntas"]:
        exp = _exp10(p["expediente"])
        reg = {"s": ses["fecha"], "h": p.get("hora", ""),
               "a": p.get("autor_natural", ""), "g": p.get("grupo", ""),
               "slug": p.get("slug", ""), "t": (p.get("texto") or "")[:400],
               "gob": cd.nombre_natural(p.get("contesta", "")) if p.get("contesta") else "",
               "cargo": p.get("cargo", ""), "pdf": p.get("pdf", ""),
               "txt": url.split("#")[0]}
        reg.update(intercambio(turnos(pars, exp)))
        salida[exp] = {k: v for k, v in reg.items() if v}
    return salida


def actualizar_orales(filas: list, censo: dict, get, log,
                      max_sesiones: int = MAX_SESIONES) -> int:
    """Lee los Diarios de Sesiones que falten, de la sesión más reciente
    hacia atrás. La más reciente va siempre primero: es la que sale hoy en
    portada. Devuelve cuántas sesiones se han leído."""
    hechas = set()
    for a in anios():
        hechas |= set(cargar(a)["sesiones"])
    pendientes = [f for f in sesiones_en_volcado(filas) if f not in hechas]
    leidas = 0
    hoy = dt.date.today().isoformat()
    for fecha in pendientes[:max_sesiones]:
        ses = cd.preguntas_orales(filas, censo, fecha=fecha)
        if not ses:
            continue
        regs = leer_sesion(ses, get, log)
        if regs is None:
            continue                       # se reintenta en la próxima ejecución
        almacen = cargar(fecha[:4])
        almacen["orales"].update(regs)
        almacen["sesiones"][fecha] = {"n": len(regs),
                                      "con_texto": sum(1 for r in regs.values() if r.get("c1")),
                                      "leida": hoy}
        guardar(fecha[:4])
        leidas += 1
        time.sleep(cd.PAUSA_BUSCADOR)
    total = sum(len(cargar(a)["sesiones"]) for a in anios())
    log(f"respuestas orales: {leidas} sesiones leídas hoy, {total} en el archivo, "
        f"{max(0, len(pendientes) - leidas)} pendientes")
    return leidas


# ---------------------------------------------------------- (B) escritas

ENLACE_CONTESTACION = re.compile(
    r'href="([^"]*/l15p/[^"]+\.pdf)"[^>]*>(?:\s|<[^>]+>)*Contestaci[óo]n', re.I)


def enlace_contestacion(html: str) -> str | None:
    """El PDF de la contestación en la ficha de una pregunta escrita, con la
    URL completa. None si todavía no se ha publicado."""
    m = ENLACE_CONTESTACION.search(html or "")
    if not m:
        return None
    u = m.group(1)
    return u if u.startswith("http") else cd.CONGRESO + u


def extraer_escrita(texto: str) -> dict | None:
    """{"cita", "pal"} del PDF de una contestación. None si el PDF no tiene
    texto extraíble (escaneado) o no sigue el formato."""
    t = texto or ""
    m = re.search(r"RESPUESTA\s*:\s*", t)
    if not m:
        return None
    cuerpo = t[m.end():]
    fin = re.search(r"\n\s*Madrid,\s*\d{1,2}\s+de\s+[a-záéíóú]+\s+de\s+\d{4}", cuerpo, re.I)
    if fin:
        cuerpo = cuerpo[:fin.start()]
    # La cabecera se repite en cada página.
    cuerpo = re.sub(r"SECRETAR[ÍI]A DE ESTADO DE\s+RELACIONES CON LAS CORTES.{0,120}?"
                    r"CONSTITUCIONALES", " ", cuerpo, flags=re.S)
    cuerpo = " ".join(cuerpo.split())
    if len(cuerpo) < 20:
        return None
    return {"cita": cita(cuerpo, LARGO_CITA_ESCRITA), "pal": len(cuerpo.split())}


def actualizar_escritas(get, pdf_text, log, max_peticiones: int = MAX_PETICIONES_ESCRITAS) -> list:
    """Busca el texto de las contestaciones escritas que aún no lo tienen.

    Recorre las preguntas contestadas de state/preguntas_escritas.json sin
    registro aquí: primero las que ya tienen PDF o boletín de contestación,
    después el resto, de la contestación más antigua a la más reciente. Si la ficha aún
    no enlaza el PDF, se anota la fecha del intento («rt») y se vuelve dentro
    de REINTENTO_DIAS. Devuelve los expedientes con texto nuevo hoy."""
    import preguntas as pq
    e = pq.cargar_escritas()
    hoy = dt.date.today()
    hoy_s = hoy.isoformat()
    cand = [(k, v) for k, v in e["exp"].items() if v.get("c") and not escrita(k)]
    # Orden: primero las que ya tienen el PDF localizado o el boletín de la
    # contestación en la ficha («cb»): su texto existe. Después, de la
    # contestación más antigua a la más reciente, porque el PDF tarda dos o
    # tres semanas en aparecer; empezar por las de ayer gastaba el
    # presupuesto en fichas que aún no lo enlazan (comprobado: 80 de 80 el
    # 30 de septiembre de 2026). Las recientes se reintentan cada
    # REINTENTO_DIAS y entran en cuanto el PDF sale.
    cand.sort(key=lambda kv: (not (kv[1].get("cu") or kv[1].get("cb")), kv[1]["c"]))
    peticiones, nuevos, sin_pdf, tocados = 0, [], 0, set()
    for exp, v in cand:
        if peticiones >= max_peticiones:
            break
        url = v.get("cu")
        if not url:
            rt = v.get("rt")
            if rt and (hoy - dt.date.fromisoformat(rt)).days < REINTENTO_DIAS:
                continue
            r = get(pq.url_ficha(exp), tries=1)
            peticiones += 1
            v["rt"] = hoy_s
            url = enlace_contestacion(r.text) if r else None
            if not url:
                sin_pdf += 1
                continue
            v["cu"] = url
            time.sleep(cd.PAUSA_BUSCADOR)
        texto = pdf_text(url)
        peticiones += 1
        datos = extraer_escrita(texto)
        almacen = cargar(v["c"][:4])
        # También lo que no se puede leer queda anotado: sin esto se
        # descargaría el mismo PDF escaneado cada día.
        almacen["escritas"][exp] = {"c": v["c"], "pdf": url, "leida": hoy_s,
                                    **(datos or {"sin_texto": True})}
        tocados.add(v["c"][:4])
        if datos:
            nuevos.append(exp)
        time.sleep(cd.PAUSA_BUSCADOR)
    for a in tocados:
        guardar(a)
    pq._guardar(pq.ESTADO_ESCRITAS, e)
    total = sum(len(cargar(a)["escritas"]) for a in anios())
    log(f"respuestas escritas: {len(nuevos)} textos nuevos, {sin_pdf} fichas aún sin PDF, "
        f"{peticiones} peticiones, {total} en el archivo")
    return nuevos


def escritas_para_portada(e: dict, hoy: str | None = None) -> list:
    """[(exp, pregunta, respuesta)] cuyo texto se ha leído hoy y que son
    noticia: las vimos pasar a contestadas (vista_c) y la contestación es de
    los últimos NOTICIA_DIAS días. El resto del atraso va a las páginas."""
    hoy = hoy or dt.date.today().isoformat()
    lim = (dt.date.fromisoformat(hoy) - dt.timedelta(days=NOTICIA_DIAS)).isoformat()
    salida = []
    for exp, v in (e.get("exp") or {}).items():
        r = escrita(exp)
        if (r and r.get("cita") and r.get("leida") == hoy and v.get("vista_c")
                and (v.get("c") or "") >= lim):
            salida.append((exp, v, r))
    return sorted(salida, key=lambda x: x[1].get("c") or "", reverse=True)


# ------------------------------------------------------------- páginas

def _a_quien(cargo: str) -> str:
    """«Vicepresidente Primero del Gobierno y Ministro de Economía, Comercio y
    Empresa» -> «al ministro de Economía, Comercio y Empresa». Como en
    preguntas._cargo_titular, pero en minúscula de frase."""
    c = " ".join((cargo or "").split())
    if not c:
        return "al Gobierno"
    m = re.search(r"\b(Ministr[oa]\b.*)$", c)
    if m and " y " in c:
        c = m.group(1)
    art = "a la" if re.match(r"(Ministra|Vicepresidenta|Presidenta)\b", c) else "al"
    return f"{art} {c[0].lower()}{c[1:]}"


def generar_paginas(h: dict) -> list:
    """/sesiones/: índice por años y una página por sesión de control, con
    cada pregunta, quién contesta y las tres citas del Diario de Sesiones."""
    esc, attr, fecha = h["esc_html"], h["esc_attr"], h["fmt_date_es"]
    carpeta, site = h["carpeta"], h["site_url"]
    import preguntas as pq
    sesiones = []
    for a in anios():
        alm = cargar(a)
        for f, meta in alm["sesiones"].items():
            regs = sorted(((k, r) for k, r in alm["orales"].items() if r.get("s") == f),
                          key=lambda kr: kr[1].get("h") or "")
            if regs:
                sesiones.append((f, meta, regs))
    if not sesiones:
        return []
    sesiones.sort(key=lambda x: x[0], reverse=True)
    carpeta.mkdir(exist_ok=True)
    salidas = []

    def pagina(nombre, titulo, desc, h1, entradilla, cuerpo, lastmod, ficha, miga_final):
        url = f"{site}sesiones/{'' if nombre == 'index.html' else nombre}"
        miga = ('<a href="../">Portada</a> › <a href="../seguimiento/">Seguimiento</a> › '
                + (f'<span aria-current="page">Sesiones de control</span>' if nombre == "index.html"
                   else f'<a href="./">Sesiones de control</a> › '
                        f'<span aria-current="page">{esc(miga_final)}</span>'))
        h["pagina_suelta"](h["plantilla"], carpeta, nombre, {
            "TITLE": esc(f"{titulo} | La Tercera Cámara"),
            "META_DESC": attr(desc[:155]),
            "CANONICAL": url,
            "JSONLD": h["jsonld_script"]([{"@type": "WebPage", "url": url, "name": titulo,
                                           "inLanguage": "es-ES", "dateModified": lastmod}]),
            "EDITION_DATE": esc(f"Datos al {fecha(lastmod)}"),
            "MIGA": miga,
            "KICKER": "Control al Gobierno",
            "HEADLINE": esc(h1),
            "STANDFIRST": esc(entradilla),
            "FICHA": ficha,
            "CUERPO": cuerpo,
            "FUENTE": ('Fuente: Diario de Sesiones del Congreso de los Diputados y volcado de '
                       'intervenciones de sus datos abiertos. <a class="srclink" '
                       'href="metodologia.html">Cómo se hace</a>.'),
            "RELACIONADAS": "", "RELACIONADAS_HIDDEN": "hidden",
        })
        salidas.append({"url": url, "lastmod": lastmod})

    def bloque_cita(texto, autor):
        return (f'<blockquote class="pull"><p>«{esc(texto)}»</p>'
                f'<cite>{esc(autor)}</cite></blockquote>') if texto else ""

    for f, meta, regs in sesiones:
        fl = fecha(f).replace(",", "")
        partes = []
        for exp, r in regs:
            grupo = pq.grupo_corto(r.get("g", ""))
            autor = f'{r.get("a", "")} ({grupo})' if grupo else r.get("a", "")
            enlaces = [f'<a class="srclink" href="{attr(cd.ficha_iniciativa_url(exp))}" '
                       f'target="_blank" rel="noopener">Ficha oficial {esc(exp)}</a>']
            if r.get("pdf"):
                pag = re.search(r"#page=(\d+)", r["pdf"])
                enlaces.append(f'<a class="srclink" href="{attr(r["pdf"])}" target="_blank" '
                               f'rel="noopener">Diario de Sesiones'
                               f'{", pág. " + pag.group(1) if pag else ""}</a>')
            if r.get("slug"):
                enlaces.append(f'<a class="srclink" href="../diputados/{attr(r["slug"])}.html">'
                               f'Ficha de {esc(r.get("a", ""))}</a>')
            contesta = ", ".join(x for x in (r.get("gob"), r.get("cargo")) if x)
            cuerpo_p = (bloque_cita(r.get("c1"), f"Contesta {contesta}") +
                        bloque_cita(r.get("r"), f"Réplica de {autor}") +
                        bloque_cita(r.get("c2"), f"Cierra {r.get('gob') or 'el Gobierno'}"))
            if not r.get("c1"):
                cuerpo_p = ('<p class="ref">No se ha localizado la contestación en el Diario de '
                            'Sesiones: puede ser una pregunta acumulada a otra o que no llegara '
                            'a contestarse en el Pleno.</p>')
            partes.append(
                f'<h2 class="rotulo" id="{attr(exp.replace("/", "-"))}">{esc(autor)} pregunta '
                f'{esc(_a_quien(r.get("cargo", "")))}</h2>'
                f'<p><b>Pregunta registrada:</b> «{esc(r.get("t", ""))}»</p>'
                + cuerpo_p + f'<p>{" · ".join(enlaces)}</p>')
        con = sum(1 for _k, r in regs if r.get("c1"))
        ministros = sorted({r.get("gob") for _k, r in regs if r.get("gob")})
        pagina(f"{f}.html",
               f"Sesión de control del {fl}: preguntas y respuestas",
               f"Las {len(regs)} preguntas orales al Gobierno en el Pleno del Congreso del {fl}, "
               f"con lo que contestó cada ministro, citado del Diario de Sesiones.",
               f"Sesión de control del {fl}",
               f"{len(regs)} preguntas orales en el Pleno del Congreso. Qué se preguntó, quién "
               f"contestó y qué dijo, con citas literales del Diario de Sesiones.",
               "".join(partes), meta.get("leida") or f,
               (f"<dt>Preguntas</dt><dd>{len(regs)}</dd>"
                f"<dt>Con contestación localizada</dt><dd>{con}</dd>"
                f"<dt>Contestan</dt><dd>{len(ministros)} {'miembro' if len(ministros) == 1 else 'miembros'} del Gobierno</dd>"),
               fl)

    por_anio: dict = {}
    for f, meta, regs in sesiones:
        por_anio.setdefault(f[:4], []).append((f, regs))
    cuerpo = ""
    for a in sorted(por_anio, reverse=True):
        cuerpo += f'<h2 class="rotulo" id="a{a}">{a}</h2><ul class="indice">'
        for f, regs in por_anio[a]:
            cuerpo += (f'<li><a href="{f}.html">{esc(fecha(f).replace(",", ""))}</a>'
                       f'<span class="ref">{len(regs)} preguntas</span></li>')
        cuerpo += "</ul>"
    ultima = sesiones[0]
    n_preg = sum(len(r) for _f, _m, r in sesiones)
    pagina("index.html", "Sesiones de control al Gobierno en el Congreso",
           "Cada sesión de control del Pleno del Congreso: las preguntas orales al Gobierno y lo "
           "que contestó cada ministro, con citas del Diario de Sesiones.",
           "Lo que se pregunta al Gobierno cara a cara",
           "Las sesiones de control del Pleno del Congreso, una a una: la pregunta registrada, "
           "la contestación, la réplica y la dúplica, citadas del Diario de Sesiones.",
           cuerpo, ultima[1].get("leida") or ultima[0],
           (f"<dt>Sesiones</dt><dd>{len(sesiones)}</dd><dt>Preguntas</dt><dd>{n_preg}</dd>"
            f"<dt>Última</dt><dd>{esc(fecha(ultima[0]))}</dd>"), "")

    metod = f"""
<h2 class="rotulo">Fuente</h2>
<p>El volcado de intervenciones de los datos abiertos del Congreso
(IntervencionesCronologicamente) da, para cada pregunta oral en Pleno, quién la registra, su
texto, quién contesta y el enlace al Diario de Sesiones de la sesión. De ese Diario, en la versión
de texto íntegro del buscador de intervenciones, salen las citas.</p>
<h2 class="rotulo">Qué se cita</h2>
<p>Tres intervenciones por pregunta: la primera contestación del Gobierno, la réplica de quien
pregunta y la última intervención del Gobierno. La formulación oral de la pregunta no se cita
porque la pregunta registrada ya va entera. Cada cita son las primeras frases completas de la
intervención, hasta unos {LARGO_CITA} caracteres; «[…]» indica que la intervención sigue.</p>
<h2 class="rotulo">Qué se quita</h2>
<p>El saludo de cortesía del principio («Gracias, señora presidenta») y las acotaciones del
Diario de Sesiones («Aplausos», «Rumores», «Un señor diputado: …»), que no son palabras de quien
interviene. No se cambia ninguna palabra.</p>
<h2 class="rotulo">Limitaciones</h2>
<p>En algunas sesiones antiguas unas pocas preguntas (menos del 1 %) no tienen la contestación
localizada: preguntas acumuladas a otra, con un rótulo distinto, o sin respuesta en el Pleno. Se
publican sin cita. El texto íntegro completo y el vídeo están siempre en el Diario de Sesiones
enlazado.</p>"""
    pagina("metodologia.html", "Cómo citamos las sesiones de control",
           "De dónde salen las citas de las sesiones de control al Gobierno y qué se quita.",
           "Metodología de las sesiones de control",
           "Qué se cita, de dónde sale y qué no se toca.", metod,
           ultima[1].get("leida") or ultima[0], "", "Metodología")
    return salidas
