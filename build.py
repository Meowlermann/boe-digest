#!/usr/bin/env python3
"""
BOE Digest & Cortes en Directo — pipeline diario.

Se ejecuta en GitHub Actions. Hace tres cosas:

  1. RECOLECTA   el sumario del BOE del día y las publicaciones oficiales
                 del Congreso y del Senado (BOCG y Diarios de Sesiones).
  2. REDACTA     titulares y artículos. Si hay un modelo disponible via
                 GitHub Models lo usa; si no, cae a plantillas deterministas
                 que nunca inventan hechos.
  3. RENDERIZA   data/*.json -> index.html con la plantilla template.html.

Principio de diseño: el sitio NUNCA debe romperse. Si la recolección falla,
se conserva lo que ya había publicado y se deja constancia en la edición.

Uso:
    python build.py              # recolecta el día de hoy y renderiza
    python build.py --render     # solo renderiza desde data/*.json
    python build.py --date 2026-09-17
"""

from __future__ import annotations

import argparse
import datetime as dt
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
TEMPLATE = ROOT / "template.html"
OUTPUT = ROOT / "index.html"

SITE_URL = "https://meowlermann.github.io/boe-digest/"
SITE_TITLE = "BOE Digest & Cortes en Directo"
SITE_DESC = (
    "El BOE y las Cortes, contados sin somnífero. Auditoría pública diaria de lo que "
    "publica el Estado y de lo que hacen diputados y senadores, con enlace a la fuente oficial."
)
MAX_DAYS = 30           # ediciones que se conservan en la página
REQUEST_TIMEOUT = 45
UA = {"User-Agent": "boe-digest/1.0 (+https://meowlermann.github.io/boe-digest/)"}

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
MES_ABBR = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN",
            "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]


def log(msg: str) -> None:
    print(f"[build] {msg}", flush=True)


def get(url: str, tries: int = 3) -> requests.Response | None:
    """GET tolerante: reintenta, y devuelve None en vez de reventar."""
    for attempt in range(1, tries + 1):
        try:
            r = requests.get(url, headers=UA, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                return r
            log(f"  {r.status_code} en {url}")
            if r.status_code == 404:
                return None
        except Exception as exc:                      # noqa: BLE001
            log(f"  error en {url}: {exc}")
        if attempt < tries:
            time.sleep(3 * attempt)
    return None


# ---------------------------------------------------------------------------
# 1. RECOLECCIÓN — BOE
# ---------------------------------------------------------------------------

CAT_RULES = [
    ("fiscal", ["hacienda", "tributar", "impuesto", "banco de españa", "presupuest",
                "aduan", "iva ", "irpf", "deuda pública", "tesoro"]),
    ("laboral", ["trabajo", "seguridad social", "empleo", "salarial", "convenio colectivo",
                 "formación profesional", "aula mentor", "desempleo", "autónomo"]),
    ("mercantil", ["mercantil", "sociedades", "competencia", "auditoría", "contabilidad",
                   "concursal", "registro de", "mercado de valores"]),
]


def clasificar(texto: str) -> str:
    bajo = texto.lower()
    for cat, claves in CAT_RULES:
        if any(k in bajo for k in claves):
            return cat
    return "otros"


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
        seccion_actual = ""
        departamento = ""

        # El sumario alterna encabezados de sección/departamento y listas de disposiciones.
        for el in soup.find_all(["h2", "h3", "h4", "h5", "li", "p"]):
            txt = " ".join(el.get_text(" ", strip=True).split())
            if not txt:
                continue
            if el.name in ("h2", "h3") and re.match(r"^[IVX]+\.", txt):
                seccion_actual = txt
                continue
            if el.name in ("h4", "h5"):
                departamento = txt
                continue
            if el.name in ("li", "p") and len(txt) > 60:
                if not re.match(r"^(Orden|Resolución|Real Decreto|Ley|Acuerdo|Corrección|"
                                r"Extracto|Anuncio|Circular|Instrucción)", txt):
                    continue
                enlace = ""
                a = el.find("a", href=True)
                if a:
                    href = a["href"]
                    enlace = href if href.startswith("http") else f"https://www.boe.es{href}"
                entradas.append({
                    "seccion": seccion_actual,
                    "dept": departamento,
                    "titulo": txt,
                    "url": enlace,
                })

        num = ""
        m = re.search(r"[Nn]úm(?:ero)?\.?\s*(\d+)", soup.get_text(" ", strip=True)[:4000])
        if m:
            num = m.group(1)

        log(f"BOE: {len(entradas)} entradas encontradas para {d.isoformat()}")
        if entradas:
            return {
                "fecha_boe": d,
                "numero": num,
                "sourceUrl": url,
                "entradas": entradas,
            }
    return None


# ---------------------------------------------------------------------------
# 1b. RECOLECCIÓN — Congreso y Senado
# ---------------------------------------------------------------------------

def pdf_text(url: str, max_chars: int = 120_000) -> str:
    """Descarga un PDF y devuelve su texto. Cadena vacía si no se puede."""
    r = get(url, tries=2)
    if not r:
        return ""
    try:
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(r.content))
        partes = []
        total = 0
        for page in reader.pages:
            t = page.extract_text() or ""
            partes.append(t)
            total += len(t)
            if total > max_chars:
                break
        return "\n".join(partes)
    except Exception as exc:                          # noqa: BLE001
        log(f"  no se pudo leer el PDF {url}: {exc}")
        return ""


def fetch_congreso() -> list[dict]:
    """Últimas publicaciones oficiales del Congreso: BOCG y Diarios de Sesiones."""
    docs: list[dict] = []
    r = get("https://www.congreso.es/ultimas-publicaciones-oficiales")
    if not r:
        log("Congreso: no se pudo abrir la página de publicaciones")
        return docs

    soup = BeautifulSoup(r.text, "html.parser")
    vistos = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".PDF" not in href.upper():
            continue
        full = href if href.startswith("http") else f"https://www.congreso.es{href}"
        if full in vistos:
            continue
        vistos.add(full)
        nombre = full.rsplit("/", 1)[-1]
        if "/DS/" in full.upper() or nombre.upper().startswith("DSCD"):
            tipo = "Diario de Sesiones"
        elif "/BOCG/" in full.upper():
            tipo = "BOCG"
        else:
            continue
        docs.append({"tipo": tipo, "url": full, "nombre": nombre})

    log(f"Congreso: {len(docs)} publicaciones detectadas")
    # Priorizamos un Diario de Sesiones (trae intervenciones literales) y un BOCG.
    ds = [d for d in docs if d["tipo"] == "Diario de Sesiones"][:1]
    bocg = [d for d in docs if d["tipo"] == "BOCG"][:2]
    seleccion = ds + bocg
    for d in seleccion:
        d["texto"] = pdf_text(d["url"])
        log(f"  {d['nombre']}: {len(d['texto'])} caracteres")
    return seleccion


def fetch_senado() -> list[dict]:
    """Últimos boletines oficiales del Senado."""
    docs: list[dict] = []
    idx = ("https://www.senado.es/web/actividadparlamentaria/publicacionesoficiales/"
           "senado/boletinesoficiales/index.html")
    r = get(idx)
    if not r:
        log("Senado: no se pudo abrir el índice de boletines")
        return docs

    soup = BeautifulSoup(r.text, "html.parser")
    nums = set()
    for a in soup.find_all("a", href=True):
        m = re.search(r"BOCG_T_15_(\d+)\.PDF", a["href"], re.I)
        if m:
            nums.add(int(m.group(1)))
    if not nums:
        # Plan B: los números son correlativos; probamos el texto plano de la página.
        for m in re.finditer(r"BOCG_T_15_(\d+)", r.text, re.I):
            nums.add(int(m.group(1)))

    for n in sorted(nums, reverse=True)[:1]:
        url = f"https://www.senado.es/legis15/publicaciones/pdf/senado/bocg/BOCG_T_15_{n}.PDF"
        texto = pdf_text(url)
        log(f"Senado: boletín {n}, {len(texto)} caracteres")
        if texto:
            docs.append({"tipo": "BOCG Senado", "numero": n, "url": url,
                         "nombre": f"BOCG Senado núm. {n}", "texto": texto})
    return docs


# ---------------------------------------------------------------------------
# 2. REDACCIÓN
# ---------------------------------------------------------------------------

MODEL_ENDPOINT = "https://models.github.ai/inference/chat/completions"
MODEL_NAME = os.environ.get("DIGEST_MODEL", "openai/gpt-4o-mini")

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
    return bool(os.environ.get("GITHUB_TOKEN") or os.environ.get("MODELS_TOKEN"))


def llm(prompt: str, max_tokens: int = 3000) -> dict | None:
    """Llama a GitHub Models. Devuelve None si no está disponible o falla."""
    token = os.environ.get("MODELS_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        return None
    try:
        r = requests.post(
            MODEL_ENDPOINT,
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json",
                     "Accept": "application/vnd.github+json"},
            json={"model": MODEL_NAME,
                  "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                               {"role": "user", "content": prompt}],
                  "temperature": 0.7,
                  "max_tokens": max_tokens},
            timeout=120,
        )
        if r.status_code != 200:
            log(f"  modelo no disponible ({r.status_code}): {r.text[:200]}")
            return None
        contenido = r.json()["choices"][0]["message"]["content"]
        contenido = re.sub(r"^```(?:json)?|```$", "", contenido.strip(), flags=re.M).strip()
        return json.loads(contenido)
    except Exception as exc:                          # noqa: BLE001
        log(f"  fallo al redactar con modelo: {exc}")
        return None


# --- Redacción determinista (sin modelo): nunca inventa, solo reformula --------

GANCHOS = {
    "subvención": "DINERO PÚBLICO EN MARCHA",
    "convenio": "ACUERDO FIRMADO",
    "premio": "HAY PREMIO",
    "beca": "SE BUSCA BECARIO",
    "plan de estudios": "CAMBIO EN LAS AULAS",
    "instalación eléctrica": "LUZ VERDE A LA RED",
    "fiesta": "FIESTA CON SELLO OFICIAL",
    "nombramiento": "CAMBIO DE SILLAS",
    "cese": "CAMBIO DE SILLAS",
    "cambios del euro": "LA CALCULADORA DEL EURO",
}


def gancho(titulo: str) -> str:
    bajo = titulo.lower()
    for clave, valor in GANCHOS.items():
        if clave in bajo:
            return valor
    return "LO PUBLICA EL BOE"


def articulo_deterministico(entrada: dict) -> dict:
    titulo = entrada["titulo"]
    corto = titulo.split(", por la que")[0].split(", por el que")[0]
    corto = corto[:110].rstrip(" ,.")
    return {
        "cat": clasificar(f"{entrada.get('dept','')} {titulo}"),
        "size": "sm",
        "headline": f"{gancho(titulo)}: {corto.upper()}",
        "standfirst": titulo[:300],
        "body": [
            f"Publicado en el BOE por {entrada.get('dept') or 'el organismo firmante'}. "
            "El texto completo está enlazado al pie de esta pieza.",
            "Esta edición se ha generado sin la capa de redacción automática, así que "
            "el titular es descriptivo y el contenido se limita a lo que dice literalmente "
            "el boletín.",
        ],
        "dept": entrada.get("dept") or "BOE",
        "ref": entrada.get("seccion") or "",
    }


def redactar_boe(boe: dict) -> dict:
    """Convierte las entradas del sumario en artículos."""
    entradas = boe["entradas"]
    # Solo las secciones sustantivas: I (disposiciones generales) y III (otras disposiciones)
    sustantivas = [e for e in entradas
                   if e["seccion"].startswith(("I.", "III.")) or not e["seccion"]]
    if not sustantivas:
        sustantivas = entradas
    sustantivas = sustantivas[:14]

    otras = len(entradas) - len(sustantivas)
    extra = (f"Además, el resto del sumario suma unas {otras} entradas entre nombramientos, "
             "oposiciones, anuncios y licitaciones." if otras > 0 else "")

    articulos: list[dict] = []
    if llm_disponible() and sustantivas:
        material = "\n".join(
            f"- [{e.get('seccion','')}] {e.get('dept','')}: {e['titulo']}"
            for e in sustantivas
        )
        prompt = f"""Material del BOE de hoy (sumario oficial, títulos literales):

{material}

Escribe un artículo por cada entrada. Devuelve JSON con esta forma exacta:
{{"articulos": [
  {{"cat": "fiscal|laboral|mercantil|otros",
    "size": "lead|md|sm",
    "headline": "TITULAR EN MAYÚSCULAS, mordaz pero fiel, con el dato concreto dentro",
    "standfirst": "una o dos frases de entradilla",
    "body": ["párrafo 1", "párrafo 2", "párrafo 3"],
    "dept": "organismo emisor",
    "ref": "referencia de la orden o sección"}}
]}}

Exactamente una entrada debe llevar size "lead" (la más noticiable para el gran público),
dos o tres "md" y el resto "sm". En el cuerpo explica en lenguaje llano qué es y por qué
importa, incluido el mecanismo jurídico (qué es una subvención directa, un convenio, una
orden). No inventes importes ni datos que no estén en los títulos."""
        resp = llm(prompt, max_tokens=4000)
        if resp and isinstance(resp.get("articulos"), list):
            articulos = [a for a in resp["articulos"] if a.get("headline")]
            log(f"BOE: {len(articulos)} artículos redactados con modelo")

    if not articulos:
        log("BOE: usando redacción determinista")
        articulos = [articulo_deterministico(e) for e in sustantivas]
        if articulos:
            articulos[0]["size"] = "lead"
            for a in articulos[1:3]:
                a["size"] = "md"

    counts = {"fiscal": 0, "laboral": 0, "mercantil": 0, "otros": 0}
    for a in articulos:
        counts[a.get("cat", "otros") if a.get("cat") in counts else "otros"] += 1

    d = boe["fecha_boe"]
    return {
        "numero": boe.get("numero", ""),
        "fecha": f"{d.day} de {MESES[d.month-1]} de {d.year}",
        "sourceUrl": boe["sourceUrl"],
        "counts": counts,
        "extra": extra,
        "stories": articulos,
    }


def redactar_cortes(docs: list[dict], anterior: dict | None) -> dict:
    """Artículos de auditoría a partir de las publicaciones de ambas cámaras."""
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

    if not docs:
        base["constructionNote"] = (
            "Hoy no se pudo descargar ninguna publicación oficial legible del Congreso "
            "ni del Senado. Antes que rellenar con ruido, lo decimos: volvemos mañana.")
        return base

    if llm_disponible():
        material = ""
        for d in docs:
            material += (f"\n\n=== {d['nombre']} ({d['tipo']}) — fuente: {d['url']} ===\n"
                         + d.get("texto", "")[:28000])
        prompt = f"""Material oficial de las Cortes publicado hoy:
{material}

Escribe entre 3 y 6 artículos de AUDITORÍA PÚBLICA sobre lo que hacen sus señorías.
Devuelve JSON con esta forma exacta:
{{"feed": [
  {{"chamber": "congreso|senado",
    "type": "Pleno|Comisión|Comisión de investigación|Interpelaciones urgentes|Preguntas escritas|Tramitación legislativa|Administración de la Cámara",
    "date": "DD mmm AAAA",
    "headline": "TITULAR mordaz pero fiel",
    "standfirst": "entradilla de una o dos frases",
    "quote": {{"text": "cita LITERAL del documento", "author": "nombre y cargo"}},
    "body": ["párrafo 1", "párrafo 2", "párrafo 3 que empieza por 'Auditoría del día:'"],
    "source": {{"label": "nombre del documento", "url": "url del PDF"}}}}
 ],
 "scoreboard": {{"note": "aclaración de qué se ha contado",
                 "rows": [{{"g": "grupo parlamentario", "n": 2}}]}}
}}

Baja al detalle: nombres y apellidos de quien interviene o es nombrado, grupo parlamentario,
número de expediente, ministerio destinatario. El campo "quote" es opcional y SOLO se incluye
si la frase aparece literalmente en el material. El último párrafo de cada artículo empieza
por "Auditoría del día:" y aporta el ángulo de escrutinio. Reparte la mordacidad entre todos
los partidos que aparezcan."""
        resp = llm(prompt, max_tokens=4000)
        if resp and isinstance(resp.get("feed"), list) and resp["feed"]:
            base["feed"] = resp["feed"]
            if isinstance(resp.get("scoreboard"), dict):
                base["scoreboard"] = resp["scoreboard"]
            log(f"Cortes: {len(base['feed'])} artículos redactados con modelo")
            return base

    # Sin modelo: publicamos el inventario verificable, que ya es auditoría.
    log("Cortes: usando inventario determinista")
    hoy = dt.date.today()
    fecha_txt = f"{hoy.day} {MES_ABBR[hoy.month-1].lower()} {hoy.year}"
    for d in docs:
        camara = "senado" if "Senado" in d["nombre"] or "Senado" in d["tipo"] else "congreso"
        texto = d.get("texto", "")
        primeras = [ln.strip() for ln in texto.splitlines() if len(ln.strip()) > 70][:3]
        base["feed"].append({
            "chamber": camara,
            "type": d["tipo"],
            "date": fecha_txt,
            "headline": f"PUBLICADO HOY: {d['nombre'].upper()}",
            "standfirst": ("Publicación oficial registrada hoy. Esta edición se ha generado "
                           "sin la capa de redacción automática, así que reproducimos el "
                           "inventario verificable y el enlace al documento."),
            "body": (primeras or ["El documento está disponible en el enlace de la fuente."]) +
                    ["Auditoría del día: el documento queda registrado y enlazado. "
                     "Todo lo que aquí aparece procede literalmente de la publicación oficial."],
            "source": {"label": d["nombre"], "url": d["url"]},
        })
    return base


# ---------------------------------------------------------------------------
# 3. RENDERIZADO
# ---------------------------------------------------------------------------

def construir_dia(fecha: dt.date) -> dict | None:
    log(f"=== Construyendo edición del {fecha.isoformat()} ===")
    boe_raw = fetch_boe(fecha)
    congreso = fetch_congreso()
    senado = fetch_senado()

    anterior = None
    previos = sorted(DATA_DIR.glob("*.json"), reverse=True)
    if previos:
        try:
            anterior = json.loads(previos[0].read_text(encoding="utf-8")).get("cortes")
        except Exception:                             # noqa: BLE001
            anterior = None

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
    return dia


def renderizar() -> None:
    dias = []
    for f in sorted(DATA_DIR.glob("*.json"), reverse=True)[:MAX_DAYS]:
        try:
            dias.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception as exc:                      # noqa: BLE001
            log(f"  {f.name} ilegible: {exc}")
    if not dias:
        log("No hay datos que renderizar.")
        sys.exit(1)

    tpl = TEMPLATE.read_text(encoding="utf-8")
    payload = json.dumps(dias, ensure_ascii=False, separators=(",", ":"))
    html = tpl.replace("__DIGEST_DATA__", payload)
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
    ap.add_argument("--render", action="store_true", help="solo renderizar")
    ap.add_argument("--date", help="fecha AAAA-MM-DD (por defecto, hoy)")
    args = ap.parse_args()

    DATA_DIR.mkdir(exist_ok=True)

    if not args.render:
        fecha = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
        dia = construir_dia(fecha)
        if dia:
            destino = DATA_DIR / f"{dia['id']}.json"
            destino.write_text(json.dumps(dia, ensure_ascii=False, indent=2), encoding="utf-8")
            log(f"escrito {destino.name}")
        else:
            log("Edición no escrita; se conserva lo publicado.")

    renderizar()


if __name__ == "__main__":
    main()
