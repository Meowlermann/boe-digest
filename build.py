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
OUTPUT = ROOT / "index.html"

SITE_URL = "https://meowlermann.github.io/boe-digest/"
MAX_DAYS = 30
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


def get(url: str, tries: int = 3, referer: str | None = None) -> requests.Response | None:
    """GET tolerante. Devuelve None en vez de reventar, y anota el diagnóstico."""
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

    html = TEMPLATE.read_text(encoding="utf-8").replace(
        "__DIGEST_DATA__", json.dumps(dias, ensure_ascii=False, separators=(",", ":")))
    OUTPUT.write_text(html, encoding="utf-8")
    log(f"index.html generado con {len(dias)} ediciones ({len(html)} bytes)")

    hoy = dt.date.today().isoformat()
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url>\n    <loc>{SITE_URL}</loc>\n    <lastmod>{hoy}</lastmod>\n"
        "    <changefreq>daily</changefreq>\n    <priority>1.0</priority>\n  </url>\n"
        "</urlset>\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--date")
    args = ap.parse_args()

    DATA_DIR.mkdir(exist_ok=True)
    DEBUG_DIR.mkdir(exist_ok=True)

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
