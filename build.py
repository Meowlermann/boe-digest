#!/usr/bin/env python3
"""
La Tercera Cámara — pipeline diario.

Se ejecuta en GitHub Actions. Hace tres cosas:

  1. RECOLECTA   el sumario del BOE del día y las publicaciones oficiales
                 del Congreso y del Senado (BOCG y Diarios de Sesiones).
  2. REDACTA     titulares y artículos. Si hay un modelo configurado (cualquier
                 proveedor compatible con la API de OpenAI) lo usa; si no, cae a
                 una redacción determinista que nunca inventa hechos.
  3. RENDERIZA   data/*.json -> index.html con la plantilla template.html.

Principios de diseño:
  - El sitio NUNCA debe romperse. Si la recolección falla, se conserva lo
    publicado y se deja constancia.
  - El trabajo curado a mano NUNCA se pierde: lo que haya en curated/ se
    fusiona por encima de lo generado automáticamente.
  - Cada ejecución deja un diagnóstico en debug/last-run.json.

Uso:
    python build.py              # recolecta el día de hoy y renderiza
    python build.py --render     # solo renderiza desde data/*.json
    python build.py --date 2026-09-17
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import pathlib
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).parent
DATA_DIR = ROOT / "data"
CURATED_DIR = ROOT / "curated"
DEBUG_DIR = ROOT / "debug"
TEMPLATE = ROOT / "template.html"
TEMPLATE_EDICION = ROOT / "template_edicion.html"
TEMPLATE_ARCHIVO = ROOT / "template_archivo.html"
OUTPUT = ROOT / "index.html"
EDICIONES_DIR = ROOT / "ediciones"
NORMAS_DIR = ROOT / "normas"
TEMAS_DIR = ROOT / "temas"
DIPUTADOS_DIR = ROOT / "diputados"
DATOS_DIR = ROOT / "datos"
PLAZOS_DIR = ROOT / "plazos"
BUSCAR_DIR = ROOT / "buscar"
TEMPLATE_NORMA = ROOT / "template_norma.html"
FEED_FILE = ROOT / "feed.xml"

SITE_URL = "https://terceracamara.es/"
MAX_DAYS = 30
MAX_FEED_ITEMS = 20

# IndexNow: avisa a Bing, Yandex, Seznam, Naver, Yep e Internet Archive de las
# URLs que han cambiado, sin cuenta ni verificación. El fichero de clave vive en
# la raíz del dominio, así que alcanza a cualquier URL del sitio. (Google no participa: ahí hace falta Search
# Console, porque retiró el ping de sitemaps en 2023.)
INDEXNOW_KEY = "d29eac49b00fed8432cc6c405d618f35"
INDEXNOW_HOST = "terceracamara.es"
INDEXNOW_JSON = ROOT / "indexnow.json"      # sin versionar: lo publica el workflow con curl
REQUEST_TIMEOUT = 45

# Cabeceras de navegador real: las webs del Congreso y del Senado rechazan
# con 403 a los clientes que se identifican como script.
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "application/pdf;q=0.9,image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
MES_ABBR = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN",
            "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]

DIAG: dict = {"inicio": dt.datetime.now(dt.timezone.utc).isoformat(), "peticiones": []}


def log(msg: str) -> None:
    print(f"[build] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Capa de red — con calentamiento de sesión y cookies
# ---------------------------------------------------------------------------

_sesiones: dict[str, requests.Session] = {}


def sesion_para(url: str) -> requests.Session:
    """Una sesión por dominio. La primera vez visita la home para coger cookies."""
    host = re.sub(r"^https?://([^/]+).*$", r"\1", url)
    if host in _sesiones:
        return _sesiones[host]
    s = requests.Session()
    s.headers.update(HEADERS)
    try:
        s.get(f"https://{host}/", timeout=REQUEST_TIMEOUT)
        log(f"  sesión iniciada en {host}")
    except Exception as exc:                                  # noqa: BLE001
        log(f"  no se pudo calentar la sesión de {host}: {exc}")
    _sesiones[host] = s
    return s


_BLOQUEADOS: set[str] = set()


def get(url: str, tries: int = 3, referer: str | None = None) -> requests.Response | None:
    """GET tolerante. Devuelve None en vez de reventar, y anota el diagnóstico."""
    host = re.sub(r"^https?://([^/]+).*$", r"\1", url)
    if host in _BLOQUEADOS:
        # Ya nos ha denegado el acceso en esta ejecución: no insistimos.
        log(f"  {host} ya denegó el acceso; no se reintenta")
        return None
    s = sesion_para(url)
    ultimo = None
    for intento in range(1, tries + 1):
        try:
            headers = {"Referer": referer} if referer else {}
            r = s.get(url, timeout=REQUEST_TIMEOUT, headers=headers, allow_redirects=True)
            ultimo = r.status_code
            if r.status_code == 200:
                DIAG["peticiones"].append({"url": url, "status": 200, "bytes": len(r.content)})
                return r
            log(f"  {r.status_code} en {url}")
            if r.status_code == 403:
                _BLOQUEADOS.add(re.sub(r"^https?://([^/]+).*$", r"\1", url))
            if r.status_code == 403 and "403" not in DIAG:
                # Guardamos una muestra del bloqueo: sirve para saber qué WAF responde
                DIAG["403"] = {
                    "url": url,
                    "server": r.headers.get("Server", ""),
                    "via": r.headers.get("Via", ""),
                    "set_cookie": r.headers.get("Set-Cookie", "")[:200],
                    "cuerpo": re.sub(r"\s+", " ", r.text[:400]),
                }
            if r.status_code in (404, 410):
                break
        except Exception as exc:                              # noqa: BLE001
            ultimo = str(exc)[:120]
            log(f"  error en {url}: {exc}")
        if intento < tries:
            time.sleep(2 * intento)
    DIAG["peticiones"].append({"url": url, "status": ultimo})
    return None


# ---------------------------------------------------------------------------
# BOE — recolección y limpieza
# ---------------------------------------------------------------------------

RUIDO = re.compile(
    r"\s*PDF\s*\(\s*(?P<id>BOE-[A-Z]-\d{4}-\d+)?[^)]*\)\s*(?:Otros\s+formatos)?\s*$",
    re.I)
ID_BOE = re.compile(r"BOE-[A-Z]-\d{4}-\d+")


def limpiar_titulo(texto: str) -> tuple[str, str]:
    """Devuelve (título limpio, identificador BOE-A-... si aparece)."""
    ident = ""
    m = ID_BOE.search(texto)
    if m:
        ident = m.group(0)
    limpio = RUIDO.sub("", texto).strip()
    limpio = re.sub(r"\s*PDF\s*\(.*$", "", limpio).strip()
    limpio = re.sub(r"\s*Otros\s+formatos\s*$", "", limpio, flags=re.I).strip()
    limpio = " ".join(limpio.split())
    return limpio, ident


def clave_dedup(titulo: str) -> str:
    return re.sub(r"[^a-z0-9]", "", titulo.lower())[:120]


def fetch_boe(fecha: dt.date) -> dict | None:
    """Sumario del BOE. Prueba la fecha dada y hasta 3 días hacia atrás."""
    for delta in range(0, 4):
        d = fecha - dt.timedelta(days=delta)
        url = f"https://www.boe.es/boe/dias/{d.year}/{d.month:02d}/{d.day:02d}/index.php"
        log(f"BOE: probando {url}")
        r = get(url, tries=2)
        if not r:
            continue

        soup = BeautifulSoup(r.text, "html.parser")
        entradas: list[dict] = []
        vistos: set[str] = set()
        seccion = departamento = epigrafe = ""

        for el in soup.find_all(["h2", "h3", "h4", "h5", "li"]):
            txt = " ".join(el.get_text(" ", strip=True).split())
            if not txt:
                continue

            if el.name in ("h2", "h3"):
                if re.match(r"^[IVX]+\.", txt):
                    seccion = txt
                    departamento = epigrafe = ""
                continue
            if el.name == "h4":
                departamento = txt
                epigrafe = ""
                continue
            if el.name == "h5":
                epigrafe = txt
                continue

            # <li> con una disposición: debe empezar por un tipo de norma conocido
            if not re.match(r"^(Orden|Resolución|Real Decreto|Ley|Ley Orgánica|Acuerdo|"
                            r"Corrección|Extracto|Circular|Instrucción|Decreto)", txt):
                continue
            if len(txt) < 40:
                continue

            titulo, ident = limpiar_titulo(txt)
            k = clave_dedup(titulo)
            if not k or k in vistos:
                continue
            vistos.add(k)

            enlace = ""
            a = el.find("a", href=True)
            if a:
                href = a["href"]
                enlace = href if href.startswith("http") else f"https://www.boe.es{href}"
            if ident and not enlace:
                enlace = f"https://www.boe.es/diario_boe/txt.php?id={ident}"

            entradas.append({
                "seccion": seccion,
                "dept": departamento,
                "epigrafe": epigrafe,
                "titulo": titulo,
                "ident": ident,
                "url": enlace,
            })

        num = ""
        cab = soup.get_text(" ", strip=True)[:3000]
        m = re.search(r"[Nn]úm(?:ero)?\.?\s*(\d+)", cab)
        if m:
            num = m.group(1)

        log(f"BOE: {len(entradas)} disposiciones únicas para {d.isoformat()}")
        if entradas:
            return {"fecha_boe": d, "numero": num, "sourceUrl": url, "entradas": entradas}
    return None


# ---------------------------------------------------------------------------
# Congreso y Senado
# ---------------------------------------------------------------------------

def pdf_text(url: str, referer: str | None = None, max_chars: int = 120_000) -> str:
    r = get(url, tries=2, referer=referer)
    if not r:
        return ""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(r.content))
        partes, total = [], 0
        for page in reader.pages:
            t = page.extract_text() or ""
            partes.append(t)
            total += len(t)
            if total > max_chars:
                break
        return "\n".join(partes)
    except Exception as exc:                                  # noqa: BLE001
        log(f"  no se pudo leer el PDF {url}: {exc}")
        return ""


def fetch_congreso() -> list[dict]:
    docs: list[dict] = []
    idx = "https://www.congreso.es/ultimas-publicaciones-oficiales"
    r = get(idx)
    if not r:
        log("Congreso: no se pudo abrir la página de publicaciones")
        return docs

    soup = BeautifulSoup(r.text, "html.parser")
    candidatos, vistos = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".PDF" not in href.upper():
            continue
        full = href if href.startswith("http") else f"https://www.congreso.es{href}"
        if full in vistos:
            continue
        vistos.add(full)
        nombre = full.rsplit("/", 1)[-1]
        up = full.upper()
        if "/DS/" in up or nombre.upper().startswith("DSCD"):
            tipo = "Diario de Sesiones"
        elif "/BOCG/" in up:
            tipo = "BOCG"
        else:
            continue
        candidatos.append({"tipo": tipo, "url": full, "nombre": nombre,
                           "chamber_hint": "congreso"})

    log(f"Congreso: {len(candidatos)} publicaciones detectadas")
    ds = [d for d in candidatos if d["tipo"] == "Diario de Sesiones"][:2]
    bocg = [d for d in candidatos if d["tipo"] == "BOCG"][:2]
    for d in ds + bocg:
        d["texto"] = pdf_text(d["url"], referer=idx)
        log(f"  {d['nombre']}: {len(d['texto'])} caracteres")
        if d["texto"]:
            docs.append(d)
    return docs


SENADO_IDX = ("https://www.senado.es/web/actividadparlamentaria/publicacionesoficiales/"
              "senado/boletinesoficiales/index.html")
SENADO_PDF = "https://www.senado.es/legis15/publicaciones/pdf/senado/bocg/BOCG_T_15_{n}.PDF"
ESTADO = ROOT / "state"


def _ancla_senado() -> tuple[int, dt.date]:
    """Último boletín del Senado que se pudo leer, para estimar el siguiente."""
    f = ESTADO / "senado.json"
    if f.exists():
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            return int(d["numero"]), dt.date.fromisoformat(d["fecha"])
        except Exception:                                     # noqa: BLE001
            pass
    return 459, dt.date(2026, 9, 17)      # comprobado a mano


def _guardar_ancla(numero: int, fecha: dt.date) -> None:
    ESTADO.mkdir(exist_ok=True)
    (ESTADO / "senado.json").write_text(
        json.dumps({"numero": numero, "fecha": fecha.isoformat()}, indent=2),
        encoding="utf-8")


def _numeros_probables(hoy: dt.date) -> list[int]:
    """El Senado publica ~1 boletín por día hábil. Estimamos desde el último conocido."""
    base_n, base_f = _ancla_senado()
    habiles = sum(1 for i in range((hoy - base_f).days)
                  if (base_f + dt.timedelta(days=i + 1)).weekday() < 5)
    estimado = base_n + habiles
    # Probamos alrededor de la estimación, de mayor a menor: el más alto que exista es el actual
    candidatos = list(range(estimado + 2, max(base_n - 1, 0), -1))[:8]
    return candidatos


def fetch_senado() -> list[dict]:
    """Primero el índice; si el WAF lo bloquea, vamos directos al PDF por numeración."""
    docs: list[dict] = []
    hoy = dt.date.today()

    numeros: list[int] = []
    r = get(SENADO_IDX, tries=2)
    if r:
        vistos = {int(m.group(1)) for m in re.finditer(r"BOCG_T_15_(\d+)", r.text, re.I)}
        numeros = sorted(vistos, reverse=True)[:2]
        log(f"Senado: índice legible, boletines {numeros}")
    else:
        numeros = _numeros_probables(hoy)
        log(f"Senado: índice bloqueado; probando por numeración {numeros[:4]}…")
        DIAG["senado_fallback"] = numeros

    for n in numeros:
        url = SENADO_PDF.format(n=n)
        texto = pdf_text(url, referer=SENADO_IDX)
        if texto:
            log(f"Senado: boletín {n} leído ({len(texto)} caracteres)")
            _guardar_ancla(n, hoy)
            docs.append({"tipo": "BOCG Senado", "numero": n, "url": url,
                         "nombre": f"BOCG Senado núm. {n}", "texto": texto,
                         "chamber_hint": "senado"})
            break
        time.sleep(1)

    if not docs:
        log("Senado: no se pudo obtener ningún boletín")
    return docs


# ---------------------------------------------------------------------------
# Clasificación
# ---------------------------------------------------------------------------

REGLAS = [
    ("fiscal", ["hacienda", "tributar", "impuesto", "fiscal", "presupuesto", "banco de españa",
                "cambios del euro", "deuda pública", "tesoro público", "aduana", "iva",
                "irpf", "subvenci", "financiación", "ayudas", "crédito extraordinario"]),
    ("laboral", ["trabajo", "seguridad social", "empleo", "convenio colectivo", "salario",
                 "formación profesional", "aula mentor", "desempleo", "autónomo",
                 "jubilación", "pensiones", "relaciones laborales", "prevención de riesgos"]),
    ("mercantil", ["mercantil", "sociedades", "competencia", "auditoría", "contabilidad",
                   "concursal", "mercado de valores", "consumidores", "empresa",
                   "inversiones estratégicas", "industria"]),
]


def _patron(clave: str) -> re.Pattern:
    """Palabra completa para claves cortas ('iva' no debe casar con 'Universidad');
    prefijo para las largas ('subvenci' casa con 'subvenciones')."""
    fin = r"\b" if len(clave) <= 4 else ""
    return re.compile(r"\b" + re.escape(clave) + fin)


_REGLAS_C = [(cat, [_patron(k) for k in claves]) for cat, claves in REGLAS]


def clasificar(*textos: str) -> str:
    bajo = " ".join(t for t in textos if t).lower()
    mejor, puntos_mejor = "otros", 0
    for cat, patrones in _REGLAS_C:
        puntos = sum(1 for p in patrones if p.search(bajo))
        if puntos > puntos_mejor:
            mejor, puntos_mejor = cat, puntos
    return mejor


# ---------------------------------------------------------------------------
# Redacción determinista (sin modelo)
# ---------------------------------------------------------------------------

SEPARADORES = [", por la que se ", ", por el que se ", ", por los que se ",
               ", por la que ", ", por el que ", ", sobre ", ", relativa a ",
               ", de la que ", " por la que se ", " por el que se "]

# Verbo con el que arranca el objeto de la disposición -> gancho del titular.
# El verbo se elimina del objeto para que el titular no se repita a sí mismo
# ("NUEVAS REGLAS PARA: REGULA EL COMITÉ..." queda en "NUEVAS REGLAS PARA EL COMITÉ...").
VERBOS = [
    (r"^crean?\b", "NACE"),
    (r"^regulan?\b", "NUEVAS REGLAS PARA"),
    (r"^modifican?\b", "CAMBIA"),
    (r"^conceden?\b", "DINERO PÚBLICO PARA"),
    (r"^convocan?\b", "CONVOCATORIA ABIERTA:"),
    (r"^publican?\b", "SE PUBLICA"),
    (r"^apruebae?n?\b|^aprueban?\b", "APROBADO:"),
    (r"^declaran?\b", "SELLO OFICIAL PARA"),
    (r"^autorizan?\b", "LUZ VERDE A"),
    (r"^desarrollan?\b", "LETRA PEQUEÑA NUEVA:"),
    (r"^delegan?\b", "CAMBIA QUIEN FIRMA:"),
    (r"^fijan?\b|^establecen?\b", "QUEDA FIJADO:"),
    (r"^nombran?\b|^cesan?\b", "CAMBIO DE SILLAS:"),
    (r"^dispone[n]?\b|^ordenan?\b", "ORDENADO:"),
    (r"^prorrogan?\b", "SE ALARGA:"),
    (r"^suprimen?\b|^deroga[n]?\b", "SE ELIMINA:"),
]

INSTRUMENTOS = [
    (r"^Ley Orgánica", "Ley Orgánica",
     "Una ley orgánica regula derechos fundamentales o materias reservadas por la "
     "Constitución, y necesita mayoría absoluta del Congreso para salir adelante."),
    (r"^Ley\b", "Ley",
     "Una ley la aprueba un parlamento — el estatal o el autonómico — y se publica en el "
     "BOE para entrar en vigor."),
    (r"^Real Decreto-ley", "Real Decreto-ley",
     "Un real decreto-ley lo dicta el Gobierno por urgencia y tiene fuerza de ley, pero el "
     "Congreso debe convalidarlo en 30 días o decae."),
    (r"^Real Decreto", "Real Decreto",
     "Un real decreto es una norma del Gobierno aprobada en Consejo de Ministros: desarrolla "
     "lo que una ley deja abierto y es donde suele estar la letra pequeña que de verdad aplica."),
    (r"^Orden", "Orden ministerial",
     "Una orden ministerial la firma un ministerio y está por debajo del real decreto: "
     "concreta detalles técnicos y procedimientos sin pasar por el Consejo de Ministros."),
    (r"^Resolución", "Resolución",
     "Una resolución es un acto de un órgano concreto de la Administración. No crea normas "
     "generales: aplica las que ya existen a un caso determinado."),
    (r"^Corrección", "Corrección de errores",
     "Una corrección de errores enmienda lo ya publicado. Conviene mirarlas: a veces lo que "
     "se corrige cambia el sentido de la norma original."),
    (r"^Acuerdo", "Acuerdo",
     "Un acuerdo recoge lo pactado entre administraciones u órganos y se publica para que "
     "sea oponible a terceros."),
    (r"^Extracto", "Extracto de convocatoria",
     "Un extracto anuncia una convocatoria de ayudas: el texto completo vive en la Base de "
     "Datos Nacional de Subvenciones."),
]


_BILATERAL = re.compile(
    r"Comisi[óo]n Bilateral de Cooperaci[óo]n.*?Comunidad Aut[óo]noma de\s+"
    r"(?:las?\s+|los?\s+)?([^,]+?)\s*,\s*en relaci[óo]n con\s+(.+)$", re.I | re.S)

_FECHA_EN_TITULO = re.compile(r"de\s+\d{1,2}\s+de\s+[a-záéíóú]+(?:\s+de\s+\d{4})?\s*,\s*", re.I)


def materia_de(texto: str) -> str:
    """Lo que una norma regula de verdad, que en los títulos oficiales va
    detrás de la última fecha: «Ley 8/2026, de 23 de junio, de Ordenación del
    Transporte Marítimo» -> «Ordenación del Transporte Marítimo»."""
    cola = _FECHA_EN_TITULO.split(texto)[-1].strip()
    cola = re.sub(r"^por\s+(?:la|el|los|las)\s+que\s+se\s+\w+\s+", "", cola, flags=re.I)
    cola = re.sub(r"^(?:de|del|sobre|por)\s+", "", cola, flags=re.I)
    return cola.strip(" .;,")


def titular_bilateral(titulo: str) -> str:
    """Los acuerdos de las comisiones bilaterales Estado-comunidad llegan cuatro
    y cinco el mismo día, y su título solo se diferencia al final: la comunidad
    y la ley de la que tratan. Un titular cortado por los primeros 95 caracteres
    los deja idénticos en pantalla, así que a esta familia se le da la vuelta y
    se pone delante lo que los distingue."""
    m = _BILATERAL.search(titulo)
    if not m:
        return ""
    comunidad = " ".join(m.group(1).split()).strip(" .")
    materia = materia_de(m.group(2))
    # «Coordinación de Policías Locales de Cantabria» ya dice Cantabria arriba
    materia = re.sub(rf",?\s+de\s+(?:las?\s+|los?\s+)?{re.escape(comunidad)}\s*$", "",
                     materia, flags=re.I).strip(" .;,")
    if not comunidad or not materia:
        return ""
    return f"EL ESTADO Y {comunidad.upper()}, SOBRE {recortar(materia, 62).upper()}"


def desambiguar_titulares(articulos: list[dict]) -> None:
    """Red de seguridad: si dos titulares del día se ven iguales una vez
    recortados, se les añade lo que los diferencia. Dos piezas distintas nunca
    pueden aparecer como la misma noticia repetida."""
    vistos: dict[str, list[dict]] = {}
    for a in articulos:
        clave = re.sub(r"[^A-ZÁÉÍÓÚÑ0-9]", "", (a.get("headline") or "").upper())[:60]
        vistos.setdefault(clave, []).append(a)
    for grupo in vistos.values():
        if len(grupo) < 2:
            continue
        for a in grupo:
            materia = materia_de(a.get("titulo_oficial") or a.get("standfirst") or "")
            if materia:
                base = recortar(a.get("headline", ""), 58).rstrip("…").rstrip(" ,;")
                a["headline"] = f"{base}: {recortar(materia, 58).upper()}"



# ---------------------------------------------------------------------------
# Lectura del texto de la norma: lo relevante casi nunca está en el título
# ---------------------------------------------------------------------------
#
# El sumario del BOE solo trae títulos. Pero lo que le importa a quien lee
# —hasta cuándo dura una prórroga, cuánto dinero se reparte, qué plazo hay
# para pedir algo— está en el articulado. Ejemplo real: la orden que prorroga
# los controles fronterizos con Italia no dice en su título hasta cuándo; el
# «hasta las 24:00 horas del día 7 de octubre de 2026» está en el artículo 2.
#
# Así que para las piezas desarrolladas se descarga el texto íntegro y se
# extraen los datos duros. Son ~16 peticiones más al día a boe.es.

BOE_TXT = "https://www.boe.es/diario_boe/txt.php?id={ident}"
MESES_RE = ("enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
            "septiembre|octubre|noviembre|diciembre")


def texto_disposicion(ident: str) -> str:
    """Texto íntegro de una disposición, desde su versión consolidada en HTML."""
    if not re.fullmatch(r"BOE-[A-Z]-\d{4}-\d+", ident or ""):
        return ""
    r = get(BOE_TXT.format(ident=ident), tries=2)
    if not r:
        return ""
    try:
        soup = BeautifulSoup(r.text, "html.parser")
        cuerpo = soup.find("div", id="textoxslt")
        if not cuerpo:
            return ""
        return " ".join(cuerpo.get_text(" ", strip=True).split())
    except Exception as exc:                                  # noqa: BLE001
        log(f"  no se pudo leer el texto de {ident}: {exc}")
        return ""


def _fecha_larga(txt: str) -> str:
    return " ".join(txt.split()).strip(" .,")


_FIN_DISPOSITIVO = re.compile(
    r"(?:Contra (?:la|el) presente|Palacio del|Madrid,\s*\d|Disposici[óo]n (?:adicional|transitoria|"
    r"derogatoria|final)|La presente resoluci[óo]n (?:podr[áa]|ser[áa] recurrible)|"
    r"lo que se hace p[úu]blico)", re.I)


def parte_dispositiva(texto: str) -> str:
    """Lo que la norma ORDENA. Casi nunca está en el título.

    «Se modifica la dirección electrónica de la sede electrónica» es lo que dice
    el título; cuál era y cuál pasa a ser está en el artículo único. Un artículo
    que no lo cuenta obliga a abrir el BOE, que es justo lo que veníamos a
    evitar."""
    if not texto:
        return ""
    m = re.search(r"(?:Art[íi]culo [úu]nico[.\s]|DISPONGO[:.\s]|RESUELVO[:.\s]|"
                  r"\bPrimero[.º]\s|\bAcuerdo [úu]nico[.\s])", texto)
    if not m:
        return ""
    cuerpo = texto[m.end():]
    corte = _FIN_DISPOSITIVO.search(cuerpo)
    if corte:
        cuerpo = cuerpo[:corte.start()]
    cuerpo = " ".join(cuerpo.split())
    if len(cuerpo) < 30:
        return ""
    # Frases enteras hasta unos 420 caracteres: cortar a media frase una parte
    # dispositiva es peor que no ponerla.
    todas = [f.strip() for f in re.split(r"(?<=[.:])\s+", cuerpo) if f.strip()]
    frases, total = [], 0
    for f in todas:
        if total + len(f) > 520 and frases:
            break
        frases.append(f); total += len(f)
    # Si la norma da una dirección web, esa frase es EL dato: entra aunque el
    # presupuesto de caracteres se haya agotado antes de llegar a ella.
    if "http" in cuerpo and not any("http" in f for f in frases):
        con_url = next((f for f in todas if "http" in f), "")
        if con_url:
            frases.append(con_url)
    salida = " ".join(frases).strip()
    # Un ordinal suelto al final («… transición. Cuarto.») es el encabezado del
    # apartado que no ha cabido: anuncia algo que no llega.
    salida = re.sub(r"\s+(?:Primero|Segundo|Tercero|Cuarto|Quinto|Sexto|S[ée]ptimo|Octavo|"
                    r"Noveno|D[ée]cimo)[.º:]?\s*$", "", salida, flags=re.I).strip()
    return salida if salida.endswith((".", ":")) else salida + "."


def datos_clave(texto: str) -> dict:
    """Los datos duros del articulado. Solo se extrae lo que aparece literal:
    fechas, importes y plazos. Nada se deduce ni se redondea."""
    if not texto:
        return {}
    d: dict = {}

    # Vigencia. Cuidado: el preámbulo de una prórroga recita las fechas de las
    # órdenes ANTERIORES, así que quedarse con la primera coincidencia da la
    # fecha equivocada. Se busca primero el par «surtirá efectos desde … hasta
    # …», que es el dispositivo; y si no aparece, la ÚLTIMA fecha del texto,
    # porque el articulado va después de los antecedentes.
    fecha = rf"(\d{{1,2}}\s+de\s+(?:{MESES_RE})\s+de\s+\d{{4}})"
    hora = r"(?:las?\s+[\d:.]+\s*horas\s+del\s+d[íi]a\s+|el\s+(?:d[íi]a\s+)?)"

    par = re.search(rf"(?:surtir[áa]\s+efectos|con\s+efectos|tendr[áa]\s+efectos|ser[áa]n?\s+"
                    rf"de\s+aplicaci[óo]n)\s+desde\s+{hora}{fecha}\s+hasta\s+{hora}{fecha}",
                    texto, re.I)
    if par:
        d["desde"], d["hasta"] = _fecha_larga(par.group(1)), _fecha_larga(par.group(2))
    else:
        finales = re.findall(rf"hasta\s+{hora}{fecha}", texto, re.I)
        if finales:
            d["hasta"] = _fecha_larga(finales[-1])
        inicios = re.findall(rf"(?:surtir[áa]\s+efectos|con\s+efectos)\s+desde\s+{hora}{fecha}",
                             texto, re.I)
        if inicios:
            d["desde"] = _fecha_larga(inicios[-1])

    # Importe. Desde que la cifra sube al titular hay que hilar más fino: en una
    # resolución de precios del tabaco hay cientos de importes y ninguno es «el»
    # importe de la norma. Primero se buscan las cifras ancladas a una palabra
    # que las declare como totales; solo si no hay ninguna se cae al máximo, y
    # únicamente cuando el texto no parece un tarifario.
    NUM = r"(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)\s*(?:euros|€)"
    ANCLA = (r"(?:importe|coste|cuant[íi]a|presupuesto|dotaci[óo]n|aportaci[óo]n|"
             r"asciende a|valorad[oa] en|por un total de|total de)")

    def _num(lit: str):
        try:
            return float(lit.replace(".", "").replace(",", "."))
        except ValueError:
            return None

    todos = [x for x in (_num(m.group(1)) for m in re.finditer(NUM, texto)) if x is not None]
    anclados = []
    for m in re.finditer(rf"{ANCLA}[^.;]{{0,80}}?{NUM}", texto, re.I):
        v = _num(m.group(1))
        if v is not None:
            anclados.append((v, m.group(1)))

    elegido = None
    if anclados:
        elegido = max(anclados)
    elif len(todos) <= 12:            # más de doce cifras ya es una tabla de tarifas
        crudos = [(v, m.group(1)) for m, v in
                  ((m, _num(m.group(1))) for m in re.finditer(NUM, texto)) if v is not None]
        elegido = max(crudos) if crudos else None
    if elegido and elegido[0] >= 1000:        # por debajo suele ser una tasa suelta
        d["importe"] = f"{elegido[1]} euros"

    m = re.search(r"plazo\s+de\s+(\w+|\d+)\s+(d[íi]as?|meses?|a[ñn]os?)", texto, re.I)
    if m:
        d["plazo"] = f"{m.group(1)} {m.group(2)}"

    m = re.search(rf"entrar[áa]\s+en\s+vigor\s+(el\s+(?:d[íi]a\s+)?"
                  rf"(?:\d{{1,2}}\s+de\s+(?:{MESES_RE})\s+de\s+\d{{4}}|siguiente[^.]{{0,60}}))",
                  texto, re.I)
    if m:
        d["vigor"] = _fecha_larga(m.group(1))
    return d


def _euros_titular(importe: str) -> str:
    """«1.040.000 euros» -> «1.040.000 EUROS»; «27.991,89 euros» se deja igual.
    No se redondea: la cifra es la que dice el BOE."""
    return importe.upper().replace("EUROS", "EUROS").strip()


def enriquecer_titular(headline: str, d: dict, limite: int = 104) -> str:
    """El dato que convierte una nota administrativa en una noticia —cuánto
    dinero, hasta cuándo, cuánto plazo— está en el articulado, no en el título.
    Aquí se sube al titular, que es donde lo busca quien lee.

    Orden de importancia: el dinero manda; después la fecha límite; después el
    plazo para reaccionar. Solo se añade uno: dos datos en un titular ya son
    una ficha."""
    if not headline or not d:
        return headline
    plano = headline.upper()

    if d.get("importe") and not re.search(r"\bEUROS?\b|€", plano):
        cifra = _euros_titular(d["importe"])
        cand = f"{headline}: {cifra}"
        if len(cand) <= limite:
            return cand

    if d.get("hasta") and "HASTA" not in plano:
        cand = cerrar(headline + coletilla_fecha(d), limite)
        if "HASTA" in cand.upper():
            return cand

    # El plazo solo sube al titular cuando la norma abre de verdad una puerta
    # al ciudadano. En un convenio, «plazo de cinco días» es una cláusula
    # interna: ponerlo como «cinco días para reclamar» sería inventarse el
    # sentido de la norma.
    if (d.get("plazo") and d.get("_reclamable")
            and "PLAZO" not in plano and " DÍAS" not in plano and " MESES" not in plano):
        cand = f"{headline}: {d['plazo'].upper()} PARA {d.get('_accion', 'RECURRIR')}"
        if len(cand) <= limite:
            return cand

    if d.get("vigor") and re.search(r"\d", d["vigor"]) and "VIGOR" not in plano:
        corto = _SIN_MES.sub("", d["vigor"])
        cand = f"{headline}, EN VIGOR {corto.upper()}"
        if len(cand) <= limite:
            return cand
    return headline


def frase_datos_clave(d: dict) -> str:
    """Una línea con lo que hay que saber, en el orden en que importa."""
    trozos = []
    if d.get("desde") and d.get("hasta"):
        trozos.append(f"en vigor del {d['desde']} al {d['hasta']}")
    elif d.get("hasta"):
        trozos.append(f"con efecto hasta el {d['hasta']}")
    elif d.get("vigor"):
        trozos.append(f"entra en vigor {d['vigor']}")
    if d.get("importe"):
        trozos.append(f"importe: {d['importe']}")
    if d.get("plazo"):
        trozos.append(f"plazo de {d['plazo']}")
    if not trozos:
        return ""
    return "Datos clave: " + "; ".join(trozos) + "."


_SIN_MES = re.compile(rf"\s+de\s+\d{{4}}$", re.I)


def coletilla_fecha(d: dict) -> str:
    """Para el titular: «HASTA EL 7 DE OCTUBRE». Sin el año, que en un titular
    del día sobra salvo que sea de otro año."""
    hasta = d.get("hasta", "")
    if not hasta:
        return ""
    corto = _SIN_MES.sub("", hasta)
    anio = re.search(r"(\d{4})$", hasta)
    if anio and anio.group(1) != str(dt.date.today().year):
        corto = hasta
    return f" HASTA EL {corto.upper()}"


# ---------------------------------------------------------------------------
# Titulares: buscar el núcleo noticioso, no cortar el título legal
# ---------------------------------------------------------------------------
#
# Un titular no puede ser el principio del título oficial rematado con «…».
# Estas reglas localizan lo noticioso de las familias que el BOE repite cada
# día —convalidaciones, subvenciones, convenios, retribuciones reguladas,
# listas de admitidos— y lo ponen delante, entero y corto. Lo que no encaja
# en ninguna cae al compositor genérico de más abajo, que tampoco trunca.
#
# El techo de esto son reglas: para titulares de verdad mordaces está la vía
# del modelo (LLM_BASE_URL / LLM_MODEL / LLM_API_KEY), que ya existe.

CONECTORES_FINALES = {
    "de","del","la","el","los","las","y","e","o","u","en","con","para","por","a","al",
    "que","se","su","sus","un","una","unos","unas","sobre","entre","desde","hasta",
    "como","ante","tras","segun","según","cuyo","cuya","lo","le","les","esta","este"}


def cerrar(texto: str, limite: int = 78) -> str:
    """Corta por palabra y cierra limpio. NUNCA deja puntos suspensivos:
    un titular que acaba en «…» no es un titular, es un texto cortado."""
    t = " ".join((texto or "").split()).lstrip(" .,;:—-–»").rstrip(" .,;:—-–«")
    if len(t) > limite:
        t = t[:limite]
        if " " in t:
            t = t[:t.rfind(" ")]
    palabras = t.split()
    while palabras and palabras[-1].lower().strip(",;:.»«") in CONECTORES_FINALES:
        palabras.pop()
    t = " ".join(palabras).strip(" .,;:—-–")
    # «SEGRIA LEVANTE sin cerrar es una errata a la vista de todo el mundo.
    if t.count("«") > t.count("»"):
        t = t[:t.rfind("«")].strip(" .,;:—-–")
    return t.strip(" .,;:—-–")


def _limpiar(t: str) -> str:
    """Quita la chatarra identificativa: números de norma y fechas."""
    t = re.sub(r"\b(?:Real Decreto-ley|Real Decreto|Ley Orgánica|Ley|Orden|Resolución|"
               r"Circular|Instrucción|Decreto-ley|Decreto)\s+[A-Z]{0,4}/?[\d./]+/\d{4}\b", "", t)
    t = re.sub(r",?\s*de\s+\d{1,2}\s+de\s+[a-záéíóú]+(?:\s+de\s+\d{4})?", "", t, flags=re.I)
    return " ".join(t.split()).strip(" ,;")


def _materia_final(t: str) -> str:
    """Lo que la norma trata, que suele ir tras el último «, de » o «por el que se»."""
    m = re.search(r"por (?:el|la|los|las) que se\s+\w+\s+(.+)$", t, re.I)
    if m:
        return m.group(1)
    partes = re.split(r",\s*de\s+", t)
    return partes[-1] if len(partes) > 1 else t


def _proposito(t: str) -> str:
    """La cláusula de finalidad: «para <hacer algo>». Es lo más noticioso."""
    m = re.search(r"\bpara\s+(?!el|la|los|las|su|sus)([a-záéíóúñ]+(?:ar|er|ir)\b.+?)"
                  r"(?=,|;| y de | y la | y el |$)", t, re.I)
    return m.group(1) if m else ""


def _entidad(t: str) -> str:
    """Nombre propio del destinatario. Solo palabras con mayúscula inicial, o
    «Canarias para abaratar…» acaba dentro del nombre de la comunidad."""
    propio = r"[A-ZÁÉÍÓÚÑ][\wáéíóúñ]*(?:\s+(?:de|del|la|las|y)\s+[A-ZÁÉÍÓÚÑ][\wáéíóúñ]*)*"
    for patron in (rf"\b(?:Comunidad|Ciudad) Autónoma de\s+(?:las\s+|los\s+)?({propio})",
                   rf"\b(?:Universidad|Ayuntamiento|Diputación)\s+de\s+({propio})",
                   rf"\bMancomunidad de Municipios del\s+({propio})"):
        m = re.search(patron, t)
        if m:
            return m.group(1).strip()
    return ""


def _organo(t: str) -> str:
    """Quién dicta la norma: va entre la fecha y el «por la que se»."""
    m = re.search(r",\s*de\s+(?:la|el)\s+(.+?),\s*(?:AAI,\s*)?por (?:la|el) que se", t, re.I)
    if not m:
        return ""
    o = m.group(1).strip()
    # «Dirección General para la Eficiencia del Servicio Público de Justicia»
    # se lee como «Justicia»: el nombre del ramo está al final.
    if re.match(r"(?:Direcci[óo]n General|Subdirecci[óo]n|Secretar[íi]a)", o, re.I):
        cola = re.findall(r"\bde\s+([A-ZÁÉÍÓÚÑ][\wáéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+)*)", o)
        if cola:
            return cerrar(cola[-1], 40)
    return cerrar(o, 48)


_COLETILLA_ENTE = re.compile(r",\s*(?:M\.?\s?P\.?|O\.?\s?A\.?|AAI|F\.?S\.?P\.?|"
                             r"E\.?P\.?E\.?)\.?(?=[,.]|\s|$)", re.I)


def _sin_para_interno(t: str) -> str:
    """«el Instituto para la Competitividad Empresarial de Castilla y León, para
    la mejora…»: el primer «para» es parte del nombre, el segundo es la
    finalidad. Solo corta el «para» que viene detrás de una coma."""
    t = _COLETILLA_ENTE.sub("", t)
    m = re.search(r",\s*(?:para|por|con el fin de|a fin de)\b", t)
    return (t[:m.start()] if m else t).strip(" ,;.")


REGLAS_TITULAR = []


def _regla_titular(patron):
    def deco(f):
        REGLAS_TITULAR.append((re.compile(patron, re.I | re.S), f))
        return f
    return deco


@_regla_titular(r"Acuerdo de (convalidación|derogación) del Real Decreto-ley\s*[\d/]*\s*,?\s*(.+)$")
def _convalidacion(m, t):
    verbo = "CONVALIDA" if m.group(1).lower().startswith("conval") else "DEROGA"
    # La materia es la del decreto convalidado, que va detrás de su referencia
    materia = cerrar(_limpiar(_materia_final(m.group(2))), 52)
    return f"EL CONGRESO {verbo} EL DECRETO DE {materia.upper()}" if materia else \
           f"EL CONGRESO {verbo} UN DECRETO-LEY"


@_regla_titular(r"concesión directa de (?:una |)(?:subvención|subvenciones|ayudas?)")
def _subvencion(m, t):
    quien = _entidad(t)
    fin = cerrar(_limpiar(_proposito(t)), 48)
    if quien and fin:
        return f"{quien.upper()} RECIBE DINERO PÚBLICO PARA {fin.upper()}"
    if quien:
        return f"DINERO PÚBLICO PARA {quien.upper()}"
    return f"DINERO PÚBLICO PARA {cerrar(_limpiar(_materia_final(t)), 50).upper()}"


@_regla_titular(r"metodolog[íi]a\s+(?:de retribución|para determinar la retribución)\s+(?:de\s+)?(.+)")
def _retribucion(m, t):
    return f"QUEDA FIJADO CUÁNTO SE COBRA POR {cerrar(_limpiar(m.group(1)), 50).upper()}"


@_regla_titular(r"tasa de retribución financiera aplicable a (?:las actividades de\s+)?(.+)")
def _tasa(m, t):
    return f"NUEVA TASA DE RETRIBUCIÓN PARA {cerrar(_limpiar(m.group(1)), 48).upper()}"


@_regla_titular(r"Adenda de (prórroga|modificación) del Convenio con ((?:la|el|los|las)\s+.+?|.+?)(?:,|\s+para\b|$)")
def _adenda(m, t):
    verbo = "SE PRORROGA" if m.group(1).lower().startswith("pr") else "CAMBIA"
    return f"{verbo} EL CONVENIO CON {cerrar(_limpiar(m.group(2)), 50).upper()}"


@_regla_titular(r"relación de (?:personas |aspirantes |)admitid[oa]s y excluid[oa]s.*?"
       r"(?:para|de)\s+(?:el proceso selectivo de\s+|)([^,.]+)")
def _admitidos(m, t):
    return f"LISTA DE ADMITIDOS: {cerrar(_limpiar(m.group(1)), 52).upper()}"


@_regla_titular(r"se publica (?:el |la |)Convenio con (.+)$")
def _convenio(m, t):
    """El nombre de la entidad entero (el «para» de «Instituto para la
    Competitividad» no es el «para» de la finalidad) y, detrás, para qué es el
    acuerdo, que es lo que le importa a quien lo lee."""
    cola = m.group(1)
    quien = cerrar(_limpiar(_sin_para_interno(cola)), 78)
    fin = cerrar(_limpiar(_proposito(cola)), 46)
    if len(fin.split()) < 3:
        fin = ""
    # Si la finalidad no cabe entera, no se pone: media finalidad engaña más
    # que ninguna («…CIENTÍFICAS: COLABORAR» no dice en qué).
    if quien and fin and len(f"ACUERDO CON {quien}: {fin}") <= 94:
        return f"ACUERDO CON {quien.upper()}: {fin.upper()}"
    return f"ACUERDO CON {quien.upper()}" if quien else ""


@_regla_titular(r"se publica (?:el |la |)Convenio entre (.+?)\s+y\s+((?:la|el|los|las)\s+.+)$")
def _convenio_entre(m, t):
    uno = cerrar(_limpiar(_sin_para_interno(m.group(1))), 52)
    dos = cerrar(_limpiar(_sin_para_interno(m.group(2))), 52)
    if not (uno and dos):
        return ""
    return f"{uno.upper()} FIRMA CON {dos.upper()}"


@_regla_titular(r"se publica (?:el |la |)Anexo\s+([IVXΙ\d]+)\s+al Convenio con (.+)$")
def _anexo_convenio(m, t):
    quien = cerrar(_limpiar(_sin_para_interno(m.group(2))), 60)
    return f"SE AMPLÍA EL ACUERDO CON {quien.upper()}" if quien else ""


@_regla_titular(r"se concede el t[íi]tulo de\s+(.+?)\s+a la\s+(?:fiesta\s+)?«(.+?)»"
                r"(?:,?\s*de\s+([^,.]+))?")
def _concede_titulo(m, t):
    """La noticia es la fiesta que lo gana, no la categoría administrativa."""
    titulo_dado = cerrar(_limpiar(m.group(1)), 56)
    fiesta = cerrar(_limpiar(m.group(2)), 44)
    lugar = cerrar(_limpiar(m.group(3) or ""), 26)
    donde = f" DE {lugar.upper()}" if lugar else ""
    return f"«{fiesta.upper()}»{donde} YA ES {titulo_dado.upper()}"


@_regla_titular(r"se declara\s+Bien de Inter[ée]s Cultural"
                r"(?:,\s*con la categor[íi]a de\s+([^,]+))?,\s*(.+)$")
def _declara_bic(m, t):
    que = cerrar(_limpiar(m.group(2)), 62)
    cat = cerrar(_limpiar(m.group(1) or ""), 26)
    if not que:
        return ""
    coda = f", COMO {cat.upper()}" if cat else ""
    return f"{que.upper()} YA ES BIEN DE INTERÉS CULTURAL{coda}"


@_regla_titular(r"se emplaza a (?:las personas |los |)interesad[oa]s en el\s+(recurso[^,.]*)")
def _emplaza(m, t):
    quien = _organo(t)
    cabeza = f"{quien.upper()} LLAMA" if quien else "LA ADMINISTRACIÓN LLAMA"
    return f"{cabeza} A LOS AFECTADOS POR UN {cerrar(_limpiar(m.group(1)), 46).upper()}"


@_regla_titular(r"se publican? los precios de venta al p[úu]blico de determinadas labores"
                r"(?:\s+de\s+(tabaco))?")
def _precios_tabaco(m, t):
    return "CAMBIAN LOS PRECIOS DEL TABACO EN LOS ESTANCOS" if m.group(1) \
        else "CAMBIAN LOS PRECIOS DE VENTA AL PÚBLICO DE DETERMINADAS LABORES"


@_regla_titular(r"cambio de titularidad de\s+(.+?)(?:,\s*entre sus puntos[^,]*)?"
                r",?\s*a favor d(el|e la|e los|e las)\s+(.+?)(?:,|\.|$)")
def _cambio_titularidad(m, t):
    art = {"el": "EL", "e la": "LA", "e los": "LOS", "e las": "LAS"}.get(m.group(2).lower(), "EL")
    que = cerrar(_limpiar(m.group(1)), 50)
    quien = cerrar(_limpiar(m.group(3)), 46)
    quien = f"{art} {quien}" if quien else ""
    if not (que and quien):
        return ""
    return f"{quien.upper()} SE QUEDA {que.upper()}"


@_regla_titular(r"se cancela ((?:la|el|los|las)\s+.+|.+)$")
def _cancela(m, t):
    que = cerrar(_limpiar(m.group(1)), 80)
    return f"SE DISUELVE {que.upper()}" if que else ""


@_regla_titular(r"se publica el Acuerdo del Consejo de Ministros[^,]*,\s*"
                r"por el que se\s+(\w+)\s+(.+)$")
def _acuerdo_consejo(m, t):
    verbo = {"aprueba": "APRUEBA", "aprueban": "APRUEBA", "declara": "DECLARA",
             "modifica": "CAMBIA", "autoriza": "AUTORIZA"}.get(m.group(1).lower(),
                                                               m.group(1).upper())
    que = cerrar(_limpiar(m.group(2)), 58)
    return f"EL CONSEJO DE MINISTROS {verbo} {que.upper()}" if que else ""


@_regla_titular(r"se (?:modifica|modifican) (?:la|el|los|las)\s+.*?por (?:la|el) que se \w+\s+(.+)")
def _modifica(m, t):
    return f"CAMBIAN LAS REGLAS: {cerrar(_limpiar(m.group(1)), 52).upper()}"


@_regla_titular(r"se (?:regula|regulan|crea|crean)\s+((?:el|la|los|las|un|una)\s+.+)")
def _regula(m, t):
    nucleo = re.split(r"\s+y (?:el|la|los|las)\s+", m.group(1))[0]
    return f"NUEVAS REGLAS PARA {cerrar(_limpiar(nucleo), 52).upper()}"


@_regla_titular(r"actuaciones urgentes en materia de\s+(.+)")
def _urgentes(m, t):
    return f"MEDIDAS EXPRÉS EN {cerrar(_limpiar(m.group(1)), 54).upper()}"


@_regla_titular(r"se (?:determina|determinan|establece|establecen)\s+(?:el|la|los|las)\s+(.+)")
def _determina(m, t):
    nucleo = re.split(r"\s+para\s+su\s+|\s+en función de\s+|,", m.group(1))[0]
    return f"QUEDA FIJADA {cerrar(_limpiar(nucleo), 54).upper()}"


@_regla_titular(r"se publican?\s+(?:el|la|los|las)?\s*«(.+?)»")
def _entrecomillado(m, t):
    return f"SE PUBLICAN LAS CUENTAS: {cerrar(_limpiar(m.group(1)), 50).upper()}"


@_regla_titular(r"medidas (extraordinarias|urgentes|excepcionales)[^,]*?\s+(?:orientadas a|para|de)\s+(.+)")
def _medidas(m, t):
    return f"MEDIDAS {m.group(1).upper()}: {cerrar(_limpiar(m.group(2)), 52).upper()}"


# Gentilicios que aparecen en los títulos del BOE como «República X»
_PAISES = {"italiana": "Italia", "francesa": "Francia", "portuguesa": "Portugal",
           "alemana": "Alemania", "hel[ée]nica": "Grecia", "checa": "Chequia",
           "eslovaca": "Eslovaquia", "polaca": "Polonia", "argentina": "Argentina",
           "dominicana": "República Dominicana", "oriental del uruguay": "Uruguay",
           "bolivariana de venezuela": "Venezuela", "islámica de ir[áa]n": "Irán"}


def _pais_de(t: str) -> str:
    m = re.search(r"procedentes de (?:la |el |los |las )?(?:Rep[úu]blica\s+)?"
                  r"([A-Za-zÁÉÍÓÚÑáéíóúñ][\wáéíóúñ\s]{2,30}?)(?:[.,]|$)", t)
    if not m:
        return ""
    bruto = m.group(1).strip().lower()
    for patron, nombre in _PAISES.items():
        if re.fullmatch(patron, bruto):
            return nombre
    return m.group(1).strip()


@_regla_titular(r"se prorroga(?:n)?\s+((?:el|la|los|las)\s+.+)")
def _prorroga(m, t):
    """Una prórroga tiene dos datos y el título solo trae uno: qué se prorroga.
    El «con Italia» se rescata de la cola del título; el «hasta cuándo» lo pone
    después datos_clave(), que sí ha leído el articulado."""
    obj = re.split(r"\s+en las\s+|\s+con respecto a\s+|\s+respecto a\s+|,", m.group(1))[0]
    # «el restablecimiento temporal de los controles fronterizos» habla de los
    # controles, no del restablecimiento: se quita la nominalización de delante.
    sin_nominal = re.sub(r"^(?:el|la|los|las)\s+\w+(?:\s+(?:temporal|parcial|extraordinari[oa]|"
                         r"provisional))?\s+de\s+(?=(?:el|la|los|las)\s+\w{4,})", "", obj, flags=re.I)
    if len(sin_nominal.split()) >= 2:
        obj = sin_nominal
    pais = _pais_de(t)
    cola = f" CON {pais.upper()}" if pais else ""
    return f"SE PRORROGAN {cerrar(_limpiar(obj), 46).upper()}{cola}"


def titular_por_reglas(titulo: str) -> str:
    for patron, f in REGLAS_TITULAR:
        m = patron.search(titulo)
        if m:
            try:
                salida = f(m, titulo)
            except Exception:
                continue
            if salida and len(salida) > 18:
                return cerrar(salida, 96)
    return ""


def instrumento(titulo: str) -> tuple[str, str]:
    for patron, nombre, explicacion in INSTRUMENTOS:
        if re.match(patron, titulo, re.I):
            return nombre, explicacion
    return "Disposición", "El texto íntegro está enlazado al pie de esta pieza."


def objeto_de(titulo: str) -> str:
    """Lo que la disposición HACE, que es lo informativo — no su número."""
    for sep in SEPARADORES:
        if sep in titulo:
            obj = titulo.split(sep, 1)[1]
            return obj.strip().rstrip(".")
    # Sin separador: quitamos la parte identificativa inicial si la hay
    sin_id = re.sub(r"^[^,]+,\s*de\s+\d{1,2}\s+de\s+\w+(?:\s+de\s+\d{4})?,\s*", "", titulo)
    sin_id = (sin_id or titulo).strip().rstrip(".")
    # "Ley 4/2026, de 22 de julio, de presupuestos..." -> "presupuestos..."
    sin_id = re.sub(r"^de\s+", "", sin_id)
    return sin_id


def titular_de(objeto: str, titulo: str) -> str:
    """Compone el titular sin repetir el verbo que ya expresa el gancho."""
    obj = objeto.strip()
    # Un titular dice una cosa: cortamos antes de la segunda oración encadenada.
    obj = re.split(r"\s+y\s+se\s+|\s*;\s*", obj, maxsplit=1)[0].strip().rstrip(",;")
    for patron, gancho in VERBOS:
        m = re.match(patron, obj, re.I)
        if m:
            resto = obj[m.end():].strip()
            # "publica el Convenio ..." merece un gancho más específico
            if gancho == "SE PUBLICA" and re.match(r"^el convenio\b", resto, re.I):
                gancho = "ACUERDO FIRMADO:"
                resto = re.sub(r"^el convenio\s*", "", resto, flags=re.I)
            # cerrar() en vez de recortar(): un titular nunca acaba en «…»,
            # se corta por palabra y se cierra en seco.
            return f"{gancho} {cerrar(_limpiar(resto or obj), 58).upper()}".strip()
    # Sin verbo reconocible: el objeto ya es informativo por sí solo
    return cerrar(_limpiar(obj or titulo), 72).upper()


def recortar(texto: str, limite: int = 95) -> str:
    if len(texto) <= limite:
        return texto
    corte = texto[:limite]
    if " " in corte:
        corte = corte[:corte.rfind(" ")]
    return corte.rstrip(" ,;:") + "…"


FEMENINOS = {"Ley", "Ley Orgánica", "Orden ministerial", "Resolución",
             "Corrección de errores", "Disposición"}


def articulo_deterministico(e: dict) -> dict:
    titulo = e["titulo"]
    obj = objeto_de(titulo)
    nombre_inst, explicacion = instrumento(titulo)
    quien = (e.get("dept") or "").strip()
    epi = (e.get("epigrafe") or "").strip()

    headline = (titular_bilateral(titulo) or titular_por_reglas(titulo)
                or titular_de(obj, titulo))

    # Lo relevante suele estar en el articulado, no en el título: se lee la
    # norma y, si trae fecha de fin, se pone en el titular, que es donde la
    # busca quien lee.
    texto = texto_disposicion(e.get("ident", ""))
    clave = datos_clave(texto)
    if clave.get("hasta") and re.search(r"PRORROG|RESTABLEC|SUSPEN|AMPL[IÍ]A|ALARG", headline):
        headline = cerrar(headline + coletilla_fecha(clave), 104)
    else:
        if re.search(r"emplaza|recurso contencioso|interposici[óo]n de recurso|"
                     r"alegaciones|informaci[óo]n p[úu]blica|convocatoria|concurso|"
                     r"subvenci[óo]n|solicitudes", titulo, re.I):
            clave["_reclamable"] = True
            clave["_accion"] = ("PERSONARSE" if re.search(r"emplaza|recurso", titulo, re.I)
                                else "PRESENTARSE")
        headline = enriquecer_titular(headline, clave)
        # Se conserva la marca: es lo que distingue un plazo que le corre a la
        # gente (alegar, concurrir, recurrir) de una cláusula interna de un
        # convenio. Solo los primeros entran en la agenda de vencimientos.
        if clave.pop("_reclamable", None):
            clave["plazo_publico"] = True
        clave.pop("_accion", None)

    participio = "publicada" if nombre_inst in FEMENINOS else "publicado"
    if quien and epi:
        origen = f"{participio} por {quien}, en el epígrafe «{epi}»"
    elif quien:
        origen = f"{participio} bajo el epígrafe «{quien}»" if quien.istitle() and len(quien) < 45 \
                 else f"{participio} por {quien}"
    else:
        origen = participio

    body = [
        f"{nombre_inst} {origen}. Lo que hace: {obj[:400]}.",
        explicacion,
    ]
    disp = parte_dispositiva(texto)
    if disp:
        # Va en primer lugar y con sus palabras: aquí están las direcciones,
        # las cifras y los nombres que el título se calla.
        body.insert(0, "Lo que dice la norma: " + disp)
    frase = frase_datos_clave(clave)
    if frase:
        body.insert(0, frase)          # lo primero que se lee es el dato duro
    if e.get("seccion", "").startswith("I."):
        body.append(
            "Va en la Sección I del BOE, la de disposiciones generales: es donde aparece lo "
            "que cambia las reglas para todo el mundo, no solo para un expediente concreto.")

    return {
        "cat": clasificar(e.get("dept", ""), epi, titulo),
        "size": "sm",
        "headline": headline,
        "standfirst": recortar(titulo, 260),
        # El título oficial íntegro, sin recortar y sin tocar. El titular de la
        # casa es nuestro; esto es de la norma, y es lo que se declara como
        # nombre en los datos estructurados.
        "titulo_oficial": titulo,
        "datos": clave,
        "body": body,
        "dept": quien,
        "ref": e.get("ident") or e.get("seccion") or "",
        "url": e.get("url", ""),
    }


# ---------------------------------------------------------------------------
# Redacción con modelo (cualquier proveedor compatible con OpenAI)
# ---------------------------------------------------------------------------

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "").rstrip("/")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "")

SYSTEM_PROMPT = """Eres la redacción de "La Tercera Cámara", una publicación
para el gran público que cuenta lo que publica el BOE y lo que hacen diputados y senadores,
con tono de tabloide inteligente: titulares mordaces y con gancho, pero SIEMPRE fieles a los
hechos.

REGLAS INQUEBRANTABLES:
- Nunca inventes datos, cifras, nombres ni citas. Solo puedes usar lo que aparece en el
  material que se te entrega.
- Nunca atribuyas a una persona una frase que no figure literalmente en el material.
- Equidad política: la mordacidad se reparte por igual entre gobierno, oposición,
  nacionalistas, regionalistas e independientes, izquierda y derecha. Ningún día puede
  quedar como un ataque desproporcionado a un solo partido.
- Baja siempre al detalle concreto: nombres propios, municipios, titulaciones, expedientes.
- La sátira va en el titular y en el ángulo, jamás en los hechos.

Responde SIEMPRE con JSON válido y nada más."""


def llm_disponible() -> bool:
    return bool(LLM_BASE_URL and LLM_API_KEY and LLM_MODEL)


def llm(prompt: str, max_tokens: int = 4000) -> dict | None:
    if not llm_disponible():
        return None
    try:
        r = requests.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {LLM_API_KEY}",
                     "Content-Type": "application/json"},
            json={"model": LLM_MODEL,
                  "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                               {"role": "user", "content": prompt}],
                  "temperature": 0.7,
                  "max_tokens": max_tokens},
            timeout=180,
        )
        if r.status_code != 200:
            log(f"  modelo no disponible ({r.status_code}): {r.text[:200]}")
            DIAG["llm"] = f"error {r.status_code}"
            return None
        contenido = r.json()["choices"][0]["message"]["content"]
        contenido = re.sub(r"^```(?:json)?|```$", "", contenido.strip(), flags=re.M).strip()
        DIAG["llm"] = "ok"
        return json.loads(contenido)
    except Exception as exc:                                  # noqa: BLE001
        log(f"  fallo al redactar con modelo: {exc}")
        DIAG["llm"] = f"excepción: {str(exc)[:120]}"
        return None


# ---------------------------------------------------------------------------
# Composición de la edición
# ---------------------------------------------------------------------------

def redactar_boe(boe: dict) -> dict:
    entradas = boe["entradas"]
    sustantivas = [e for e in entradas if e["seccion"].startswith(("I.", "III."))] or entradas
    sustantivas = sustantivas[:16]
    otras = len(entradas) - len(sustantivas)

    articulos: list[dict] = []
    if llm_disponible():
        material = "\n".join(
            f"- [{e.get('seccion','')}] [{e.get('dept','')} / {e.get('epigrafe','')}] "
            f"{e['titulo']} ({e.get('ident','')})" for e in sustantivas)
        prompt = f"""Material del BOE de hoy (sumario oficial, títulos literales):

{material}

Escribe un artículo por cada entrada. Devuelve JSON:
{{"articulos": [{{"cat":"fiscal|laboral|mercantil|otros","size":"lead|md|sm",
 "headline":"TITULAR EN MAYÚSCULAS, mordaz pero fiel, con el dato concreto",
 "standfirst":"una o dos frases","body":["párrafo 1","párrafo 2","párrafo 3"],
 "dept":"organismo","ref":"identificador BOE-A o referencia"}}]}}

Exactamente una entrada lleva size "lead" (la más noticiable para el gran público), dos o
tres "md" y el resto "sm". En el cuerpo explica en lenguaje llano qué hace la norma y por
qué importa, incluido el mecanismo jurídico. No inventes importes ni datos que no estén."""
        resp = llm(prompt)
        if resp and isinstance(resp.get("articulos"), list):
            articulos = [a for a in resp["articulos"] if a.get("headline")]
            for a, e in zip(articulos, sustantivas):
                a.setdefault("url", e.get("url", ""))
                # El modelo escribe la entradilla; el título oficial no lo escribe
                # nadie, se copia del sumario. Nunca se deja que lo redacte.
                a["titulo_oficial"] = e["titulo"]
            log(f"BOE: {len(articulos)} artículos redactados con modelo")

    if not articulos:
        log("BOE: redacción determinista")
        articulos = [articulo_deterministico(e) for e in sustantivas]
        # El lead: preferimos la Sección I (disposiciones generales), que es lo que cambia reglas
        idx_lead = next((i for i, e in enumerate(sustantivas)
                         if e["seccion"].startswith("I.")), 0)
        articulos[idx_lead]["size"] = "lead"
        puestos = 0
        for i, a in enumerate(articulos):
            if i != idx_lead and puestos < 3:
                a["size"] = "md"
                puestos += 1

    desambiguar_titulares(articulos)

    counts = {"fiscal": 0, "laboral": 0, "mercantil": 0, "otros": 0}
    for a in articulos:
        cat = a.get("cat") if a.get("cat") in counts else "otros"
        counts[cat] += 1

    d = boe["fecha_boe"]
    extra = (f"El sumario completo de hoy trae {len(entradas)} disposiciones; aquí están "
             f"desarrolladas las {len(sustantivas)} con alcance general."
             + (f" Las otras {otras} son nombramientos, oposiciones y anuncios." if otras > 0 else ""))
    return {
        "numero": boe.get("numero", ""),
        "fecha": f"{d.day} de {MESES[d.month-1]} de {d.year}",
        # Fecha REAL del sumario leído. fetch_boe retrocede hasta 3 días si el
        # del día no está publicado todavía, así que no tiene por qué coincidir
        # con el id de la edición: los datos estructurados usan esta.
        "fechaISO": d.isoformat(),
        "sourceUrl": boe["sourceUrl"],
        "counts": counts,
        "extra": extra,
        "stories": articulos,
    }


def redactar_cortes(docs: list[dict], anterior: dict | None) -> dict:
    base = {
        "congreso": (anterior or {}).get("congreso", {
            "presidenta": "Francina Armengol Socias",
            "legislatura": "XV Legislatura (2023– )",
            "sede": "Plaza de las Cortes, 1, Madrid"}),
        "senado": (anterior or {}).get("senado", {
            "presidente": "Pedro Rollán",
            "legislatura": "XV Legislatura (2023– )",
            "sede": "Bailén, 3, Madrid"}),
        "scoreboard": None,
        "feed": [],
    }

    # Transparencia de cobertura: en una auditoría, saber qué fuente no respondió
    # forma parte de la información.
    hay_congreso = any(d["chamber_hint"] == "congreso" for d in docs) if docs else False
    hay_senado = any(d["chamber_hint"] == "senado" for d in docs) if docs else False
    if hay_congreso and hay_senado:
        nota = "Congreso y Senado han respondido; la edición cubre las dos cámaras."
    elif hay_congreso:
        nota = ("El Congreso ha respondido con normalidad. El Senado ha rechazado las "
                "peticiones automatizadas, así que hoy su actividad no está cubierta. "
                "Lo decimos en vez de disimularlo.")
    elif hay_senado:
        nota = ("El Senado ha respondido. El Congreso no ha devuelto publicaciones hoy, "
                "así que su actividad no está cubierta en esta edición.")
    else:
        nota = ("Ninguna de las dos cámaras ha devuelto publicaciones legibles hoy.")
    base["coverage"] = {"congreso": hay_congreso, "senado": hay_senado, "nota": nota}

    if not docs:
        base["constructionNote"] = (
            "Hoy no se pudo descargar ninguna publicación oficial legible del Congreso ni "
            "del Senado. Antes que rellenar con ruido, lo decimos: volvemos mañana.")
        return base

    if llm_disponible():
        material = "".join(
            f"\n\n=== {d['nombre']} ({d['tipo']}) — fuente: {d['url']} ===\n"
            + d.get("texto", "")[:26000] for d in docs)
        prompt = f"""Material oficial de las Cortes publicado hoy:
{material}

Escribe entre 3 y 6 artículos de AUDITORÍA PÚBLICA sobre lo que hacen sus señorías. JSON:
{{"feed":[{{"chamber":"congreso|senado","type":"Pleno|Comisión|Comisión de investigación|
Interpelaciones urgentes|Preguntas escritas|Tramitación legislativa|Administración de la Cámara",
"date":"DD mmm AAAA","headline":"TITULAR mordaz pero fiel","standfirst":"entradilla",
"quote":{{"text":"cita LITERAL","author":"nombre y cargo"}},
"body":["p1","p2","p3 que empieza por 'Auditoría del día:'"],
"source":{{"label":"documento","url":"url del PDF"}}}}],
"scoreboard":{{"note":"qué se ha contado","rows":[{{"g":"grupo","n":2}}]}}}}

Baja al detalle: nombres y apellidos, grupo parlamentario, expediente, ministerio. "quote"
es opcional y SOLO si la frase aparece literalmente. Reparte la mordacidad entre todos."""
        resp = llm(prompt)
        if resp and isinstance(resp.get("feed"), list) and resp["feed"]:
            base["feed"] = resp["feed"]
            if isinstance(resp.get("scoreboard"), dict):
                base["scoreboard"] = resp["scoreboard"]
            log(f"Cortes: {len(base['feed'])} artículos redactados con modelo")
            return base

    # Diagnóstico: una muestra del texto extraído de cada documento. Sin esto
    # el parser de Cortes se escribe a ciegas, y un boletín parlamentario no se
    # parece a nada que uno pueda imaginar desde fuera.
    try:
        DEBUG_DIR.mkdir(exist_ok=True)
        (DEBUG_DIR / "cortes-muestra.json").write_text(json.dumps(
            [{"nombre": d.get("nombre"), "tipo": d.get("tipo"), "url": d.get("url"),
              "caracteres": len(d.get("texto", "")),
              "muestra": d.get("texto", "")[:6000]} for d in docs],
            ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as exc:                                  # noqa: BLE001
        log(f"  no se pudo escribir la muestra de Cortes: {exc}")

    log("Cortes: lectura estructurada de los boletines")
    hoy = dt.date.today()
    fecha_txt = f"{hoy.day} {MES_ABBR[hoy.month-1].lower()} {hoy.year}"
    for d in docs:
        camara = d.get("chamber_hint", "congreso")
        try:
            datos = parsear_cortes(d.get("nombre", ""), d.get("tipo", ""), d.get("texto", ""))
            titulo, entradilla = titular_cortes(datos)
        except Exception as exc:                              # noqa: BLE001
            log(f"  no se pudo leer {d.get('nombre')}: {exc}")
            datos, titulo, entradilla = {}, "", ""
        if not titulo:
            continue          # antes que publicar un nombre de fichero, no se publica

        cuerpo = cuerpo_cortes(datos, d)

        base["feed"].append({
            "chamber": camara,
            "type": d["tipo"],
            "date": datos.get("fecha") or fecha_txt,
            "headline": titulo,
            "standfirst": entradilla,
            "body": cuerpo,
            "source": {"label": d["nombre"], "url": d["url"]},
        })
    return base


# ---------------------------------------------------------------------------
# Cortes: del PDF al titular
# ---------------------------------------------------------------------------
#
# Antes esta sección publicaba «REGISTRADO HOY: BOCG-15-A-114-1.PDF», que es un
# nombre de fichero, no una noticia. Los boletines del Congreso tienen una
# estructura muy regular —expediente, autor, órgano, orden del día, acuerdos de
# la Mesa— y de ahí sale lo que de verdad importa: qué se tramita, quién lo
# trae y hasta cuándo se puede enmendar.

MESES_RE = ("enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
            "septiembre|octubre|noviembre|diciembre")

def _limpiar_c(t: str) -> str:
    t = t.replace("‑", "-").replace("\xad", "")
    t = re.sub(r"\.{3,}\s*\d*", " ", t)                 # puntos guía del índice
    t = re.sub(r"cve:\s*\S+", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()

def _grupo_c(t: str) -> str:
    m = re.search(r"Grupo Parlamentario\s+([A-ZÁÉÍÓÚÑ][\w\sáéíóúñ\-]{2,40}?)"
                  r"(?:,|\.|\s+en el Congreso|\s+relativa|\s+sobre|\s+para|$)", t)
    if not m:
        return ""
    g = " ".join(m.group(1).split())
    return {"Plurinacional SUMAR":"SUMAR","Popular":"PP","Socialista":"PSOE",
            "Republicano":"ERC","Vasco":"PNV","Mixto":"Grupo Mixto"}.get(g, g)

def _fecha_sesion(t: str) -> str:
    m = re.search(rf"celebrada el\s+\w+\s+(\d{{1,2}} de (?:{MESES_RE}) de \d{{4}})", t, re.I)
    return m.group(1) if m else ""

def _orden_del_dia(t: str) -> list:
    """Los puntos del orden del día: cada uno empieza por raya."""
    m = re.search(r"ORDEN DEL D[ÍI]A(.{0,6000})", t, re.S | re.I)
    if not m:
        return []
    bloque = m.group(1)
    puntos = []
    for trozo in re.split(r"\s—\s|\n—\s*|^—\s*", bloque, flags=re.M)[1:]:
        texto = _limpiar_c(trozo)
        texto = re.split(r"\(N[úu]mero de expediente", texto)[0]
        texto = re.sub(r"«BOCG.*?»", "", texto)
        texto = re.sub(r"serie [A-Z], n[úu]mero [\d‑\-]+, de .{0,30}\d{4}\.?", "", texto)
        texto = _limpiar_c(texto).strip(" ,.;")
        if 25 < len(texto) < 400:
            puntos.append(texto)
    # el cuerpo del diario repite el orden del día en mayúsculas
    vistos, unicos = set(), []
    for p in puntos:
        k = re.sub(r"[^a-záéíóúñ0-9]", "", p.lower())[:70]
        if k not in vistos:
            vistos.add(k); unicos.append(p)
    return unicos

def _asunto_c(punto: str) -> str:
    """Quita el «Del Grupo Parlamentario X,» de delante y deja el asunto."""
    s = re.sub(r"^Del?\s+(?:la\s+)?Grupo Parlamentario[^,]{0,45},\s*", "", punto, flags=re.I)
    s = re.sub(r"^(?:relativa a|sobre|para|por la que se)\s+", "", s, flags=re.I)
    s = re.sub(r"\s*A petici[óo]n del Grupo Parlamentario.*$", "", s, flags=re.I)
    return s.strip(" ,.;")

def _objeto_ley(t: str) -> str:
    """De qué va la ley, en una frase suya. Primero la fórmula ritual («tiene
    por objeto»), que es la declaración explícita; si no está, la primera frase
    de la exposición de motivos, que es donde el legislador cuenta el problema."""
    for patron in (r"tiene\s+por\s+objeto\s+([^.]{40,320}\.)",
                   r"El\s+objeto\s+de\s+(?:esta|la presente)\s+\w+\s+es\s+([^.]{40,320}\.)",
                   r"(?:se\s+)?regula(?:n)?\s+en\s+(?:esta|la presente)\s+\w+\s+([^.]{40,320}\.)"):
        m = re.search(patron, t, re.I)
        if m:
            return _limpiar_c(m.group(1)).strip(" .") + "."
    # La exposición de motivos empieza tras el título en mayúsculas y un «I».
    m = re.search(r"\bI\s+([A-ZÁÉÍÓÚÑ][^.]{80,560}\.)", t)
    if m:
        return _limpiar_c(m.group(1)).strip(" .") + "."
    return ""


def _votacion(t: str) -> str:
    """El resultado de una votación es el dato más noticioso de un pleno."""
    m = re.search(r"votos?\s+emitidos,?\s*(\d+)[^.]{0,60}?a\s+favor,?\s*(\d+)"
                  r"[^.]{0,60}?en\s+contra,?\s*(\d+)(?:[^.]{0,60}?abstenciones,?\s*(\d+))?",
                  t, re.I)
    if not m:
        return ""
    base = f"{m.group(2)} votos a favor, {m.group(3)} en contra"
    return base + (f" y {m.group(4)} abstenciones." if m.group(4) else ".")


def cuerpo_cortes(d: dict, doc: dict) -> list:
    """El cuerpo del artículo de Cortes.

    El objetivo de esta página es ahorrarle a la gente leerse el original. Un
    artículo que solo diga «procede de la publicación oficial enlazada» no
    ahorra nada: obliga a abrir el PDF, que es exactamente lo que veníamos a
    evitar. Aquí se cuenta lo que dice el boletín —de qué va, de dónde viene,
    quién lo tramita, hasta cuándo se puede tocar— con sus propias palabras."""
    c = []
    if d.get("clase") == "TOMA_EN_CONSIDERACION":
        estado = {"Rechazada": "la rechazó", "Aprobada": "la aprobó",
                  "Tomada en consideración": "la tomó en consideración",
                  "Retirada": "la dio por retirada",
                  "Caducada": "la dejó caducar"}.get(d.get("estado", ""), "la votó")
        quien = f", presentada por {d['autor']}," if d.get("autor") else ""
        cuando = f" en su sesión del {d['fecha']}" if d.get("fecha") else ""
        c.append(f"El Pleno del Congreso debatió la toma en consideración de la "
                 f"{d.get('titulo','proposición de ley')}{quien} y {estado}{cuando}.")
        if d.get("estado") == "Rechazada":
            c.append("Rechazada la toma en consideración, la proposición no llega a "
                     "tramitarse: se cierra el expediente y el texto no se debate ni "
                     "se enmienda. Para volver a intentarlo hay que registrarla de nuevo.")
        elif d.get("estado") in ("Aprobada", "Tomada en consideración"):
            c.append("Tomada en consideración, la proposición empieza su tramitación: "
                     "se abre plazo de enmiendas y pasa a comisión.")
        if d.get("expediente"):
            c.append(f"Fuente: {doc.get('nombre','publicación oficial')}, "
                     f"expediente {d['expediente']}.")
        return c

    if d.get("objeto"):
        c.append("De qué va: " + primera_mayuscula(d["objeto"]))

    if d.get("procedente"):
        origen = f"Viene del {d['procedente']}"
        if d.get("convalidado"):
            origen += (f", que el Congreso convalidó el {d['convalidado']} y decidió tramitar "
                       f"además como proyecto de ley")
            origen += (". Convalidar es dejarlo en vigor; tramitarlo como ley significa que "
                       "ahora sí se puede enmendar, y que el texto final puede no parecerse "
                       "al que aprobó el Gobierno.")
        else:
            origen += "."
        c.append(origen)
    elif d.get("autor"):
        quien = d["autor"]
        articulo = "el " if quien in ("Gobierno", "Senado", "Congreso") else ""
        c.append(f"Lo trae {articulo}{quien}.")

    if d.get("comision"):
        quien = f"Lo lleva la Comisión de {d['comision']}"
        if d.get("competencia_plena"):
            quien += (", con competencia legislativa plena: lo aprueba la comisión, "
                      "sin pasar por el Pleno.")
        else:
            quien += "."
        c.append(quien)

    if d.get("plazo_enmiendas"):
        plazo = (f"Quien quiera cambiar el texto tiene hasta el {d['plazo_enmiendas']} "
                 f"para registrar enmiendas")
        plazo += f" ({d['dias_plazo']})." if d.get("dias_plazo") else "."
        if d.get("urgencia"):
            plazo += (" Se tramita por el procedimiento de urgencia, que reduce los plazos "
                      "a la mitad.")
        c.append(plazo)
    elif d.get("urgencia"):
        c.append("Se tramita por el procedimiento de urgencia, que reduce los plazos a la mitad.")

    if d.get("puntos"):
        c.append("En el orden del día: " + "; ".join(
            _cerrar_c(_asunto_c(p), 150) for p in d["puntos"][:6]) + ".")
    if d.get("votacion"):
        c.append("Resultado de la votación: " + d["votacion"])

    # La procedencia va al final y con el dato concreto, no como coletilla: si
    # no hay nada más que contar, al menos se dice qué documento es.
    ident = d.get("expediente") or doc.get("nombre", "")
    sello = f"Fuente: {doc.get('nombre','publicación oficial')}"
    sello += f", expediente {ident}." if d.get("expediente") else "."
    c.append(sello)
    return c


def parsear_cortes(nombre: str, tipo: str, texto: str) -> dict:
    t = _limpiar_c(texto[:16000])
    fecha = _fecha_sesion(t)

    # --- BOCG serie B: tomas en consideración, que es donde se vota ---
    # Aquí está la noticia de verdad —el Pleno tumba o admite una proposición—
    # y antes caía al cajón genérico y salía como «SESIÓN DEL COMISIÓN».
    mb = re.search(r"(PROPOSICI[ÓO]N DE LEY)\s+(\d{3}/\d{6})\s+(.{10,300}?)\s+"
                   r"(Rechazada|Aprobada|Retirada|Caducada|Tomada en consideraci[óo]n)\b", t, re.I)
    if mb:
        titulo = _limpiar_c(mb.group(3)).strip(" .")
        estado = mb.group(4).capitalize()
        mg = re.search(r"presentada por (?:el|la)\s+(Grupo Parlamentario [^,.]{2,45}|"
                       r"[A-ZÁÉÍÓÚÑ][^,.]{2,45}?)(?=,|\.| publicada)", t)
        autor = mg.group(1).strip() if mg else ""
        if "Grupo Parlamentario" in autor:
            autor = _grupo_c(autor) or autor
        morig = re.search(rf"n[úu]m\.\s*[\d-]+,\s*de\s+(\d{{1,2}} de (?:{MESES_RE}) de \d{{4}})", t)
        return {"clase": "TOMA_EN_CONSIDERACION", "expediente": mb.group(2),
                "titulo": titulo, "nucleo": _materia_c(titulo), "estado": estado,
                "autor": autor, "registrada": morig.group(1) if morig else "",
                "organo": "Pleno", "fecha": fecha, "puntos": []}

    # --- BOCG serie A y B: proyectos y proposiciones de ley ---
    m = re.search(r"(PROYECTO DE LEY|PROPOSICI[ÓO]N DE LEY)\s+(\d{3}/\d{6})\s+(.{10,260}?)"
                  r"(?=\s+La Mesa|\s*\(procedente|\.\s+En cumplimiento)", t, re.I)
    if m:
        clase, exp, titulo = m.group(1).upper(), m.group(2), _limpiar_c(m.group(3)).strip(" .")
        autor = ""
        ma = re.search(r"Autor:\s*(Gobierno|Grupo Parlamentario [^,.]{2,40}|[A-ZÁÉÍÓÚÑ][^,.]{2,40}?)"
                       r"(?=\s+(?:Proyecto|Proposici|Acuerdo|Exposici|En ejecuci))", t)
        if ma:
            autor = ma.group(1).strip()
            if "Grupo Parlamentario" in autor:
                autor = _grupo_c(autor) or autor
        # La comisión puede acabar en punto («…a la Comisión de Sanidad.») o
        # seguir con la competencia («…y Migraciones, para su aprobación…»).
        com = re.search(r"(?:remisi[óo]n|env[íi]o)?\s*a la Comisi[óo]n de "
                        r"([A-ZÁÉÍÓÚÑ][\w\sáéíóúñ,]{2,90}?)"
                        r"(?=\.|,\s*(?:para|con|a fin)|\s+para su)", t)
        # Dos redacciones para lo mismo: «el plazo … finaliza el día X» y
        # «abrir un plazo de ocho días hábiles que expira el día X».
        plazo = re.search(rf"plazo de enmiendas.{{0,120}}?finaliza el d[íi]a\s+"
                          rf"(\d{{1,2}} de (?:{MESES_RE}) de \d{{4}})", t, re.I)
        if not plazo:
            plazo = re.search(rf"plazo\s+de\s+[\w\s]{{0,24}}?(?:que\s+)?(?:expira|finaliza|"
                              rf"termina|vence)\s+el\s+d[íi]a\s+"
                              rf"(\d{{1,2}} de (?:{MESES_RE}) de \d{{4}})", t, re.I)
        mdias = re.search(r"plazo de ([\w]+ d[íi]as?(?:\s+h[áa]biles)?)", t, re.I)
        mproc = re.search(rf"procedente del (Real Decreto-ley\s+[\d/]+,?\s*de\s+\d{{1,2}} de "
                          rf"(?:{MESES_RE}))", t, re.I)
        mconv = re.search(rf"sesi[óo]n\s+del\s+d[íi]a\s+(\d{{1,2}} de (?:{MESES_RE}) de \d{{4}}),"
                          rf"\s*en la que se acord[óo] su convalidaci[óo]n", t, re.I)
        nucleo = re.sub(r"^(?:Proyecto|Proposici[óo]n) de Ley\s+(?:Org[áa]nica\s+)?(?:del?\s+|sobre\s+)?",
                        "", titulo, flags=re.I)
        return {"clase": clase, "expediente": exp, "titulo": titulo, "nucleo": nucleo,
                "de_decreto": bool(re.search(r"procedente del Real Decreto-ley", t, re.I)),
                "autor": autor,
                "comision": " ".join(com.group(1).split()).strip(" ,.") if com else "",
                "plazo_enmiendas": plazo.group(1) if plazo else "",
                "dias_plazo": mdias.group(1).lower() if mdias else "",
                "procedente": mproc.group(1) if mproc else "",
                "convalidado": mconv.group(1) if mconv else "",
                "competencia_plena": bool(re.search(r"competencia legislativa plena", t, re.I)),
                "urgencia": bool(re.search(r"procedimiento de urgencia", t, re.I)),
                "objeto": _objeto_ley(t),
                "fecha": fecha, "puntos": []}

    # --- Diario de Sesiones ---
    puntos = _orden_del_dia(t)
    organo = ""
    if re.search(r"\bPLENO\b", t):
        organo = "Pleno"
    else:
        mc = re.search(r"SESI[ÓO]N DE LA COMISI[ÓO]N DE\s+([A-ZÁÉÍÓÚÑ\s,Y]{4,60}?)\s+CELEBRADA", t)
        if not mc:
            mc = re.search(r"N[úu]m\. \d+\s+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s,Y]{4,55}?)\s+PRESIDENCIA", t)
        organo = ("Comisión de " + " ".join(mc.group(1).split()).title()) if mc else ""
    return {"clase": "DIARIO", "organo": organo, "fecha": fecha, "puntos": puntos,
            "votacion": _votacion(t),
            "grupos": [g for g in (_grupo_c(p) for p in puntos) if g]}


# --- De los datos al titular -------------------------------------------------

CONECTORES_C = {
    "de","del","la","el","los","las","y","e","o","u","en","con","para","por","a","al",
    "que","se","su","sus","un","una","unos","unas","lo",
    # Un titular cortado en «...PROTECCIÓN LABORAL Y SOCIAL FRENTE» no es un titular.
    # Toda preposición o nexo que pide complemento tiene que caer con él.
    "frente","ante","bajo","cabe","contra","desde","durante","entre","hacia","hasta",
    "mediante","salvo","según","segun","sin","sobre","tras","como","cuando","donde",
    "cuyo","cuya","cuyos","cuyas","cual","cuales","tanto","tan","más","mas","menos",
    "respecto","relativa","relativo","relativas","relativos","así","asi","no","ni",
}

def _cerrar_c(t, n=64):
    t = " ".join(t.split())
    cortado = len(t) > n
    if cortado:
        t = t[:n]
        if " " in t: t = t[:t.rfind(" ")]
    pal = t.split()
    # Si el corte dejó colgando el último elemento de una enumeración («A, B, C,
    # D» -> «A, B, C»), ese elemento suelto sobra: la coma anterior ya prometía
    # una lista que no se va a completar.
    if cortado and len(pal) > 2 and pal[-2].endswith(","):
        pal = pal[:-1]
    while pal and pal[-1].lower().strip(",;.:") in CONECTORES_C:
        pal.pop()
    salida = " ".join(pal).strip(" .,;:-–—")
    # Contracciones: al unir trozos sale «DE EL DERECHO», que no es español.
    salida = re.sub(r"\bDE EL\b", "DEL", salida)
    salida = re.sub(r"\bA EL\b", "AL", salida)
    salida = re.sub(r"\bde el\b", "del", salida)
    return salida

def _materia_c(t):
    """«Orgánica de modificación de la Ley Orgánica 5/2005, de 17 de noviembre,
    de la Defensa Nacional» -> «la Defensa Nacional»: lo que la ley regula va
    detrás de la última fecha."""
    partes = re.split(rf",\s*de\s+\d{{1,2}} de (?:{MESES_RE})(?: de \d{{4}})?,\s*", t)
    cola = partes[-1] if len(partes) > 1 else t
    cola = re.sub(r"^(?:por (?:la|el) que se \w+|de|sobre|para)\s+", "", cola, flags=re.I)
    return cola.strip(" .,;")

def _corto_c(t, n=64):
    t = " ".join(t.split())
    if len(t) <= n:
        return t.strip(" .,;")
    t = t[:n]
    return t[:t.rfind(" ")].strip(" .,;") if " " in t else t

def titular_cortes(d: dict) -> tuple:
    if d.get("clase") == "TOMA_EN_CONSIDERACION":
        materia = d.get("nucleo") or d.get("titulo", "")
        # «Ley 12/2023, por el derecho a la vivienda» -> «el derecho a la vivienda»:
        # el «por» es del título legal, no del titular.
        materia = re.sub(r"^por\s+(?=(?:el|la|los|las)\s)", "", materia, flags=re.I)
        materia = _cerrar_c(materia, 58)
        de_quien = f" DE {d['autor'].upper()}" if d.get("autor") else ""
        verbo = {"Rechazada": "TUMBA", "Aprobada": "APRUEBA",
                 "Tomada en consideración": "ADMITE A TRÁMITE",
                 "Retirada": "SE QUEDA SIN", "Caducada": "DEJA CADUCAR"}.get(
                     d.get("estado", ""), "VOTA")
        titulo = _cerrar_c(f"EL CONGRESO {verbo} LA REFORMA DE {materia.upper()}{de_quien}", 96)
        partes = []
        if d.get("autor"):
            partes.append(f"La presentó {d['autor']}")
        if d.get("registrada"):
            partes.append(f"estaba registrada desde el {d['registrada']}")
        entradilla = (", ".join(partes) + ".") if partes else ""
        return titulo, entradilla

    """Devuelve (titular, entradilla). Lo relevante delante: qué se tramita,
    quién lo trae y hasta cuándo se puede enmendar."""
    if d["clase"] in ("PROYECTO DE LEY", "PROPOSICIÓN DE LEY", "PROPOSICION DE LEY"):
        quien = d.get("autor") or ""
        crudo = d.get("nucleo") or d.get("titulo", "")
        crudo = re.sub(r"^(?:por (?:la|el) que se \w+)\s+", "", crudo, flags=re.I)
        nucleo = _cerrar_c(crudo, 70)
        if d.get("de_decreto"):
            cabeza = "SE TRAMITA COMO LEY EL DECRETO DE"
        elif quien.lower().startswith("gobierno"):
            cabeza = "EL GOBIERNO LLEVA AL CONGRESO"
        elif quien:
            cabeza = f"{quien.upper()} LLEVA AL CONGRESO"
        else:
            cabeza = "ENTRA EN EL CONGRESO"
        tit = f"{cabeza} {nucleo.upper()}"
        if d.get("plazo_enmiendas"):
            corta = re.sub(r"\s+de\s+\d{4}$", "", d["plazo_enmiendas"])
            tit += f": ENMIENDAS HASTA EL {corta.upper()}"
        partes = [f"Expediente {d['expediente']}"]
        if d.get("comision"):
            partes.append(f"se tramita en la Comisión de {d['comision']}")
        if d.get("plazo_enmiendas"):
            partes.append(f"el plazo de enmiendas acaba el {d['plazo_enmiendas']}")
        return tit, ", ".join(partes) + "."

    puntos = d.get("puntos", [])
    organo = d.get("organo", "El Pleno")
    if not puntos:
        return f"SESIÓN DEL {organo.upper()}", "Publicación oficial del Diario de Sesiones."
    asuntos = [_asunto_c(p) for p in puntos]
    grupos = [g for g in d.get("grupos", []) if g]
    if organo == "Pleno":
        primero = _cerrar_c(_materia_c(asuntos[0]), 54)
        g0 = grupos[0] if grupos else ""
        tit = (f"{g0.upper()} LLEVA AL PLENO {primero.upper()}" if g0
               else f"EL PLENO DEBATE {primero.upper()}")
        if len(asuntos) > 1:
            tit += f", Y {len(asuntos)-1} ASUNTOS MÁS"
    else:
        comparecientes = re.findall(r"(?:Del?|De la)\s+([a-záéíóúñ\s\-]{4,40}?)\s+(?:de la |de |del )"
                                    r"(?:organizaci[óo]n |Fundaci[óo]n |)([A-ZÁÉÍÓÚÑ][\w\s]{2,30})", " | ".join(puntos))
        quienes = ", ".join(dict.fromkeys(c[1].strip() for c in comparecientes))[:60]
        tit = (f"{organo.upper()} ESCUCHA A {quienes.upper()}" if quienes
               else f"{organo.upper()}: {_corto_c(asuntos[0], 52).upper()}")
    entradilla = f"Orden del día de la sesión: {len(puntos)} punto{'s' if len(puntos)>1 else ''}."
    if grupos:
        entradilla += " Intervienen " + ", ".join(dict.fromkeys(grupos)) + "."
    return tit, entradilla


def fusionar_curado(dia: dict) -> dict:
    """Lo curado a mano manda sobre lo generado. Nunca se pierde trabajo."""
    f = CURATED_DIR / f"{dia['id']}.json"
    if not f.exists():
        return dia
    try:
        cur = json.loads(f.read_text(encoding="utf-8"))
    except Exception as exc:                                  # noqa: BLE001
        log(f"curated/{f.name} ilegible: {exc}")
        return dia

    for seccion in ("boe", "cortes"):
        if seccion in cur:
            dia.setdefault(seccion, {})
            for k, v in cur[seccion].items():
                if k in ("feed_append", "stories_append"):
                    destino = "feed" if k == "feed_append" else "stories"
                    dia[seccion].setdefault(destino, [])
                    existentes = {a.get("headline") for a in dia[seccion][destino]}
                    dia[seccion][destino] += [a for a in v
                                              if a.get("headline") not in existentes]
                else:
                    dia[seccion][k] = v
    for k, v in cur.items():
        if k not in ("boe", "cortes"):
            dia[k] = v

    # Si lo curado aporta artículos, el aviso de "no se pudo descargar nada" sobra.
    if dia.get("cortes", {}).get("feed"):
        dia["cortes"].pop("constructionNote", None)

    dia["curated"] = True
    log(f"curated/{f.name} fusionado sobre la edición generada")
    return dia


# ---------------------------------------------------------------------------
# Renderizado estático (SSR) — SEO y accesibilidad para lectores sin JS
# ---------------------------------------------------------------------------
#
# El sitio es, de cara al humano, una SPA: el JS del template pinta el día
# activo a partir de __DIGEST_DATA__. Pero los rastreadores de las IAs
# (GPTBot, ClaudeBot, CCBot, PerplexityBot...) normalmente NO ejecutan
# JavaScript: solo leen el HTML que devuelve el servidor. Si el contenido
# solo existiera dentro del <script>, esos rastreadores verían una página
# casi vacía. Por eso estas funciones generan en Python el mismo HTML que
# el JS generaría para el día activo, y ese HTML va ya escrito en el
# documento: el navegador con JS lo vuelve a pintar igual (sin parpadeo
# visible) y el rastreador sin JS ya lo tiene desde la primera respuesta.

# ---------------------------------------------------------------------------
# Materias: una norma puede estar en varias
# ---------------------------------------------------------------------------
#
# `cat` pinta la tarjeta y es excluyente; esto es otra cosa: las materias por
# las que alguien buscaría o querría que le avisaran. Una orden de subvenciones
# a la contratación es a la vez «subvenciones» y «laboral», y tiene que salir
# en las dos secciones.

MATERIAS = [
    ("subvenciones", "Subvenciones y ayudas",
     ["subvenci", "ayudas", "concesión directa", "convocatoria", "bases reguladoras",
      "premios", "beca", "financiación de proyectos"]),
    ("fiscal", "Fiscal y tributario",
     ["tribut", "impuesto", "iva", "irpf", "sociedades", "hacienda", "aduana",
      "recaudación", "catastro", "tasa", "arancel"]),
    ("laboral", "Laboral y empleo",
     ["laboral", "trabajo", "empleo", "convenio colectivo", "salario", "salarios",
      "despido", "jornada", "prevención de riesgos", "autónomo", "desemple",
      "formación profesional para el empleo"]),
    ("seguridad-social", "Seguridad Social y pensiones",
     ["seguridad social", "pensión", "pensiones", "jubilación", "cotización",
      "incapacidad", "prestación"]),
    ("mercantil", "Mercantil y contable",
     ["mercantil", "sociedades de capital", "contabilidad", "auditoría", "concursal",
      "registro mercantil", "mercado de valores", "competencia", "consumidores"]),
    ("contratacion", "Contratación pública",
     ["contratación del sector público", "licitación", "pliego", "adjudicación",
      "encargo a medio propio", "contrato menor", "mesa de contratación"]),
    ("convenios", "Convenios y colaboración",
     ["convenio con", "convenio entre", "adenda", "protocolo general de actuación",
      "encomienda de gestión"]),
    ("administracion", "Administración y función pública",
     ["función pública", "personal estatutario", "oposicion", "proceso selectivo",
      "admitidos y excluidos", "cuerpo superior", "nombramiento", "sede electrónica",
      "administración digital"]),
    ("energia", "Energía",
     ["energía", "eléctric", "hidrocarburo", "renovable", "gas natural", "carburante"]),
    ("vivienda", "Vivienda y urbanismo",
     ["vivienda", "alquiler", "urbanis", "suelo", "edificación"]),
    ("sanidad", "Sanidad",
     ["sanidad", "sanitari", "medicamento", "farmac", "servicios de salud", "salud pública"]),
    ("educacion", "Educación",
     ["educación", "universidad", "enseñanza", "título universitario", "profesorado",
      "formación profesional"]),
    ("transporte", "Transporte e infraestructuras",
     ["transporte", "carretera", "ferroviari", "aeropuerto", "aviación", "puerto",
      "movilidad"]),
    ("agricultura", "Agricultura, pesca y alimentación",
     ["agricultura", "agrari", "pesca", "alimentación", "ganader", "denominación de origen"]),
    ("medioambiente", "Medio ambiente",
     ["medio ambiente", "ambiental", "residuos", "emisiones", "biodiversidad",
      "cambio climático", "incendios forestales", "agua"]),
    ("justicia", "Justicia e interior",
     ["justicia", "judicial", "penal", "penitenciari", "recurso contencioso",
      "seguridad ciudadana", "fronter", "extranjería", "guardia civil", "policía"]),
    ("cultura", "Cultura y patrimonio",
     ["cultura", "patrimonio histórico", "bien de interés cultural", "museo",
      "archivo", "artes escénicas", "cinematograf", "interés turístico"]),
]

_MATERIAS_C = [(slug, etiqueta, [_patron(k) for k in claves])
               for slug, etiqueta, claves in MATERIAS]
MATERIA_LABEL = {slug: etiqueta for slug, etiqueta, _ in MATERIAS}


def materias_de(*textos: str) -> list:
    """Todas las materias que toca un texto, no solo la principal."""
    bajo = " ".join(t for t in textos if t).lower()
    return [slug for slug, _, patrones in _MATERIAS_C if any(p.search(bajo) for p in patrones)]


CAT_LABEL = {"fiscal": "Fiscal / Hacienda", "laboral": "Laboral",
             "mercantil": "Mercantil / Contable", "otros": "Sociedad / Varios"}
CHAMBER_LABEL = {"congreso": "Congreso", "senado": "Senado"}
DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def esc_html(s) -> str:
    """Igual que la función esc() del JS: solo &, < y >."""
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def esc_attr(s) -> str:
    """Como esc_html, pero también apta para ir dentro de un atributo con comillas."""
    return esc_html(s).replace('"', "&quot;")


def fmt_date_es(iso: str) -> str:
    """Equivalente en Python de fmtDate() del JS (toLocaleDateString es-ES)."""
    try:
        d = dt.date.fromisoformat(iso)
        return f"{DIAS_SEMANA[d.weekday()]}, {d.day} de {MESES[d.month-1]} de {d.year}"
    except Exception:                                         # noqa: BLE001
        return iso


def body_html_ssr(paras: list[str] | None) -> str:
    return '<div class="articlebody">' + "".join(
        f"<p>{esc_html(p)}</p>" for p in (paras or [])) + "</div>"


def render_ticker_ssr(day: dict) -> str:
    items = []
    for s in (day.get("boe", {}).get("stories") or [])[:5]:
        items.append(f"<span><b>BOE</b>{esc_html(s.get('headline'))}</span>")
    for f in (day.get("cortes", {}).get("feed") or [])[:4]:
        etiqueta = CHAMBER_LABEL.get(f.get("chamber"), "CORTES")
        items.append(f"<span><b>{esc_html(etiqueta)}</b>{esc_html(f.get('headline'))}</span>")
    if not items:
        items.append("<span><b>AVISO</b>Sin titulares en esta edición.</span>")
    html = "".join(items)
    return html + html


def render_daystrip_ssr(dias: list[dict], current_id: str) -> str:
    """Enlaces de verdad a cada edición, no pestañas de JavaScript: así el
    rastreador los sigue y cada día se alcanza con una URL propia."""
    out = []
    for d in dias[:14]:
        actual = d["id"] == current_id
        destino = "./" if actual else f'ediciones/{d["id"]}.html'
        aria = ' aria-current="page"' if actual else ""
        out.append(f'<a class="daypill" href="{destino}"{aria}>{esc_html(d.get("label"))}</a>')
    out.append('<a class="daypill archivo" href="ediciones/">ARCHIVO →</a>')
    return "".join(out)


def _entero(v) -> int:
    """curated/ lo escribe una persona a mano: un "3" con comillas no puede
    tumbar la publicación del día."""
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def render_boe_stats_ssr(day: dict) -> str:
    c = day.get("boe", {}).get("counts") or {}
    orden = ["fiscal", "laboral", "mercantil", "otros"]
    maximo = max(1, *(_entero(c.get(k)) for k in orden))
    out = []
    for k in orden:
        n = _entero(c.get(k))
        pct = round((n / maximo) * 100)
        out.append(
            f'<div class="stat"><div class="label">{esc_html(CAT_LABEL[k])}</div>'
            f'<div class="n">{n}</div>'
            f'<div class="meter"><i style="width:{pct}%;background:var(--{k})"></i></div></div>')
    return "".join(out)


def render_boe_grid_ssr(day: dict) -> str:
    out = []
    for i, s in enumerate(day.get("boe", {}).get("stories") or []):
        is_lead = s.get("size") == "lead"
        cuerpo = body_html_ssr(s.get("body"))
        articulo = cuerpo if is_lead else (
            f'<details class="reader"><summary>Leer el artículo</summary>{cuerpo}</details>')
        cat = s.get("cat") or "otros"
        out.append(
            f'<article id="{esc_attr(ancla_de(s, i))}" class="story {esc_attr(s.get("size",""))}" '
            f'style="--cat:var(--{cat});--catsoft:var(--{cat}-soft)">'
            f'<div class="kicker"><span class="pill">{icono(cat)}{esc_html(CAT_LABEL.get(cat, "Varios"))}</span></div>'
            f'<h3>{esc_html(s.get("headline"))}</h3>'
            f'<p class="standfirst">{esc_html(s.get("standfirst"))}</p>'
            f'{articulo}'
            f'<div class="foot"><span>{esc_html(s.get("dept"))}</span>'
            f'{ficha_link(s)}'
            f'<span class="ref">{esc_html(s.get("ref",""))}</span></div>'
            f'</article>')
    return "".join(out)


def render_boe_note_ssr(day: dict) -> str:
    b = day.get("boe", {}) or {}
    enlace = ""
    if b.get("sourceUrl"):
        enlace = (f' <a class="srclink" href="{esc_attr(b["sourceUrl"])}" target="_blank" '
                  f'rel="noopener">Ver el sumario oficial ↗</a>')
    return (f'<b>BOE núm. {esc_html(b.get("numero",""))}</b> · {esc_html(b.get("fecha",""))}. '
            f'{esc_html(b.get("extra",""))}{enlace}')


def render_chamber_cards_ssr(day: dict) -> str:
    c = day.get("cortes", {}) or {}
    cong = c.get("congreso") or {}
    sen = c.get("senado") or {}
    return (
        '<div class="chamber-card" style="--cc:var(--congreso)"><div class="h">CONGRESO DE LOS DIPUTADOS</div>'
        f'<div class="who">{esc_html(cong.get("presidenta","—"))}</div>'
        f'<div class="meta">Presidenta · {esc_html(cong.get("legislatura",""))}<br>{esc_html(cong.get("sede",""))}</div></div>'
        '<div class="chamber-card" style="--cc:var(--senado)"><div class="h">SENADO</div>'
        f'<div class="who">{esc_html(sen.get("presidente","—"))}</div>'
        f'<div class="meta">Presidente · {esc_html(sen.get("legislatura",""))}<br>{esc_html(sen.get("sede",""))}</div></div>')


def render_scoreboard_ssr(day: dict) -> tuple[bool, str]:
    sb = (day.get("cortes", {}) or {}).get("scoreboard")
    if not sb or not sb.get("rows"):
        return True, ""
    maximo = max(1, *(_entero(r.get("n")) for r in sb["rows"]))
    filas = []
    for r in sb["rows"]:
        n = _entero(r.get("n"))
        pct = round((n / maximo) * 100)
        filas.append(
            f'<div class="scorerow"><span class="g">{esc_html(r.get("g"))}</span>'
            f'<span class="bar"><i style="width:{pct}%"></i></span>'
            f'<span class="v">{esc_html(n)}</span></div>')
    html = (f'<h3>Marcador del día</h3><p class="sub">{esc_html(sb.get("note",""))}</p>'
            + "".join(filas))
    return False, html


def render_coverage_note_ssr(day: dict) -> tuple[bool, str]:
    cov = (day.get("cortes", {}) or {}).get("coverage")
    if not cov or not cov.get("nota"):
        return True, ""
    return False, f'<b>Cobertura de hoy:</b> {esc_html(cov["nota"])}'


def render_cortes_feed_ssr(day: dict) -> str:
    feed = (day.get("cortes", {}) or {}).get("feed") or []
    if not feed:
        nota = (day.get("cortes", {}) or {}).get("constructionNote") or (
            "La extracción del día no obtuvo publicaciones oficiales legibles. "
            "Antes que rellenar con ruido, lo decimos.")
        return (
            '<div class="acard" style="--cc:var(--otros);--ccsoft:var(--otros-soft)">'
            '<div class="row1"><span class="tag-cc">Sin datos verificados</span></div>'
            '<h3>Hoy no se ha podido verificar actividad en las fuentes oficiales</h3>'
            f'<p class="standfirst">{esc_html(nota)}</p></div>')
    out = []
    for n, f in enumerate(feed, start=1):
        cc = "senado" if f.get("chamber") == "senado" else "congreso"
        cita = ""
        if f.get("quote"):
            cita = (f'<blockquote class="pull"><p>«{esc_html(f["quote"].get("text"))}»</p>'
                    f'<cite>{esc_html(f["quote"].get("author"))}</cite></blockquote>')
        fuente = ""
        if f.get("source"):
            fuente = (f'<a class="srclink" href="{esc_attr(f["source"].get("url"))}" '
                      f'target="_blank" rel="noopener">{esc_html(f["source"].get("label"))} ↗</a>')
        out.append(
            f'<article id="cortes-{n}" class="acard" style="--cc:var(--{cc});--ccsoft:var(--{cc}-soft)">'
            f'<div class="row1"><span class="tag-cc">{icono(cc)}{esc_html(CHAMBER_LABEL[cc])}</span>'
            f'<span class="tag-cc">{esc_html(f.get("type",""))}</span>'
            f'<span class="tstamp">{esc_html(f.get("date",""))}</span></div>'
            f'<h3>{esc_html(f.get("headline"))}</h3>'
            f'<p class="standfirst">{esc_html(f.get("standfirst",""))}</p>{cita}'
            f'<details class="reader"><summary>Leer la auditoría completa</summary>'
            f'{body_html_ssr(f.get("body"))}</details>'
            f'<div class="foot"><span>Verificado en fuente oficial</span>{fuente}</div>'
            f'</article>')
    return "".join(out)


# --- Iconografía ------------------------------------------------------------
# SVG en línea, trazo en currentColor: heredan el color de la categoría y
# funcionan igual en claro y en oscuro sin duplicar nada.

_SVG = ('<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" '
        'aria-hidden="true" focusable="false">{}</svg>')

ICONOS = {
    # Fiscal / Hacienda: moneda
    "fiscal": _SVG.format('<circle cx="12" cy="12" r="8"/><path d="M14.5 9.5a3.5 3.5 0 1 0 0 5"/>'
                          '<path d="M8.5 11.2h4.2M8.5 13.2h4.2"/>'),
    # Laboral: casco de trabajo
    "laboral": _SVG.format('<path d="M3 16h18"/><path d="M5 16a7 7 0 0 1 14 0"/>'
                           '<path d="M10 9.4V5.6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v3.8"/>'
                           '<path d="M3 16v1.5a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1V16"/>'),
    # Mercantil / Contable: edificio de oficinas
    "mercantil": _SVG.format('<path d="M4 20V5.6a1 1 0 0 1 1-1h9a1 1 0 0 1 1 1V20"/>'
                             '<path d="M15 10h4a1 1 0 0 1 1 1v9"/><path d="M2.5 20h19"/>'
                             '<path d="M7 8h1.5M11 8h1.5M7 11.5h1.5M11 11.5h1.5M7 15h1.5M11 15h1.5"/>'),
    # Sociedad / Varios: documento con sello
    "otros": _SVG.format('<path d="M14 3.5H7a1 1 0 0 0-1 1v15a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7.5z"/>'
                         '<path d="M14 3.5v4h4"/><circle cx="12" cy="14.5" r="2.2"/>'),
    # Congreso: hemiciclo
    "congreso": _SVG.format('<path d="M3 19h18"/><path d="M4.5 19v-6M9 19v-6M15 19v-6M19.5 19v-6"/>'
                            '<path d="M3 13h18"/><path d="M12 4.5 21 10H3z"/>'),
    # Senado: fachada con frontón
    "senado": _SVG.format('<path d="M3 19.5h18"/><path d="M5.5 16.5v-6M12 16.5v-6M18.5 16.5v-6"/>'
                          '<path d="M3.5 16.5h17"/><path d="M12 3.5l8 5H4z"/>'),
}


def icono(clave: str) -> str:
    return ICONOS.get(clave, ICONOS["otros"])


def ancla_de(story: dict, i: int) -> str:
    ref = (story.get("ref") or "").strip()
    return ref if ref.startswith("BOE-") else f"pieza-{i+1}"


def _normalizar(t: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFD", (t or "").lower())
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9 ]", " ", t)


def _parrafo(clase: str, texto: str) -> str:
    """Un <p> vacío deja un hueco raro en la maqueta; si no hay texto, no hay <p>."""
    return f'<p class="{clase}">{esc_html(texto)}</p>' if texto else ""


def una_linea(story: dict, limite: int = 150) -> str:
    """Qué hace la norma, en una línea y bien escrita. Sale del título oficial,
    que ya viene en mayúscula/minúscula correcta, no del titular en mayúsculas.

    Si acaba diciendo lo mismo que el titular —pasa con las leyes, cuyo título
    ya ES su objeto— se devuelve vacío: repetir la misma frase dos veces
    seguidas es justo el ruido que esta portada quiere quitarse."""
    texto = objeto_de(titulo_oficial_de(story)) or story.get("standfirst", "")
    corto = primera_mayuscula(recortar(texto, limite))

    # Comparar por el principio no sirve: el titular arranca con su gancho
    # («NUEVAS REGLAS PARA…») y la línea con el verbo («Regula…»), así que
    # empiezan distintos y siguen diciendo lo mismo. Se mide el solape de
    # palabras con carga, ignorando las vacías.
    vacias = {"de", "del", "la", "el", "los", "las", "y", "en", "para", "por",
              "que", "se", "al", "con", "un", "una", "lo", "su", "sus"}
    def cargadas(t: str) -> set:
        return {w for w in _normalizar(t).split() if len(w) > 2 and w not in vacias}
    a, b = cargadas(corto), cargadas(story.get("headline", ""))
    if a and b and len(a & b) / len(a) >= 0.7:
        return ""
    return corto


# --- Portada: jerarquía de periódico ----------------------------------------

def render_dateline_ssr(day: dict, permalink: str) -> str:
    """Cintillo de cabecera: número de boletín y fecha, como el de un periódico.
    Sin contadores: un número grande que nadie va a comparar con nada no informa,
    solo ocupa la primera pantalla."""
    boe = day.get("boe", {}) or {}
    piezas = []
    if boe.get("numero"):
        piezas.append(f'<b>BOE núm. {esc_html(boe["numero"])}</b>')
    piezas.append(esc_html(fmt_date_es(day["id"]).capitalize()))
    if boe.get("sourceUrl"):
        piezas.append(f'<a href="{esc_attr(boe["sourceUrl"])}" target="_blank" '
                      f'rel="noopener">Sumario oficial ↗</a>')
    piezas.append(f'<a href="{permalink}">Edición completa →</a>')
    return " <span class=\"sep\">·</span> ".join(piezas)


def render_boe_lead_ssr(day: dict, permalink: str) -> str:
    stories = (day.get("boe", {}) or {}).get("stories") or []
    if not stories:
        return ('<p class="aside-note">Hoy no se pudo leer el sumario del BOE.</p>')
    s = next((x for x in stories if x.get("size") == "lead"), stories[0])
    i = stories.index(s)
    cat = s.get("cat") or "otros"
    return (
        f'<article class="lead" style="--cat:var(--{cat});--catsoft:var(--{cat}-soft)">'
        f'<div class="lead-marca">{icono(cat)}</div>'
        f'<div class="kicker"><span class="pill">{icono(cat)}{esc_html(CAT_LABEL.get(cat,"Varios"))}</span>'
        f'<span class="ref mono">{esc_html(s.get("ref",""))}</span></div>'
        f'<h3 class="lead-h">{esc_html(s.get("headline"))}</h3>'
        f'{_parrafo("lead-sub", una_linea(s, 190))}'
        f'<div class="foot"><span>{esc_html(s.get("dept"))}</span>'
        f'<a class="srclink" href="{permalink}#{esc_attr(ancla_de(s,i))}">Leer la pieza completa →</a></div>'
        f'</article>')


def render_boe_destacados_ssr(day: dict, permalink: str) -> str:
    stories = (day.get("boe", {}) or {}).get("stories") or []
    lead = next((x for x in stories if x.get("size") == "lead"), stories[0] if stories else None)
    resto = [(i, x) for i, x in enumerate(stories) if x is not lead]
    destacados = [(i, x) for i, x in resto if x.get("size") == "md"][:3]
    if not destacados:
        destacados = resto[:3]
    out = []
    for i, s in destacados:
        cat = s.get("cat") or "otros"
        out.append(
            f'<article class="tarjeta" style="--cat:var(--{cat});--catsoft:var(--{cat}-soft)">'
            f'<div class="kicker"><span class="pill">{icono(cat)}{esc_html(CAT_LABEL.get(cat,"Varios"))}</span></div>'
            f'<h3>{esc_html(s.get("headline"))}</h3>'
            f'{_parrafo("linea", una_linea(s, 120))}'
            f'<div class="foot"><span>{esc_html(recortar(s.get("dept",""), 44))}</span>'
            f'{ficha_link(s, "normas/")}'
            f'<a class="srclink" href="{permalink}#{esc_attr(ancla_de(s,i))}">Leer →</a></div>'
            f'</article>')
    return "".join(out)


def render_boe_resto_ssr(day: dict, permalink: str) -> str:
    """El resto del día no se vuelca como lista de titulares en el pie: se
    anuncia y se enlaza. La portada enseña, la edición contiene."""
    stories = (day.get("boe", {}) or {}).get("stories") or []
    n = max(len(stories) - 4, 0)
    if not n:
        return ""
    return (f'<p class="sigue"><a href="{permalink}">'
            f'<span class="sigue-n">+{n}</span>'
            f'<span>disposiciones más del BOE de hoy, desarrolladas una a una '
            f'en la edición completa</span><span class="sigue-f">→</span></a></p>')


def render_cortes_lead_ssr(day: dict, permalink: str) -> str:
    feed = (day.get("cortes", {}) or {}).get("feed") or []
    if not feed:
        nota = (day.get("cortes", {}) or {}).get("constructionNote") or (
            "La extracción del día no obtuvo publicaciones oficiales legibles.")
        return (f'<article class="tarjeta" style="--cat:var(--otros);--catsoft:var(--otros-soft)">'
                f'<h3>Hoy no se ha podido verificar actividad</h3>'
                f'<p class="linea">{esc_html(nota)}</p></article>')
    f = feed[0]
    cc = "senado" if f.get("chamber") == "senado" else "congreso"
    cita = ""
    if f.get("quote"):
        cita = (f'<blockquote class="pull"><p>«{esc_html(recortar(f["quote"].get("text",""), 240))}»</p>'
                f'<cite>{esc_html(f["quote"].get("author"))}</cite></blockquote>')
    return (
        f'<article class="lead cortes" style="--cat:var(--{cc});--catsoft:var(--{cc}-soft)">'
        f'<div class="lead-marca">{icono(cc)}</div>'
        f'<div class="kicker"><span class="pill">{icono(cc)}{esc_html(CHAMBER_LABEL[cc])}</span>'
        f'<span class="pill ghost">{esc_html(f.get("type",""))}</span>'
        f'<span class="ref mono">{esc_html(f.get("date",""))}</span></div>'
        f'<h3 class="lead-h">{esc_html(f.get("headline"))}</h3>'
        f'<p class="lead-sub">{esc_html(recortar(f.get("standfirst",""), 200))}</p>{cita}'
        f'<div class="foot"><span>Verificado en fuente oficial</span>'
        f'<a class="srclink" href="{permalink}#cortes-1">Leer la auditoría completa →</a></div>'
        f'</article>')


def render_cortes_resto_ssr(day: dict, permalink: str) -> str:
    feed = (day.get("cortes", {}) or {}).get("feed") or []
    n = max(len(feed) - 1, 0)
    if not n:
        return ""
    return (f'<p class="sigue cortes"><a href="{permalink}#cortes-2">'
            f'<span class="sigue-n">+{n}</span>'
            f'<span>piezas más de auditoría parlamentaria en la edición de hoy</span>'
            f'<span class="sigue-f">→</span></a></p>')


def lead_story(day: dict) -> dict | None:
    stories = (day.get("boe", {}) or {}).get("stories") or []
    return next((s for s in stories if s.get("size") == "lead"), stories[0] if stories else None)


def titulo_oficial_de(story: dict) -> str:
    """El título literal de la norma. En las ediciones antiguas no existe el
    campo, pero en modo determinista la entradilla ES el título oficial."""
    return (story.get("titulo_oficial") or story.get("standfirst") or "").strip()


def primera_mayuscula(texto: str) -> str:
    """Mayúscula inicial SIN tocar el resto. str.capitalize() pasa a minúscula
    todo lo demás y se lleva por delante los nombres propios: «PRESUPUESTOS DE
    LA GENERALITAT» acabaría como «Presupuestos de la generalitat»."""
    texto = texto.strip()
    return texto[:1].upper() + texto[1:] if texto else ""


def fecha_boe_iso(day: dict) -> str:
    """Fecha del sumario realmente leído; si no consta, la de la edición."""
    return (day.get("boe", {}) or {}).get("fechaISO") or day["id"]


def build_title(day: dict, edicion: bool = False) -> str:
    fecha = fmt_date_es(day["id"])
    if edicion:
        return f"Edición del {fecha} — La Tercera Cámara"
    return f"La Tercera Cámara — {fecha}"


def build_meta_description(day: dict) -> str:
    """Máximo ~155 caracteres: es lo que muestra Google. Lo concreto va primero.

    El gancho sale del título oficial (que viene en mayúscula/minúscula correcta),
    no del titular de la casa (que va en mayúsculas y es editorial)."""
    boe = day.get("boe", {}) or {}
    n = len(boe.get("stories") or [])
    m = len((day.get("cortes", {}) or {}).get("feed") or [])
    d = dt.date.fromisoformat(day["id"])
    fecha_corta = f"{d.day} de {MESES[d.month-1]}"

    lead = lead_story(day)
    gancho = ""
    if lead:
        gancho = primera_mayuscula(recortar(objeto_de(titulo_oficial_de(lead)), 72))
    if not gancho:
        gancho = f"El BOE del {fecha_corta}, explicado en lenguaje llano"
    # recortar() ya cierra con «…»; añadir un punto detrás deja «los….»
    if not gancho.endswith("…"):
        gancho += "."

    cola = f" {n} disposiciones del BOE del {fecha_corta}" if n else f" Edición del {fecha_corta}"
    cola += f" y {m} piezas de las Cortes." if m else "."
    return recortar(f"{gancho}{cola}", 155)


def jsonld_script(objetos: list[dict]) -> str:
    grafo = {"@context": "https://schema.org", "@graph": objetos}
    payload = json.dumps(grafo, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")           # nunca cerrar el <script> por accidente
    return f'<script type="application/ld+json">{payload}</script>'


def jsonld_portada(day: dict, permalink_abs: str) -> str:
    """Portada: describe lo que la portada enseña de verdad, que son titulares
    y enlaces, no los títulos oficiales completos. Esos se declaran en la página
    de la edición, que es donde están escritos. Los datos estructurados tienen
    que coincidir con el contenido visible."""
    editor = {"@type": "Organization", "name": "La Tercera Cámara", "url": SITE_URL}
    elementos = []
    stories = (day.get("boe", {}) or {}).get("stories") or []
    for i, s in enumerate(stories):
        elementos.append({
            "@type": "ListItem", "position": len(elementos) + 1,
            "name": s.get("headline", ""),
            "url": f"{permalink_abs}#{ancla_de(s, i)}",
        })
    for n, f in enumerate((day.get("cortes", {}) or {}).get("feed") or [], start=1):
        elementos.append({
            "@type": "ListItem", "position": len(elementos) + 1,
            "name": f.get("headline", ""),
            "url": f"{permalink_abs}#cortes-{n}",
        })
    return jsonld_script([
        {"@type": "WebSite", "name": "La Tercera Cámara", "url": SITE_URL,
         "description": build_meta_description(day), "inLanguage": "es-ES",
         "publisher": editor, "dateModified": day["id"]},
        {"@type": "CollectionPage", "url": SITE_URL,
         "name": build_title(day), "inLanguage": "es-ES",
         "mainEntity": {"@type": "ItemList", "numberOfItems": len(elementos),
                        "itemListElement": elementos}},
    ])


def jsonld_for_day(day: dict, page_url: str) -> str:
    """Datos estructurados de la edición.

    Regla: en `name` de una norma va SIEMPRE su título oficial. El titular de la
    casa es editorial y va en `alternativeHeadline`. Publicar el titular como
    nombre de la norma, junto a su identificador BOE-A-…, sería afirmar a una
    máquina que la norma se llama así — exactamente lo que este proyecto se
    prohíbe a sí mismo.
    """
    editor = {"@type": "Organization", "name": "La Tercera Cámara", "url": SITE_URL}
    objetos: list[dict] = [{
        "@type": "WebSite",
        "name": "La Tercera Cámara",
        "url": SITE_URL,
        "description": build_meta_description(day),
        "inLanguage": "es-ES",
        "publisher": editor,
        "dateModified": day["id"],
    }]

    fecha_norma = fecha_boe_iso(day)          # la del sumario leído, no la de hoy
    for s in (day.get("boe", {}) or {}).get("stories") or []:
        oficial = titulo_oficial_de(s)
        item = {
            "@type": "Legislation",
            "name": oficial or s.get("headline", ""),
            "datePublished": fecha_norma,
            "inLanguage": "es-ES",
            "legislationJurisdiction": "ES",
            "isBasedOn": s.get("url") or page_url,
            "subjectOf": {"@type": "WebPage", "url": page_url},
        }
        if oficial and s.get("headline"):
            item["alternativeHeadline"] = s["headline"]
        if s.get("ref", "").startswith("BOE-"):
            item["legislationIdentifier"] = s["ref"]
        if s.get("url"):
            item["url"] = s["url"]
        if s.get("dept"):
            item["legislationPassedBy"] = {"@type": "GovernmentOrganization", "name": s["dept"]}
        objetos.append(item)

    for f in (day.get("cortes", {}) or {}).get("feed") or []:
        item = {
            "@type": "NewsArticle",
            "headline": recortar(f.get("headline", ""), 110),
            "description": f.get("standfirst", ""),
            "datePublished": day["id"],
            "inLanguage": "es-ES",
            "author": editor,
            "publisher": editor,
            "mainEntityOfPage": {"@type": "WebPage", "@id": page_url},
        }
        if f.get("source", {}).get("url"):
            item["isBasedOn"] = f["source"]["url"]
        objetos.append(item)

    return jsonld_script(objetos)


def render_ssr_fragments(day: dict, dias: list[dict] | None = None) -> dict:
    """Todos los trozos de HTML/estado que hacen falta para pintar una edición."""
    cov_hidden, cov_html = render_coverage_note_ssr(day)
    sb_hidden, sb_html = render_scoreboard_ssr(day)
    frag = {
        "EDITION_DATE": fmt_date_es(day["id"]).upper(),
        "TICKER": render_ticker_ssr(day),
        "BOE_STATS": render_boe_stats_ssr(day),
        "BOE_GRID": render_boe_grid_ssr(day),
        "BOE_NOTE": render_boe_note_ssr(day),
        "COVERAGE_HIDDEN": "hidden" if cov_hidden else "",
        "COVERAGE_NOTE": cov_html,
        "CHAMBER_CARDS": render_chamber_cards_ssr(day),
        "SCOREBOARD_HIDDEN": "hidden" if sb_hidden else "",
        "SCOREBOARD": sb_html,
        "CORTES_FEED": render_cortes_feed_ssr(day),
    }
    if dias is not None:
        frag["DAYSTRIP"] = render_daystrip_ssr(dias, day["id"])
    return frag


# ---------------------------------------------------------------------------
# Construcción y renderizado
# ---------------------------------------------------------------------------

def construir_dia(fecha: dt.date) -> dict | None:
    log(f"=== Edición del {fecha.isoformat()} ===")
    boe_raw = fetch_boe(fecha)
    congreso = fetch_congreso()
    senado = fetch_senado()

    DIAG["resumen"] = {
        "boe_entradas": len(boe_raw["entradas"]) if boe_raw else 0,
        "congreso_docs": len(congreso),
        "senado_docs": len(senado),
    }

    anterior = None
    previos = sorted(DATA_DIR.glob("*.json"), reverse=True)
    if previos:
        try:
            anterior = json.loads(previos[0].read_text(encoding="utf-8")).get("cortes")
        except Exception:                                     # noqa: BLE001
            pass

    if not boe_raw and not congreso and not senado:
        log("No se obtuvo NINGUNA fuente. No se escribe edición.")
        return None

    dia = {
        "id": fecha.isoformat(),
        "label": f"{fecha.day} {MES_ABBR[fecha.month-1]}",
        "boe": redactar_boe(boe_raw) if boe_raw else {
            "numero": "", "fecha": "", "sourceUrl": "",
            "counts": {"fiscal": 0, "laboral": 0, "mercantil": 0, "otros": 0},
            "extra": "Hoy no se pudo leer el sumario del BOE.", "stories": []},
        "cortes": redactar_cortes(congreso + senado, anterior),
    }
    return fusionar_curado(dia)


def _replace_placeholders(html: str, frag: dict) -> str:
    for clave, valor in frag.items():
        html = html.replace(f"__SSR_{clave}__", valor)
    # Red de seguridad: un marcador sin sustituir (una plantilla editada, una
    # clave que se renombra) no puede llegar al lector. Se avisa y se borra.
    sueltos = sorted(set(re.findall(r"__SSR_[A-Z_]+__", html)))
    if sueltos:
        log(f"  AVISO: marcadores sin sustituir, se eliminan: {', '.join(sueltos)}")
        for m in sueltos:
            html = html.replace(m, "")
    return html


# --- Fechas de última modificación reales -----------------------------------
#
# No sirve el mtime del fichero: actions/checkout deja todo con la hora del
# checkout, así que cada día parecería que han cambiado las 300 ediciones. Y no
# sirve la fecha de la edición: cuando senado_local.py añade el Senado a un día
# ya publicado vía curated/, esa página CAMBIA y hay que decírselo al buscador.
# Se lleva un registro propio: si el HTML generado difiere del que hay en disco,
# esa edición se modificó hoy; si no, conserva su fecha anterior.

MANIFIESTO = ESTADO / "ediciones.json"


def _cargar_manifiesto() -> dict:
    if MANIFIESTO.exists():
        try:
            return json.loads(MANIFIESTO.read_text(encoding="utf-8"))
        except Exception as exc:                              # noqa: BLE001
            log(f"  state/ediciones.json ilegible ({exc}); se reconstruye")
    return {}


def _guardar_manifiesto(m: dict) -> None:
    ESTADO.mkdir(exist_ok=True)
    MANIFIESTO.write_text(json.dumps(m, ensure_ascii=False, indent=2, sort_keys=True),
                          encoding="utf-8")


def ids_de_ediciones() -> list[str]:
    """Todas las ediciones publicadas alguna vez, no solo la ventana de render."""
    ids = set()
    for p in EDICIONES_DIR.glob("*.html"):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.stem):
            ids.add(p.stem)
    for p in DATA_DIR.glob("*.json"):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.stem):
            ids.add(p.stem)
    return sorted(ids)


def renderizar_index(dias: list[dict]) -> None:
    """Portada: escaparate, no archivo.

    Cada pieza aparece con titular y una línea de qué hace; el texto completo
    vive en la página de la edición, que es la que se indexa para ese día. Eso
    quita el muro de texto y, de paso, deja de competir consigo misma en el
    buscador con contenido duplicado.

    No lleva JavaScript: todo el contenido está en el HTML servido y cada día
    se alcanza por un enlace real, no por estado de una SPA."""
    day0 = dias[0]
    permalink = f"ediciones/{day0['id']}.html"
    cov_hidden, cov_html = render_coverage_note_ssr(day0)
    sb_hidden, sb_html = render_scoreboard_ssr(day0)

    frag = {
        "TITLE": esc_html(build_title(day0)),
        "META_DESC": esc_attr(build_meta_description(day0)),
        "JSONLD": jsonld_portada(day0, f"{SITE_URL}{permalink}"),
        "EDITION_DATE": fmt_date_es(day0["id"]).upper(),
        "TICKER": render_ticker_ssr(day0),
        "DAYSTRIP": render_daystrip_ssr(dias, day0["id"]),
        "DATELINE": render_dateline_ssr(day0, permalink),
        "BOE_LEAD": render_boe_lead_ssr(day0, permalink),
        "BOE_DESTACADOS": render_boe_destacados_ssr(day0, permalink),
        "BOE_RESTO": render_boe_resto_ssr(day0, permalink),
        "BOE_NOTE": render_boe_note_ssr(day0),
        "COVERAGE_HIDDEN": "hidden" if cov_hidden else "",
        "COVERAGE_NOTE": cov_html,
        "CHAMBER_CARDS": render_chamber_cards_ssr(day0),
        "SCOREBOARD_HIDDEN": "hidden" if sb_hidden else "",
        "SCOREBOARD": sb_html,
        "CORTES_LEAD": render_cortes_lead_ssr(day0, permalink),
        "CORTES_RESTO": render_cortes_resto_ssr(day0, permalink),
        "PERMALINK_HOY": permalink,
        "FECHA_HOY": esc_html(fmt_date_es(day0["id"])),
    }
    html = _replace_placeholders(TEMPLATE.read_text(encoding="utf-8"), frag)
    OUTPUT.write_text(html, encoding="utf-8")
    log(f"index.html generado ({len(html)} bytes, sin JavaScript)")


def renderizar_ediciones(dias: list[dict]) -> list[dict]:
    """Una página estática por edición (ediciones/AAAA-MM-DD.html): URL propia,
    indexable y enlazable por separado — la palanca principal para que cada día
    de contenido pueda encontrarse en buscadores y agentes de IA, no solo hoy.

    La cadena anterior/siguiente se teje sobre TODAS las ediciones publicadas,
    no sobre la ventana de render: si no, la más antigua de la ventana se queda
    sin enlace hacia atrás y todo el archivo anterior queda inalcanzable."""
    EDICIONES_DIR.mkdir(exist_ok=True)
    plantilla = TEMPLATE_EDICION.read_text(encoding="utf-8")
    manifiesto_prev = _cargar_manifiesto()
    manifiesto_nuevo = dict(manifiesto_prev)
    hoy = dt.date.today().isoformat()

    ids_todas = ids_de_ediciones()
    pos = {ident: i for i, ident in enumerate(ids_todas)}
    cambiadas = []

    for day in sorted(dias, key=lambda d: d["id"]):
        ident = day["id"]
        page_url = f"{SITE_URL}ediciones/{ident}.html"
        try:
            frag = render_ssr_fragments(day)
            frag["TITLE"] = esc_html(build_title(day, edicion=True))
            frag["META_DESC"] = esc_attr(build_meta_description(day))
            frag["CANONICAL"] = page_url
            frag["JSONLD"] = jsonld_for_day(day, page_url)
            frag["LABEL_LARGO"] = esc_html(fmt_date_es(ident))

            i = pos.get(ident, 0)
            anterior = ids_todas[i - 1] if i > 0 else None
            siguiente = ids_todas[i + 1] if i + 1 < len(ids_todas) else None
            frag["PREV_LINK"] = (f'<a class="srclink" rel="prev" href="{anterior}.html">← '
                                  f'{esc_html(fmt_date_es(anterior))}</a>') if anterior else ""
            frag["NEXT_LINK"] = (f'<a class="srclink" rel="next" href="{siguiente}.html">'
                                  f'{esc_html(fmt_date_es(siguiente))} →</a>') if siguiente else ""

            html = _replace_placeholders(plantilla, frag)
        except Exception as exc:                              # noqa: BLE001
            # Una edición con datos curados raros no puede tumbar la publicación
            # entera: se salta, se deja constancia y el resto sale.
            log(f"  ediciones/{ident}.html NO regenerada: {exc}")
            DIAG.setdefault("ediciones_fallidas", []).append({"id": ident, "error": str(exc)[:200]})
            continue

        destino = EDICIONES_DIR / f"{ident}.html"
        anterior_html = destino.read_text(encoding="utf-8") if destino.exists() else None
        if anterior_html != html:
            destino.write_text(html, encoding="utf-8")
            manifiesto_nuevo[ident] = hoy
            cambiadas.append(page_url)
        else:
            manifiesto_nuevo.setdefault(ident, ident)

    for ident in ids_todas:
        manifiesto_nuevo.setdefault(ident, ident)
    _guardar_manifiesto(manifiesto_nuevo)

    entradas = [{"id": i, "url": f"{SITE_URL}ediciones/{i}.html",
                 "lastmod": manifiesto_nuevo.get(i, i)} for i in ids_todas]
    log(f"ediciones/: {len(entradas)} en el archivo, {len(cambiadas)} regeneradas hoy")
    DIAG["urls_cambiadas"] = cambiadas
    return entradas


def renderizar_archivo(entradas: list[dict], dias: list[dict]) -> None:
    """ediciones/index.html — el índice del archivo.

    GitHub Pages no sirve listados de directorio: sin esta página, /ediciones/
    devuelve un 404 y las ediciones que salen de la ventana de render se quedan
    sin ningún enlace que las alcance."""
    titulares = {}
    for d in dias:
        lead = lead_story(d)
        if lead and lead.get("headline"):
            titulares[d["id"]] = lead["headline"]

    filas, mes_actual = [], None
    for e in sorted(entradas, key=lambda x: x["id"], reverse=True):
        f = dt.date.fromisoformat(e["id"])
        mes = f"{MESES[f.month-1]} de {f.year}"
        if mes != mes_actual:
            if mes_actual is not None:
                filas.append("</ul>")
            filas.append(f"<h2>{esc_html(mes[:1].upper() + mes[1:])}</h2><ul class=\"archivo\">")
            mes_actual = mes
        titular = titulares.get(e["id"], "")
        extra = f' — <span class="arch-tit">{esc_html(recortar(titular, 90))}</span>' if titular else ""
        filas.append(f'<li><a href="{e["id"]}.html">{esc_html(fmt_date_es(e["id"]))}</a>{extra}</li>')
    if mes_actual is not None:
        filas.append("</ul>")

    desc = (f"Archivo completo de La Tercera Cámara: {len(entradas)} ediciones "
            f"diarias del BOE, el Congreso y el Senado, cada una con su enlace permanente.")
    frag = {
        "TITLE": esc_html("Archivo de ediciones — La Tercera Cámara"),
        "META_DESC": esc_attr(recortar(desc, 155)),
        "CANONICAL": f"{SITE_URL}ediciones/",
        "TOTAL": str(len(entradas)),
        "LISTA": "\n".join(filas),
        "JSONLD": jsonld_script([{
            "@type": "CollectionPage",
            "name": "Archivo de ediciones — La Tercera Cámara",
            "url": f"{SITE_URL}ediciones/",
            "inLanguage": "es-ES",
            "isPartOf": {"@type": "WebSite", "url": SITE_URL},
            "hasPart": [{"@type": "WebPage", "url": e["url"],
                         "name": f"Edición del {fmt_date_es(e['id'])}"}
                        for e in sorted(entradas, key=lambda x: x["id"], reverse=True)[:50]],
        }]),
    }
    html = _replace_placeholders(TEMPLATE_ARCHIVO.read_text(encoding="utf-8"), frag)
    (EDICIONES_DIR / "index.html").write_text(html, encoding="utf-8")
    log(f"ediciones/index.html generado con {len(entradas)} entradas")


RE_REF_BOE = re.compile(r"^BOE-[A-Z]-\d{4}-\d+$")


def ref_norma(story: dict) -> str:
    """El identificador oficial, que es lo que da una URL estable y única."""
    r = (story.get("ref") or "").strip()
    return r if RE_REF_BOE.fullmatch(r) else ""


def ficha_link(story: dict, prefijo: str = "../normas/") -> str:
    r = ref_norma(story)
    if not r:
        return ""
    return (f'<a class="srclink fichalink" href="{prefijo}{r}.html">Ficha completa</a>')


def _ficha_filas(s: dict, day: dict) -> str:
    """La tabla de datos duros. Es lo que un buscador y un agente de IA pueden
    leer sin interpretar prosa, y lo que busca quien llega desde Google."""
    filas = []
    def fila(k, v):
        if v:
            filas.append(f"<dt>{esc_html(k)}</dt><dd>{esc_html(v)}</dd>")
    d = s.get("datos") or {}
    fila("Identificador", s.get("ref", ""))
    fila("Publicado", fmt_date_es(fecha_boe_iso(day)))
    fila("Organismo", s.get("dept", ""))
    if d.get("desde") and d.get("hasta"):
        fila("Vigencia", f"del {d['desde']} al {d['hasta']}")
    elif d.get("hasta"):
        fila("Hasta", d["hasta"])
    fila("Entrada en vigor", d.get("vigor", ""))
    fila("Importe", d.get("importe", ""))
    fila("Plazo", d.get("plazo", ""))
    return "".join(filas)


def jsonld_for_norma(s: dict, day: dict, page_url: str) -> str:
    oficial = titulo_oficial_de(s)
    editor = {"@type": "Organization", "name": "La Tercera Cámara", "url": SITE_URL}
    norma = {
        "@type": "Legislation",
        "name": oficial or s.get("headline", ""),
        "datePublished": fecha_boe_iso(day),
        "inLanguage": "es-ES",
        "legislationJurisdiction": "ES",
        "url": page_url,
    }
    if oficial and s.get("headline"):
        norma["alternativeHeadline"] = s["headline"]
    if ref_norma(s):
        norma["legislationIdentifier"] = s["ref"]
    if s.get("url"):
        norma["isBasedOn"] = s["url"]
    if s.get("dept"):
        norma["legislationPassedBy"] = {"@type": "GovernmentOrganization", "name": s["dept"]}

    articulo = {
        "@type": "NewsArticle",
        "headline": recortar(s.get("headline", ""), 110),
        "description": recortar(oficial, 260),
        "datePublished": fecha_boe_iso(day),
        "dateModified": day["id"],
        "inLanguage": "es-ES",
        "author": editor,
        "publisher": editor,
        "isBasedOn": s.get("url") or SITE_URL,
        "mainEntityOfPage": {"@type": "WebPage", "@id": page_url},
        "about": norma,
    }
    miga = {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Portada", "item": SITE_URL},
            {"@type": "ListItem", "position": 2, "name": "Archivo",
             "item": f"{SITE_URL}ediciones/"},
            {"@type": "ListItem", "position": 3, "name": fmt_date_es(day["id"]),
             "item": f"{SITE_URL}ediciones/{day['id']}.html"},
            {"@type": "ListItem", "position": 4, "name": recortar(s.get("headline", ""), 90),
             "item": page_url},
        ],
    }
    return jsonld_script([articulo, miga])


def renderizar_normas(dias: list[dict]) -> list[dict]:
    """Una página por disposición del BOE.

    Es la palanca de posicionamiento que faltaba: nadie busca «BOE del 19 de
    septiembre», la gente busca «Orden INT/977/2026» o «prórroga controles
    fronterizos Italia». Una URL por norma, con el título oficial en el
    <title>, el dato duro en una ficha legible por máquina y el enlace a la
    fuente, es lo que compite por esa consulta. Y son cientos de páginas nuevas
    con contenido distinto entre sí, no una sola que lo repite todo."""
    if not TEMPLATE_NORMA.exists():
        log("  template_norma.html no está; no se generan fichas por norma")
        return []
    NORMAS_DIR.mkdir(exist_ok=True)
    plantilla = TEMPLATE_NORMA.read_text(encoding="utf-8")
    fichas, escritas = [], 0

    for day in sorted(dias, key=lambda d: d["id"]):
        stories = (day.get("boe", {}) or {}).get("stories") or []
        conocidas = [x for x in stories if ref_norma(x)]
        for s in conocidas:
            ref = ref_norma(s)
            page_url = f"{SITE_URL}normas/{ref}.html"
            oficial = titulo_oficial_de(s)
            try:
                relacionadas = "".join(
                    f'<li><a href="{esc_attr(ref_norma(o))}.html">{esc_html(o.get("headline",""))}</a></li>'
                    for o in conocidas if ref_norma(o) != ref)[:12000]
                frag = {
                    "TITLE": esc_html(cerrar(primera_mayuscula(oficial) or s.get("headline", ""), 88)
                                      + " | La Tercera Cámara"),
                    "META_DESC": esc_attr(recortar(
                        (frase_datos_clave(s.get("datos") or {}) + " " +
                         primera_mayuscula(objeto_de(oficial) or oficial)).strip(), 155)),
                    "CANONICAL": page_url,
                    "JSONLD": jsonld_for_norma(s, day, page_url),
                    "EDITION_DATE": esc_html(fmt_date_es(day["id"])),
                    "MIGA": (f'<a href="../">Portada</a> › <a href="../ediciones/">Archivo</a> › '
                             f'<a href="../ediciones/{day["id"]}.html">{esc_html(fmt_date_es(day["id"]))}</a>'
                             f' › <span aria-current="page">{esc_html(s.get("ref",""))}</span>'),
                    "KICKER": esc_html(CAT_LABEL.get(s.get("cat") or "otros", "Varios")),
                    "HEADLINE": esc_html(s.get("headline", "")),
                    "STANDFIRST": esc_html(primera_mayuscula(oficial)),
                    "FICHA": _ficha_filas(s, day),
                    "CUERPO": body_html_ssr(s.get("body")),
                    "FUENTE": (f'Texto oficial: <a class="srclink" href="{esc_attr(s.get("url",""))}" '
                               f'target="_blank" rel="noopener">{esc_html(s.get("ref",""))} en el BOE ↗</a>'
                               if s.get("url") else "Fuente: Boletín Oficial del Estado."),
                    "RELACIONADAS": relacionadas,
                    "RELACIONADAS_HIDDEN": "" if relacionadas else "hidden",
                }
                html = _replace_placeholders(plantilla, frag)
            except Exception as exc:                          # noqa: BLE001
                log(f"  normas/{ref}.html NO generada: {exc}")
                continue
            destino = NORMAS_DIR / f"{ref}.html"
            if not destino.exists() or destino.read_text(encoding="utf-8") != html:
                destino.write_text(html, encoding="utf-8")
                escritas += 1
            fichas.append({"url": page_url, "lastmod": day["id"], "id": ref})

    _indice_normas(dias, plantilla)
    log(f"normas/: {len(fichas)} fichas ({escritas} escritas o actualizadas)")
    return fichas


def _indice_normas(dias: list[dict], plantilla: str) -> None:
    """normas/index.html. GitHub Pages no lista directorios: sin esta página la
    carpeta devuelve 404 y el enlace del pie apunta a la nada."""
    bloques = []
    for day in sorted(dias, key=lambda d: d["id"], reverse=True):
        filas = "".join(
            f'<li><a href="{esc_attr(ref_norma(x))}.html">{esc_html(x.get("headline",""))}</a>'
            f' <span class="ref">{esc_html(x.get("ref",""))}</span></li>'
            for x in ((day.get("boe", {}) or {}).get("stories") or []) if ref_norma(x))
        if filas:
            bloques.append(f'<h2 class="rotulo">{esc_html(fmt_date_es(day["id"]))}</h2>'
                           f'<ul class="indice">{filas}</ul>')
    cuerpo = "".join(bloques) or "<p>Todavía no hay fichas publicadas.</p>"
    url = f"{SITE_URL}normas/"
    frag = {
        "TITLE": "Todas las normas del BOE, una a una | La Tercera Cámara",
        "META_DESC": esc_attr("Índice de las disposiciones del BOE cubiertas por La Tercera Cámara: "
                              "una ficha por norma, con el dato clave y el enlace oficial."),
        "CANONICAL": url,
        "JSONLD": jsonld_script([{
            "@type": "CollectionPage", "name": "Fichas por norma", "url": url,
            "inLanguage": "es-ES",
            "isPartOf": {"@type": "WebSite", "name": "La Tercera Cámara",
                         "url": SITE_URL}}]),
        "EDITION_DATE": esc_html(fmt_date_es(dt.date.today().isoformat())),
        "MIGA": ('<a href="../">Portada</a> › <span aria-current="page">Normas</span>'),
        "KICKER": "Índice",
        "HEADLINE": "Una ficha por norma",
        "STANDFIRST": ("Cada disposición del BOE que hemos cubierto tiene su propia página, "
                       "con el dato duro por delante y el texto oficial a un clic."),
        "FICHA": "", "CUERPO": cuerpo, "FUENTE": "Fuente: Boletín Oficial del Estado.",
        "RELACIONADAS": "", "RELACIONADAS_HIDDEN": "hidden",
    }
    (NORMAS_DIR / "index.html").write_text(_replace_placeholders(plantilla, frag),
                                           encoding="utf-8")


MES_NUM = {m.lower(): i + 1 for i, m in enumerate(MESES)}
_NUM_PALABRA = {"un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
                "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11,
                "doce": 12, "quince": 15, "veinte": 20, "treinta": 30}


def fecha_es_a_iso(texto: str) -> str:
    """«7 de octubre de 2026» -> «2026-10-07». Devuelve "" si no es una fecha."""
    m = re.search(r"(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+de\s+(\d{4})", texto or "", re.I)
    if not m:
        return ""
    mes = MES_NUM.get(m.group(2).lower())
    if not mes:
        return ""
    try:
        return dt.date(int(m.group(3)), mes, int(m.group(1))).isoformat()
    except ValueError:
        return ""


def sumar_plazo(desde_iso: str, plazo: str) -> str:
    """«dos meses» desde la publicación -> fecha ISO. Cálculo de calendario, no
    de días hábiles: por eso en la página se marca como orientativo y se remite
    al texto oficial, que es el que manda."""
    if not (desde_iso and plazo):
        return ""
    m = re.match(r"(\w+)\s+(d[íi]as?|meses?|a[ñn]os?)", plazo.strip(), re.I)
    if not m:
        return ""
    bruto = m.group(1).lower()
    n = int(bruto) if bruto.isdigit() else _NUM_PALABRA.get(bruto, 0)
    if not n:
        return ""
    unidad = m.group(2).lower()
    try:
        d = dt.date.fromisoformat(desde_iso)
    except ValueError:
        return ""
    if unidad.startswith("d"):
        return (d + dt.timedelta(days=n)).isoformat()
    if unidad.startswith("a"):
        try:
            return d.replace(year=d.year + n).isoformat()
        except ValueError:
            return d.replace(year=d.year + n, day=28).isoformat()
    mes = d.month - 1 + n
    anio, mes = d.year + mes // 12, mes % 12 + 1
    import calendar
    return dt.date(anio, mes, min(d.day, calendar.monthrange(anio, mes)[1])).isoformat()


def recolectar_plazos(dias: list) -> list:
    """La agenda de vencimientos: todo lo que tiene fecha de caducidad y sigue
    abierto. Es la información más útil que da este sitio y la que nadie agrega:
    el BOE publica el plazo dentro de cada norma y nunca en una lista."""
    hoy = dt.date.today().isoformat()
    filas = []
    for day in dias:
        pub = fecha_boe_iso(day)
        for s_ in (day.get("boe", {}) or {}).get("stories") or []:
            d = s_.get("datos") or {}
            vence, clase, nota = "", "", ""
            if d.get("hasta"):
                vence, clase = fecha_es_a_iso(d["hasta"]), "Vigencia"
                nota = "Fecha que fija la propia norma."
            elif d.get("plazo") and d.get("plazo_publico"):
                vence = sumar_plazo(pub, d["plazo"])
                clase = "Plazo abierto"
                nota = f"{d['plazo']} desde la publicación ({fmt_date_es(pub)}). Cómputo orientativo."
            if not vence or vence < hoy:
                continue
            filas.append({"vence": vence, "clase": clase, "nota": nota,
                          "titular": s_.get("headline", ""), "ref": s_.get("ref", ""),
                          "url": (f"{SITE_URL}normas/{s_['ref']}.html"
                                  if ref_norma(s_) else f"{SITE_URL}ediciones/{day['id']}.html"),
                          "fuente": s_.get("url", ""), "origen": "BOE",
                          "dept": s_.get("dept", "")})
        for f in (day.get("cortes", {}) or {}).get("feed") or []:
            m = re.search(rf"hasta el (\d{{1,2}} de (?:{MESES_RE}) de \d{{4}})",
                          " ".join(f.get("body") or []), re.I)
            if not m:
                continue
            vence = fecha_es_a_iso(m.group(1))
            if not vence or vence < hoy:
                continue
            filas.append({"vence": vence, "clase": "Enmiendas", "nota": "Plazo fijado por la Mesa.",
                          "titular": f.get("headline", ""), "ref": f.get("source", {}).get("label", ""),
                          "url": f"{SITE_URL}ediciones/{day['id']}.html",
                          "fuente": f.get("source", {}).get("url", ""),
                          "origen": "Congreso", "dept": ""})
    vistos, unicas = set(), []
    for f in sorted(filas, key=lambda x: (x["vence"], x["titular"])):
        k = (f["vence"], f["ref"])
        if k not in vistos:
            vistos.add(k); unicas.append(f)
    return unicas


def _slug_txt(t: str) -> str:
    import unicodedata
    base = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")[:50] or "sin-nombre"


def _pagina_suelta(plantilla: str, carpeta: pathlib.Path, nombre: str, frag: dict) -> None:
    """Todas las páginas auxiliares comparten la plantilla de ficha: un diseño,
    un sitio donde tocarlo."""
    carpeta.mkdir(exist_ok=True)
    (carpeta / nombre).write_text(_replace_placeholders(plantilla, frag), encoding="utf-8")


def renderizar_plazos(dias: list) -> list:
    if not TEMPLATE_NORMA.exists():
        return []
    filas = recolectar_plazos(dias)
    hoy = dt.date.today()
    bloques, grupo_actual = [], None
    for f in filas[:300]:
        v = dt.date.fromisoformat(f["vence"])
        quedan = (v - hoy).days
        grupo = ("Esta semana" if quedan <= 7 else
                 "En dos semanas" if quedan <= 14 else
                 "Este mes" if quedan <= 31 else "Más adelante")
        if grupo != grupo_actual:
            if grupo_actual is not None:
                bloques.append("</ul>")
            bloques.append(f'<h2 class="rotulo">{esc_html(grupo)}</h2><ul class="indice">')
            grupo_actual = grupo
        cuenta = ("vence hoy" if quedan == 0 else
                  "vence mañana" if quedan == 1 else f"quedan {quedan} días")
        bloques.append(
            f'<li><a href="../{esc_attr(f["url"].replace(SITE_URL, ""))}">'
            f'{esc_html(f["titular"])}</a> '
            f'<span class="ref">{esc_html(f["clase"])} · {esc_html(fmt_date_es(f["vence"]))} '
            f'· {esc_html(cuenta)}</span>'
            + (f'<span class="nota">{esc_html(f["nota"])}</span>' if f.get("nota") else "")
            + '</li>')
    if grupo_actual is not None:
        bloques.append("</ul>")
    cuerpo = "".join(bloques) or "<p>Ahora mismo no hay ningún plazo abierto en las ediciones publicadas.</p>"
    url = f"{SITE_URL}plazos/"
    _pagina_suelta(TEMPLATE_NORMA.read_text(encoding="utf-8"), PLAZOS_DIR, "index.html", {
        "TITLE": "Plazos del BOE que vencen | La Tercera Cámara",
        "META_DESC": esc_attr("Todos los plazos abiertos publicados en el BOE y en el Congreso, "
                              "ordenados por fecha de vencimiento: alegaciones, convocatorias, "
                              "recursos y enmiendas."),
        "CANONICAL": url,
        "JSONLD": jsonld_script([{
            "@type": "CollectionPage", "name": "Plazos que vencen", "url": url,
            "inLanguage": "es-ES", "dateModified": hoy.isoformat(),
            "isPartOf": {"@type": "WebSite", "name": "La Tercera Cámara",
                         "url": SITE_URL}}]),
        "EDITION_DATE": esc_html(fmt_date_es(hoy.isoformat())),
        "MIGA": '<a href="../">Portada</a> › <span aria-current="page">Plazos</span>',
        "KICKER": "Agenda",
        "HEADLINE": "Plazos que vencen",
        "STANDFIRST": ("Lo que el BOE publica con fecha de caducidad —alegaciones, convocatorias, "
                       "recursos, vigencias— y lo que el Congreso abre a enmiendas, en una sola "
                       "lista y por orden de urgencia."),
        "FICHA": ("<dt>Plazos abiertos</dt><dd>" + str(len(filas)) + "</dd>"
                  "<dt>Actualizado</dt><dd>" + esc_html(fmt_date_es(hoy.isoformat())) + "</dd>"),
        "CUERPO": cuerpo,
        "FUENTE": ("Aviso: el cómputo marcado como orientativo es de días naturales sobre la fecha "
                   "de publicación. El plazo que vale es el del texto oficial enlazado en cada "
                   "ficha, que puede contar días hábiles o arrancar en otra fecha."),
        "RELACIONADAS": "", "RELACIONADAS_HIDDEN": "hidden",
    })
    log(f"plazos/: {len(filas)} plazos abiertos")
    return [{"url": url, "lastmod": hoy.isoformat()}]


def renderizar_temas(dias: list) -> list:
    """Una página por materia. Es la sección que la gente busca («subvenciones
    BOE», «plazos laborales») y el cimiento de las alertas: cuando haya correo,
    suscribirse será elegir estas mismas materias."""
    if not TEMPLATE_NORMA.exists():
        return []
    plantilla = TEMPLATE_NORMA.read_text(encoding="utf-8")
    hoy = dt.date.today().isoformat()
    por_materia: dict = {}
    for day in sorted(dias, key=lambda d: d["id"], reverse=True):
        for s_ in (day.get("boe", {}) or {}).get("stories") or []:
            for slug in materias_de(titulo_oficial_de(s_), s_.get("headline", "")):
                por_materia.setdefault(slug, []).append((day, s_))

    salidas = []
    for slug, etiqueta, _ in MATERIAS:
        piezas = por_materia.get(slug, [])
        if not piezas:
            continue
        filas = "".join(
            f'<li><a href="{esc_attr("../normas/" + ref_norma(x) + ".html") if ref_norma(x) else esc_attr("../ediciones/" + d["id"] + ".html")}">'
            f'{esc_html(x.get("headline",""))}</a>'
            f'<span class="ref">{esc_html(fmt_date_es(d["id"]))}'
            + (f' · {esc_html(recortar(x.get("dept",""), 60))}' if x.get("dept") else "")
            + '</span></li>' for d, x in piezas[:150])
        otras = "".join(
            f'<a class="srclink" href="{o}.html">{esc_html(MATERIA_LABEL[o])}</a> '
            for o, _e, _k in MATERIAS if o != slug and por_materia.get(o))
        url = f"{SITE_URL}temas/{slug}.html"
        _pagina_suelta(plantilla, TEMAS_DIR, f"{slug}.html", {
            "TITLE": f"{etiqueta} en el BOE | La Tercera Cámara",
            "META_DESC": esc_attr(f"Todo lo que el BOE publica sobre {etiqueta.lower()}, "
                                  f"día a día, con el dato clave por delante y enlace al "
                                  f"texto oficial. {len(piezas)} disposiciones recogidas."),
            "CANONICAL": url,
            "JSONLD": jsonld_script([
                {"@type": "CollectionPage", "name": f"{etiqueta} en el BOE", "url": url,
                 "inLanguage": "es-ES", "dateModified": hoy,
                 "isPartOf": {"@type": "WebSite", "name": "La Tercera Cámara",
                              "url": SITE_URL}},
                {"@type": "BreadcrumbList", "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Portada", "item": SITE_URL},
                    {"@type": "ListItem", "position": 2, "name": "Materias",
                     "item": f"{SITE_URL}temas/"},
                    {"@type": "ListItem", "position": 3, "name": etiqueta, "item": url}]}]),
            "EDITION_DATE": esc_html(fmt_date_es(hoy)),
            "MIGA": (f'<a href="../">Portada</a> › <a href="./">Materias</a> › '
                     f'<span aria-current="page">{esc_html(etiqueta)}</span>'),
            "KICKER": "Materia",
            "HEADLINE": etiqueta,
            "STANDFIRST": (f"Todo lo que hemos recogido del BOE en esta materia, de lo más "
                           f"reciente a lo más antiguo."),
            "FICHA": f"<dt>Disposiciones</dt><dd>{len(piezas)}</dd>",
            "CUERPO": f'<ul class="indice">{filas}</ul>',
            "FUENTE": "Fuente: Boletín Oficial del Estado.",
            "RELACIONADAS": f'<li>{otras}</li>' if otras else "",
            "RELACIONADAS_HIDDEN": "" if otras else "hidden",
        })
        salidas.append({"url": url, "lastmod": hoy, "slug": slug,
                        "etiqueta": etiqueta, "n": len(piezas)})

    if salidas:
        indice = "".join(
            f'<li><a href="{esc_attr(x["slug"])}.html">{esc_html(x["etiqueta"])}</a>'
            f'<span class="ref">{x["n"]} disposici{"ón" if x["n"] == 1 else "ones"}</span></li>'
            for x in sorted(salidas, key=lambda x: -x["n"]))
        url = f"{SITE_URL}temas/"
        _pagina_suelta(plantilla, TEMAS_DIR, "index.html", {
            "TITLE": "El BOE por materias | La Tercera Cámara",
            "META_DESC": esc_attr("El BOE ordenado por materias: subvenciones, fiscal, laboral, "
                                  "seguridad social, contratación pública y once materias más."),
            "CANONICAL": url,
            "JSONLD": jsonld_script([{"@type": "CollectionPage", "name": "Materias", "url": url,
                                      "inLanguage": "es-ES", "dateModified": hoy}]),
            "EDITION_DATE": esc_html(fmt_date_es(hoy)),
            "MIGA": '<a href="../">Portada</a> › <span aria-current="page">Materias</span>',
            "KICKER": "Índice",
            "HEADLINE": "El BOE por materias",
            "STANDFIRST": ("Cada materia tiene su propia página con todo lo publicado en ella. "
                           "Una norma puede estar en varias: una subvención a la contratación "
                           "es subvención y es laboral."),
            "FICHA": f"<dt>Materias con contenido</dt><dd>{len(salidas)}</dd>",
            "CUERPO": f'<ul class="indice">{indice}</ul>',
            "FUENTE": "Fuente: Boletín Oficial del Estado.",
            "RELACIONADAS": "", "RELACIONADAS_HIDDEN": "hidden",
        })
        salidas.append({"url": url, "lastmod": hoy})
    log(f"temas/: {len(salidas)} páginas de materia")
    return salidas


ESTADO_CONGRESO = ESTADO / "congreso.json"


def _pct(n, total):
    return f"{round(100 * n / total)} %" if total else "—"


def cosechar_congreso() -> list:
    """Censo, intervenciones y votaciones del Congreso, acumuladas en state/.

    Se hace aquí y no en construir_dia porque no es información de una edición:
    es una serie que crece. Si el portal falla un día, se sigue con lo que ya
    había en vez de publicar fichas vacías."""
    try:
        import congreso_datos as cd
    except Exception as exc:                                  # noqa: BLE001
        log(f"Congreso: módulo de datos no disponible ({exc})")
        return []

    estado = {}
    if ESTADO_CONGRESO.exists():
        try:
            estado = json.loads(ESTADO_CONGRESO.read_text(encoding="utf-8"))
        except Exception as exc:                              # noqa: BLE001
            log(f"  estado de Congreso ilegible, se empieza de cero: {exc}")

    # Los nombres pasaron a indexarse normalizados; el acumulado anterior está
    # en el formato viejo y no se puede mezclar. Se descarta y se reconstruye:
    # las votaciones se vuelven a cosechar solas.
    ESQUEMA = 4
    if estado.get("esquema") != ESQUEMA:
        if estado:
            log("  formato de estado antiguo: se reinicia el acumulado de votaciones")
        estado = {"esquema": ESQUEMA}

    log("Congreso: datos abiertos de diputados, intervenciones y votaciones")
    censo = cd.censo(get, log) or estado.get("censo") or {}
    if censo:
        estado["censo"] = censo
    try:
        estado = cd.acumular(estado, cd.votaciones_publicadas(get, log), log)
    except Exception as exc:                                  # noqa: BLE001
        log(f"  no se pudieron acumular votaciones: {exc}")
    # Y un trozo del histórico en cada ejecución, hasta completar la legislatura.
    try:
        estado = cd.acumular(estado, cd.cosechar_historico(get, log, estado), log)
    except Exception as exc:                                  # noqa: BLE001
        log(f"  no se pudo cosechar el histórico: {exc}")

    # Las intervenciones son un volcado de decenas de megas: no se guarda
    # entero, solo el resumen por persona que cabe en el repositorio.
    intervs = {}
    try:
        intervs = cd.intervenciones(get, log)
        if intervs:
            estado["intervenciones"] = intervs
    except Exception as exc:                                  # noqa: BLE001
        log(f"  no se pudieron leer las intervenciones: {exc}")
    if not intervs:
        intervs = estado.get("intervenciones") or {}

    ESTADO.mkdir(exist_ok=True)
    ESTADO_CONGRESO.write_text(json.dumps(estado, ensure_ascii=False), encoding="utf-8")
    return cd.fusionar(censo, estado, intervs)


def _barra(n, total, etiqueta):
    """Una barra de porcentaje, con el dato crudo al lado. El porcentaje solo
    engaña si se esconde de qué sobre qué."""
    if not total:
        return ""
    # Redondear 429 de 430 a «100 %» es mentir en el último dígito: si falta
    # aunque sea uno, no está al 100.
    pct = round(100 * n / total)
    if pct == 100 and n < total:
        pct = 99
    if pct == 0 and n:
        pct = 1
    return (f'<div class="metrica"><div class="metrica-cab"><span>{esc_html(etiqueta)}</span>'
            f'<b>{pct} %</b></div>'
            f'<div class="barra"><i style="width:{pct}%"></i></div>'
            f'<div class="metrica-pie">{n} de {total}</div></div>')


def _tarjeta_diputado(f, prefijo=""):
    sigla = f.get("sigla") or f.get("partido") or ""
    return (f'<li class="dip"><a href="{prefijo}{esc_attr(f["slug"])}.html">'
            f'<span class="dip-nombre">{esc_html(f["natural"])}</span>'
            f'<span class="dip-meta">{esc_html(sigla)} · {esc_html(f["circunscripcion"])}</span>'
            f'<span class="dip-cifras">{f["intervenciones"]} intervenciones'
            + (f' · {f["votaciones"]} votaciones' if f["votaciones"] else "")
            + '</span></a></li>')


def _pagina_listado(plantilla, carpeta, nombre, titulo, h1, entradilla, fichas,
                    url, miga, kicker, ficha_extra="", cuerpo_extra=""):
    filas = "".join(_tarjeta_diputado(f, "../") for f in fichas)
    hoy = dt.date.today().isoformat()
    _pagina_suelta(plantilla, carpeta, nombre, {
        "TITLE": esc_html(titulo),
        "META_DESC": esc_attr(entradilla[:155]),
        "CANONICAL": url,
        "JSONLD": jsonld_script([{"@type": "CollectionPage", "name": h1, "url": url,
                                  "inLanguage": "es-ES", "dateModified": hoy}]),
        "EDITION_DATE": esc_html(fmt_date_es(hoy)),
        "MIGA": miga,
        "KICKER": esc_html(kicker),
        "HEADLINE": esc_html(h1),
        "STANDFIRST": esc_html(entradilla),
        "FICHA": ficha_extra or f"<dt>Diputados</dt><dd>{len(fichas)}</dd>",
        "CUERPO": cuerpo_extra + f'<ul class="rejilla-dip">{filas}</ul>',
        "FUENTE": "Fuente: datos abiertos del Congreso de los Diputados.",
        "RELACIONADAS": "", "RELACIONADAS_HIDDEN": "hidden",
    })
    return {"url": url, "lastmod": hoy}


def _datos_parlamento(orden: list, cd) -> None:
    """El JSON que consume la capa interactiva.

    Va aparte y no incrustado en el HTML por dos razones: la página sigue
    pesando lo mismo para quien solo quiere leerla, y el fichero se cachea
    entre visitas. Solo lleva lo que la interfaz necesita enseñar; la ficha
    completa sigue estando en su propia página."""
    ultima = ""
    for f in orden:
        for i in f.get("ultimas_intervenciones") or []:
            fecha = _fecha_int(i.get("fecha", ""))
            if fecha > ultima:
                ultima = fecha

    salida = []
    for f in orden:
        intervenciones = f.get("ultimas_intervenciones") or []
        reciente = next(iter(intervenciones), {})
        salida.append({
            "s": f["slug"],
            "n": f["natural"],
            "g": cd.GRUPO_CORTO.get(f.get("grupo", ""), f.get("partido", "")),
            "gs": cd.GRUPO_SLUG.get(f.get("grupo", ""), ""),
            "c": f.get("circunscripcion", ""),
            "p": f.get("partido", ""),
            "iv": f.get("intervenciones", 0),
            "vt": f.get("votaciones", 0),
            "si": f.get("si", 0), "no": f.get("no", 0),
            "ab": f.get("abstencion", 0), "ds": f.get("disidencias", 0),
            "sa": f.get("sesiones_asistidas", 0), "st": f.get("sesiones_totales", 0),
            # ¿Intervino en la última sesión de la que tenemos constancia?
            "ult": bool(reciente and _fecha_int(reciente.get("fecha", "")) == ultima),
            "ua": " ".join((reciente.get("asunto") or "").split())[:110],
            "uf": reciente.get("fecha", ""),
        })
    DATOS_DIR.mkdir(exist_ok=True)
    (DATOS_DIR / "parlamento.json").write_text(json.dumps({
        "actualizado": dt.date.today().isoformat(),
        "ultimaSesion": ultima,
        "grupos": [{"n": corto, "s": slug, "c": color}
                   for _l, corto, slug, color in cd.GRUPOS],
        "diputados": salida,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"datos/parlamento.json: {len(salida)} diputados")


def _fecha_int(f: str) -> str:
    """«17/09/2026» -> «20260917», para comparar sin parsear."""
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", f or "")
    return f"{m.group(3)}{m.group(2)}{m.group(1)}" if m else ""


def renderizar_diputados(fichas: list) -> list:
    """La sección de parlamentarios: hemiciclo, filtros y una ficha por persona.

    Los filtros son páginas de verdad —una por grupo y una por provincia— y no
    un desplegable de JavaScript. Cuesta lo mismo generarlas y la diferencia es
    que existen: se pueden enlazar, compartir e indexar. Un buscador ve sesenta
    listados en vez de una página con un menú que no sabe abrir."""
    if not (fichas and TEMPLATE_NORMA.exists()):
        return []
    try:
        import congreso_datos as cd
    except Exception:                                          # noqa: BLE001
        return []
    plantilla = TEMPLATE_NORMA.read_text(encoding="utf-8")
    hoy = dt.date.today().isoformat()
    salidas = []

    # --- ficha individual -------------------------------------------------
    for f in fichas:
        url = f"{SITE_URL}diputados/{f['slug']}.html"
        organos = "".join(
            f"<dt>{esc_html(o)}</dt><dd>{n}</dd>"
            for o, n in sorted(f["organos"].items(), key=lambda x: -x[1])[:5])
        ficha = (
            f'<dt>Grupo</dt><dd>{esc_html(f["grupo"] or "—")}</dd>'
            f'<dt>Partido</dt><dd>{esc_html(f["partido"] or "—")}</dd>'
            f'<dt>Circunscripción</dt><dd>{esc_html(f["circunscripcion"] or "—")}</dd>'
            f'<dt>Escaño desde</dt><dd>{esc_html(f["alta"] or "—")}</dd>'
            f'<dt>Intervenciones</dt><dd>{f["intervenciones"]}</dd>' + organos)

        metricas = []
        if f.get("sesiones_totales"):
            metricas.append(_barra(f.get("sesiones_asistidas", 0),
                                   f["sesiones_totales"], "Asistencia a sesiones"))
        if f["votaciones"]:
            metricas.append(_barra(f["emitidos"], f["votaciones"], "Votos emitidos"))
            metricas.append(_barra(f["si"], f["votaciones"], "A favor"))
            metricas.append(_barra(f["no"], f["votaciones"], "En contra"))
            if f["disidencias"]:
                metricas.append(_barra(f["disidencias"], f["votaciones"],
                                       "Votos distintos a su grupo"))

        cuerpo = []
        if metricas:
            cuerpo.append('<h2 class="rotulo">Su actividad en cifras</h2>'
                          '<div class="metricas">' + "".join(metricas) + "</div>")
        if f["ultimas_intervenciones"]:
            cuerpo.append('<h2 class="rotulo">Últimas intervenciones</h2><ul class="indice">')
            for i in f["ultimas_intervenciones"]:
                enlace = (f'<a href="{esc_attr(i["video"])}" rel="nofollow noopener" '
                          f'target="_blank">{esc_html(i["asunto"] or "Intervención")}</a>'
                          if i.get("video") else esc_html(i["asunto"] or "Intervención"))
                cuerpo.append(f'<li>{enlace}<span class="ref">'
                              f'{esc_html(i["fecha"])} · {esc_html(i["organo"])}'
                              + (f' · {esc_html(i["fase"])}' if i.get("fase") else "")
                              + '</span></li>')
            cuerpo.append("</ul>")
        if f["ultimos_votos"]:
            cuerpo.append('<h2 class="rotulo">Últimos votos</h2><ul class="indice">')
            etiqueta = {"si": "A favor", "no": "En contra",
                        "abstencion": "Abstención", "no_vota": "No votó"}
            for v in f["ultimos_votos"]:
                coda = "" if v.get("con_su_grupo", True) else " · distinto a su grupo"
                cuerpo.append(f'<li>{esc_html(v["asunto"])}<span class="ref">'
                              f'{esc_html(v["fecha"])} · {etiqueta.get(v["voto"], v["voto"])}'
                              f'{coda}</span></li>')
            cuerpo.append("</ul>")
        if not cuerpo:
            cuerpo = ["<p>Todavía no hay actividad registrada de este diputado en las "
                      "series que publicamos.</p>"]

        gslug = cd.GRUPO_SLUG.get(f["grupo"], "")
        rel = []
        if gslug:
            rel.append(f'<a class="srclink" href="grupo-{esc_attr(gslug)}.html">'
                       f'Todo el grupo {esc_html(cd.GRUPO_CORTO.get(f["grupo"], ""))}</a>')
        if f["circunscripcion"]:
            rel.append(f'<a class="srclink" href="provincia-{esc_attr(_slug_txt(f["circunscripcion"]))}.html">'
                       f'Diputados por {esc_html(f["circunscripcion"])}</a>')

        _pagina_suelta(plantilla, DIPUTADOS_DIR, f"{f['slug']}.html", {
            "TITLE": esc_html(f"{f['natural']} — cómo vota y qué hace | La Tercera Cámara"),
            "META_DESC": esc_attr(
                f"{f['natural']} ({f['sigla'] or f['partido']}, {f['circunscripcion']}): "
                f"{f['intervenciones']} intervenciones y {f['votaciones']} votaciones "
                f"registradas, con enlace a la fuente oficial."),
            "CANONICAL": url,
            "JSONLD": jsonld_script([
                {"@type": "ProfilePage", "url": url, "inLanguage": "es-ES",
                 "dateModified": hoy,
                 "mainEntity": {"@type": "Person", "name": f["natural"],
                                "jobTitle": "Diputado del Congreso de los Diputados",
                                "affiliation": {"@type": "Organization",
                                                "name": f["grupo"] or f["partido"]},
                                "workLocation": f["circunscripcion"]}},
                {"@type": "BreadcrumbList", "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Portada", "item": SITE_URL},
                    {"@type": "ListItem", "position": 2, "name": "Parlamentarios",
                     "item": f"{SITE_URL}diputados/"},
                    {"@type": "ListItem", "position": 3, "name": f["natural"], "item": url}]}]),
            "EDITION_DATE": esc_html(fmt_date_es(hoy)),
            "MIGA": (f'<a href="../">Portada</a> › <a href="./">Parlamentarios</a> › '
                     f'<span aria-current="page">{esc_html(f["natural"])}</span>'),
            "KICKER": esc_html(cd.GRUPO_CORTO.get(f["grupo"], f["partido"] or "Congreso")),
            "HEADLINE": esc_html(f["natural"]),
            "STANDFIRST": esc_html(
                f"Diputado por {f['circunscripcion']}. Todo lo que consta de su actividad "
                f"en las publicaciones oficiales del Congreso."),
            "FICHA": ficha,
            "CUERPO": "".join(cuerpo),
            "FUENTE": ("Fuente: datos abiertos del Congreso de los Diputados. Recuentos de "
                       "actos públicos; ninguna cifra es una valoración."),
            "RELACIONADAS": ("<li>" + " ".join(rel) + "</li>") if rel else "",
            "RELACIONADAS_HIDDEN": "" if rel else "hidden",
        })
        salidas.append({"url": url, "lastmod": hoy})

    # --- una página por grupo --------------------------------------------
    por_grupo = {}
    for f in fichas:
        por_grupo.setdefault(f["grupo"] or "Sin grupo", []).append(f)
    for largo, corto, slug, _color in cd.GRUPOS:
        gente = por_grupo.get(largo)
        if not gente:
            continue
        url = f"{SITE_URL}diputados/grupo-{slug}.html"
        salidas.append(_pagina_listado(
            plantilla, DIPUTADOS_DIR, f"grupo-{slug}.html",
            f"Diputados de {corto} — actividad y votos | La Tercera Cámara",
            f"Diputados de {corto}",
            f"Los {len(gente)} diputados del {largo}, con sus intervenciones y sus votos.",
            gente, url,
            f'<a href="../">Portada</a> › <a href="./">Parlamentarios</a> › '
            f'<span aria-current="page">{esc_html(corto)}</span>',
            "Grupo parlamentario",
            f"<dt>Diputados</dt><dd>{len(gente)}</dd><dt>Grupo</dt><dd>{esc_html(largo)}</dd>"))

    # --- una página por provincia ----------------------------------------
    por_prov = {}
    for f in fichas:
        if f["circunscripcion"]:
            por_prov.setdefault(f["circunscripcion"], []).append(f)
    for prov, gente in sorted(por_prov.items()):
        ps = _slug_txt(prov)
        url = f"{SITE_URL}diputados/provincia-{ps}.html"
        salidas.append(_pagina_listado(
            plantilla, DIPUTADOS_DIR, f"provincia-{ps}.html",
            f"Diputados por {prov} — quiénes son y cómo votan | La Tercera Cámara",
            f"Diputados por {prov}",
            f"Los {len(gente)} diputados que representan a {prov} en el Congreso, "
            f"con su actividad y sus votos.",
            gente, url,
            f'<a href="../">Portada</a> › <a href="./">Parlamentarios</a> › '
            f'<span aria-current="page">{esc_html(prov)}</span>',
            "Circunscripción",
            f"<dt>Diputados</dt><dd>{len(gente)}</dd>"
            f"<dt>Circunscripción</dt><dd>{esc_html(prov)}</dd>"))

    # --- índice con hemiciclo --------------------------------------------
    conteo = {g: len(v) for g, v in por_grupo.items()}
    orden = cd.orden_hemiciclo(fichas)
    hemi = cd.hemiciclo_svg(orden)
    _datos_parlamento(orden, cd)
    leyenda = "".join(
        f'<li><a href="grupo-{slug}.html"><i style="background:{color}"></i>'
        f'<span>{esc_html(corto)}</span><b>{conteo.get(largo, 0)}</b></a></li>'
        for largo, corto, slug, color in cd.GRUPOS if conteo.get(largo))
    provincias = "".join(
        f'<li><a href="provincia-{_slug_txt(p)}.html">{esc_html(p)}'
        f'<span class="ref">{len(v)}</span></a></li>'
        for p, v in sorted(por_prov.items()))
    activos = sorted(fichas, key=lambda f: -f["intervenciones"])[:15]

    # El SVG y la leyenda ya van servidos; el <div> de la app y el script solo
    # añaden la capa interactiva encima. Si el script no carga, lo de debajo
    # sigue siendo una página completa.
    cuerpo = (
        f'<div class="hemi-caja">{hemi}<ul class="leyenda-grupos">{leyenda}</ul></div>'
        f'<div id="hemiciclo-app" data-src="../datos/parlamento.json"></div>'
        f'<p class="hemi-nota">Pasa el ratón por cualquier escaño para ver quién lo ocupa. '
        f'Dentro de cada grupo el orden es alfabético: el Congreso no publica el plano '
        f'de asientos, así que ninguna silla del dibujo es la de nadie en concreto.</p>'
        f'<h2 class="rotulo">Los que más intervienen</h2>'
        f'<ul class="rejilla-dip">{"".join(_tarjeta_diputado(f) for f in activos)}</ul>'
        f'<h2 class="rotulo">Por circunscripción</h2>'
        f'<ul class="provincias">{provincias}</ul>'
        f'<script src="../assets/parlamento.js" defer></script>')
    url = f"{SITE_URL}diputados/"
    _pagina_suelta(plantilla, DIPUTADOS_DIR, "index.html", {
        "TITLE": "Así vota y así trabaja cada diputado | La Tercera Cámara",
        "META_DESC": esc_attr("Los 350 diputados del Congreso, uno a uno: intervenciones, "
                              "votaciones, asistencia y votos distintos a los de su grupo, "
                              "con enlace a la publicación oficial."),
        "CANONICAL": url,
        "JSONLD": jsonld_script([{"@type": "CollectionPage", "name": "Parlamentarios",
                                  "url": url, "inLanguage": "es-ES", "dateModified": hoy}]),
        "EDITION_DATE": esc_html(fmt_date_es(hoy)),
        "MIGA": '<a href="../">Portada</a> › <span aria-current="page">Parlamentarios</span>',
        "KICKER": "Seguimiento",
        "HEADLINE": "Así vota y así trabaja cada diputado",
        "STANDFIRST": ("Cuántas veces interviene, cómo vota, a cuántas sesiones asiste y "
                       "cuántas veces se aparta de su grupo. Recuentos sobre las "
                       "publicaciones oficiales del Congreso, sin adjetivos."),
        "FICHA": f"<dt>Diputados con ficha</dt><dd>{len(fichas)}</dd>"
                 f"<dt>Grupos</dt><dd>{len(conteo)}</dd>"
                 f"<dt>Circunscripciones</dt><dd>{len(por_prov)}</dd>"
                 f"<dt>Actualizado</dt><dd>{esc_html(fmt_date_es(hoy))}</dd>",
        "CUERPO": cuerpo,
        "FUENTE": ("Fuente: datos abiertos del Congreso de los Diputados. Las cifras de "
                   "votación se acumulan desde que empezamos a registrarlas; las de "
                   "intervenciones cubren toda la legislatura."),
        "RELACIONADAS": "", "RELACIONADAS_HIDDEN": "hidden",
    })
    salidas.append({"url": url, "lastmod": hoy})
    log(f"diputados/: {len(fichas)} fichas, {len(conteo)} grupos, {len(por_prov)} provincias")
    return salidas


def _entrada_indice(titulo, sub, url, clase, fecha="", extra=""):
    """Una fila del índice del buscador. Campos de una letra porque esto viaja
    por la red entero: con quinientas normas, cada nombre de campo largo son
    kilobytes que el lector paga sin ver nada a cambio."""
    def cortar(t, n):
        t = " ".join((t or "").split())
        if len(t) <= n:
            return t
        corte = t[:n].rsplit(" ", 1)[0]
        return (corte or t[:n]).rstrip(" ,;:") + "…"
    return {"t": cortar(titulo, 140), "s": cortar(sub, 120),
            "u": url, "k": clase, "d": fecha, "x": " ".join((extra or "").split())[:90]}


def renderizar_buscador(dias: list, fichas_dip: list) -> list:
    """El metabuscador: una sola caja que busca a la vez en las normas del BOE,
    en los diputados, en las materias, en los plazos y en las ediciones.

    Hasta ahora, para encontrar algo había que saber de antemano en qué sección
    estaba. El índice se genera aquí, en el build, y se resuelve en el navegador:
    no hay servidor que mantener ni consulta que se caiga, y funciona igual de
    rápido con quinientas fichas que con cinco mil."""
    if not TEMPLATE_NORMA.exists():
        return []
    hoy = dt.date.today().isoformat()
    idx: list = []

    # Normas del BOE: lo que más gente busca y con el nombre más raro.
    for day in sorted(dias, key=lambda d: d["id"], reverse=True):
        for s in (day.get("boe", {}) or {}).get("stories") or []:
            ref = ref_norma(s)
            oficial = titulo_oficial_de(s)
            if ref:
                idx.append(_entrada_indice(
                    s.get("headline", ""), primera_mayuscula(oficial),
                    f"normas/{ref}.html", "norma", day["id"],
                    s.get("ref", "") + " " + (s.get("dept") or "")))
            else:
                idx.append(_entrada_indice(
                    s.get("headline", ""), primera_mayuscula(oficial),
                    f"ediciones/{day['id']}.html", "norma", day["id"],
                    s.get("dept") or ""))
        # Las Cortes no van en «stories» sino en «feed», con otra forma: aquí
        # el subtítulo útil es el standfirst, que ya resume la sesión.
        for it in (day.get("cortes", {}) or {}).get("feed") or []:
            fuente = (it.get("source") or {}).get("label") or ""
            idx.append(_entrada_indice(
                it.get("headline", ""), it.get("standfirst", ""),
                f"ediciones/{day['id']}.html", "cortes", day["id"],
                f'{it.get("chamber", "")} {it.get("type", "")} {fuente}'))

    # Diputados: el nombre propio es la consulta más natural que existe.
    for f in fichas_dip or []:
        sigla = f.get("sigla") or f.get("partido") or ""
        idx.append(_entrada_indice(
            f.get("natural", ""),
            f'{sigla} · {f.get("circunscripcion", "")}',
            f'diputados/{f.get("slug", "")}.html', "diputado", "",
            f'{f.get("partido", "")} {f.get("grupo", "")}'))

    # Materias y ediciones, para que la caja cubra también la navegación.
    for slug, etiqueta, claves in MATERIAS:
        idx.append(_entrada_indice(etiqueta, "Materia del BOE",
                                   f"temas/{slug}.html", "tema", "",
                                   " ".join(claves) if isinstance(claves, (list, tuple)) else str(claves)))
    for day in sorted(dias, key=lambda d: d["id"], reverse=True):
        idx.append(_entrada_indice(f'Edición del {fmt_date_es(day["id"])}',
                                   "Todo lo publicado ese día",
                                   f'ediciones/{day["id"]}.html', "edicion", day["id"]))

    # Deduplicar por URL+titular: una norma citada dos días no es dos resultados.
    vistos, limpio = set(), []
    for e in idx:
        clave = (e["u"], e["t"])
        if clave in vistos:
            continue
        vistos.add(clave)
        limpio.append(e)

    DATOS_DIR.mkdir(exist_ok=True)
    (DATOS_DIR / "indice.json").write_text(json.dumps(
        {"actualizado": hoy, "n": len(limpio), "items": limpio},
        ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # La página. Sin JavaScript sigue siendo útil: lleva los enlaces a las
    # secciones y un formulario que delega en el buscador de Google acotado
    # al sitio. Con JavaScript, la caja resuelve en local y sin salir de aquí.
    por_clase: dict = {}
    for e in limpio:
        por_clase[e["k"]] = por_clase.get(e["k"], 0) + 1
    resumen = "".join(
        f'<dt>{esc_html(ETIQUETA_CLASE.get(k, k))}</dt><dd>{v}</dd>'
        for k, v in sorted(por_clase.items(), key=lambda kv: -kv[1]))
    recientes = "".join(
        f'<li><a href="../{esc_attr(e["u"])}">{esc_html(e["t"])}</a>'
        f'<span class="ref">{esc_html(ETIQUETA_CLASE.get(e["k"], e["k"]))}'
        + (f' · {esc_html(fmt_date_es(e["d"]))}' if e["d"] else "") + '</span></li>'
        for e in limpio[:40])
    url = f"{SITE_URL}buscar/"
    cuerpo = (
        '<div id="buscador-app" data-src="../datos/indice.json"></div>'
        '<noscript><form class="buscador-fallback" action="https://www.google.com/search" '
        'method="get" target="_blank" rel="noopener">'
        '<input type="hidden" name="q" value="site:terceracamara.es">'
        '<label for="qg">Buscar en el sitio</label> '
        '<input id="qg" type="search" name="q" placeholder="Orden INT, subvenciones, Gamarra…">'
        '<button type="submit">Buscar</button></form></noscript>'
        f'<h2 class="rotulo">Lo más reciente</h2><ul class="indice">{recientes}</ul>'
        '<script src="../assets/buscar.js" defer></script>')
    _pagina_suelta(TEMPLATE_NORMA.read_text(encoding="utf-8"), BUSCAR_DIR, "index.html", {
        "TITLE": "Buscador: normas del BOE, diputados, materias y plazos | La Tercera Cámara",
        "META_DESC": esc_attr("Busca de una vez en las normas del BOE, en los 350 diputados, "
                              "en las materias y en los plazos abiertos. Sin registro."),
        "CANONICAL": url,
        "JSONLD": jsonld_script([
            {"@type": "WebSite", "name": "La Tercera Cámara", "url": SITE_URL,
             "potentialAction": {"@type": "SearchAction",
                                 "target": {"@type": "EntryPoint",
                                            "urlTemplate": f"{url}?q={{search_term_string}}"},
                                 "query-input": "required name=search_term_string"}},
            {"@type": "CollectionPage", "name": "Buscador", "url": url,
             "inLanguage": "es-ES", "dateModified": hoy},
            {"@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Portada", "item": SITE_URL},
                {"@type": "ListItem", "position": 2, "name": "Buscador", "item": url}]}]),
        "EDITION_DATE": esc_html(fmt_date_es(hoy)),
        "MIGA": '<a href="../">Portada</a> › <span aria-current="page">Buscador</span>',
        "KICKER": "Buscador",
        "HEADLINE": "Todo el sitio en una sola caja",
        "STANDFIRST": ("Normas del BOE, actividad de las Cortes, los 350 diputados, las materias "
                       "y los plazos abiertos. Se busca en el navegador: ni se registra la "
                       "consulta ni sale de tu ordenador."),
        "FICHA": resumen,
        "CUERPO": cuerpo,
        "FUENTE": "Fuentes: Boletín Oficial del Estado y datos abiertos del Congreso.",
        "RELACIONADAS": "", "RELACIONADAS_HIDDEN": "hidden",
    })
    log(f"buscar/: índice con {len(limpio)} entradas")
    return [{"url": url, "lastmod": hoy}]


ETIQUETA_CLASE = {"norma": "Norma del BOE", "cortes": "Cortes", "diputado": "Diputado",
                  "tema": "Materia", "plazo": "Plazo", "edicion": "Edición"}


def renderizar_sitemap(entradas: list[dict], fichas: list[dict] | None = None) -> None:
    """Todas las ediciones, no solo la ventana de render, y con la fecha de
    modificación real de cada una."""
    hoy = dt.date.today().isoformat()
    urls = [f"  <url>\n    <loc>{SITE_URL}</loc>\n    <lastmod>{hoy}</lastmod>\n"
            "    <changefreq>daily</changefreq>\n    <priority>1.0</priority>\n  </url>",
            f"  <url>\n    <loc>{SITE_URL}ediciones/</loc>\n    <lastmod>{hoy}</lastmod>\n"
            "    <changefreq>daily</changefreq>\n    <priority>0.8</priority>\n  </url>"]
    limite = (dt.date.today() - dt.timedelta(days=MAX_DAYS)).isoformat()
    for e in sorted(entradas, key=lambda x: x["id"], reverse=True):
        # Dentro de la ventana todavía puede cambiar (curated/, senado_local.py);
        # fuera de ella ya está cerrada, pero nunca "never": se corrigen erratas.
        freq = "weekly" if e["id"] >= limite else "monthly"
        urls.append(f"  <url>\n    <loc>{e['url']}</loc>\n    <lastmod>{e['lastmod']}</lastmod>\n"
                    f"    <changefreq>{freq}</changefreq>\n    <priority>0.7</priority>\n  </url>")
    if fichas:
        urls.append(f"  <url>\n    <loc>{SITE_URL}normas/</loc>\n    <lastmod>{hoy}</lastmod>\n"
                    "    <changefreq>daily</changefreq>\n    <priority>0.8</priority>\n  </url>")
    for f in sorted(fichas or [], key=lambda x: x["lastmod"], reverse=True):
        # Una ficha por norma no cambia nunca una vez publicada: el BOE no
        # reescribe lo publicado, lo corrige con otra disposición.
        urls.append(f"  <url>\n    <loc>{f['url']}</loc>\n    <lastmod>{f['lastmod']}</lastmod>\n"
                    f"    <changefreq>monthly</changefreq>\n    <priority>0.6</priority>\n  </url>")
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls) + "\n</urlset>\n", encoding="utf-8")
    log(f"sitemap.xml generado con {len(urls)} URLs")


def renderizar_feed(dias: list[dict]) -> None:
    """RSS 2.0: descubrible por agregadores, lectores de feeds y bastantes
    pipelines de ingesta de IA que sí saben seguir un <link rel=alternate>."""
    from email.utils import format_datetime
    from xml.sax.saxutils import escape as xml_esc

    items = []
    for day in dias[:MAX_FEED_ITEMS]:
        link = f"{SITE_URL}ediciones/{day['id']}.html"
        pub_dt = dt.datetime.combine(dt.date.fromisoformat(day["id"]), dt.time(7, 0),
                                      tzinfo=dt.timezone.utc)
        items.append(
            "  <item>\n"
            f"    <title>{xml_esc(build_title(day, edicion=True))}</title>\n"
            f"    <link>{xml_esc(link)}</link>\n"
            f'    <guid isPermaLink="true">{xml_esc(link)}</guid>\n'
            f"    <pubDate>{format_datetime(pub_dt)}</pubDate>\n"
            f"    <description>{xml_esc(build_meta_description(day))}</description>\n"
            "  </item>")

    canal = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>\n'
        "  <title>La Tercera Cámara</title>\n"
        f"  <link>{SITE_URL}</link>\n"
        "  <description>Auditoría pública diaria del BOE, el Congreso y el Senado, "
        "con enlace a la fuente oficial.</description>\n"
        "  <language>es-es</language>\n"
        f'  <atom:link href="{SITE_URL}feed.xml" rel="self" type="application/rss+xml"/>\n'
        + "\n".join(items) + "\n</channel></rss>\n")
    FEED_FILE.write_text(canal, encoding="utf-8")
    log(f"feed.xml generado con {len(items)} ediciones")


def renderizar() -> None:
    dias = []
    for f in sorted(DATA_DIR.glob("*.json"), reverse=True)[:MAX_DAYS]:
        try:
            dias.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception as exc:                              # noqa: BLE001
            log(f"  {f.name} ilegible: {exc}")
    if not dias:
        log("No hay datos que renderizar.")
        sys.exit(1)

    renderizar_index(dias)
    entradas = renderizar_ediciones(dias)
    fichas = renderizar_normas(dias)
    extras = renderizar_temas(dias) + renderizar_plazos(dias)
    fichas_dip: list = []
    try:
        fichas_dip = cosechar_congreso()
        extras += renderizar_diputados(fichas_dip)
    except Exception as exc:                                  # noqa: BLE001
        log(f"diputados/: no se pudo generar ({exc})")
    try:
        extras += renderizar_buscador(dias, fichas_dip)
    except Exception as exc:                                  # noqa: BLE001
        log(f"buscar/: no se pudo generar ({exc})")
    renderizar_archivo(entradas, dias)
    renderizar_sitemap(entradas, fichas + extras)
    renderizar_feed(dias)

    # Portada y archivo cambian cada día; las ediciones, solo las que se han
    # regenerado de verdad. Se avisa de esas, no de las 300 del archivo.
    # El JSON se deja montado aquí para que el workflow solo tenga que hacer
    # un curl: así no hay que escribir Python dentro del YAML.
    hoy_iso = dt.date.today().isoformat()
    fichas_hoy = [f["url"] for f in fichas if f["lastmod"] == hoy_iso]
    urls = list(dict.fromkeys([SITE_URL, f"{SITE_URL}ediciones/"]
                              + DIAG.get("urls_cambiadas", []) + fichas_hoy))[:1000]
    INDEXNOW_JSON.write_text(json.dumps({
        "host": INDEXNOW_HOST,
        "key": INDEXNOW_KEY,
        "keyLocation": f"{SITE_URL}{INDEXNOW_KEY}.txt",
        "urlList": urls,
    }, ensure_ascii=False), encoding="utf-8")
    log(f"indexnow.json: {len(urls)} URLs para notificar")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--date")
    args = ap.parse_args()

    # Todas las carpetas del repositorio existen siempre: el paso de publicación del
    # workflow hace `git add` sobre ellas y falla si alguna no está creada.
    for carpeta in (DATA_DIR, CURATED_DIR, DEBUG_DIR, ESTADO, EDICIONES_DIR,
                NORMAS_DIR, TEMAS_DIR, PLAZOS_DIR, DIPUTADOS_DIR, DATOS_DIR):
        carpeta.mkdir(exist_ok=True)

    if not args.render:
        fecha = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
        dia = construir_dia(fecha)
        if dia:
            (DATA_DIR / f"{dia['id']}.json").write_text(
                json.dumps(dia, ensure_ascii=False, indent=2), encoding="utf-8")
            log(f"escrito data/{dia['id']}.json")
        else:
            log("Edición no escrita; se conserva lo publicado.")
        DIAG["fin"] = dt.datetime.now(dt.timezone.utc).isoformat()
        (DEBUG_DIR / "last-run.json").write_text(
            json.dumps(DIAG, ensure_ascii=False, indent=2), encoding="utf-8")

    renderizar()


if __name__ == "__main__":
    main()
