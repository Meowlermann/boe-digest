"""Provincias: qué se dice de cada circunscripción en el BOE y en las Cortes.

Tres piezas, todas deterministas y sin red propia:

  1. menciones(texto): qué provincias nombra un título. Se busca por palabra
     completa y sin tildes el nombre oficial, las variantes (bilingües y
     tradicionales: Girona/Gerona, Ourense/Orense…), la capital y las
     localidades que se añadan a mano en curated/provincias.json.
  2. extraer(entradas, fecha): las disposiciones de las secciones I y III del
     sumario del BOE que nombran una provincia o una comunidad autónoma, o que
     firma una comunidad autónoma, con una categoría deducida del título.
  3. El estado state/provincias.json, indexado por identificador BOE: volver a
     procesar un día sustituye, nunca duplica.

Mejor quedarse corto que asignar mal. Por eso:

  - Solo cuentan menciones explícitas en el TÍTULO. No se lee el texto.
  - Se exige mayúscula inicial (o el título entero en mayúsculas): «cuenca
    hidrográfica» o «granada» en minúscula no son Cuenca ni Granada.
  - Los nombres ambiguos (apellidos, bancos, ciudades de otros países) solo
    cuentan con contexto: «en X», «de X», «provincia de X», «a su paso por X»
    o entre paréntesis detrás de un municipio, «Espinosa de los Monteros (Burgos)».
    Aun así se descartan detrás de «don/doña» y en unas pocas expresiones
    fijas (Banco Santander, Teruel Existe…). Ver AMBIGUOS y NEGATIVOS.
  - Las comunidades autónomas se buscan antes que las provincias y se tapan:
    «Castilla y León» no es León, «Comunitat Valenciana» no es Valencia.
    Una mención de comunidad se asigna a la comunidad, no a cada provincia;
    solo en las uniprovinciales (Madrid, Murcia, Navarra…) cuenta además para
    su única provincia, porque ahí son lo mismo.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import unicodedata

ROOT = pathlib.Path(__file__).parent
REFERENCIA = ROOT / "curated" / "provincias.json"
ESTADO = ROOT / "state" / "provincias.json"
VERSION = 1

# Nombres que también son apellidos, empresas o lugares de fuera de España.
# Solo cuentan precedidos de CONTEXTO. «Victoria» y «Mérida» figuran aquí por
# si alguien los añade a «localidades»: hoy no son variante de nada (Vitoria sí
# lo es de Álava, con t), así que no asignan provincia en ningún caso.
AMBIGUOS = {
    "Leon", "Granada", "Santander", "Toledo", "Soria", "Teruel", "Merida", "Victoria",
    "Burgos", "Lugo", "Zamora", "Avila", "Segovia", "Salamanca", "Cordoba", "Valencia",
    "Cuenca", "Navarra", "Guadalajara", "Sevilla", "Palma", "Oviedo", "Madrid",
}
CONTEXTO = r"(?:\b(?:en|de|del)\s+|\bprovincia\s+de\s+|\ba\s+su\s+paso\s+por\s+|\(\s*)$"
# Aunque haya contexto: una persona («don José de León») o una marca.
PERSONA = re.compile(r"\b(?:don|dona|d\.|dna\.)\s+(?:\S+\s+){0,3}(?:de\s+)?$", re.I)
NEGATIVOS = [r"Banco\s+(?:de\s+)?Santander", r"Teruel\s+Existe", r"Soria\s+Ya",
             r"Real\s+Madrid", r"Atletico\s+de\s+Madrid", r"Jaen\s+Merece\s+Mas",
             r"(?:F\.?\s?C\.?|Futbol\s+Club)\s+Barcelona", r"Sevilla\s+F\.?\s?C\b",
             r"Valencia\s+C\.?\s?F\b", r"Athletic\s+(?:Club\s+)?(?:de\s+)?Bilbao"]

# Categorías del BOE, en orden de prioridad: la primera que encaja se queda.
# Se deducen de palabras del título (sin tildes, en minúscula).
CATEGORIAS = [
    # «Temporal» o «incendio» a secas no bastan: salen en «ocupación temporal»
    # o en convenios de prevención. Hace falta la zona, el daño o el fenómeno.
    ("zona-afectada", "Zona afectada o catástrofe",
     r"zona afectada|emergencia de proteccion civil|catastrofe|\bdana\b|borrasca|"
     r"temporal de (?:lluvia|viento|nieve|mar)|terremoto|seism|erupcion volcanica|"
     r"danos? (?:causados|ocasionados|producidos)"),
    # La subvención directa va antes que el interés general: un real decreto de
    # concesión directa «para actuaciones de interés general» es una subvención.
    ("subvencion", "Subvención nominativa o directa",
     r"subvencion(?:es)? (?:directa|nominativa)|concesion directa|subvencion(?:es)? .{0,40}"
     r"(?:real decreto|excepcional)|ayudas? directas?"),
    ("interes-general", "Obra o actuación de interés general",
     r"interes general|obras? de emergencia|actuaciones? de emergencia"),
    ("convenio", "Convenio con la comunidad autónoma o una entidad local",
     r"\bconvenio\b|\badenda\b|protocolo general de actuacion"),
    ("patrimonio", "Bien de interés cultural o patrimonio",
     r"bien(?:es)? de interes cultural|patrimonio (?:historico|cultural|mundial|de la humanidad)|"
     r"conjunto historico|zona arqueologica|sitio historico|monumento"),
    ("medio-ambiente", "Espacio natural o medio ambiente",
     r"parque nacional|parque natural|espacio natural|reserva de la biosfera|zona especial de "
     r"conservacion|red natura|impacto ambiental|evaluacion ambiental|dominio publico "
     r"maritimo|deslinde|humedal|\bzepa\b|vertido|aguas residuales"),
    ("infraestructuras", "Infraestructuras",
     r"carretera|autovia|autopista|\bvariante\b|ferrocarril|ferroviari|adif|alta velocidad|"
     r"cercanias|\bpuerto\b|portuari|aeropuerto|aeroportuari|\btramo\b|estacion de"),
    ("otras", "Otras", r""),
]
ETIQUETA_CATEGORIA = {c: e for c, e, _r in CATEGORIAS}


# ---------------------------------------------------------------- referencia

def _plano(t: str) -> str:
    """Sin tildes, conservando mayúsculas y longitud (Ñ → N): las posiciones
    del texto plano sirven para el original."""
    return "".join(unicodedata.normalize("NFKD", c)[0] for c in (t or ""))


def cargar_referencia() -> dict:
    return json.loads(REFERENCIA.read_text(encoding="utf-8"))


_TERMINOS: dict = {}


def _terminos() -> dict:
    """Términos ordenados de más largo a más corto, para que «Santa Cruz de
    Tenerife» gane a «Tenerife» y «La Palma» a «Palma». Se calcula una vez."""
    if _TERMINOS:
        return _TERMINOS
    ref = cargar_referencia()
    ccaa, prov = [], []
    uniprov: dict = {}
    for p in ref["provincias"]:
        uniprov.setdefault(p["ccaa"], []).append(p["slug"])
    for slug, c in ref["ccaa"].items():
        for n in {c["nombre"], *c.get("variantes", [])}:
            ccaa.append((_plano(n), slug))
    for p in ref["provincias"]:
        nombres = {p["nombre"], p["capital"], *p.get("variantes", []), *p.get("localidades", [])}
        for n in list(nombres):
            nombres.update(x.strip() for x in n.split("/"))
        for n in nombres:
            if n and "/" not in n:
                prov.append((_plano(n), p["slug"]))
    orden = lambda xs: sorted(set(xs), key=lambda x: -len(x[0]))       # noqa: E731
    _TERMINOS.update({
        "ccaa": orden(ccaa), "prov": orden(prov),
        "uniprov": {c: s[0] for c, s in uniprov.items() if len(s) == 1},
        "ref": ref,
    })
    return _TERMINOS


def _patron(termino: str) -> re.Pattern:
    """Palabra completa, con mayúscula inicial o todo en mayúsculas."""
    e = re.escape(termino).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<![\w-])(?:{e}|{e.upper()})(?![\w])")


_CACHE_PATRONES: dict = {}


def _buscar(texto: str, termino: str):
    p = _CACHE_PATRONES.get(termino)
    if p is None:
        p = _CACHE_PATRONES[termino] = _patron(termino)
    return p.finditer(texto)


def _tapar(texto: str, a: int, b: int) -> str:
    return texto[:a] + "#" * (b - a) + texto[b:]


def analizar(texto: str) -> dict:
    """{"provincias": set, "ccaa": set, "descartes": [(término, motivo)]}.
    Es lo que usan menciones() y menciones_ccaa(); los descartes van al log
    del reprocesado para ver qué se ha dejado fuera por ambigüedad."""
    t = _terminos()
    plano = _plano(" ".join((texto or "").split()))
    for neg in NEGATIVOS:
        for m in re.finditer(neg, plano, re.I):
            plano = _tapar(plano, m.start(), m.end())
    provs, comunidades, descartes = set(), set(), []
    for termino, ccaa in t["ccaa"]:
        for m in list(_buscar(plano, termino)):
            comunidades.add(ccaa)
            if ccaa in t["uniprov"]:
                provs.add(t["uniprov"][ccaa])
            plano = _tapar(plano, m.start(), m.end())
    for termino, slug in t["prov"]:
        for m in list(_buscar(plano, termino)):
            antes = plano[max(0, m.start() - 40):m.start()]
            if termino in AMBIGUOS:
                if not re.search(CONTEXTO, antes, re.I):
                    descartes.append((termino, "ambiguo sin contexto"))
                    continue
                if PERSONA.search(antes):
                    descartes.append((termino, "nombre de persona"))
                    continue
            provs.add(slug)
            plano = _tapar(plano, m.start(), m.end())
    return {"provincias": provs, "ccaa": comunidades, "descartes": descartes}


_MENCIONES: dict = {}


def menciones(texto: str) -> set[str]:
    """Slugs de las provincias que nombra el texto (ver el docstring del
    módulo para las reglas). Las comunidades pluriprovinciales no cuentan.
    Con caché por texto: los canales de provincia (build.renderizar_feeds) y
    las páginas analizan los mismos 15.000 títulos de preguntas en cada pase."""
    if texto not in _MENCIONES:
        _MENCIONES[texto] = frozenset(analizar(texto)["provincias"])
    return set(_MENCIONES[texto])


def menciones_ccaa(texto: str) -> set[str]:
    """Slugs de las comunidades autónomas que nombra el texto."""
    return analizar(texto)["ccaa"]


def ccaa_de_dept(dept: str) -> str | None:
    """«COMUNIDAD AUTÓNOMA DE ANDALUCÍA» → «andalucia». Solo departamentos que
    son una comunidad o ciudad autónoma: un ministerio no cuenta."""
    d = " ".join((dept or "").split())
    if not re.match(r"^(COMUNIDAD|COMUNITAT|CIUDAD|PRINCIPADO|REGI[OÓ]N|ILLES|JUNTA|XUNTA|"
                    r"GENERALITAT|GOBIERNO DE|DIPUTACI[OÓ]N FORAL)", d, re.I):
        return None
    c = analizar(d.title())["ccaa"] | analizar(d)["ccaa"]
    return sorted(c)[0] if len(c) == 1 else None


# ------------------------------------------------------------------ extractor

def _seccion(e: dict) -> str | None:
    """«I» o «III», del código de la API o del rótulo del HTML."""
    cod = str(e.get("codigo") or "")
    if cod in ("1", "3"):
        return "I" if cod == "1" else "III"
    m = re.match(r"^(I|III)\.\s", e.get("seccion") or "")
    return m.group(1) if m else None


def categoria(titulo: str) -> str:
    t = _plano(titulo).lower()
    for slug, _et, rx in CATEGORIAS:
        if not rx or re.search(rx, t):
            return slug
    return "otras"


def extraer(entradas: list[dict], fecha_boe, log=print) -> list[dict]:
    """Disposiciones de las secciones I y III con impacto territorial.

    Entra lo que nombra una provincia o una comunidad en el título, o lo que
    firma una comunidad autónoma. Fuera la Administración Local (son anuncios
    de ayuntamientos, que quedan para otra fase) y la sección V."""
    fecha = fecha_boe.isoformat() if hasattr(fecha_boe, "isoformat") else str(fecha_boe)
    salida, descartes = [], {}

    def descarta(motivo, n=1):
        descartes[motivo] = descartes.get(motivo, 0) + n

    vistas = 0
    for e in entradas or []:
        sec = _seccion(e)
        if not sec:
            continue
        dept = " ".join((e.get("dept") or "").split())
        if re.search(r"ADMINISTRACI[OÓ]N LOCAL", dept, re.I):
            continue
        vistas += 1
        titulo = " ".join((e.get("titulo") or "").split())
        ident = e.get("ident") or ""
        if not re.fullmatch(r"BOE-A-\d{4}-\d+", ident):
            descarta("sin identificador BOE")
            continue
        a = analizar(titulo)
        for termino, motivo in a["descartes"]:
            descarta(f"{motivo}: {termino}")
        comunidades = set(a["ccaa"])
        c_dept = ccaa_de_dept(dept)
        if c_dept:
            comunidades.add(c_dept)
        if not a["provincias"] and not comunidades:
            continue
        reg = {"id": ident, "fecha": fecha, "seccion": sec, "cat": categoria(titulo),
               "titulo": titulo, "provincias": sorted(a["provincias"]), "ccaa": sorted(comunidades)}
        url = e.get("url") or ""
        if url and url != url_boe(ident):
            reg["url"] = url
        salida.append(reg)
    detalle = ", ".join(f"{k}: {v}" for k, v in sorted(descartes.items(), key=lambda x: -x[1])[:8])
    log(f"provincias {fecha}: {len(salida)} con impacto territorial de {vistas} en las "
        f"secciones I y III" + (f"; descartes — {detalle}" if detalle else ""))
    extraer.ultimos_descartes = descartes
    return salida


extraer.ultimos_descartes = {}


def url_boe(ident: str) -> str:
    """La URL se deduce del identificador y no se guarda salvo que venga otra:
    en un estado de miles de registros son decenas de KB."""
    return f"https://www.boe.es/diario_boe/txt.php?id={ident}"


# ---------------------------------------------------------------------- estado

def cargar() -> dict:
    try:
        e = json.loads(ESTADO.read_text(encoding="utf-8"))
        if e.get("version") == VERSION:
            e.setdefault("registros", {})
            e.setdefault("dias", {})
            return e
    except Exception:                                         # noqa: BLE001
        pass
    return {"version": VERSION, "registros": {}, "dias": {}}


def guardar(e: dict) -> None:
    ESTADO.parent.mkdir(exist_ok=True)
    texto = json.dumps(e, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if not ESTADO.exists() or ESTADO.read_text(encoding="utf-8") != texto:
        ESTADO.write_text(texto, encoding="utf-8")


def incorporar(registros: list[dict], fecha, fuente: str = "") -> dict:
    """Mete los registros de un día. Por identificador y sustituyendo los de
    ese día: reprocesar no duplica y lo que ya no encaja desaparece."""
    e = cargar()
    f = fecha.isoformat() if hasattr(fecha, "isoformat") else str(fecha)
    for k in [k for k, v in e["registros"].items() if v.get("fecha") == f]:
        del e["registros"][k]
    for r in registros:
        e["registros"][r["id"]] = {k: v for k, v in r.items() if k != "id"}
    e["dias"][f] = {"n": len(registros), "fuente": fuente}
    guardar(e)
    return e


# Secciones de la API que usa este extractor en el reprocesado común: I y III.
SECCIONES = ("1", "3")


def resumen_reproceso() -> dict:
    """Tamaño del estado tras reprocesar, por categoría: lo que va al log."""
    e = cargar()
    por_cat: dict = {}
    for v in e["registros"].values():
        por_cat[v["cat"]] = por_cat.get(v["cat"], 0) + 1
    tam = ESTADO.stat().st_size if ESTADO.exists() else 0
    return {"registros": len(e["registros"]), "por_categoria": por_cat, "bytes": tam}


def procesar_dia(entradas: list[dict], fecha, fuente: str, log=print) -> tuple[int, dict]:
    """Lo que llama el reprocesado común (reproceso.py) con cada sumario."""
    regs = extraer(entradas, fecha, log)
    incorporar(regs, fecha, fuente)
    return len(regs), dict(extraer.ultimos_descartes)


def de_la_provincia(e: dict, slug: str, ccaa: str) -> tuple[list, list]:
    """(registros que nombran la provincia, registros solo de su comunidad)."""
    propios, comunidad = [], []
    for k, v in e["registros"].items():
        r = {"id": k, **v}
        if slug in v.get("provincias", []):
            propios.append(r)
        elif ccaa in v.get("ccaa", []):
            comunidad.append(r)
    orden = lambda xs: sorted(xs, key=lambda r: (r["fecha"], r["id"]), reverse=True)   # noqa: E731
    return orden(propios), orden(comunidad)


# ---------------------------------------------------------------------- páginas

VENTANA_INDICE = 90        # días que cuenta el índice de provincias
CLASE_PROPIA = ' class="propia"'   # preguntas firmadas por diputados de la provincia


def _en_rango(fechas: list) -> tuple[str, str]:
    fs = sorted(f for f in fechas if f)
    return (fs[0], fs[-1]) if fs else ("", "")


# ---------------------------------------------------------------------------
# Mapa del índice
# ---------------------------------------------------------------------------
#
# Coropletas de una sola tinta: cada provincia se pinta por uno de tres
# recuentos (preguntas y BOE de los últimos VENTANA_INDICE días, diputados),
# a nivel de provincia o de comunidad autónoma. Cero va en gris neutro, sin
# tinta. Los cortes son por rangos de la distribución de ese recuento entre
# las unidades que no tienen cero, así que cada tono agrupa unidades
# parecidas. En la vista por comunidades no hay geometría nueva: cada
# provincia se pinta con el valor de su comunidad y se borran las fronteras
# internas. Sin JavaScript se ve el mapa de preguntas por provincia y cada
# provincia sigue siendo un enlace a su página.

MAPA_FICHERO = ROOT / "geo" / "provincias.json"
MAPA_METRICAS = [("preg", "Preguntas al Gobierno"), ("boe", "En el BOE"), ("dip", "Diputados")]
MAPA_NIVELES_VISTA = [("prov", "Provincias"), ("ccaa", "Comunidades")]
MAPA_NIVELES = 5


def cortes_mapa(valores: list[int], niveles: int = MAPA_NIVELES) -> list[tuple[int, int]]:
    """Rangos [desde, hasta] de cada nivel, por cuantiles de los valores
    positivos. Nunca repite un rango ni deja uno vacío: con pocos valores
    distintos salen menos niveles."""
    pos = sorted(v for v in valores if v > 0)
    if not pos:
        return []
    distintos = sorted(set(pos))
    if len(distintos) <= niveles:
        return [(v, v) for v in distintos]
    techos = []
    for i in range(1, niveles + 1):
        techo = pos[min(len(pos) - 1, round(i * len(pos) / niveles) - 1)]
        if not techos or techo > techos[-1]:
            techos.append(techo)
    rangos, desde = [], pos[0]
    for techo in techos:
        rangos.append((desde, techo))
        desde = next((v for v in distintos if v > techo), techo + 1)
    return rangos


def nivel_mapa(v: int, rangos: list[tuple[int, int]]) -> int:
    """0 para cero; 1..n según el rango en que cae."""
    if v <= 0:
        return 0
    for i, (_a, b) in enumerate(rangos, 1):
        if v <= b:
            return i
    return len(rangos)


def agregados_ccaa(resumen: list, preg_ccaa: dict, boe_ccaa: dict) -> dict:
    """Totales por comunidad: diputados sumados; preguntas y BOE como UNIÓN
    de identificadores (lo de cualquiera de sus provincias más lo que nombra
    la comunidad), para no contar dos veces una pregunta que nombra Alicante
    y Valencia."""
    ag: dict = {}
    for r in resumen:
        c = r["p"]["ccaa"]
        a = ag.setdefault(c, {"dip": 0, "preg": set(), "boe": set(), "provincias": []})
        a["dip"] += r["diputados"]
        a["preg"] |= r.get("preg_ids", set())
        a["boe"] |= r.get("boe_ids", set())
        a["provincias"].append(r["p"]["slug"])
    for c, a in ag.items():
        a["preg"] = len(a["preg"] | preg_ccaa.get(c, set()))
        a["boe"] = len(a["boe"] | boe_ccaa.get(c, set()))
    return ag


def mapa_html(resumen: list, ref: dict, esc, attr, ag: dict | None = None) -> str:
    """El mapa entero (SVG en línea, selectores, leyendas y el script del
    tooltip). Si falta la geometría, cadena vacía y el índice queda como
    estaba: la lista siempre está debajo."""
    try:
        geo = json.loads(MAPA_FICHERO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    ag = ag or {}
    campos = {"preg": "preguntas_90", "boe": "boe_90", "dip": "diputados"}
    rangos = {("prov", m): cortes_mapa([r[campos[m]] for r in resumen]) for m, _e in MAPA_METRICAS}
    rangos.update({("ccaa", m): cortes_mapa([a[m] for a in ag.values()]) for m, _e in MAPA_METRICAS})
    formas = []
    for r in sorted(resumen, key=lambda r: r["p"]["slug"]):
        p = r["p"]
        d = geo["provincias"].get(p["slug"])
        if not d:
            continue
        c = p["ccaa"]
        a = ag.get(c)
        niveles = [f'data-q-prov-{m}="{nivel_mapa(r[campos[m]], rangos[("prov", m)])}"' for m, _e in MAPA_METRICAS]
        if a:
            niveles += [f'data-q-ccaa-{m}="{nivel_mapa(a[m], rangos[("ccaa", m)])}"' for m, _e in MAPA_METRICAS]
            # Comunidad de una sola provincia: su página es la de la provincia.
            destino = (f'{p["slug"]}.html' if len(a["provincias"]) == 1 else f'#ccaa-{c}')
            niveles.append(f'data-cc="{attr(c)}" data-cn="{attr(ref["ccaa"][c]["nombre"])}" '
                           f'data-cdip="{a["dip"]}" data-cpreg="{a["preg"]}" data-cboe="{a["boe"]}" '
                           f'data-cnp="{len(a["provincias"])}" data-cdest="{attr(destino)}"')
        etiqueta = (f'{p["nombre"]}: {r["diputados"]} diputados, {r["preguntas_90"]} preguntas '
                    f'y {r["boe_90"]} disposiciones del BOE en {VENTANA_INDICE} días')
        forma = f'<path d="{d}"/>'
        if p["slug"] in ("ceuta", "melilla"):
            # Demasiado pequeñas para verse o para acertarles: un punto encima.
            x, y = geo["centros"][p["slug"]]
            forma += (f'<circle cx="{x}" cy="{y}" r="6"/>'
                      f'<text x="{x + 10}" y="{y + 4}">{esc(p["nombre"])}</text>')
        q0 = nivel_mapa(r["preguntas_90"], rangos[("prov", "preg")])
        formas.append(
            f'<a href="{attr(p["slug"])}.html" class="mp-prov" aria-label="{attr(etiqueta)}" '
            f'data-n="{attr(p["nombre"])}" data-c="{attr(ref["ccaa"][c]["nombre"])}" '
            f'data-dip="{r["diputados"]}" data-preg="{r["preguntas_90"]}" data-boe="{r["boe_90"]}" '
            f'data-q="{q0}" {" ".join(niveles)}>{forma}</a>')

    def leyenda(nivel, m, etiqueta):
        rs = rangos[(nivel, m)]
        celdas = ['<li><i class="mp-q0"></i>0</li>'] + [
            f'<li><i class="mp-q{i}"></i>{a if a == b else f"{a}–{b}"}</li>'
            for i, (a, b) in enumerate(rs, 1)]
        return (f'<ul class="mp-leyenda" data-para="{nivel}-{m}" aria-label="{attr(etiqueta)}">'
                + "".join(celdas) + '</ul>')

    def grupo(clase, opciones, etiqueta):
        return (f'<div class="mp-filtros {clase}" role="group" aria-label="{attr(etiqueta)}">' + "".join(
            f'<button type="button" data-v="{v}" aria-pressed="{"true" if i == 0 else "false"}">'
            f'{esc(e)}</button>' for i, (v, e) in enumerate(opciones)) + '</div>')

    v = VENTANA_INDICE
    notas = {
        "prov-preg": f"Preguntas al Gobierno que nombran la provincia en su título, últimos {v} días.",
        "prov-boe": f"Disposiciones de las secciones I y III del BOE que nombran la provincia, últimos {v} días.",
        "prov-dip": "Escaños en el Congreso por circunscripción.",
        "ccaa-preg": f"Preguntas que nombran la comunidad o alguna de sus provincias, sin contar dos veces la misma, últimos {v} días.",
        "ccaa-boe": f"Disposiciones del BOE que nombran la comunidad o alguna de sus provincias, o que firma la comunidad, últimos {v} días.",
        "ccaa-dip": "Escaños en el Congreso sumando sus circunscripciones.",
    }
    return (
        '<figure class="mp" data-m="preg" data-nivel="prov">'
        '<div class="mp-controles">'
        + grupo("mp-metrica", MAPA_METRICAS, "Qué se pinta en el mapa")
        + (grupo("mp-nivel", MAPA_NIVELES_VISTA, "Por provincias o por comunidades") if ag else "")
        + '</div><p class="mp-nota">' + "".join(
            f'<span data-para="{k}">{esc(n)}</span>' for k, n in notas.items()) + '</p>'
        f'<div class="mp-lienzo"><svg viewBox="{geo["viewBox"]}" role="group" '
        'aria-label="Mapa de España por provincias; cada provincia enlaza a su página">'
        f'<path class="mp-marco" d="{geo["marco"]}"/>'
        + _rotulo_canarias(geo["marco"])
        + "".join(formas)
        + f'<path class="mp-ccaa" d="{geo["ccaa"]}"/>'
        '</svg><div class="mp-tip" hidden></div></div>'
        + "".join(leyenda(n, m, e) for n, _en in MAPA_NIVELES_VISTA for m, e in MAPA_METRICAS)
        + f'<figcaption>Pasa por encima para ver las cifras; haz clic para abrir la provincia, o '
          f'la comunidad en la lista de abajo. Límites: {esc(geo.get("fuente", "IGN"))}.</figcaption>'
        '</figure>' + MAPA_JS)


def _rotulo_canarias(marco: str) -> str:
    """«Canarias» en la esquina del recuadro (marco = «Mx,yH…»)."""
    m = re.match(r"M([\d.]+),([\d.]+)", marco or "")
    if not m:
        return ""
    return (f'<text class="mp-rotulo" x="{float(m.group(1)) + 8}" '
            f'y="{float(m.group(2)) + 16}">Canarias</text>')


MAPA_JS = """<script>
(function () {
  var fig = document.querySelector('.mp'); if (!fig) return;
  var tip = fig.querySelector('.mp-tip'), lienzo = fig.querySelector('.mp-lienzo');
  var provs = [].slice.call(fig.querySelectorAll('.mp-prov'));
  function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
  function pintar() {
    var n = fig.getAttribute('data-nivel'), m = fig.getAttribute('data-m');
    provs.forEach(function (a) { a.setAttribute('data-q', a.dataset['q' + cap(n) + cap(m)] || '0'); });
  }
  function grupo(sel, attr) {
    fig.querySelectorAll(sel + ' button').forEach(function (b) {
      b.addEventListener('click', function () {
        fig.setAttribute(attr, b.dataset.v);
        fig.querySelectorAll(sel + ' button').forEach(function (o) {
          o.setAttribute('aria-pressed', o === b ? 'true' : 'false'); });
        pintar(); tip.hidden = true;
      });
    });
  }
  grupo('.mp-metrica', 'data-m'); grupo('.mp-nivel', 'data-nivel');
  function linea(n, uno, varios, on) {
    return '<span' + (on ? ' class="on"' : '') + '><b>' + n + '</b> ' + (n == 1 ? uno : varios) + '</span>';
  }
  function marcar(a) {
    var cc = fig.getAttribute('data-nivel') === 'ccaa' ? a.dataset.cc : null;
    fig.classList.add('hay-sel');
    provs.forEach(function (o) { o.classList.toggle('sel', cc ? o.dataset.cc === cc : o === a); });
  }
  function soltar() { fig.classList.remove('hay-sel'); provs.forEach(function (o) { o.classList.remove('sel'); }); tip.hidden = true; }
  function mostrar(a, x, y, subir) {
    var d = a.dataset, m = fig.getAttribute('data-m'), cc = fig.getAttribute('data-nivel') === 'ccaa';
    var t = cc ? { n: d.cn, c: d.cnp == 1 ? 'Comunidad uniprovincial' : d.cnp + ' provincias', preg: d.cpreg, boe: d.cboe, dip: d.cdip }
               : { n: d.n, c: d.c, preg: d.preg, boe: d.boe, dip: d.dip };
    tip.innerHTML = '<strong>' + t.n + '</strong><span class="mp-tip-c">' + t.c + '</span>' +
      linea(t.preg, 'pregunta', 'preguntas', m === 'preg') +
      linea(t.boe, 'disposición del BOE', 'disposiciones del BOE', m === 'boe') +
      linea(t.dip, 'diputado', 'diputados', m === 'dip');
    tip.hidden = false; marcar(a);
    var r = lienzo.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
    var left = x - r.left + 14, top = y - r.top + 14;
    if (left + w > r.width) left = x - r.left - w - 14;
    if (top + h > r.height) top = y - r.top - h - 14;
    tip.style.left = Math.max(0, left) + 'px'; tip.style.top = Math.max(0, top) + 'px';
    var ccaa = a.parentNode.querySelector('.mp-ccaa');
    if (subir && !cc && a.nextElementSibling !== ccaa) a.parentNode.insertBefore(a, ccaa);
  }
  provs.forEach(function (a) {
    a.addEventListener('pointermove', function (e) { if (e.pointerType === 'mouse') mostrar(a, e.clientX, e.clientY, true); });
    a.addEventListener('pointerleave', soltar);
    a.addEventListener('focus', function () { var b = a.getBoundingClientRect(); mostrar(a, b.left + b.width / 2, b.top + b.height / 2); });
    a.addEventListener('blur', soltar);
    a.addEventListener('click', function (e) {
      if (fig.getAttribute('data-nivel') !== 'ccaa' || !a.dataset.cdest) return;
      e.preventDefault(); location.href = a.dataset.cdest;
    });
  });
})();
</script>"""


def _menciones_ccaa_90(h: dict, estado: dict) -> tuple[dict, dict]:
    """Lo que nombra una comunidad (no una provincia) en los últimos
    VENTANA_INDICE días: preguntas y disposiciones del BOE, por identificador."""
    lim = (dt.date.today() - dt.timedelta(days=VENTANA_INDICE)).isoformat()
    preg: dict = {}
    for exp, v in (h["escritas"] or {}).items():
        if (v.get("c") or v.get("pr") or "") >= lim:
            for c in menciones_ccaa(v.get("t") or ""):
                preg.setdefault(c, set()).add(exp)
    for o in h["orales"] or []:
        if o["fecha"] >= lim:
            for c in menciones_ccaa(o["texto"]):
                preg.setdefault(c, set()).add("o:" + o["fecha"] + o["texto"])
    boe: dict = {}
    for k, v in estado["registros"].items():
        if v["fecha"] >= lim:
            for c in v.get("ccaa", []):
                boe.setdefault(c, set()).add(k)
    return preg, boe


def generar_paginas(h: dict) -> list:
    """/provincias/<slug>.html, el índice por comunidad y la metodología.

    `h` trae de build.py los datos ya calculados (fichas, filas de rankings,
    preguntas, tramitación, votaciones, nombramientos) y las utilidades de
    página. Aquí no se recalcula nada que ya tenga su sitio: la participación
    y la disidencia son las filas de rankings.filas_personas() y sus medias
    las de rankings.medias()."""
    esc, attr, fecha = h["esc_html"], h["esc_attr"], h["fmt_date_es"]
    site, plantilla, carpeta = h["site_url"], h["plantilla"], h["carpeta"]
    carpeta.mkdir(exist_ok=True)
    hoy = dt.date.today().isoformat()
    ref = cargar_referencia()
    estado = cargar()
    pct, umbral = h["pct"], h["umbral"]
    filas = {f["clave"]: f for f in h["filas"]}
    media_prov = {r["circ"]: r for r in h["participacion_provincias"]}
    nacional = h["medias_nacionales"]
    etiquetas = h["etiquetas"]
    det, det_nombres, cod_voto = h["detalle"], h["det_nombres"], h["cod_voto"]
    vent = h["ventana"]
    indice_nombres = {n: i for i, n in enumerate(det_nombres)}
    fuente = ('Fuentes: Congreso de los Diputados (datos abiertos y buscador de iniciativas) y '
              'sumario del BOE. <a class="srclink" href="/provincias/metodologia.html">Cómo se '
              'asignan las menciones</a>.')
    salidas, resumen = [], []

    def periodo(fechas):
        a, b = _en_rango(fechas)
        if not a:
            return ""
        return (f'<p class="rk-nota">Periodo: del {esc(fecha(a))} al {esc(fecha(b))}.</p>'
                if a != b else f'<p class="rk-nota">Periodo: {esc(fecha(a))}.</p>')

    def dias_txt(n):
        return f"{n} {'día' if n == 1 else 'días'}"

    # Preguntas y tramitación se casan una vez para las 52 provincias.
    escritas_por = {}
    for exp, v in (h["escritas"] or {}).items():
        for s in menciones(v.get("t") or ""):
            escritas_por.setdefault(s, []).append((exp, v))
    orales_por = {}
    for o in h["orales"] or []:
        for s in menciones(o["texto"]):
            orales_por.setdefault(s, []).append(o)
    ini_por = {}
    for exp, v in (h["iniciativas"] or {}).items():
        for s in menciones(v.get("t") or ""):
            ini_por.setdefault(s, []).append((exp, v))
    delegados = []
    for r in h["nombramientos"] or []:
        if re.search(r"\b(?:Sub)?[Dd]elegad[oa] del Gobierno\b", r.get("cargo") or ""):
            a = analizar(r["cargo"])
            delegados.append((r, a["provincias"], a["ccaa"]))

    for p in ref["provincias"]:
        slug, nombre, ccaa = p["slug"], p["nombre"], p["ccaa"]
        ccaa_nombre = ref["ccaa"][ccaa]["nombre"]
        fichas = sorted((f for f in h["fichas"] if h["slug_txt"](f.get("circunscripcion", "")) == slug),
                        key=lambda f: f.get("natural", ""))
        claves = {f.get("clave") for f in fichas}
        slugs_dip = {f.get("slug") for f in fichas}
        fechas_todas = []
        bloques = []

        # a) Sus diputados, con las cifras de /rankings/ y la media nacional.
        filas_dip = []
        for f in fichas:
            r = filas.get(f.get("clave")) or {}
            et = r.get("etiqueta") or etiquetas.get(f.get("clave"), "")
            corta = r.get("votaciones", 0) < umbral
            filas_dip.append(
                f'<tr><td><a href="/diputados/{attr(f["slug"])}.html">{esc(f["natural"])}</a>'
                + (f' <span class="rk-etq">{esc(et)}</span>' if et else "") + '</td>'
                f'<td>{esc(r.get("grupo") or f.get("sigla") or "")}</td>'
                f'<td class="num">{esc(pct(r["participacion"])) if r.get("participacion") is not None else "—"}'
                + (' <span class="ref">pocas votaciones</span>' if corta and r.get("votaciones") else "")
                + '</td>'
                f'<td class="num">{esc(pct(r["disidencia"])) if r.get("disidencia") is not None else "—"}</td>'
                f'<td class="num">{r.get("intervenciones", 0)}</td></tr>')
        mp = media_prov.get(p["circunscripcion"])
        comparacion = ""
        if mp and nacional.get("participacion") is not None:
            comparacion = (f'<p>Participación media de sus diputados: <b>{esc(pct(mp["media"]))}</b>; '
                           f'media nacional: {esc(pct(nacional["participacion"]))}. '
                           f'Intervenciones por diputado: media nacional '
                           f'{nacional["intervenciones"]:.0f}.</p>')
        bloques.append(
            f'<h2 class="rotulo" id="diputados">Sus diputados</h2>'
            f'<p>{len(fichas)} {"diputado" if len(fichas) == 1 else "diputados"} en el Congreso por '
            f'{esc(nombre)}. <a class="srclink" href="/diputados/provincia-{attr(slug)}.html">'
            f'Sus fichas, una a una</a></p>{comparacion}'
            + ('<table class="rk-tabla"><thead><tr><th>Diputado</th><th>Grupo</th><th>Participación</th>'
               '<th>Votos contra su grupo</th><th>Intervenciones</th></tr></thead><tbody>'
               + "".join(filas_dip) + '</tbody></table>' if filas_dip else "")
            + f'<p class="rk-nota">Mismos cálculos que <a href="/rankings/">los rankings</a>: '
              f'participación = 1 − («no vota» ÷ votaciones en que figura) y votos contra su grupo '
              f'sobre toda la legislatura; la media nacional y la provincial solo cuentan a quien '
              f'tiene al menos {umbral} votaciones.</p>')

        # b) Qué se pregunta sobre la provincia.
        items = []
        for exp, v in escritas_por.get(slug, []):
            autores = v.get("a") or []
            propio = any(h["clave_nombre"](a) in claves for a in autores)
            grupo = ", ".join(h["grupo_corto"](g) for g in v.get("g") or [])
            if v.get("c"):
                estado_txt = f'respondida el {fecha(v["c"])}'
                n = h["dias"](v.get("pr"), v["c"])
                if n is not None:
                    estado_txt += f' ({dias_txt(n)})'
            else:
                n = h["dias"](v.get("pr"), hoy)
                estado_txt = "pendiente" + (f' desde hace {dias_txt(n)}' if n is not None else "")
            items.append((v.get("c") or v.get("pr") or "", propio,
                          f'<li{CLASE_PROPIA if propio else ""}><a href="{attr(h["url_ficha"](exp))}" '
                          f'target="_blank" rel="noopener">{esc(v.get("t") or exp)}</a>'
                          f'<span class="ref">Escrita · {esc(", ".join(h["nombre_natural"](a) for a in autores[:3]))}'
                          f'{" (" + esc(grupo) + ")" if grupo else ""} · al Gobierno · {esc(estado_txt)}'
                          f'{" · diputado de la provincia" if propio else ""}</span></li>'))
        for o in orales_por.get(slug, []):
            propio = o.get("slug") in slugs_dip
            items.append((o["fecha"], propio,
                          f'<li{CLASE_PROPIA if propio else ""}><a href="/ediciones/{attr(o["edicion"])}.html">'
                          f'{esc(o["texto"])}</a><span class="ref">Oral en Pleno · {esc(o["autor"])} · '
                          f'{esc(o["destinatario"] or "al Gobierno")} · respondida en la sesión del '
                          f'{esc(fecha(o["fecha"]))}{" · diputado de la provincia" if propio else ""}</span></li>'))
        items.sort(key=lambda x: x[0], reverse=True)
        n_preg = len(items)
        n_preg_90 = sum(1 for f, _p, _h in items if f and f >= (dt.date.today() - dt.timedelta(days=VENTANA_INDICE)).isoformat())
        if items:
            fechas_todas += [f for f, _p, _h in items]
            bloques.append(
                f'<h2 class="rotulo" id="preguntas">Qué se pregunta sobre {esc(nombre)}</h2>'
                + periodo([f for f, _p, _h in items])
                + f'<p>{n_preg} preguntas al Gobierno nombran {esc(nombre)} en su título; '
                  f'{sum(1 for _f, pr, _h in items if pr)} las firman diputados de la provincia.</p>'
                + '<ul class="indice">' + "".join(x for _f, _p, x in items[:40]) + '</ul>')

        # c) Qué se tramita.
        inis = sorted(ini_por.get(slug, []), key=lambda x: h["ultima_fecha"](x[1]), reverse=True)
        if inis:
            fechas_todas += [h["ultima_fecha"](v) for _e, v in inis]
            bloques.append(
                f'<h2 class="rotulo" id="tramitacion">Qué se tramita</h2>'
                + periodo([v.get("fp") for _e, v in inis])
                + '<ul class="indice">' + "".join(
                    f'<li><a href="/tramitacion/{attr(h["slug_ini"](exp))}.html">{esc(v["t"].rstrip("."))}</a>'
                    f'<span class="ref">{esc(h["etiqueta_estado"].get(v["est"], v["est"]))} · {esc(exp)}</span></li>'
                    for exp, v in inis[:30]) + '</ul>')

        # d) Cómo votaron sus diputados en esas iniciativas.
        vots = []
        for exp, v in inis:
            for d in h["votaciones_de"](v, det):
                vots.append((exp, v, d))
        if vots and fichas:
            filas_v = []
            for exp, v, d in sorted(vots, key=lambda x: x[2]["f"], reverse=True)[:20]:
                celdas = []
                for f in fichas:
                    i = indice_nombres.get(f.get("clave"))
                    letra = d["v"][i] if i is not None and i < len(d.get("v") or "") else "-"
                    celdas.append(f'<td>{esc(cod_voto.get(letra, "—") if letra != "-" else "—")}</td>')
                filas_v.append(f'<tr><td><a href="/votaciones/{attr(h["pagina_votacion"](d))}">'
                               f'{esc(d.get("sub") or d.get("t") or "Votación")}</a>'
                               f'<span class="ref">{esc(fecha(d["f"]))} · {esc(v["t"][:90])}</span></td>'
                               + "".join(celdas) + '</tr>')
            fechas_todas += [d["f"] for _e, _v, d in vots]
            bloques.append(
                f'<h2 class="rotulo" id="votos">Cómo votaron sus diputados</h2>'
                f'<p class="rk-nota">Voto nominal de las votaciones del Pleno sobre esas iniciativas. '
                f'Solo se conserva el detalle de las últimas {vent["n"]} votaciones'
                + (f', del {esc(fecha(vent["desde"]))} al {esc(fecha(vent["hasta"]))}' if vent["n"] else "")
                + '.</p><div class="tabla-ancha"><table class="rk-tabla"><thead><tr><th>Votación</th>'
                + "".join(f'<th>{esc(f["natural"])}</th>' for f in fichas) + '</tr></thead><tbody>'
                + "".join(filas_v) + '</tbody></table></div>')

        # e) Lo que el BOE publica sobre la provincia.
        propios, comunidad = de_la_provincia(estado, slug, ccaa)
        n_boe_90 = sum(1 for r in propios if r["fecha"] >= (dt.date.today() - dt.timedelta(days=VENTANA_INDICE)).isoformat())

        def lista_boe(regs):
            por_cat: dict = {}
            for r in regs:
                por_cat.setdefault(r["cat"], []).append(r)
            html = ""
            for c, et, _rx in CATEGORIAS:
                if c not in por_cat:
                    continue
                html += (f'<h3 class="rotulo-sub">{esc(et)}</h3><ul class="indice">' + "".join(
                    f'<li><a href="{attr(r.get("url") or url_boe(r["id"]))}" target="_blank" rel="noopener">'
                    f'{esc(r["titulo"])}</a><span class="ref">{esc(fecha(r["fecha"]))} · {esc(r["id"])}</span></li>'
                    for r in por_cat[c][:15]) + '</ul>')
            return html
        if propios or comunidad:
            fechas_todas += [r["fecha"] for r in propios]
            bloques.append(
                f'<h2 class="rotulo" id="boe">Lo que el BOE publica sobre {esc(nombre)}</h2>'
                + periodo([r["fecha"] for r in propios + comunidad])
                + (f'<p>{len(propios)} disposiciones de las secciones I y III nombran {esc(nombre)} '
                   f'en su título.</p>' + lista_boe(propios) if propios else "")
                + (f'<h3 class="rotulo-sub" id="ccaa">De tu comunidad autónoma: {esc(ccaa_nombre)}</h3>'
                   + lista_boe(comunidad[:60]) if comunidad and ccaa not in h["uniprovinciales"] else ""))

        # f) Nombramientos territoriales.
        dels = [r for r, ps, cs in delegados if slug in ps or (not ps and ccaa in cs)]
        if dels:
            dels.sort(key=lambda r: r["fecha"], reverse=True)
            fechas_todas += [r["fecha"] for r in dels]
            bloques.append(
                f'<h2 class="rotulo" id="nombramientos">Delegación del Gobierno</h2>'
                + periodo([r["fecha"] for r in dels]) + '<ul class="indice">' + "".join(
                    f'<li><a href="/personas/{attr(h["slug_persona"].get(r["clave"], ""))}.html">'
                    f'{esc(r["persona"])}</a><span class="ref">{esc(h["etiqueta_nb"](r))}: '
                    f'{esc(r["cargo"])} · {esc(fecha(r["fecha"]))}</span></li>' for r in dels[:10]) + '</ul>')

        lastmod = max([f for f in fechas_todas if f] or [hoy])
        titulo = f"{nombre} en las Cortes y en el BOE: diputados, preguntas y votaciones"
        desc = (f"{nombre}: {len(fichas)} diputados, {n_preg} preguntas al Gobierno que la nombran y "
                f"{len(propios)} disposiciones del BOE sobre la provincia, con datos oficiales.")
        url = f"{site}provincias/{slug}.html"
        ficha = (f"<dt>Comunidad</dt><dd>{esc(ccaa_nombre)}</dd><dt>Capital</dt><dd>{esc(p['capital'])}</dd>"
                 f"<dt>Diputados</dt><dd>{len(fichas)}</dd><dt>Preguntas</dt><dd>{n_preg}</dd>"
                 f"<dt>BOE</dt><dd>{len(propios)} disposiciones</dd>")
        h["pagina_suelta"](plantilla, carpeta, f"{slug}.html", {
            "TITLE": esc(titulo), "META_DESC": attr(desc[:155]), "CANONICAL": url,
            "JSONLD": h["jsonld_script"]([
                {"@type": "Place", "name": nombre, "url": url,
                 **({"alternateName": sorted(set(p["variantes"]) - {nombre})} if p["variantes"] else {}),
                 "containedInPlace": {"@type": "AdministrativeArea", "name": ccaa_nombre}},
                {"@type": "BreadcrumbList", "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Portada", "item": site},
                    {"@type": "ListItem", "position": 2, "name": "Tu provincia", "item": f"{site}provincias/"},
                    {"@type": "ListItem", "position": 3, "name": nombre, "item": url}]}]),
            "EDITION_DATE": esc(f"Datos al {fecha(lastmod)}"),
            "MIGA": ('<a href="../">Portada</a> › <a href="./">Tu provincia</a> › '
                     f'<span aria-current="page">{esc(nombre)}</span>'),
            "KICKER": "Tu provincia en las Cortes y en el BOE", "HEADLINE": esc(nombre),
            "STANDFIRST": esc(f"Qué hacen los diputados de {nombre} en el Congreso y qué publica el "
                              f"Estado que le afecte."),
            "FICHA": ficha, "CUERPO": "".join(bloques), "FUENTE": fuente,
            "RELACIONADAS": "", "RELACIONADAS_HIDDEN": "hidden",
        })
        salidas.append({"url": url, "lastmod": lastmod})
        lim = (dt.date.today() - dt.timedelta(days=VENTANA_INDICE)).isoformat()
        preg_ids = ({exp for exp, v in escritas_por.get(slug, []) if (v.get("c") or v.get("pr") or "") >= lim}
                    | {"o:" + o["fecha"] + o["texto"] for o in orales_por.get(slug, []) if o["fecha"] >= lim})
        boe_ids = {r["id"] for r in propios if r["fecha"] >= lim}
        resumen.append({"p": p, "diputados": len(fichas), "preguntas_90": n_preg_90,
                        "boe_90": n_boe_90, "preg_ids": preg_ids, "boe_ids": boe_ids, "bloques": [b.split('id="')[1].split('"')[0] for b in bloques]})

    # Índice por comunidad autónoma.
    por_ccaa: dict = {}
    for r in resumen:
        por_ccaa.setdefault(r["p"]["ccaa"], []).append(r)
    cuerpo = (f'<p>Una página por circunscripción: sus diputados, lo que se pregunta y se tramita '
              f'sobre ella y lo que publica el BOE. Las cifras cuentan los últimos {VENTANA_INDICE} días.</p>'
              + mapa_html(resumen, ref, esc, attr, agregados_ccaa(resumen, *_menciones_ccaa_90(h, estado)))
              + '<h2 class="rotulo" id="lista">Todas las provincias</h2>')
    for c in sorted(por_ccaa, key=lambda c: ref["ccaa"][c]["nombre"]):
        cuerpo += (f'<h2 class="rotulo-sub" id="ccaa-{attr(c)}">{esc(ref["ccaa"][c]["nombre"])}</h2><ul class="indice">' + "".join(
            f'<li><a href="{attr(r["p"]["slug"])}.html">{esc(r["p"]["nombre"])}</a>'
            f'<span class="ref">{r["diputados"]} diputados · {r["preguntas_90"]} preguntas · '
            f'{r["boe_90"]} en el BOE</span></li>' for r in sorted(por_ccaa[c], key=lambda r: r["p"]["nombre"]))
            + '</ul>')
    url = f"{site}provincias/"
    h["pagina_suelta"](plantilla, carpeta, "index.html", {
        "TITLE": esc("Tu provincia en las Cortes y en el BOE | La Tercera Cámara"),
        "META_DESC": attr("Las 52 circunscripciones: qué hacen sus diputados en el Congreso, qué se "
                          "pregunta y se tramita sobre cada provincia y qué publica el BOE."),
        "CANONICAL": url,
        "JSONLD": h["jsonld_script"]([{"@type": "CollectionPage", "name": "Tu provincia", "url": url,
                                       "inLanguage": "es-ES", "dateModified": hoy}]),
        "EDITION_DATE": esc(f"Datos al {fecha(hoy)}"),
        "MIGA": '<a href="../">Portada</a> › <span aria-current="page">Tu provincia</span>',
        "KICKER": "Tu provincia", "HEADLINE": "Tu provincia en las Cortes y en el BOE",
        "STANDFIRST": "Elige tu circunscripción.", "FICHA": "", "CUERPO": cuerpo, "FUENTE": fuente,
        "RELACIONADAS": "", "RELACIONADAS_HIDDEN": "hidden",
    })
    salidas.append({"url": url, "lastmod": hoy})

    # Metodología.
    amb = ", ".join(sorted(AMBIGUOS))
    cats = "".join(f"<li>{esc(et)}</li>" for _c, et, _r in CATEGORIAS)
    cuerpo = (
        '<h2 class="rotulo">Fuentes</h2><p>Diputados, votaciones, intervenciones y preguntas: datos '
        'abiertos y buscador de iniciativas del Congreso. Iniciativas en tramitación: sus ficheros de '
        'datos abiertos. Disposiciones: el sumario diario del BOE, secciones I (disposiciones generales) y '
        'III (otras disposiciones). Nombramientos: la sección II del BOE.</p>'
        '<h2 class="rotulo">Cómo se asigna una provincia</h2><p>Solo cuenta lo que el TÍTULO nombra de '
        'forma explícita: el nombre oficial de la provincia, sus variantes bilingües o tradicionales '
        '(Girona/Gerona, Ourense/Orense, Bizkaia/Vizcaya…), su capital, sus islas y las localidades que se '
        'añadan a mano. Se busca palabra por palabra, sin distinguir tildes y exigiendo mayúscula inicial: '
        '«cuenca hidrográfica» no es Cuenca.</p><p>Los nombres que también son apellidos, empresas o '
        f'lugares de otros países ({esc(amb)}) solo cuentan con contexto: «en X», «de X», «provincia de X» '
        'o «a su paso por X», o entre paréntesis detrás de un municipio, y nunca detrás de «don» o «doña». Tampoco cuentan dentro de expresiones fijas '
        'como Banco Santander o Teruel Existe. Las comunidades autónomas se buscan antes: «Castilla y León» '
        'no es León y «Comunitat Valenciana» no es Valencia. Una mención de una comunidad con varias '
        'provincias va al apartado «De tu comunidad autónoma», no a cada provincia; en las uniprovinciales '
        'cuenta para su provincia. Preferimos dejar fuera una mención dudosa a asignarla mal.</p>'
        f'<h2 class="rotulo">Categorías del BOE</h2><p>Se deducen de palabras del título, en este orden de '
        f'prioridad:</p><ul>{cats}</ul>'
        '<h2 class="rotulo">Limitaciones</h2><p>No se leen los textos, solo los títulos. No se incluyen '
        'los boletines provinciales ni los autonómicos, ni los anuncios de ayuntamientos (Administración '
        'Local y sección V del BOE), ni páginas de municipios. El voto nominal solo se conserva para las '
        'últimas votaciones del Pleno. Las preguntas orales solo cuentan desde que el sitio las recoge.</p>'
        '<h2 class="rotulo">Contacto</h2><p>Para señalar un error o una asignación incorrecta: '
        '<a href="mailto:datos@terceracamara.es">datos@terceracamara.es</a>.</p>')
    url = f"{site}provincias/metodologia.html"
    h["pagina_suelta"](plantilla, carpeta, "metodologia.html", {
        "TITLE": esc("Cómo se hacen las páginas de provincia | La Tercera Cámara"),
        "META_DESC": attr("Fuentes, reglas de asignación de menciones, exclusiones y limitaciones de las "
                          "páginas de provincia de La Tercera Cámara."),
        "CANONICAL": url,
        "JSONLD": h["jsonld_script"]([{"@type": "WebPage", "name": "Metodología: provincias", "url": url,
                                       "inLanguage": "es-ES"}]),
        "EDITION_DATE": esc(f"Datos al {fecha(hoy)}"),
        "MIGA": ('<a href="../">Portada</a> › <a href="./">Tu provincia</a> › '
                 '<span aria-current="page">Metodología</span>'),
        "KICKER": "Metodología", "HEADLINE": "Cómo se hacen las páginas de provincia",
        "STANDFIRST": "De dónde sale cada dato y qué se deja fuera.", "FICHA": "", "CUERPO": cuerpo,
        "FUENTE": fuente, "RELACIONADAS": "", "RELACIONADAS_HIDDEN": "hidden",
    })
    salidas.append({"url": url, "lastmod": hoy})
    generar_paginas.resumen = resumen
    return salidas


generar_paginas.resumen = []


def entradas_buscador(entrada) -> list:
    """Una fila por provincia, con las variantes en el texto buscable para
    que «Gerona» encuentre Girona."""
    ref = cargar_referencia()
    return [entrada(f'{p["nombre"]}: en las Cortes y en el BOE',
                    f'Tu provincia · {ref["ccaa"][p["ccaa"]]["nombre"]}',
                    f'provincias/{p["slug"]}.html', "provincia", "",
                    " ".join([p["circunscripcion"], p["capital"], *p["variantes"], *p["localidades"]]),
                    largo=300)
            for p in ref["provincias"]]
