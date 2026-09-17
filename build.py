#!/usr/bin/env python3
"""
BOE Digest & Cortes en Directo — pipeline diario.

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
FEED_FILE = ROOT / "feed.xml"

SITE_URL = "https://meowlermann.github.io/boe-digest/"
MAX_DAYS = 30
MAX_FEED_ITEMS = 20

# IndexNow: avisa a Bing, Yandex, Seznam, Naver, Yep e Internet Archive de las
# URLs que han cambiado, sin cuenta ni verificación. El fichero de clave vive en
# /boe-digest/ y eso delimita lo que se puede enviar: cualquier URL bajo esa
# ruta, que son todas las nuestras. (Google no participa: ahí hace falta Search
# Console, porque retiró el ping de sitemaps en 2023.)
INDEXNOW_KEY = "d29eac49b00fed8432cc6c405d618f35"
INDEXNOW_HOST = "meowlermann.github.io"
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
            sep = "" if gancho.endswith(":") else ""
            return f"{gancho}{sep} {recortar(resto or obj).upper()}".strip()
    # Sin verbo reconocible: el objeto ya es informativo por sí solo
    return recortar(obj or titulo, 105).upper()


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

    headline = titular_de(obj, titulo)

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

SYSTEM_PROMPT = """Eres la redacción de "BOE Digest & Cortes en Directo", una publicación
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

    log("Cortes: inventario determinista")
    hoy = dt.date.today()
    fecha_txt = f"{hoy.day} {MES_ABBR[hoy.month-1].lower()} {hoy.year}"
    for d in docs:
        camara = d.get("chamber_hint", "congreso")
        texto = d.get("texto", "")
        lineas = [ln.strip() for ln in texto.splitlines() if len(ln.strip()) > 70][:4]
        base["feed"].append({
            "chamber": camara,
            "type": d["tipo"],
            "date": fecha_txt,
            "headline": f"REGISTRADO HOY: {d['nombre'].upper()}",
            "standfirst": ("Publicación oficial de hoy. Reproducimos el inventario "
                           "verificable y el enlace al documento completo."),
            "body": (lineas or ["El documento está disponible en el enlace de la fuente."]) +
                    ["Auditoría del día: todo lo que aparece aquí procede literalmente de "
                     "la publicación oficial enlazada."],
            "source": {"label": d["nombre"], "url": d["url"]},
        })
    return base


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
    out = []
    for d in dias:
        sel = "true" if d["id"] == current_id else "false"
        out.append(f'<button class="daypill" aria-selected="{sel}">{esc_html(d.get("label"))}</button>')
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
    for s in day.get("boe", {}).get("stories") or []:
        is_lead = s.get("size") == "lead"
        cuerpo = body_html_ssr(s.get("body"))
        articulo = cuerpo if is_lead else (
            f'<details class="reader"><summary>Leer el artículo</summary>{cuerpo}</details>')
        cat = s.get("cat") or "otros"
        out.append(
            f'<article class="story {esc_attr(s.get("size",""))}" '
            f'style="--cat:var(--{cat});--catsoft:var(--{cat}-soft)">'
            f'<div class="kicker"><span class="pill">{esc_html(CAT_LABEL.get(cat, "Varios"))}</span></div>'
            f'<h3>{esc_html(s.get("headline"))}</h3>'
            f'<p class="standfirst">{esc_html(s.get("standfirst"))}</p>'
            f'{articulo}'
            f'<div class="foot"><span>{esc_html(s.get("dept"))}</span>'
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
    for f in feed:
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
            f'<article class="acard" style="--cc:var(--{cc});--ccsoft:var(--{cc}-soft)">'
            f'<div class="row1"><span class="tag-cc">{esc_html(CHAMBER_LABEL[cc])}</span>'
            f'<span class="tag-cc">{esc_html(f.get("type",""))}</span>'
            f'<span class="tstamp">{esc_html(f.get("date",""))}</span></div>'
            f'<h3>{esc_html(f.get("headline"))}</h3>'
            f'<p class="standfirst">{esc_html(f.get("standfirst",""))}</p>{cita}'
            f'<details class="reader"><summary>Leer la auditoría completa</summary>'
            f'{body_html_ssr(f.get("body"))}</details>'
            f'<div class="foot"><span>Verificado en fuente oficial</span>{fuente}</div>'
            f'</article>')
    return "".join(out)


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
        return f"Edición del {fecha} — BOE Digest & Cortes en Directo"
    return f"BOE Digest & Cortes en Directo — {fecha}"


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


def jsonld_for_day(day: dict, page_url: str) -> str:
    """Datos estructurados de la edición.

    Regla: en `name` de una norma va SIEMPRE su título oficial. El titular de la
    casa es editorial y va en `alternativeHeadline`. Publicar el titular como
    nombre de la norma, junto a su identificador BOE-A-…, sería afirmar a una
    máquina que la norma se llama así — exactamente lo que este proyecto se
    prohíbe a sí mismo.
    """
    editor = {"@type": "Organization", "name": "BOE Digest & Cortes en Directo", "url": SITE_URL}
    objetos: list[dict] = [{
        "@type": "WebSite",
        "name": "BOE Digest & Cortes en Directo",
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
    """Portada: SPA interactiva, con el día de hoy ya pintado en el HTML servido
    (para que un rastreador sin JS reciba contenido completo, no un <script> vacío)."""
    day0 = dias[0]
    frag = render_ssr_fragments(day0, dias=dias)
    frag["TITLE"] = esc_html(build_title(day0))
    frag["META_DESC"] = esc_attr(build_meta_description(day0))
    frag["JSONLD"] = jsonld_for_day(day0, SITE_URL)
    frag["PERMALINK_HOY"] = f"ediciones/{day0['id']}.html"
    frag["FECHA_HOY"] = esc_html(fmt_date_es(day0["id"]))

    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace(
        "__DIGEST_DATA__", json.dumps(dias, ensure_ascii=False, separators=(",", ":")))
    html = _replace_placeholders(html, frag)
    OUTPUT.write_text(html, encoding="utf-8")
    log(f"index.html generado con {len(dias)} ediciones ({len(html)} bytes)")


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

    desc = (f"Archivo completo de BOE Digest & Cortes en Directo: {len(entradas)} ediciones "
            f"diarias del BOE, el Congreso y el Senado, cada una con su enlace permanente.")
    frag = {
        "TITLE": esc_html("Archivo de ediciones — BOE Digest & Cortes en Directo"),
        "META_DESC": esc_attr(recortar(desc, 155)),
        "CANONICAL": f"{SITE_URL}ediciones/",
        "TOTAL": str(len(entradas)),
        "LISTA": "\n".join(filas),
        "JSONLD": jsonld_script([{
            "@type": "CollectionPage",
            "name": "Archivo de ediciones — BOE Digest & Cortes en Directo",
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


def renderizar_sitemap(entradas: list[dict]) -> None:
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
        "  <title>BOE Digest &amp; Cortes en Directo</title>\n"
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
    renderizar_archivo(entradas, dias)
    renderizar_sitemap(entradas)
    renderizar_feed(dias)

    # Portada y archivo cambian cada día; las ediciones, solo las que se han
    # regenerado de verdad. Se avisa de esas, no de las 300 del archivo.
    # El JSON se deja montado aquí para que el workflow solo tenga que hacer
    # un curl: así no hay que escribir Python dentro del YAML.
    urls = list(dict.fromkeys([SITE_URL, f"{SITE_URL}ediciones/"]
                              + DIAG.get("urls_cambiadas", [])))[:1000]
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
    for carpeta in (DATA_DIR, CURATED_DIR, DEBUG_DIR, ESTADO, EDICIONES_DIR):
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
