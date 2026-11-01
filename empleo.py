"""Empleo público (TC-013, v1): la sección II.B del BOE, «Oposiciones y concursos».

Determinista y sin red propia. Tres piezas:

  1. extraer(entradas, fecha): TODAS las disposiciones II.B del sumario (por
     identificador BOE, sin filtrar por tipo ni deduplicar por título: dos
     acuerdos del CGPJ con el mismo título son dos convocatorias), con un tipo
     deducido del título y del epígrafe, el organismo convocante y las
     provincias que el título nombra (provincias.menciones).
  2. El estado state/empleo.json, indexado por identificador: reprocesar un
     día lo sustituye, nunca duplica. Se poda a VENTANA_ESTADO días.
  3. generar_paginas(h): /empleo/ (últimos días), una ficha por organismo
     convocante (departamento del sumario) y una por provincia, cada una con su
     canal Atom (misma ruta, .xml). Cada disposición enlaza al BOE.

Fuera de v1: boletines autonómicos, una ficha por convocatoria (plazos,
plazas, temario) y el JSON-LD JobPosting: una oposición no es una oferta de
empleo al uso (no hay salario ni empleador únicos en el título) y Google
penaliza el JobPosting incompleto. Hasta que se decida, cada página declara
CollectionPage + ItemList con los enlaces al BOE.

Personas: el título de la II.B casi nunca nombra a nadie; si lo hace es el
BOE quien lo publica y por su función pública. No se lee el texto.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import unicodedata

import empleo_campos

ROOT = pathlib.Path(__file__).parent
ESTADO = ROOT / "state" / "empleo.json"
VERSION = 1
# Versión de la lectura del texto: sube cuando detalle() extrae algo nuevo,
# para que enriquecer() relea lo leído con una versión anterior (1 = antes de
# los campos de #45; 2 = antes de los puestos de provisión; 3 = antes del nombre sobre «Código de puesto», 22467). Lo que ya está
# al día no se relee.
LECTURA = 4
SECCIONES = ("2B",)              # código de la II.B en la API de datos abiertos
VENTANA_ESTADO = 400             # días que guarda el estado (regla 7: nada crece sin límite)
VENTANA_PAGINAS = 90             # días que enseñan las fichas
DIAS_PORTADA = VENTANA_PAGINAS   # días que enseña /empleo/ (UX-3: los mismos que las fichas)
DIAS_FILTRO = 30                 # chip «Últimos N días» de /empleo/ (UX-3)
JS_FILTRO = "/assets/empleo.js"  # filtrado en cliente de /empleo/ (UX-3), <3 KB
MAX_FILAS = 300                  # tope de filas por página
# Se enseña la cita del plazo solo tras validarla a mano (TC-013, iteración 1).
# /empleo/ y sus fichas van en noindex (y fuera del sitemap) hasta que haya
# fichas por convocatoria con valor propio: hoy son listados del sumario.
ROBOTS = "noindex, follow"

# Tipo de disposición, en orden de prioridad: la primera que encaja se queda.
# Se busca en título + epígrafe, sin tildes y en minúscula.
TIPOS = [
    ("admitidos", "Listas de admitidos y excluidos",
     r"admitid[oa]s|excluid[oa]s"),
    ("tribunal", "Tribunales y órganos de selección",
     r"\btribunal(?:es)? (?:calificador|de selecci|que ha de)|comision de seleccion|"
     r"organo de seleccion|(?:nombra|designa|modifica)\w* (?:el|los|la) (?:tribunal|comision)"),
    ("resultados", "Resultados, aprobados y adjudicaciones",
     r"aprobad[oa]s|han superado|superad[oa] el proceso|se resuelve|resuelve (?:el|la|parcialmente)|"
     r"adjudica|relacion definitiva de|nombra\w* funcionari"),
    ("provision", "Provisión de puestos (concursos y libre designación)",
     r"libre designacion|provision de puestos?|concurso (?:general|especifico|de traslados|de meritos)"),
    ("convocatoria", "Convocatorias de procesos selectivos",
     r"convoca|proceso selectivo|oposicion|concurso-oposicion|bolsa de (?:empleo|trabajo)|"
     r"plazas?\b"),
    ("otras", "Otras disposiciones", r""),
]
ETIQUETA_TIPO = {t: e for t, e, _r in TIPOS}
# Orden en que se enseñan los bloques en /empleo/ y sus fichas (UX-1).
ORDEN_ABIERTOS = ("convocatoria", "provision")
ORDEN_SEGUIMIENTO = ("admitidos", "tribunal", "resultados")
ORDEN_RESTO = ("otras",)
# A dónde lleva la nota de un listado recortado (rutas absolutas: sirven igual
# en el índice que en las fichas por organismo y provincia).
RSS_EMPLEO = "/empleo/index.xml"
ENLACE_ORGANISMOS = "/empleo/#organismos"
ENLACE_PROVINCIAS = "/empleo/#provincias"

DEPT_LOCAL = "ADMINISTRACIÓN LOCAL"
DEPT_UNIV = "UNIVERSIDADES"


def _plano(t: str) -> str:
    base = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return " ".join(base.split())


def slug(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _plano(t).lower()).strip("-")[:60] or "sin-nombre"


def tipo(titulo: str, epigrafe: str = "") -> str:
    t = (_plano(titulo) + " " + _plano(epigrafe)).lower()
    for clave, _et, rx in TIPOS:
        if not rx or re.search(rx, t):
            return clave
    return "otras"


# Regla de nombres de organismo (lenguaje llano, 31-10-2026). Determinista:
# - solo convierte si el nombre llega ENTERO en mayúsculas; si no, tal cual;
# - artículos, preposiciones y conjunciones en minúscula (salvo la primera);
# - siglas conocidas (SIGLAS), palabras con cifras («2030») y palabras sin
#   vocal («CSN») se dejan como están;
# - cada parte de «A-B» o «A/B» lleva su mayúscula;
# - ante cualquier carácter inesperado, el original (en la duda, lo del BOE).
MENORES = frozenset({"de", "del", "la", "las", "el", "los", "y", "e", "o", "u", "para", "con", "en",
                     "a", "al", "por", "sobre", "contra", "entre", "sin"})
SIGLAS = frozenset({"CNMC", "CSN", "CGPJ", "UNED", "CSIC", "AEAT", "SEPE", "INSS", "DGT", "BOE",
                    "UE", "II", "III", "IV", "VI", "VII", "VIII", "IX", "XI"})
RE_NOMBRE_OK = re.compile(r"^[A-ZÁÉÍÓÚÜÑÇÀÈÒÏ0-9 ,.\-/'·()]+$")


def _palabra(p: str, primera: bool) -> str:
    if not p:
        return p
    if not primera and p.lower().strip(",.()") in MENORES:
        return p.lower()
    if p.strip(",.()") in SIGLAS or any(ch.isdigit() for ch in p) or \
            not re.search(r"[AEIOUÁÉÍÓÚÜÀÈÒÏ]", p):
        return p
    for sep in ("-", "/"):
        if sep in p:
            return sep.join(_palabra(x, primera and i == 0) for i, x in enumerate(p.split(sep)))
    b = p.lower()
    nucleo = b.strip(",.()")
    if not primera and nucleo in MENORES:
        return b
    i = len(b) - len(b.lstrip("(")) if b else 0
    return b[:i] + b[i:i + 1].upper() + b[i + 1:]


def nombre_dept(dept: str) -> str:
    """«MINISTERIO DEL INTERIOR» -> «Ministerio del Interior»; «CONSEJO DE
    SEGURIDAD NUCLEAR» -> «Consejo de Seguridad Nuclear». Ver la regla arriba."""
    d = " ".join((dept or "").split())
    if not d or d != d.upper() or not RE_NOMBRE_OK.match(d):
        return d
    return " ".join(_palabra(p, i == 0) for i, p in enumerate(d.split(" ")))


RE_UNIV = re.compile(r"\bde la (Universi(?:dad|tat|dade)\b[^,(]*?)(?:,| \()")


def nombre_organismo(reg: dict) -> str:
    """Quién convoca, en llano. Local: el órgano del título (lugar():
    «Tamarite de Litera», «Consorcio Provincial…»), o «Administración Local».
    Universidades: la universidad del título, o «Universidades». Resto: el
    departamento con la regla de mayúsculas."""
    d = reg.get("dept") or ""
    if d.upper() == DEPT_LOCAL:
        lg = empleo_campos.lugar(reg)
        m = empleo_campos.RE_ORGANO_LOCAL.search(reg.get("titulo") or "")
        if lg and m and m.group(1) in ("Ayuntamiento", "Concello", "Ajuntament"):
            return f"{m.group(1)} de {lg}"   # como el título: «Ajuntament de Olot»
        return lg or "Administración Local"
    if d.upper() == DEPT_UNIV:
        m = RE_UNIV.search(reg.get("titulo") or "")
        return m.group(1).strip() if m else "Universidades"
    return nombre_dept(d)


# ------------------------------------------------------------------ extracción

def entradas_de_sumario(datos: dict, secciones=SECCIONES) -> list[dict]:
    """Las entradas de las secciones pedidas de un data.sumario de la API, sin
    filtro ni deduplicado. Mismo formato que reproceso.sumario_api()."""
    import reproceso
    return reproceso.entradas_de_sumario(datos, secciones)


def extraer(entradas: list[dict], fecha_boe, log=print) -> list[dict]:
    """Una fila por disposición II.B con identificador BOE."""
    import provincias as pv
    fecha = fecha_boe.isoformat() if hasattr(fecha_boe, "isoformat") else str(fecha_boe)
    salida, vistos, sin_id = [], set(), 0
    for e in entradas or []:
        if str(e.get("codigo") or "") not in SECCIONES:
            continue
        ident = e.get("ident") or ""
        if not re.fullmatch(r"BOE-A-\d{4}-\d+", ident):
            sin_id += 1
            continue
        if ident in vistos:
            continue
        vistos.add(ident)
        titulo = " ".join((e.get("titulo") or "").split())
        epigrafe = " ".join((e.get("epigrafe") or "").split())
        dept = " ".join((e.get("dept") or "").split())
        reg = {"id": ident, "fecha": fecha, "titulo": titulo, "dept": dept, "epi": epigrafe,
               "tipo": tipo(titulo, epigrafe), "prov": sorted(pv.menciones(titulo))}
        url = e.get("url") or ""
        if url and url != url_boe(ident):
            reg["url"] = url
        salida.append(reg)
    log(f"empleo {fecha}: {len(salida)} disposiciones II.B" + (f"; {sin_id} sin identificador" if sin_id else ""))
    extraer.ultimos_descartes = {"sin identificador BOE": sin_id} if sin_id else {}
    return salida


extraer.ultimos_descartes = {}


def url_boe(ident: str) -> str:
    return f"https://www.boe.es/diario_boe/txt.php?id={ident}"


# ------------------------------------------------------- plazo y tipo de proceso
#
# Iteración 1 (TC-013): para las convocatorias se lee el texto de la disposición
# (txt.php: el BOE excluye /diario_boe/xml.php? entero en su robots.txt) y se
# cita LITERAL la frase del plazo de solicitudes. Nunca se calcula una fecha de
# cierre: el cómputo depende de hábiles/naturales, festivos y, a menudo, de otro
# boletín. Si la frase no se reconoce, no se muestra nada. Validado a mano sobre
# una muestra (ver la PR #38).

_NUM = (r"(?:\d+|un|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|"
        r"quince|dieciséis|veinte|veinticinco|treinta|cuarenta(?:\s+y\s+cinco)?)")
RE_PLAZO_DUR = re.compile(r"(?:dentro\s+de\s+los\s+(?=\S+\s+d[ií]as)|plazo\s+)(?:de\s+(?:presentaci[oó]n|admisi[oó]n)\s+de\s+(?:las\s+)?(?:solicitudes|instancias)"
                          r"(?:\s+de\s+participaci[oó]n)?(?:\s+ser[aá])?,?\s+)?(?:de\s+)?(?:los\s+)?" + _NUM +
                          r"\s+(?:d[ií]as|mes(?:es)?)\b", re.I)
RE_SOLICITUD = re.compile(r"solicitud|instancia", re.I)
RE_EXCLUIR = re.compile(r"recurso|retirar|alegaci|subsana|documentaci[oó]n|toma de posesi[oó]n|"
                        r"plazo m[aá]ximo|reclamaci|inscripci[oó]n", re.I)
RE_CABECERA = re.compile(r"^.{0,60}?\b\d+(?:\.\d+)+\.?\s+(?=[A-ZÁÉÍÓÚ])")
ANTES, DESPUES = 60, 240


def frases(texto):
    out, prof, ini = [], 0, 0
    for i, c in enumerate(texto):
        if c == "«":
            prof += 1
        elif c == "»":
            prof = max(0, prof - 1)
        elif (c == "." and prof == 0 and i + 2 < len(texto) and texto[i + 1] == " " and texto[i + 2].isupper()
              and not re.search(r"\b(?:Sr|Sra|Excmo|Excma|Ilmo|Ilma|núm|art|D|Dña|Avda|C)$", texto[max(0, i - 6):i])):
            out.append(texto[ini:i + 1].strip())
            ini = i + 1
    if texto[ini:].strip():
        out.append(texto[ini:].strip())
    return out


def plazo_literal(texto):
    for f in frases(texto):
        m = RE_PLAZO_DUR.search(f)
        if not m or not RE_SOLICITUD.search(f) or RE_EXCLUIR.search(f[max(0, m.start() - 120):m.end() + 120]):
            continue
        f2 = RE_CABECERA.sub("", f)
        f2 = re.sub(r"^(?:\d+(?:\.\d+)*\.?|[a-z]\)|[A-ZÁÉÍÓÚ][a-záéíóú]+\.)\s+", "", f2)
        f2 = re.sub(r"\s+\d+(?:\.\d+)*\.?$", "", f2)
        m = RE_PLAZO_DUR.search(f2)
        ini = 0 if m.start() <= ANTES else m.start()
        cierre = f2.find("»", m.end())
        # «…en el «DOGC» o en el «BOE»»: la alternativa forma parte del plazo.
        while cierre >= 0 and re.match(r"\s+o (?:en )?(?:el|la) «", f2[cierre + 1:cierre + 15]):
            cierre = f2.find("»", f2.find("«", cierre + 1))
        fin = cierre + 1 if 0 <= cierre <= m.end() + DESPUES else min(len(f2), m.end() + DESPUES)
        if fin < len(f2) and f2[fin - 1] != "»":
            fin = f2.rindex(" ", 0, fin)
        if fin >= len(f2) - 1:
            fin = len(f2)
        return ("[…] " if ini else "") + f2[ini:fin].strip().rstrip(",;:") + (" […]" if fin < len(f2) else "")
    return None


PROCESOS = {"concurso-oposicion": "Concurso-oposición", "oposicion": "Oposición",
            "concurso": "Concurso", "libre designacion": "Libre designación"}
RE_PROCESO = re.compile(r"\b(?:sistema|procedimiento|turno)(?: selectivo)? (?:general )?(?:de (?:acceso libre,? (?:por|mediante) (?:el sistema de )?)?)?"
                        r"(concurso-oposicion|oposicion libre|oposicion|concurso de meritos|concurso|libre designacion)\b"
                        r"|\bpor (?:el sistema de )?(concurso-oposicion|oposicion|libre designacion)\b"
                        r"|\b(?:convoca|convocan|convocatoria (?:de|del|para))\w* (?:el |un |la )?(concurso)\b"
                        r"|\b(concurso) (?:general|especifico|de acceso|de traslados|para la provision)")
RE_SISTEMA_BASES = re.compile(r"proceso selectivo se realizara mediante el sistema de "
                              r"(concurso-oposicion|oposicion|concurso)\b,?( (?:para|en) (?:las personas|el turno|los aspirantes))?")
RE_NO_CONVOCATORIA = re.compile(r"correccion de errores|desiert|se modifica|modifican?\b|se publica|amplia|"
                                r"anula|deja sin efecto|suspende", re.I)


def es_convocatoria(reg: dict) -> bool:
    """Solo de las convocatorias de verdad se lee el texto: no de listas,
    tribunales, correcciones, desiertas, modificaciones ni cursos."""
    if reg.get("tipo") not in ("convocatoria", "provision"):
        return False
    t = _plano(reg.get("titulo", "")).lower()
    return not RE_NO_CONVOCATORIA.search(t) and not re.search(r"\bcursos?\b", _plano(reg.get("epi", "")).lower())


def _procesos(texto: str) -> set:
    vistos = set()
    for m in RE_PROCESO.finditer(_plano(texto).lower()):
        p = next(g for g in m.groups() if g)
        p = {"oposicion libre": "oposicion", "concurso de meritos": "concurso"}.get(p, p)
        vistos.add(p)
    return vistos


def proceso(titulo: str, epigrafe: str, texto: str = "") -> str:
    """Tipo de proceso según epígrafe, título y, si no, el arranque del texto.
    Si no consta o hay varios distintos, cadena vacía (sin etiqueta)."""
    if "libre designacion" in _plano(epigrafe + " " + titulo).lower():
        return PROCESOS["libre designacion"]
    for fuente in (titulo, texto[:6000]):
        ps = _procesos(fuente)
        if len(ps) == 1:
            return PROCESOS[ps.pop()]
        if len(ps) > 1:
            return ""
    # Convocatorias largas de la AGE: «6.1 El proceso selectivo se realizará
    # mediante el sistema de oposición». Si distingue turnos («para las
    # personas…»), no hay etiqueta única.
    ps = set()
    for m in RE_SISTEMA_BASES.finditer(_plano(texto).lower()):
        if m.group(2):
            return ""
        ps.add(m.group(1))
    return PROCESOS[ps.pop()] if len(ps) == 1 else ""


def detalle(html: str, reg: dict) -> dict:
    """{'plazo': cita literal o ausente, 'proc': etiqueta o ausente, y lo que
    dé empleo_campos: 'campos' (dict) o 'no_oferta' (etiqueta)}. Todo
    opcional: un registro sin estas claves se pinta como antes."""
    from bs4 import BeautifulSoup
    cuerpo = BeautifulSoup(html, "html.parser").find(id="textoxslt")
    texto = " ".join(cuerpo.get_text(" ", strip=True).split()) if cuerpo else ""
    out = {}
    if cuerpo:
        out.update(empleo_campos.extraer_campos(reg, cuerpo.get_text("\n", strip=True), str(cuerpo)))
    pl = plazo_literal(texto) if texto else None
    if pl:
        out["plazo"] = pl
    pr = proceso(reg.get("titulo", ""), reg.get("epi", ""), texto)
    if pr:
        out["proc"] = pr
    return out


def url_texto(ident: str) -> str:
    return f"https://www.boe.es/diario_boe/txt.php?id={ident}"


_get = None


def usar_get(get) -> None:
    """El recolector (build.get: robots.txt del BOE y pausa mínima) que usa
    enriquecer() en el reprocesado. Sin él no se lee ningún texto."""
    global _get
    _get = get


def al_dia(anterior: dict) -> bool:
    """¿Lectura guardada con la versión actual? `leido: 1` (o True) es previa."""
    v = anterior.get("leido")
    return isinstance(v, int) and not isinstance(v, bool) and v >= LECTURA


def _copiar(anterior: dict, r: dict) -> bool:
    if not anterior.get("leido"):
        return False
    for k in ("plazo", "proc", "leido", "campos", "no_oferta"):
        if k in anterior:
            r[k] = anterior[k]
    return True


def pendientes(regs: list[dict], previo: dict | None = None) -> int:
    """Peticiones que haría enriquecer() con red (sin hacer ninguna)."""
    previo = previo or {}
    return sum(1 for r in regs if es_convocatoria(r)
               and not al_dia(previo.get(r["id"]) or {}))


def enriquecer(regs: list[dict], get=None, log=print, previo: dict | None = None) -> dict:
    """Añade plazo literal y tipo de proceso a las convocatorias. Reutiliza lo
    ya leído en `previo` (estado). Una petición por convocatoria nueva, por
    build.get (respeta robots.txt y el ritmo del colector)."""
    get = get or _get
    cuenta = {"leidas": 0, "reutilizadas": 0, "fallos": 0, "con_plazo": 0}
    previo = previo or {}
    for r in regs:
        if not es_convocatoria(r):
            continue
        anterior = previo.get(r["id"]) or {}
        if al_dia(anterior):
            _copiar(anterior, r)
            cuenta["reutilizadas"] += 1
        elif get is not None:
            try:
                resp = get(url_texto(r["id"]))
            except Exception as exc:                          # noqa: BLE001  (p. ej. --sin-red)
                log(f"empleo: sin lectura de textos ({type(exc).__name__}); el resto va sin plazo")
                get, resp = None, None
            if resp is None:
                cuenta["fallos"] += 1
                if _copiar(anterior, r):      # lectura antigua: mejor que nada
                    cuenta["con_plazo"] += "plazo" in r
                    continue
                pr = proceso(r["titulo"], r.get("epi", ""))
                if pr:
                    r["proc"] = pr
                continue
            r.update(detalle(resp.text, r))
            r["leido"] = LECTURA
            cuenta["leidas"] += 1
        elif _copiar(anterior, r):
            cuenta["reutilizadas"] += 1
        else:
            pr = proceso(r["titulo"], r.get("epi", ""))
            if pr:
                r["proc"] = pr
        cuenta["con_plazo"] += "plazo" in r
    log(f"empleo: textos {cuenta}")
    return cuenta


# ---------------------------------------------------------------------- estado

def cargar(ruta: pathlib.Path | None = None) -> dict:
    ruta = ruta or ESTADO
    try:
        e = json.loads(ruta.read_text(encoding="utf-8"))
        if e.get("version") == VERSION:
            e.setdefault("registros", {})
            e.setdefault("dias", {})
            return e
    except Exception:                                         # noqa: BLE001
        pass
    return {"version": VERSION, "registros": {}, "dias": {}}


def guardar(e: dict, ruta: pathlib.Path | None = None) -> None:
    ruta = ruta or ESTADO
    ruta.parent.mkdir(exist_ok=True)
    texto = json.dumps(e, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if not ruta.exists() or ruta.read_text(encoding="utf-8") != texto:
        ruta.write_text(texto, encoding="utf-8")


def incorporar(registros: list[dict], fecha, fuente: str = "", ruta: pathlib.Path | None = None,
               hoy: dt.date | None = None) -> dict:
    """Mete los registros de un día sustituyendo los de esa fecha y poda lo
    anterior a VENTANA_ESTADO días."""
    e = cargar(ruta)
    f = fecha.isoformat() if hasattr(fecha, "isoformat") else str(fecha)
    for k in [k for k, v in e["registros"].items() if v.get("fecha") == f]:
        del e["registros"][k]
    for r in registros:
        e["registros"][r["id"]] = {k: v for k, v in r.items() if k != "id"}
    e["dias"][f] = {"n": len(registros), "fuente": fuente}
    corte = ((hoy or dt.date.today()) - dt.timedelta(days=VENTANA_ESTADO)).isoformat()
    e["registros"] = {k: v for k, v in e["registros"].items() if v.get("fecha", "") >= corte}
    e["dias"] = {k: v for k, v in e["dias"].items() if k >= corte}
    guardar(e, ruta)
    return e


def resumen_reproceso() -> dict:
    e = cargar()
    por_tipo: dict = {}
    for v in e["registros"].values():
        por_tipo[v["tipo"]] = por_tipo.get(v["tipo"], 0) + 1
    tam = ESTADO.stat().st_size if ESTADO.exists() else 0
    return {"registros": len(e["registros"]), "por_tipo": por_tipo, "bytes": tam}


def procesar_dia(entradas: list[dict], fecha, fuente: str, log=print) -> tuple[int, dict]:
    """Lo que llama el reprocesado común (reproceso.py) con cada sumario."""
    regs = extraer(entradas, fecha, log)
    enriquecer(regs, None, log, cargar()["registros"])
    incorporar(regs, fecha, fuente)
    return len(regs), dict(extraer.ultimos_descartes)


# --------------------------------------------------------------------- páginas

def _regs(estado: dict, hoy: str, dias: int) -> list[dict]:
    corte = (dt.date.fromisoformat(hoy) - dt.timedelta(days=dias)).isoformat()
    regs = [{"id": k, **v} for k, v in estado["registros"].items() if v.get("fecha", "") >= corte]
    for r in regs:
        if r.get("tipo") in ORDEN_ABIERTOS and empleo_campos.fuera_de_abiertos(r):
            r["tipo"] = "otras"
    return sorted(regs, key=lambda r: (r["fecha"], r["id"]), reverse=True)


def agrupar(regs: list[dict]) -> tuple[dict, dict]:
    """({slug_dept: (nombre, [regs])}, {slug_prov: [regs]})."""
    por_dept: dict = {}
    por_prov: dict = {}
    for r in regs:
        s = slug(r["dept"])
        por_dept.setdefault(s, (nombre_dept(r["dept"]), []))[1].append(r)
        for p in r.get("prov") or []:
            por_prov.setdefault(p, []).append(r)
    return por_dept, por_prov


def canales(h: dict, estado: dict | None = None) -> dict:
    """Escribe los canales Atom de /empleo/ y devuelve {(carpeta, página):
    (fichero .xml, título)} para que build los anuncie en cada página."""
    import feeds as fd
    estado = estado or cargar()
    hoy = h.get("hoy") or dt.date.today().isoformat()
    carpeta, site = h["carpeta"], h["site_url"]
    regs = _regs(estado, hoy, VENTANA_PAGINAS)
    por_dept, por_prov = agrupar(regs)
    nombres_prov = {p["slug"]: p["nombre"] for p in h["ref_provincias"]}
    salida: dict = {}

    def escribir(base: str, titulo: str, subtitulo: str, filas: list) -> None:
        entradas = fd.ordenar([fd.entrada(f"{r['id']}:empleo", r["titulo"], r["fecha"],
                                          r.get("url") or url_boe(r["id"]),
                                          ETIQUETA_TIPO.get(r["tipo"], "")) for r in filas])
        texto = fd.atom(titulo, subtitulo, f"{site}empleo/{base}.xml",
                        f"{site}empleo/{'' if base == 'index' else base + '.html'}", entradas)
        if texto:
            carpeta.mkdir(exist_ok=True)
            h["escribir"](carpeta / f"{base}.xml", texto)
            salida[(carpeta.name, f"{base}.html")] = (f"{base}.xml", titulo)

    escribir("index", "Empleo público en el BOE", "Oposiciones y concursos (sección II.B)", regs)
    for s, (nombre, filas) in por_dept.items():
        escribir(s, f"Empleo público · {nombre}", "Oposiciones y concursos en el BOE", filas)
    for p, filas in por_prov.items():
        if p in nombres_prov:
            escribir(f"provincia-{p}", f"Empleo público · {nombres_prov[p]}",
                     "Oposiciones y concursos del BOE que nombran la provincia", filas)
    return salida


def avisos(enlaces_prov: list, enlaces_dept: list) -> str:
    """UX-3: «Recibe avisos». Solo canales Atom (los que ya escribe canales()):
    el general y uno por provincia y por organismo. Sin correo ni registro."""
    def plegable(titulo: str, enlaces: list) -> str:
        if not enlaces:
            return ""
        return (f'<details class="em-sel"><summary>{titulo} <span class="ref">({len(enlaces)})</span>'
                f'</summary><ul class="em-sel-l">{"".join(enlaces)}</ul></details>')
    return ('<section id="avisos" class="em-avisos" aria-labelledby="avisos-t">'
            '<h2 id="avisos-t">Recibe avisos</h2>'
            '<p>Suscríbete a un canal RSS (Atom) en tu lector de noticias y te avisará de cada disposición '
            'nueva.<br>Sin correo ni registro: elige el canal general o el de una provincia u organismo. '
            '<a href="/seguir/">Cómo usar un lector RSS</a>.</p>'
            f'<p><a class="em-btn" href="{RSS_EMPLEO}">Canal de todo el empleo público</a></p>'
            '<div class="em-filtros">' + plegable("Canal por provincia", enlaces_prov)
            + plegable("Canal por organismo convocante", enlaces_dept) + '</div></section>')


def selectores(enlaces_prov: list, enlaces_dept: list) -> str:
    """UX-2: dos listas plegables (<details>) con enlaces a las páginas por
    provincia y por organismo, antes del listado. Sin JS: son enlaces."""
    def plegable(clase: str, titulo: str, enlaces: list) -> str:
        if not enlaces:
            return ""
        return (f'<details class="em-sel em-sel-{clase}"><summary>{titulo} '
                f'<span class="ref">({len(enlaces)})</span></summary>'
                f'<ul class="em-sel-l">{"".join(enlaces)}</ul></details>')
    html = (plegable("prov", "Elegir provincia", enlaces_prov)
            + plegable("org", "Elegir organismo convocante", enlaces_dept))
    return f'<nav id="filtros" class="em-filtros" aria-label="Filtrar por provincia u organismo">{html}</nav>' if html else ""

def chips_filtro(filas: list, ref: str) -> str:
    """Pestañas de /empleo/ (lenguaje llano, 31-10-2026; antes, los botones de
    UX-3). Un tablist con una pestaña por tipo presente (Convocatorias primero)
    y «Todas»; el botón «Últimos N días» sigue aparte (aria-pressed). Todo sale
    con hidden: solo JS_FILTRO lo enseña, y sin JS se ven todas las secciones
    (las cabeceras enlazan con #t-…). Estado compartido con ?tipo=…&dias=… o
    #tipo=… (los mismos valores de siempre)."""
    from html import escape as esc
    hay = {r["tipo"] for r in filas}
    tipos = [t for t in ORDEN_ABIERTOS + ORDEN_SEGUIMIENTO + ORDEN_RESTO if t in hay]
    if not tipos:
        return ""
    tab = ('<button type="button" role="tab" class="em-fb em-tab" id="tab-{v}" data-f="tipo" data-v="{v}" '
           'aria-controls="{c}" aria-selected="{p}" tabindex="{ti}">{e}</button>')
    bt = "".join(tab.format(v=t, c=f"p-{t}", p="true" if i == 0 else "false", ti="0" if i == 0 else "-1",
                            e=esc(PESTANAS.get(t, ETIQUETA_TIPO[t]))) for i, t in enumerate(tipos))
    bt += tab.format(v="todas", c=" ".join(f"p-{t}" for t in tipos), p="false", ti="-1", e="Todas")
    bd = (f'<button type="button" class="em-fb em-dias" data-f="dias" data-v="{DIAS_FILTRO}" '
          f'aria-pressed="false">Últimos {DIAS_FILTRO} días</button>')
    return (f'<div id="filtro-tipo" class="em-filtro" data-ref="{esc(ref)}" data-defecto="{tipos[0]}" hidden>'
            f'<div role="tablist" aria-label="Tipo de disposición" class="em-fg em-tabs">{bt}</div>'
            f'<div role="group" aria-label="Filtrar por fecha" class="em-fg">{bd}</div>'
            f'<p class="ref em-fn" role="status" aria-live="polite"></p></div>'
            f'<script src="{JS_FILTRO}" defer></script>')


TITULAR_MAX = 120


def titular_corto(r: dict, maximo: int = TITULAR_MAX) -> tuple[str, bool]:
    """(titular, recortado). El cuerpo si el extractor lo diera (hoy no lo da:
    no se toca el recolector); si no, el título cortado en un límite de
    palabra, con «…», sin pasar de `maximo` caracteres en total."""
    base = " ".join((r.get("cuerpo") or r.get("titulo") or "").split())
    if r.get("cuerpo"):
        return base, True
    if len(base) <= maximo:
        return base, False
    corte = base[:maximo - 1]
    if " " in corte:
        corte = corte[:corte.rindex(" ")]
    return corte.rstrip(" ,;:.-–(") + "…", True


def url_pdf(r: dict) -> str:
    """PDF oficial de la disposición en el BOE de su día (solo se enlaza)."""
    a, m, d = r["fecha"].split("-")
    return f"https://www.boe.es/boe/dias/{a}/{m}/{d}/pdfs/{r['id']}.pdf"


def fecha_referencia(estado: dict, hoy: str) -> str:
    """Fecha del BOE más reciente recogido (la de la edición del build). Así
    «hace N días» es determinista: no depende del reloj ni del navegador."""
    fechas = [v.get("fecha", "") for v in (estado.get("registros") or {}).values() if v.get("fecha")]
    return max(fechas, default=hoy)


def convocatorias_del_dia(estado: dict, fecha_boe: str) -> int:
    """UX-4 (8): cifra del módulo de empleo de la portada.

    «Del día» es la fecha del BOE de la edición que enseña la portada
    (data/<fecha>.json, boe.fechaISO). Solo cuenta si ese BOE es también el
    último recogido en state/empleo.json (fecha_referencia); si no coinciden
    (la captura de empleo de ese día falló o va por detrás) devuelve 0 y el
    módulo no se pinta: nunca una cifra de otro día bajo la fecha de hoy.

    Se cuentan los registros de esa fecha con tipo «convocatoria» (procesos
    selectivos), con la misma regla que /empleo/: las desiertas no son oferta
    abierta (empleo_campos.fuera_de_abiertos). Nada calculado: ni plazos ni
    fechas de cierre."""
    if not fecha_boe or fecha_referencia(estado, "") != fecha_boe:
        return 0
    return sum(1 for v in (estado.get("registros") or {}).values()
               if v.get("fecha") == fecha_boe and v.get("tipo") == "convocatoria"
               and not empleo_campos.fuera_de_abiertos(v))


def publicada(fecha: str, ref: str) -> str:
    """El mismo día del BOE de referencia: «Publicada en el último BOE»;
    después, «hace 1 día», «hace N días»."""
    n = (dt.date.fromisoformat(ref) - dt.date.fromisoformat(fecha)).days
    if n <= 0:
        return "Publicada en el último BOE"
    return "Publicada hace 1 día" if n == 1 else f"Publicada hace {n} días"


# ---------------------------------------------------- tarjeta en lenguaje llano

# Plazo en llano en la tarjeta: ENCENDIDO (ver empleo_campos.MOSTRAR_PLAZO_LLANO).
PERSONAL_LLANO = {"Personal funcionario": "Personal funcionario", "Personal laboral": "Personal laboral"}
EPI_GENERICOS = frozenset({"", "Personal funcionario y laboral", "Personal funcionario", "Personal laboral",
                           "Personal de administración y servicios", "Cuerpos docentes universitarios"})
ETIQUETA_LLANA = {"provision": ("Cambio de puesto", "provision"), "admitidos": ("Lista de admitidos", "admitidos"),
                  "tribunal": ("Tribunal", "tribunal"), "resultados": ("Resultado", "resultados"),
                  "otras": ("Otra disposición", "otras")}
# Pestañas (tablist) de /empleo/: mismo valor que ?tipo= / #tipo=.
PESTANAS = {"convocatoria": "Convocatorias", "provision": "Cambio de puesto", "admitidos": "Listas de admitidos",
            "tribunal": "Tribunales", "resultados": "Resultados", "otras": "Otras"}


def etiqueta_llana(r: dict) -> tuple[str, str]:
    """(texto, clase de color) de la etiqueta de la tarjeta."""
    if r.get("tipo") == "convocatoria":
        proc = r.get("proc") or ""
        if proc == "Oposición":
            return "Oposición", "oposicion"
        if proc in ("Concurso", "Concurso-oposición"):
            return "Concurso", "concurso"
        return "Convocatoria", "convocatoria"
    return ETIQUETA_LLANA.get(r.get("tipo"), ("Otra disposición", "otras"))


def _epi_especifico(r: dict) -> str:
    e = " ".join((r.get("epi") or "").split())
    return "" if e in EPI_GENERICOS else e


def que_es(r: dict, ps: list | None = None) -> str:
    """«Qué es» de la tarjeta: solo con datos del BOE (título, epígrafe y
    campos activos), sin inventar nada; en la duda, el titular corto."""
    t, epi = r.get("tipo"), _epi_especifico(r)
    tit = _plano(r.get("titulo") or "").lower()
    corto = titular_corto(r)[0]
    ps = ps if ps is not None else empleo_campos.puestos_activos(r)
    if t == "convocatoria":
        gen = empleo_campos.titular(r)
        if gen:
            return gen.rsplit(" · ", 1)[0]
        return epi or corto
    if t == "provision":
        if len(ps) == 1:
            p = ps[0]
            return p["puesto"] + (f" · nivel {p['nivel']}" if p.get("nivel") else "")
        if ps:
            return f"{len(ps)} puestos"
        return epi or corto
    if t == "admitidos":
        base = ("Lista provisional de admitidos y excluidos" if "provisional" in tit else
                "Lista definitiva de admitidos y excluidos" if "definitiva" in tit else
                "Lista de admitidos y excluidos")
        return f"{base}: {epi}" if epi else base
    if t == "tribunal":
        return f"Tribunal: {epi}" if epi else corto
    if t == "resultados":
        if "aprobados de la fase de oposicion" in tit or "aprobados en la fase de oposicion" in tit:
            base = "Aprobados de la fase de oposición"
        elif "aprobados" in tit:
            base = "Lista de aprobados"
        else:
            base = "Resultado del proceso"
        return f"{base}: {epi}" if epi else base
    return corto


def plazo_tarjeta(r: dict, mostrar: bool | None = None) -> str | None:
    """Plazo en llano o None (⇒ «Consulta el plazo en el BOE»). Con la flag
    apagada, siempre None. Nunca una fecha de cierre."""
    mostrar = empleo_campos.MOSTRAR_PLAZO_LLANO if mostrar is None else mostrar
    if not mostrar or r.get("no_oferta"):
        return None
    return empleo_campos.plazo_llano(r.get("plazo") or "")


def generar_paginas(h: dict, estado: dict | None = None) -> list:
    """/empleo/index.html, una ficha por departamento y una por provincia."""
    estado = estado or cargar()
    esc, attr, fecha_es = h["esc_html"], h["esc_attr"], h["fmt_date_es"]
    carpeta, site = h["carpeta"], h["site_url"]
    hoy = h.get("hoy") or dt.date.today().isoformat()
    regs = _regs(estado, hoy, VENTANA_PAGINAS)
    # Sin datos (estado aún vacío tras la fusión) se pinta igualmente el índice:
    # el pie de todas las páginas enlaza a /empleo/.
    carpeta.mkdir(exist_ok=True)
    por_dept, por_prov = agrupar(regs)
    nombres_prov = {p["slug"]: p["nombre"] for p in h["ref_provincias"]}
    por_prov = {p: v for p, v in por_prov.items() if p in nombres_prov}
    salidas: list = []

    ref = fecha_referencia(estado, hoy)

    def linea_puesto(p: dict) -> str:
        # Cada dato en su etiqueta de color (UX, 29-10-2026); el « · » sigue en
        # el texto (oculto a la vista) para que se lea y se copie igual.
        sep = '<span class="em-sep"> · </span>'
        partes = [f'<span class="em-p-puesto">{esc(p["puesto"])}</span>']
        if p.get("nivel"):
            partes.append(f'<span class="em-tag em-tag-nivel">Nivel {esc(p["nivel"])}</span>')
        if p.get("localidad"):
            partes.append(f'<span class="em-tag em-tag-loc">{esc(p["localidad"])}</span>')
        return f'<li>{sep.join(partes)}</li>'

    def bloque_puestos(ps: list) -> str:
        # Provisión (tarjeta v2): «Puesto · Nivel · Localidad». Con varios,
        # «N puestos», los 3 primeros y el resto plegado. Sin puestos activos
        # (flag apagado o documento que no pasó la comprobación) no pinta nada.
        if not ps:
            return ""
        if len(ps) == 1:
            return f'<ul class="em-puestos">{linea_puesto(ps[0])}</ul>'
        resto = (f'<details class="em-completo"><summary>Ver todos los puestos ({len(ps)})</summary>'
                 f'<ul class="em-puestos">{"".join(linea_puesto(p) for p in ps)}</ul></details>'
                 if len(ps) > 3 else "")
        return (f'<span class="ref em-npuestos">{len(ps)} puestos</span>'
                f'<ul class="em-puestos">{"".join(linea_puesto(p) for p in ps[:3])}</ul>{resto}')

    def fila(r: dict, con_dept: bool = True) -> str:
        # Tarjeta en lenguaje llano (maqueta aprobada 31-10-2026): etiqueta de
        # color, «Qué es», «Quién y dónde», «Cuándo» y un único «Ver en el BOE».
        # Nunca una fecha de cierre calculada: el plazo, solo en llano con la
        # regla estricta y si MOSTRAR_PLAZO_LLANO; si no, «Consulta…».
        enlace = r.get("url") or url_boe(r["id"])
        et, clase = etiqueta_llana(r)
        no = empleo_campos.etiqueta_no_oferta(r)
        no = f'<span class="em-aviso">{esc(no)}</span>' if no else ""
        chips = "".join(f'<span class="em-chip">{esc(c)}</span>' for c in empleo_campos.chips(r))
        chips = f'<span class="em-chips">{chips}</span>' if chips else ""
        ps = empleo_campos.puestos_activos(r)
        que = que_es(r, ps)
        lista = bloque_puestos(ps) if len(ps) > 1 else ""
        quien = [nombre_organismo(r)] if (con_dept or r.get("dept", "").upper() in (DEPT_LOCAL, DEPT_UNIV)) else []
        if r.get("epi") in PERSONAL_LLANO:
            quien.append(PERSONAL_LLANO[r["epi"]])
        if len(ps) == 1 and ps[0].get("localidad"):
            quien.append(ps[0]["localidad"])
        quien = [q for q in quien if q]
        cuando = f'Publicada el {esc(fecha_es(r["fecha"]))} <span class="em-hace">({esc(publicada(r["fecha"], ref).replace("Publicada ", ""))})</span>'
        plazo = ""
        if r["tipo"] in ORDEN_ABIERTOS and not no:
            pl = plazo_tarjeta(r)
            plazo = (f'<span class="em-ll-plazo">Plazo: {esc(pl)}</span>' if pl else
                     '<span class="em-ll-plazo em-ll-consulta">Consulta el plazo en el BOE</span>')
        filas_ll = (f'<dt>Qué es</dt><dd class="em-que">{esc(que)}{lista}</dd>'
                    + (f'<dt>Quién y dónde</dt><dd>{esc(" · ".join(quien))}</dd>' if quien else "")
                    + f'<dt>Cuándo</dt><dd>{cuando}{"<br>" + plazo if plazo else ""}</dd>')
        return (f'<li class="em-card" data-fecha="{attr(r["fecha"])}">'
                f'<span class="em-etq em-etq-{clase}">{esc(et)}</span>{no}'
                f'<dl class="em-ll">{filas_ll}</dl>{chips}'
                f'<a class="em-btn em-boe" href="{attr(enlace)}" target="_blank" rel="noopener" '
                f'aria-label="Ver en el BOE: {attr(titular_corto(r, 90)[0])} ({attr(r["id"])})">'
                f'Ver en el BOE</a></li>')

    def carriles(t: str, xs: list, con_dept: bool, h: str) -> str:
        # Carriles deslizables por clase (maqueta 2 de la ronda 2, elegida el
        # 01-11-2026): una fila horizontal por etiqueta (Oposición, Concurso…),
        # con ‹ › y «Ver todos» (despliega la misma fila como lista, sin URL
        # nueva). Sin JS, las filas siguen deslizándose y todo está en el HTML.
        grupos: dict = {}
        for r in xs:
            grupos.setdefault(etiqueta_llana(r), []).append(r)
        sub = "h3" if h == "h2" else "h4"
        html = []
        for (et, clase), rs in grupos.items():
            cab = (f'<{sub} class="em-carril-t" id="c-{t}-{clase}">{esc(et)} ({len(rs)})</{sub}>'
                   if len(grupos) > 1 else "")
            nombre = et if len(grupos) > 1 else ETIQUETA_TIPO[t]
            html.append(
                f'<div class="em-carril" data-clase="{attr(clase)}">'
                f'<div class="em-carril-cab">{cab}<span class="em-carril-nav" hidden>'
                f'<button type="button" class="em-fb em-ant"><span aria-hidden="true">‹</span>'
                f'<span class="em-sep">Anteriores: {esc(nombre)}</span></button>'
                f'<button type="button" class="em-fb em-sig"><span aria-hidden="true">›</span>'
                f'<span class="em-sep">Siguientes: {esc(nombre)}</span></button></span></div>'
                f'<ul class="ix-lista em-pista" tabindex="0" aria-label="{attr(nombre)}: fila deslizable">'
                f'{"".join(fila(r, con_dept) for r in rs)}</ul>'
                f'<button type="button" class="em-fb em-vertodos" aria-expanded="false" hidden>'
                f'Ver todos ({len(rs)})</button></div>')
        return "".join(html)

    def bloque(t: str, filas: list, con_dept: bool, h: str = "h2", en_carril: bool = False) -> str:
        todas = [r for r in filas if r["tipo"] == t]
        xs = todas[:MAX_FILAS]
        if not xs:
            return ""
        # Tope visible (UX-1): si el listado se recorta, el encabezado dice
        # «N de M» y una nota lleva al resto (RSS y páginas por organismo y
        # provincia), para que contador y encabezado nunca se contradigan.
        recorte = len(todas) > len(xs)
        n = f"{len(xs)} de {len(todas)}" if recorte else f"{len(xs)}"
        nota = (f'<p class="aside-note">Se muestran {len(xs)} de {len(todas)}, las más recientes. '
                f'El resto, en el <a href="{RSS_EMPLEO}">canal RSS de empleo</a> y en las páginas '
                f'<a href="{ENLACE_ORGANISMOS}">por organismo</a> y '
                f'<a href="{ENLACE_PROVINCIAS}">por provincia</a>.</p>') if recorte else ""
        return (f'<section class="em-sec" id="p-{t}" data-tipo="{t}"><{h} id="t-{t}">{esc(ETIQUETA_TIPO[t])} '
                f'({n})</{h}>' +
                (carriles(t, xs, con_dept, h) if en_carril else
                 f'<ul class="ix-lista">{"".join(fila(r, con_dept) for r in xs)}</ul>') + f'{nota}</section>')

    def por_tipo(filas: list, con_dept: bool = True, en_carril: bool = False) -> str:
        # Orden de lectura (UX-1), distinto del de clasificación de TIPOS:
        # primero lo que se puede solicitar; después, bajo «Seguimiento de
        # procesos», las listas, tribunales y resultados de procesos en marcha.
        html = "".join(bloque(t, filas, con_dept, en_carril=en_carril) for t in ORDEN_ABIERTOS)
        seg = "".join(bloque(t, filas, con_dept, "h3", en_carril) for t in ORDEN_SEGUIMIENTO)
        if seg:
            html += ('<section class="em-sec em-grupo"><h2 id="seguimiento">Seguimiento de procesos</h2>'
                     + seg + '</section>')
        return html + "".join(bloque(t, filas, con_dept, en_carril=en_carril) for t in ORDEN_RESTO)

    def recuento(filas: list) -> str:
        # Cada contador enlaza a su sección (UX-1).
        return "".join(f'<dt>{esc(et)}</dt><dd><a href="#t-{t}">{n}</a></dd>' for t, et, _ in TIPOS
                       if (n := sum(1 for r in filas if r["tipo"] == t)))

    def primero(filas: list) -> str:
        """Tipo del primer bloque que se ve en la página (destino del total)."""
        hay = {r["tipo"] for r in filas}
        return next(t for t in ORDEN_ABIERTOS + ORDEN_SEGUIMIENTO + ORDEN_RESTO if t in hay)

    def item_list(filas: list) -> dict:
        return {"@type": "ItemList", "numberOfItems": len(filas),
                "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": r["titulo"][:200],
                                     "url": r.get("url") or url_boe(r["id"])}
                                    for i, r in enumerate(filas[:50])]}

    def pagina(nombre: str, titulo: str, desc: str, h1: str, entradilla: str, filas: list,
               cuerpo: str, miga_final: str) -> None:
        url = f"{site}empleo/{'' if nombre == 'index.html' else nombre}"
        lastmod = max((r["fecha"] for r in filas), default=hoy)
        miga = ('<a href="../">Portada</a> › '
                + ('<span aria-current="page">Empleo público</span>' if nombre == "index.html" else
                   f'<a href="./">Empleo público</a> › <span aria-current="page">{esc(miga_final)}</span>'))
        h["pagina_suelta"](h["plantilla"], carpeta, nombre, {
            "TITLE": esc(f"{titulo} | La Tercera Cámara"),
            "META_DESC": attr(desc),
            "CANONICAL": url,
            "JSONLD": h["jsonld_script"]([{"@type": "CollectionPage", "url": url, "name": titulo,
                                           "inLanguage": "es-ES", "dateModified": lastmod,
                                           "mainEntity": item_list(filas)}]),
            "EDITION_DATE": esc(f"Datos al {fecha_es(lastmod)}"),
            "MIGA": miga,
            "KICKER": "Empleo público · BOE II.B",
            "HEADLINE": esc(h1),
            "STANDFIRST": esc(entradilla),
            "FICHA": (f'<dt>Disposiciones</dt><dd><a href="#t-{primero(filas)}">{len(filas)}</a></dd>'
                      if filas else "<dt>Disposiciones</dt><dd>0</dd>") + recuento(filas),
            "CUERPO": cuerpo,
            "FUENTE": ('Fuente: sumario del Boletín Oficial del Estado, sección II.B «Oposiciones y '
                       'concursos» (API de datos abiertos). Cada disposición enlaza a su texto en el BOE, '
                       'que es el único que da fe: plazos y requisitos, allí.'),
            "RELACIONADAS": "", "RELACIONADAS_HIDDEN": "hidden",
        })
        salidas.append({"url": url, "lastmod": lastmod})

    # Fichas por departamento.
    enlaces_dept, feeds_dept, feeds_prov = [], [], []
    for s, (nombre, filas) in sorted(por_dept.items(), key=lambda x: x[1][0]):
        pagina(f"{s}.html", f"Empleo público: {nombre}",
               f"Oposiciones, concursos y listas de {nombre} publicadas en el BOE en los últimos "
               f"{VENTANA_PAGINAS} días, con enlace a cada disposición.",
               nombre, f"Lo que {nombre} ha publicado en la sección II.B del BOE (oposiciones y "
               f"concursos) en los últimos {VENTANA_PAGINAS} días.",
               filas, por_tipo(filas, con_dept=False), nombre)
        enlaces_dept.append(f'<li><a href="{attr(s)}.html">{esc(nombre)}</a>'
                            f'<span class="ref">{len(filas)}</span></li>')
        feeds_dept.append(f'<li><a href="{attr(s)}.xml">{esc(nombre)}</a></li>')
    # Fichas por provincia.
    enlaces_prov = []
    for p, filas in sorted(por_prov.items(), key=lambda x: nombres_prov[x[0]]):
        n = nombres_prov[p]
        pagina(f"provincia-{p}.html", f"Empleo público en {n}",
               f"Oposiciones y concursos del BOE que nombran {n} en el título, últimos "
               f"{VENTANA_PAGINAS} días.",
               f"Empleo público en {n}",
               f"Disposiciones de la sección II.B del BOE cuyo título nombra {n} (ayuntamientos, "
               f"diputación, universidades y plazas con destino en la provincia).",
               filas, por_tipo(filas) + f'<p><a href="/provincias/{attr(p)}.html">Todo lo de {esc(n)} '
               f'en La Tercera Cámara</a></p>', n)
        enlaces_prov.append(f'<li><a href="provincia-{attr(p)}.html">{esc(n)}</a>'
                            f'<span class="ref">{len(filas)}</span></li>')
        feeds_prov.append(f'<li><a href="provincia-{attr(p)}.xml">{esc(n)}</a></li>')
    # Índice.
    corte = (dt.date.fromisoformat(hoy) - dt.timedelta(days=DIAS_PORTADA)).isoformat()
    recientes = [r for r in regs if r["fecha"] >= corte] or regs[:MAX_FILAS]
    cuerpo = (f'<p>Disposiciones de los últimos {DIAS_PORTADA} días, también por organismo y por '
              f'provincia. Los días desde la publicación se cuentan hasta el BOE '
              f'del {esc(fecha_es(ref))}, el último recogido.</p>' + selectores(enlaces_prov, enlaces_dept)
              + chips_filtro(recientes, ref)
              + (por_tipo(recientes, en_carril=True) or
              '<p>Aún no hay disposiciones recogidas: la sección se llena con cada BOE nuevo.</p>')
              + f'<h2 id="organismos">Por organismo convocante</h2><ul class="ix-lista">{"".join(enlaces_dept)}</ul>'
              + (f'<h2 id="provincias">Por provincia</h2><ul class="ix-lista">{"".join(enlaces_prov)}</ul>'
                 if enlaces_prov else "")
              + (avisos(feeds_prov, feeds_dept) if regs else "")
              + '<p class="aside-note">Cómo se clasifica: el tipo sale de palabras del título y del '
              'epígrafe del sumario («admitidos», «tribunal», «aprobados», «libre designación», '
              '«convoca»…), en ese orden de prioridad; la provincia, de que el título la nombre. '
              'Es una ayuda para encontrar, no un dato oficial.</p>')
    pagina("index.html", "Empleo público: oposiciones y concursos del BOE",
           "Oposiciones, concursos, listas de admitidos y tribunales publicados en el BOE (sección II.B), "
           "por organismo y provincia, con enlace a cada disposición y canal RSS.",
           "Empleo público en el BOE",
           "Todas las disposiciones de la sección II.B del BOE, «Oposiciones y concursos»: "
           "convocatorias, listas, tribunales y resultados.", recientes, cuerpo, "")
    generar_paginas.resumen = {"departamentos": len(por_dept), "provincias": len(por_prov),
                               "disposiciones": len(regs)}
    return salidas


generar_paginas.resumen = {}
