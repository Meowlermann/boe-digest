"""Elecciones generales del 29-N de 2026: escaños y candidaturas al Congreso
(tanda E2). Determinista, sin LLM y sin red en el render.

Fuentes (BOE, comprobadas el 13-11-2026 en txt.php):

- BOE-A-2026-20742, Real Decreto 806/2026, de 5 de octubre: art. 2 (fecha de
  las elecciones, que se cita tal cual) y anexo con los diputados de cada
  circunscripción, en letra («Treinta y dos.»). Tabla HTML de dos columnas.
- BOE-A-2026-23103, candidaturas proclamadas (BOE núm. 273, de 3-11-2026).
  Formato del HTML: <p class="centro_negrita"> abre cada Junta Electoral
  («JUNTA ELECTORAL DE ALBACETE»; a veces se repite el encabezado, y Huelva usa
  «JUNTA ELECTORAL PROVINCIAL DE HUELVA» para el Senado);
  <p class="centro_cursiva"> abre la cámara («CONGRESO DE LOS DIPUTADOS» o
  «SENADO»); <p class="centro_redonda"> es la candidatura («1. NOMBRE
  (SIGLA)») y <p class="parrafo"> / <p class="parrafo_2"> son los candidatos
  («1. Nombre Apellidos.») y el rótulo «Suplentes:». Una candidatura que la
  Junta no proclamó aparece en su orden con un único párrafo «No proclamada.»
  (32 casos entre Congreso y Senado). En Baleares, Las Palmas y
  Santa Cruz de Tenerife hay además rótulos «Circunscripción electoral: X»
  que solo llevan Senado.
- BOE-A-2023-12663, Real Decreto 400/2023: anexo con los diputados de cada
  circunscripción en 2023 (en cifra), para decir dónde cambia el reparto.
  Se comprobó que coincide con el censo de la XV por circunscripción; cambian
  Madrid (37 → 38) y Cádiz (9 → 8).
- BOE-A-2026-23383, corrección de errores (BOE núm. 278, de 7-11-2026, mismo
  formato): por Junta y cámara, «En la candidatura:» + candidatura (o sin
  ella, y entonces el «Donde dice» empieza por la propia candidatura),
  «Donde dice:» «…» y «Debe decir:» «…».

Qué se hace con la corrección: solo se aplican las del Congreso. Cada «Donde
dice» se parte en líneas normalizadas (espacios, «» y paréntesis) y se busca
como secuencia contigua de líneas dentro de la candidatura señalada (o, si no
se señala, en las candidaturas al Congreso de esa Junta). Si no aparece
exactamente, se intenta con la misma línea sin el sufijo «(SIGLA)» que
algunas Juntas añaden al nombre; si tampoco, se para con error: nunca se
aplica a medias ni se adivina.

Limpieza de nombres: algunas Juntas añaden la sigla tras cada candidato
(«Eneka Maiz Ulaiar (EH BILDU).»); se quita el paréntesis final si no lleva
minúsculas. No se cambia nada más del texto del BOE.

No cubre: el Senado (fuera de la automatización), resultados ni fechas
distintas de la del RD. No se calcula ninguna fecha.
"""

from __future__ import annotations

import json
import pathlib
import re
import unicodedata

RAIZ = pathlib.Path(__file__).resolve().parent
DATOS = RAIZ / "curated" / "elecciones_2026.json"

ID_RD = "BOE-A-2026-20742"
ID_CANDIDATURAS = "BOE-A-2026-23103"
ID_CORRECCION = "BOE-A-2026-23383"
# Reparto de la legislatura que acaba: anexo del Real Decreto 400/2023 (BOE núm.
# 128, de 30-5-2023), con los diputados por circunscripción en cifra («37»).
ID_RD_ANTERIOR = "BOE-A-2023-12663"


def url_boe(ident: str) -> str:
    return f"https://www.boe.es/diario_boe/txt.php?id={ident}"


# --- normalización ------------------------------------------------------------

def _espacios(t: str) -> str:
    t = (t or "").replace("\u2003", " ").replace("\u2002", " ").replace("\xa0", " ")
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\(\s+", "(", t)
    return re.sub(r"\s+\)", ")", t)


def clave_nombre(t: str) -> str:
    """Nombre para comparar: sin tildes, minúsculas, solo letras y espacios."""
    base = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]+", " ", base).strip()


_NUMEROS = {
    "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
    "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13,
    "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17, "dieciocho": 18,
    "diecinueve": 19, "veinte": 20, "veintiuno": 21, "veintidos": 22, "veintitres": 23,
    "veinticuatro": 24, "veinticinco": 25, "veintiseis": 26, "veintisiete": 27,
    "veintiocho": 28, "veintinueve": 29, "treinta": 30, "cuarenta": 40,
}


def numero_en_letra(t: str) -> int:
    """«Treinta y dos.» → 32 (RD 806/2026) o «32» (RD 400/2023). Solo 1–49; si no, ValueError."""
    if re.fullmatch(r"\s*\d{1,2}\.?\s*", t or ""):     # el RD de 2023 los da en cifra
        return int(t.strip().rstrip("."))
    partes = clave_nombre(t).split(" y ")
    if len(partes) == 1 and partes[0] in _NUMEROS:
        return _NUMEROS[partes[0]]
    if len(partes) == 2 and partes[0] in ("treinta", "cuarenta") and partes[1] in _NUMEROS \
            and _NUMEROS[partes[1]] < 10:
        return _NUMEROS[partes[0]] + _NUMEROS[partes[1]]
    raise ValueError(f"número en letra no reconocido: {t!r}")


def _parrafos(html: str):
    from bs4 import BeautifulSoup
    sopa = BeautifulSoup(html, "html.parser")
    raiz = sopa.select_one("#textoxslt") or sopa
    return raiz, [(" ".join(p.get("class") or []), _espacios(p.get_text(" ", strip=True)))
                  for p in raiz.find_all("p")]


# --- RD 806/2026 ------------------------------------------------------------

def parsear_rd(html: str) -> dict:
    """{"fecha_literal": «domingo 29 de noviembre de 2026», "escanos": [[circ, n, literal]…]}."""
    raiz, ps = _parrafos(html)
    fecha = ""
    for _c, t in ps:
        m = re.search(r"que se celebrarán el (\w+ \d{1,2} de \w+ de \d{4})", t)
        if m:
            fecha = m.group(1)
            break
    if not fecha:
        raise ValueError("RD: no se encuentra la fecha de las elecciones en el art. 2")
    escanos = []
    for tr in raiz.find_all("tr"):
        celdas = [_espacios(td.get_text(" ", strip=True)) for td in tr.find_all(["td", "th"])]
        if len(celdas) != 2 or celdas[0].lower().startswith("circunscripci"):
            continue
        circ, letra = celdas[0].rstrip("."), celdas[1]
        escanos.append([circ, numero_en_letra(letra), letra.rstrip(".")])
    if not escanos:
        raise ValueError("RD: anexo sin filas")
    return {"fecha_literal": fecha, "escanos": escanos}


# --- candidaturas -----------------------------------------------------------

_RE_ITEM = re.compile(r"^(\d+)\.\s*(.+)$")
_RE_SIGLA_FINAL = re.compile(r"\s*\(([^()a-z]*(?:\([^()a-z]*\))?[^()a-z]*)\)\s*$")


def _nombre_candidato(t: str) -> str:
    t = t.strip().rstrip(".").strip()
    m = _RE_SIGLA_FINAL.search(t)
    if m and not re.search(r"[a-zà-ÿ]", m.group(1)):
        t = t[:m.start()].strip()
    return t


def _partir_cabecera(t: str) -> tuple[int, str, str]:
    m = _RE_ITEM.match(t)
    if not m:
        raise ValueError(f"cabecera de candidatura sin número: {t!r}")
    resto = m.group(2).strip()
    # La sigla es el último paréntesis de primer nivel: «SDP (PSOE-IU-MS)» anida.
    prof, ini = 0, None
    for i in range(len(resto) - 1, -1, -1):
        if resto[i] == ")":
            prof += 1
        elif resto[i] == "(":
            prof -= 1
            if prof == 0:
                ini = i
                break
    if ini is None or not resto.endswith(")"):
        return int(m.group(1)), resto, ""
    return int(m.group(1)), resto[:ini].strip(), resto[ini + 1:-1].strip()


def bloques_congreso(html: str) -> dict:
    """{junta normalizada: [[línea, …] por candidatura]} solo del Congreso, en el
    orden del BOE. Cada candidatura es una lista de líneas normalizadas: la
    cabecera y luego candidatos y «Suplentes:»."""
    _raiz, ps = _parrafos(html)
    out: dict = {}
    junta, camara, actual = None, None, None
    for clase, t in ps:
        if clase == "centro_negrita" and t.upper().startswith("JUNTA ELECTORAL"):
            junta = re.sub(r"^JUNTA ELECTORAL (PROVINCIAL )?DE ", "", t.upper()).strip()
            camara, actual = None, None
            continue
        if t.startswith("Circunscripción electoral:"):
            camara, actual = "otra", None
            continue
        if clase == "centro_cursiva":
            camara = "congreso" if t.upper().startswith("CONGRESO") else "otra"
            actual = None
            continue
        if camara != "congreso" or junta is None:
            continue
        if clase == "centro_redonda":
            actual = [t]
            out.setdefault(junta, []).append(actual)
        elif clase.startswith("parrafo") and actual is not None:
            actual.append(t)
    return out


def estructurar(lineas: list) -> dict:
    orden, nombre, sigla = _partir_cabecera(lineas[0])
    titulares, suplentes = [], []
    lista, proclamada = titulares, True
    for t in lineas[1:]:
        if t == "No proclamada.":
            proclamada = False
            continue
        if t in ("Suplentes:", "Suplente:"):
            lista = suplentes
            continue
        if t == "Titular:":      # Ceuta (un escaño): «Titular:» / «Suplente:»
            lista = titulares
            continue
        m = _RE_ITEM.match(t)
        if not m:
            raise ValueError(f"línea de candidato sin número en {lineas[0]!r}: {t!r}")
        if int(m.group(1)) != len(lista) + 1:
            raise ValueError(f"numeración saltada en {lineas[0]!r}: {t!r}")
        lista.append(_nombre_candidato(m.group(2)))
    if not proclamada and (titulares or suplentes):
        raise ValueError(f"«No proclamada» con candidatos en {lineas[0]!r}")
    return {"orden": orden, "nombre": nombre, "sigla": sigla, "proclamada": proclamada,
            "titulares": titulares, "suplentes": suplentes}


# --- corrección de errores --------------------------------------------------

def parsear_correccion(html: str) -> list:
    """[{"junta", "camara", "candidatura" (línea o None), "donde": [..], "debe": [..]}]."""
    _raiz, ps = _parrafos(html)
    out, junta, camara, cand, modo, actual = [], None, None, None, None, None
    for clase, t in ps:
        if clase == "centro_negrita" and t.upper().startswith("JUNTA ELECTORAL"):
            junta = re.sub(r"^JUNTA ELECTORAL (PROVINCIAL )?DE ", "", t.upper()).strip()
            camara, cand, modo = None, None, None
            continue
        if clase == "centro_cursiva":
            camara = "congreso" if t.upper().startswith("CONGRESO") else "otra"
            cand, modo = None, None
            continue
        if t.startswith("En la candidatura"):
            cand, modo = None, "cand"
            continue
        if t == "Donde dice:":
            actual = {"junta": junta, "camara": camara, "candidatura": cand, "donde": [], "debe": []}
            out.append(actual)
            modo = "donde"
            continue
        if t == "Debe decir:":
            modo = "debe"
            continue
        if modo == "cand" and clase == "centro_redonda":
            cand = t
            continue
        if modo in ("donde", "debe") and actual is not None:
            linea = t.replace("«", "").replace("»", "").strip()
            if linea:
                actual[modo].append(_espacios(linea))
    return out


def _sin_sigla(linea: str) -> str:
    m = _RE_ITEM.match(linea)
    if not m:
        return linea
    return f"{m.group(1)}. {_nombre_candidato(m.group(2))}."


def _norm_linea(t: str) -> str:
    t = _espacios(t)
    m = _RE_ITEM.match(t)
    return f"{m.group(1)}. {m.group(2).strip()}" if m else t


def _buscar(seq: list, sub: list) -> int:
    """Posición de sub en seq; -1 si no está. Si está más de una vez, ValueError:
    una corrección ambigua no se aplica."""
    n = len(sub)
    pos = [i for i in range(len(seq) - n + 1) if seq[i:i + n] == sub]
    if len(pos) > 1:
        raise ValueError(f"corrección ambigua: {sub[:2]} aparece {len(pos)} veces")
    return pos[0] if pos else -1


def aplicar_correccion(bloques: dict, correcciones: list) -> list:
    """Aplica en su sitio las correcciones del Congreso. Devuelve el registro de
    lo aplicado; si una no encaja exactamente, ValueError."""
    hechas = []
    for c in correcciones:
        if c["camara"] != "congreso":
            continue
        cands = bloques.get(c["junta"])
        if not cands:
            raise ValueError(f"corrección: Junta sin candidaturas al Congreso: {c['junta']}")
        donde = [_norm_linea(x) for x in c["donde"]]
        debe = [_norm_linea(x) for x in c["debe"]]
        if c["candidatura"]:
            objetivo = [b for b in cands if _norm_linea(b[0]) == _norm_linea(c["candidatura"])]
        else:
            objetivo = cands
        estado = None
        for b in objetivo:
            normal = [_norm_linea(x) for x in b]
            sin = [_sin_sigla(x) for x in normal]
            i = _buscar(normal, donde)
            if i < 0:
                i = _buscar(sin, [_sin_sigla(x) for x in donde])
            if i >= 0:
                b[i:i + len(donde)] = debe
                estado = "aplicada"
                break
            # Dos correcciones de la misma línea (Tarragona: una sin la sigla
            # y otra con ella): si lo que «debe decir» ya está, no hay nada que hacer.
            if _buscar(normal, debe) >= 0 or _buscar(sin, [_sin_sigla(x) for x in debe]) >= 0:
                estado = "ya aplicada"
                break
        if not estado:
            raise ValueError(f"corrección sin encaje exacto en {c['junta']}: {donde[:2]}")
        hechas.append({"junta": c["junta"], "estado": estado, "donde": donde, "debe": debe})
    return hechas


# --- juntas ↔ circunscripciones del RD ---------------------------------------

def _claves_circ(circ: str) -> set:
    """«Palmas (Las)» → {«palmas las», «las palmas», «palmas»}; «Alicante/Alacant» → ambas."""
    claves = set()
    for parte in circ.split("/"):
        m = re.match(r"^(.*?)\s*\((.*)\)$", parte.strip())
        if m:
            claves |= {clave_nombre(m.group(1)), clave_nombre(f"{m.group(2)} {m.group(1)}")}
        claves.add(clave_nombre(parte))
    if circ == "Santa Cruz de Tenerife":
        claves.add("santa cruz de tenerife")
    return claves


def junta_a_circunscripcion(junta: str, circunscripciones: list) -> str:
    k = clave_nombre(junta)
    candidatos = [c for c in circunscripciones if k in _claves_circ(c)]
    if len(candidatos) != 1:
        raise ValueError(f"Junta {junta!r} sin circunscripción única en el RD: {candidatos}")
    return candidatos[0]


# --- todo junto ---------------------------------------------------------------

_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre")


def parsear_publicacion(html: str) -> dict:
    """«Publicado en: «BOE» núm. 278, de 7 de noviembre de 2026, páginas…» →
    {"literal": "BOE núm. 278, de 7 de noviembre de 2026", "fecha": "2026-11-07"}.
    Solo se reescribe la fecha impresa en ISO; no se calcula nada."""
    from bs4 import BeautifulSoup
    sopa = BeautifulSoup(html, "html.parser")
    for dt_ in sopa.find_all("dt"):
        if dt_.get_text(strip=True).startswith("Publicado en"):
            dd = _espacios(dt_.find_next("dd").get_text(" ", strip=True))
            m = re.search(r"núm\. (\d+), de (\d{1,2}) de (\w+) de (\d{4})", dd)
            if m and m.group(3) in _MESES:
                return {"literal": f"BOE núm. {m.group(1)}, de {m.group(2)} de {m.group(3)} de {m.group(4)}",
                        "fecha": f"{m.group(4)}-{_MESES.index(m.group(3)) + 1:02d}-{int(m.group(2)):02d}"}
    raise ValueError("no se encuentra «Publicado en» en el documento del BOE")

def construir(html_rd: str, html_cand: str, html_corr: str, html_rd_anterior: str) -> dict:
    rd = parsear_rd(html_rd)
    anterior = {c: n for c, n, _l in parsear_rd(html_rd_anterior)["escanos"]}
    if sorted(anterior) != sorted(c for c, _n, _l in rd["escanos"]):
        raise ValueError("el RD 400/2023 y el RD 806/2026 no traen las mismas circunscripciones")
    circs = [c for c, _n, _l in rd["escanos"]]
    bloques = bloques_congreso(html_cand)
    hechas = aplicar_correccion(bloques, parsear_correccion(html_corr))
    por_circ: dict = {}
    for junta, cands in bloques.items():
        circ = junta_a_circunscripcion(junta, circs)
        if circ in por_circ:
            raise ValueError(f"dos Juntas para {circ}")
        por_circ[circ] = [estructurar(b) for b in cands]
    faltan = [c for c in circs if c not in por_circ]
    if faltan:
        raise ValueError(f"circunscripciones sin candidaturas al Congreso: {faltan}")
    circunscripciones = []
    for circ, n, letra in rd["escanos"]:
        circunscripciones.append({"circunscripcion": circ, "escanos": n, "escanos_literal": letra,
                                  "escanos_anterior": anterior[circ], "candidaturas": por_circ[circ]})
    return {
        "esquema": 1,
        "fuentes": {"rd": ID_RD, "candidaturas": ID_CANDIDATURAS, "correccion": ID_CORRECCION,
                    "rd_anterior": ID_RD_ANTERIOR},
        "publicaciones": {i: parsear_publicacion(x) for i, x in
                          ((ID_RD, html_rd), (ID_CANDIDATURAS, html_cand), (ID_CORRECCION, html_corr),
                           (ID_RD_ANTERIOR, html_rd_anterior))},
        "fecha_literal": rd["fecha_literal"],
        "correcciones_congreso": [{"junta": h["junta"], "estado": h["estado"]} for h in hechas],
        "circunscripciones": circunscripciones,
    }


def cargar(ruta: pathlib.Path = DATOS) -> dict | None:
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def anomalias(datos: dict) -> list:
    """Lo que no sale limpio: candidaturas cuyo número de titulares no coincide
    con los escaños (la LOREG pide tantos como escaños). Se informa, no se toca."""
    out = []
    for c in datos["circunscripciones"]:
        for k in c["candidaturas"]:
            if k["proclamada"] and len(k["titulares"]) != c["escanos"]:
                out.append(f"{c['circunscripcion']}: {k['orden']}. {k['nombre']} ({k['sigla']}) "
                           f"tiene {len(k['titulares'])} titulares para {c['escanos']} escaños")
    return out


# --- render -------------------------------------------------------------------
# Mismo trato para todas las candidaturas: en el orden del BOE, en lista, con
# su nombre y sigla tal como los publica la Junta. Sin tarjetas ni subrayados.

HUB = "elecciones/2026/"
LEMA_IA = "Titulares y entradillas redactados con IA a partir del BOE; el texto oficial está enlazado."
# Pie de las fichas de provincia que llevan el bloque: dice a qué parte afecta la IA.
LEMA_FICHA = ("El bloque «Elecciones 29-N» reproduce el BOE sin IA; los titulares y entradillas "
              "del resto de la página, redactados con IA a partir del BOE; el texto oficial está enlazado.")
SIN_IA = ("Esta sección no usa IA: escaños, candidaturas y nombres salen tal cual del BOE, "
          "que está enlazado.")

# Circunscripción del RD → la que usan los datos del Congreso (fichas y URL de
# /diputados/provincia-*.html). Solo cambia Santa Cruz de Tenerife.
ALIAS_CONGRESO = {"Santa Cruz de Tenerife": "S/C Tenerife"}


def circ_congreso(circ_rd: str) -> str:
    return ALIAS_CONGRESO.get(circ_rd, circ_rd)


def clave_cruce(nombre: str) -> str:
    """Para cruzar con los diputados: sin paréntesis («(Independiente)»,
    apodos), sin comillas ni tildes."""
    return clave_nombre(re.sub(r"\([^)]*\)", " ", nombre))


def cruzar_salientes(datos: dict, fichas: list) -> dict:
    """{circunscripción del RD: [{"ficha", "puesto", "lista", "candidatura", "circ"}]}.

    Solo se marca un cruce si el nombre completo normalizado de la ficha del
    diputado coincide exactamente con el de un candidato, y ese nombre es único
    entre las fichas y entre todos los candidatos al Congreso. Un nombre
    parecido (un segundo nombre de más o de menos) no se marca: es dudoso."""
    por_clave_f: dict = {}
    for f in fichas or []:
        por_clave_f.setdefault(clave_cruce(f.get("natural") or ""), []).append(f)
    apariciones: dict = {}
    for c in datos["circunscripciones"]:
        for k in c["candidaturas"]:
            for lista, nombres in (("titular", k["titulares"]), ("suplente", k["suplentes"])):
                for i, n in enumerate(nombres):
                    apariciones.setdefault(clave_cruce(n), []).append((c["circunscripcion"], k, lista, i + 1))
    out: dict = {}
    for clave, fs in por_clave_f.items():
        if not clave or len(fs) != 1 or len(apariciones.get(clave, [])) != 1:
            continue
        circ, k, lista, puesto = apariciones[clave][0]
        out.setdefault(circ, []).append({"ficha": fs[0], "lista": lista, "puesto": puesto,
                                         "candidatura": k, "circ": circ})
    for v in out.values():
        v.sort(key=lambda s: (s["candidatura"]["orden"], s["lista"] != "titular", s["puesto"]))
    return out


def _esc(t) -> str:
    from html import escape
    return escape(str(t), quote=True)


def _rotulo(k: dict) -> str:
    """El nombre de la candidatura tal como lo publica la Junta."""
    return k["nombre"]


def _sigla_aparte(k: dict) -> str:
    """El literal del BOE entre paréntesis, en pequeño, solo si añade algo al
    nombre («PODEMOS (PAZ,CASA Y TRABAJO)» en Ceuta); «VOX (VOX)» no lo repite."""
    if not k["sigla"] or clave_nombre(k["sigla"]) == clave_nombre(k["nombre"]):
        return ""
    return f'<small class="elec-sigla">Sigla en el BOE: {_esc(k["sigla"])}</small>'


def _corto(k: dict) -> str:
    """Para índices y menciones: el nombre si es corto; si no, la sigla."""
    if len(k["nombre"]) <= 22 or not k["sigla"]:
        return k["nombre"]
    return k["sigla"]


def _puesto(s: dict) -> str:
    return (f"n.º {s['puesto']} de la lista" if s["lista"] == "titular"
            else f"suplente n.º {s['puesto']}")


def fuentes_html(datos: dict, anterior: bool = False) -> str:
    """Una sola línea de fuente, con cada documento citado una vez."""
    f = datos["fuentes"]
    ant = (f'; reparto de 2023: <a href="{url_boe(f["rd_anterior"])}">Real Decreto 400/2023</a> '
           f'({_esc(f["rd_anterior"])})' if anterior else "")
    return (f'Fuente: Boletín Oficial del Estado. Candidaturas: <a href="{url_boe(f["candidaturas"])}">'
            f'{_esc(f["candidaturas"])}</a>, con su <a href="{url_boe(f["correccion"])}">corrección de errores</a> '
            f'({_esc(f["correccion"])}); escaños y fecha: <a href="{url_boe(f["rd"])}">Real Decreto 806/2026</a> '
            f'({_esc(f["rd"])}){ant}. Sin IA: datos tal cual del BOE.')


def frase_escanos(c: dict, nombre: str, datos: dict) -> str:
    """«Madrid elige 38 diputados…» y, si cambia, el número de 2023, citado.
    Se dan las dos cifras oficiales; no se calcula ninguna diferencia."""
    n, a = c["escanos"], c.get("escanos_anterior")
    base = (f'{_esc(nombre)} elige <b>{n}</b> {"diputado" if n == 1 else "diputados"} '
            f'(<a href="{url_boe(ID_RD)}">Real Decreto 806/2026</a>)')
    if a is None or a == n:
        return base
    return (base + f'. <b class="elec-cambio">El reparto cambia:</b> el 29-N hay {n} '
            f'{"escaño" if n == 1 else "escaños"} en juego, frente a los {a} de la legislatura que acaba '
            f'(<a href="{url_boe(datos["fuentes"]["rd_anterior"])}">Real Decreto 400/2023</a>)')


def _ordinal(k) -> str:
    return f"{k['orden']}.ª"


def nota_no_proclamadas(c: dict) -> str:
    """Explica los huecos de la numeración, que es la del BOE y no se cambia:
    las candidaturas que el BOE recoge como «No proclamada»."""
    np = [k for k in c["candidaturas"] if not k["proclamada"]]
    if not np:
        return ""
    if len(np) == 1:
        k = np[0]
        txt = (f"La numeración es la del BOE. La {_ordinal(k)} candidatura, {_esc(_rotulo(k))}, "
               f"no fue proclamada.")
    else:
        lista = ", ".join(f"{_ordinal(k)} ({_esc(_rotulo(k))})" for k in np[:-1])
        k = np[-1]
        txt = (f"La numeración es la del BOE. Las candidaturas {lista} y {_ordinal(k)} "
               f"({_esc(_rotulo(k))}) no fueron proclamadas.")
    return f'<p class="elec-nota elec-np">{txt}</p>'


def bloque_ficha(datos: dict, circ_rd: str, salientes: list, nombre: str, slug: str,
                 salen_fuera: list | None = None) -> str:
    """Bloque «Elecciones 29-N» para /diputados/provincia-*.html."""
    c = next(x for x in datos["circunscripciones"] if x["circunscripcion"] == circ_rd)
    prof = [k for k in c["candidaturas"] if k["proclamada"]]
    items = "".join(
        f'<li value="{k["orden"]}"><b>{_esc(_rotulo(k))}</b>{_sigla_aparte(k)}'
        + (f'<span class="elec-cab">Encabeza: {_esc(k["titulares"][0])}</span>' if k["titulares"] else "")
        + "</li>" for k in prof)
    rep = "".join(
        f'<li><a href="{_esc(s["ficha"]["slug"])}.html">{_esc(s["ficha"]["natural"])}</a> · '
        f'{_esc(_corto(s["candidatura"]))}, {_puesto(s)}'
        + (f' (en la XV, por {_esc(s["ficha"]["circunscripcion"])})'
           if s["ficha"].get("circunscripcion") != circ_congreso(circ_rd) else "")
        + "</li>" for s in salientes)
    fuera = "".join(
        f'<li><a href="{_esc(s["ficha"]["slug"])}.html">{_esc(s["ficha"]["natural"])}</a> · se presenta '
        f'por {_esc(s["circ_nombre"])}: {_esc(_corto(s["candidatura"]))}, '
        f'{_puesto(s)}</li>' for s in (salen_fuera or []))
    n = c["escanos"]
    return (
        f'<section class="elec-29n" aria-labelledby="elec-29n">'
        f'<h2 id="elec-29n">Elecciones 29-N</h2>'
        f'<p class="elec-intro">Elecciones generales del {_esc(datos["fecha_literal"])}. '
        f'{frase_escanos(c, nombre, datos)}. Concurren '
        f'<b>{len(prof)}</b> {"candidatura" if len(prof) == 1 else "candidaturas"} al Congreso, '
        f'en el orden del BOE.</p>'
        f'<ol class="elec-lista">{items}</ol>'
        + nota_no_proclamadas(c)
        + f'<h3>Diputados salientes en las listas</h3>'
        + (f'<ul class="elec-rep">{rep}{fuera}</ul>' if rep or fuera else
           f'<p class="elec-nota">Ningún diputado de la legislatura disuelta figura con el mismo nombre '
           f'en las candidaturas al Congreso por {_esc(nombre)}.</p>')
        + f'<p class="elec-nota">Se marca solo cuando el nombre completo coincide letra por letra con el '
          f'de la ficha del diputado; los parecidos no se marcan.</p>'
        f'<p class="elec-mas"><a href="/{HUB}{_esc(slug)}.html">Las listas completas de {_esc(nombre)}, '
        f'con suplentes →</a> · <a href="/{HUB}">Las 52 circunscripciones →</a></p>'
        f'<p class="elec-fuente">{fuentes_html(datos, c.get("escanos_anterior") not in (None, n))}</p></section>')


def migas(site: str, pasos) -> dict:
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, "item": u}
        for i, (n, u) in enumerate((("Portada", site),) + tuple(pasos))]}


def generar_paginas(h: dict, datos: dict, fichas: list) -> list:
    """/elecciones/2026/ y una página por circunscripción. h: esc_html,
    pagina_suelta, plantilla, site_url, carpeta, jsonld_script, nombre(circ_congreso),
    slug(circ_congreso). Devuelve [{"url", "lastmod"}]."""
    site, carpeta = h["site_url"], h["carpeta"]
    # Nada de estas páginas pasa por IA: el lema general del pie se sustituye.
    h = {**h, "plantilla": h["plantilla"].replace(LEMA_IA, SIN_IA)}
    pub = datos["publicaciones"][ID_CORRECCION]
    lastmod = pub["fecha"]
    edicion = f"Candidaturas del BOE, con la corrección del {pub['literal'].split(', de ', 1)[1]}"
    salientes = cruzar_salientes(datos, fichas)
    filas, salidas = [], []
    # La fuente va una sola vez, en el cuerpo y con enlaces (.elec-fuente, sin
    # subrayado). El pie de la plantilla solo recuerda de dónde salen los nombres.
    pie = "Los nombres de candidatos y candidaturas son los que publica el BOE."
    for c in datos["circunscripciones"]:
        cc = circ_congreso(c["circunscripcion"])
        nombre, slug = h["nombre"](cc), h["slug"](cc)
        prof = [k for k in c["candidaturas"] if k["proclamada"]]
        marcados = {(id(s["candidatura"]), s["lista"], s["puesto"]): s for s in salientes.get(c["circunscripcion"], [])}

        def li(k, lista, i, n):
            s = marcados.get((id(k), lista, i))
            extra = (f' <a class="elec-sal" href="/diputados/{_esc(s["ficha"]["slug"])}.html">diputado '
                     f'saliente →</a>' if s else "")
            return f"<li>{_esc(n)}{extra}</li>"
        bloques = "".join(
            f'<section class="elec-cand" id="c{k["orden"]}"><h2>{k["orden"]}. {_esc(_rotulo(k))}</h2>{_sigla_aparte(k)}'
            f'<ol class="elec-nombres">{"".join(li(k, "titular", i + 1, n) for i, n in enumerate(k["titulares"]))}</ol>'
            + (f'<h3>Suplentes</h3><ol class="elec-nombres">'
               f'{"".join(li(k, "suplente", i + 1, n) for i, n in enumerate(k["suplentes"]))}</ol>'
               if k["suplentes"] else "")
            + "</section>" for k in prof)
        indice = "".join(f'<li value="{k["orden"]}"><a href="#c{k["orden"]}">{_esc(_corto(k))}</a></li>'
                         for k in prof)
        nota_np = nota_no_proclamadas(c)
        n = c["escanos"]
        cuerpo = (f'<p class="elec-intro">Elecciones generales del {_esc(datos["fecha_literal"])}. '
                  f'{frase_escanos(c, nombre, datos)}. Estas son las {len(prof)} '
                  f'candidaturas proclamadas, en el orden del BOE, con sus titulares y suplentes.</p>'
                  f'<nav aria-label="Candidaturas"><ol class="elec-indice">{indice}</ol></nav>'
                  + nota_np + bloques
                  + f'<p class="elec-mas"><a href="/diputados/provincia-{_esc(slug)}.html">Los diputados por '
                    f'{_esc(nombre)} en la legislatura disuelta →</a> · <a href="./">Las 52 circunscripciones →</a></p>'
                  + f'<p class="elec-fuente">{fuentes_html(datos, c.get("escanos_anterior") not in (None, n))}</p>')
        url = f"{site}{HUB}{slug}.html"
        titulo = f"Candidatos al Congreso por {nombre} en las elecciones del 29-N"
        h["pagina_suelta"](h["plantilla"], carpeta, f"{slug}.html", {
            "TITLE": _esc(f"{titulo} | La Tercera Cámara"),
            "META_DESC": _esc(f"Las {len(prof)} candidaturas al Congreso por {nombre} para las elecciones "
                              f"generales del 29 de noviembre de 2026, con titulares y suplentes, según el BOE. "
                              f"{nombre} elige {n} {'diputado' if n == 1 else 'diputados'}.")[:300],
            "CANONICAL": url,
            "JSONLD": h["jsonld_script"]([{"@type": "CollectionPage", "url": url, "name": titulo,
                                           "inLanguage": "es-ES", "dateModified": lastmod},
                                          migas(site, (("Elecciones 2026", f"{site}{HUB}"), (nombre, url)))]),
            "EDITION_DATE": _esc(edicion),
            "MIGA": (f'<a href="/">Portada</a> › <a href="./">Elecciones 2026</a> › '
                     f'<span aria-current="page">{_esc(nombre)}</span>'),
            "KICKER": "Elecciones generales 29-N · Congreso",
            "HEADLINE": _esc(f"Candidatos al Congreso por {nombre}"),
            "STANDFIRST": _esc(f"{n} {'escaño' if n == 1 else 'escaños'} y {len(prof)} candidaturas, "
                               f"con sus listas completas tal como las publica el BOE."),
            "FICHA": (f"<dt>Escaños</dt><dd>{n}</dd><dt>Candidaturas</dt><dd>{len(prof)}</dd>"
                      f"<dt>Elecciones</dt><dd>{_esc(datos['fecha_literal'])}</dd>"),
            "CUERPO": cuerpo,
            "FUENTE": pie,
            "RELACIONADAS": "", "RELACIONADAS_HIDDEN": "hidden",
        })
        salidas.append({"url": url, "lastmod": lastmod})
        a = c.get("escanos_anterior")
        cambio = f" (en 2023, {a})" if a is not None and a != n else ""
        filas.append(f'<li><a href="{_esc(slug)}.html">{_esc(nombre)}</a>'
                     f'<span class="ref">{n} {"escaño" if n == 1 else "escaños"}{cambio} · {len(prof)} candidaturas</span></li>')
    total = sum(c["escanos"] for c in datos["circunscripciones"])
    cambian = [(h["nombre"](circ_congreso(c["circunscripcion"])), c["escanos_anterior"], c["escanos"])
               for c in datos["circunscripciones"]
               if c.get("escanos_anterior") is not None and c["escanos_anterior"] != c["escanos"]]
    url = f"{site}{HUB}"
    titulo = "Elecciones generales del 29-N de 2026: candidaturas al Congreso por provincia"
    cuerpo = (f'<p class="elec-intro">El <a href="{url_boe(ID_RD)}">Real Decreto 806/2026</a> convoca '
              f'elecciones generales para el {_esc(datos["fecha_literal"])}. Se eligen <b>{total}</b> '
              f'diputados en {len(datos["circunscripciones"])} circunscripciones. Cada página tiene las '
              f'candidaturas proclamadas al Congreso, en el orden del BOE, y qué diputados de la '
              f'legislatura disuelta repiten.</p>'
              + ('' if not cambian else
                 '<p class="elec-intro"><b class="elec-cambio">Dónde cambia el reparto respecto a 2023</b> '
                 f'(<a href="{url_boe(datos["fuentes"]["rd_anterior"])}">Real Decreto 400/2023</a>): '
                 + "; ".join(f"{_esc(nm)}, {nv} escaños frente a {an}" for nm, an, nv in cambian) + '.</p>')
              + f'<ul class="ix-lista elec-hub">{"".join(filas)}</ul>'
              '<p class="elec-nota">El Senado no está incluido: sus candidaturas también están en el BOE, '
              'pero esta sección cubre por ahora solo el Congreso.</p>'
              + f'<p class="elec-fuente">{fuentes_html(datos, bool(cambian))}</p>')
    h["pagina_suelta"](h["plantilla"], carpeta, "index.html", {
        "TITLE": _esc(f"{titulo} | La Tercera Cámara"),
        "META_DESC": _esc(f"Escaños y candidaturas al Congreso de las {len(datos['circunscripciones'])} "
                          f"circunscripciones para las elecciones generales del 29 de noviembre de 2026, "
                          f"según el BOE."),
        "CANONICAL": url,
        "JSONLD": h["jsonld_script"]([{"@type": "CollectionPage", "url": url, "name": titulo,
                                       "inLanguage": "es-ES", "dateModified": lastmod},
                                      migas(site, (("Elecciones 2026", url),))]),
        "EDITION_DATE": _esc(edicion),
        "MIGA": '<a href="/">Portada</a> › <span aria-current="page">Elecciones 2026</span>',
        "KICKER": "Elecciones generales 29-N · Congreso",
        "HEADLINE": "Elecciones generales del 29-N",
        "STANDFIRST": _esc(f"{total} escaños del Congreso y las candidaturas de cada circunscripción, "
                           f"con sus listas tal como las publica el BOE."),
        "FICHA": (f"<dt>Escaños</dt><dd>{total}</dd><dt>Circunscripciones</dt>"
                  f"<dd>{len(datos['circunscripciones'])}</dd>"
                  f"<dt>Elecciones</dt><dd>{_esc(datos['fecha_literal'])}</dd>"),
        "CUERPO": cuerpo,
        "FUENTE": pie,
        "RELACIONADAS": "", "RELACIONADAS_HIDDEN": "hidden",
    })
    salidas.append({"url": url, "lastmod": lastmod})
    return salidas
