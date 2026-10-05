#!/usr/bin/env python3
"""
Verificador común de La Tercera Cámara.

Lo usan la integración continua (.github/workflows/ci.yml, `--modo ci`) y la
salud diaria (al final de daily.yml y archivo.yml, `--modo diario`). Solo
biblioteca estándar: se puede ejecutar sin instalar nada.

Cada comprobación es una función que recibe la raíz del repositorio y
devuelve una lista de hallazgos con la forma

    {"nivel": "grave" | "aviso", "comprobacion": "…", "detalle": "…", "fichero": "…"}

Los graves terminan su detalle con «Qué hacer: …». En modo ci, un hallazgo
grave hace fallar el job; en modo diario nunca se falla: la salud informa,
no bloquea la publicación.

Comprobaciones (las letras son las de la PR que las introdujo):

  a) carpetas    Toda carpeta con HTML y todo fichero de la web de la raíz
                 están en tools/publicables.txt (ARQUITECTURA.md §8).
  b) html        Marcadores sin sustituir, <title>, meta description y
                 canonical, y enlaces internos rotos.
  c) sitemap     XML válido, URL del dominio que existen, sin duplicados,
                 ≤ 50.000 URL por fichero.
  d) indice      datos/indice*.json válido y < 1 MB cada uno.
  e) titulares   Heurísticas sobre los titulares de data/<fecha>.json.
  f) duplicados  Piezas repetidas respecto a los 7 días anteriores.
  g) tamanos     state/, historia de main y de la rama datos, y lo publicado.

Para añadir una comprobación: una función `comprobar_x(raiz, …) -> list`,
su entrada en COMPROBACIONES_CI o en ejecutar(), sus constantes arriba y
casos positivo y negativo en tests/test_verificar.py. Ver ARQUITECTURA.md,
sección «Calidad».

Uso:
    python tools/verificar.py --modo ci
    python tools/verificar.py --modo diario --fecha 2026-10-04
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SITIO = "https://terceracamara.es"

GRAVE = "grave"
AVISO = "aviso"

# Carpetas de primer nivel que no son parte del sitio aunque contengan HTML
# (o puedan contenerlo): código, pruebas, documentación y utilidades.
NO_PUBLICADAS = {".git", ".github", "node_modules", "tests", "app", "docs", "_site",
                 "disparador", "geo", "tools", "__pycache__"}
# Ficheros HTML de la raíz que no son páginas del sitio: plantillas con
# marcadores y verificaciones de propiedad de buscadores.
HTML_RAIZ_IGNORADOS = re.compile(r"^(template.*|google[0-9a-f]+)\.html$")

LISTA_PUBLICABLES = pathlib.Path(__file__).resolve().parent / "publicables.txt"
# montar_sitio.py (mismo directorio) lee esa lista; se importa desde aquí.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


def hallazgo(nivel: str, comprobacion: str, detalle: str, fichero: str = "",
             que_hacer: str = "") -> dict:
    if nivel == GRAVE and que_hacer:
        detalle = f"{detalle} Qué hacer: {que_hacer}"
    return {"nivel": nivel, "comprobacion": comprobacion, "detalle": detalle,
            "fichero": fichero}


def _rel(raiz: pathlib.Path, p: pathlib.Path) -> str:
    try:
        return p.relative_to(raiz).as_posix()
    except ValueError:
        return p.as_posix()


# ---------------------------------------------------------------------------
# a) Coherencia de carpetas publicadas
# ---------------------------------------------------------------------------

def carpetas_publicadas(raiz: pathlib.Path) -> list[str]:
    """Carpetas de primer nivel con algún .html dentro."""
    salida = []
    for d in sorted(raiz.iterdir()):
        if not d.is_dir() or d.name in NO_PUBLICADAS or d.name.startswith("."):
            continue
        if next(d.rglob("*.html"), None) is not None:
            salida.append(d.name)
    return salida


def _publicables(lista: pathlib.Path | None = None) -> list[tuple[str, bool]]:
    import montar_sitio                                       # noqa: PLC0415 (mismo directorio)
    return montar_sitio.leer_publicables(lista or LISTA_PUBLICABLES)


def ficheros_raiz_web(raiz: pathlib.Path) -> list[str]:
    """Ficheros de la raíz que forman parte de la web: los HTML (no las
    plantillas), los XML, CNAME, robots.txt, llms.txt y la clave de IndexNow."""
    clave = None
    build = raiz / "build.py"
    if build.exists():
        m = re.search(r'^INDEXNOW_KEY\s*=\s*"([0-9a-f]+)"', build.read_text(encoding="utf-8"), re.M)
        clave = f"{m.group(1)}.txt" if m else None
    salida = []
    for p in sorted(raiz.iterdir()):
        if not p.is_file():
            continue
        n = p.name
        if ((n.endswith(".html") and not n.startswith("template")) or n.endswith(".xml")
                or n in ("CNAME", "robots.txt", "llms.txt") or n == clave):
            salida.append(n)
    return salida


def comprobar_carpetas(raiz: pathlib.Path, lista: pathlib.Path | None = None) -> list[dict]:
    """(a) Todo lo que forma la web está en tools/publicables.txt, el único
    sitio donde se declara (ARQUITECTURA.md §8). Lo que no está ahí no llega al
    artefacto de Pages: una carpeta olvidada es una sección que desaparece."""
    rel_lista = "tools/publicables.txt"
    try:
        patrones = [p for p, _ in _publicables(lista)]
    except FileNotFoundError:
        return [hallazgo(GRAVE, "carpetas", "No existe tools/publicables.txt.", rel_lista,
                         "restáuralo: es la lista de lo que se publica.")]
    import montar_sitio                                       # noqa: PLC0415
    hallazgos = []
    for c in carpetas_publicadas(raiz):
        if not montar_sitio.cubre(patrones, c):
            hallazgos.append(hallazgo(GRAVE, "carpetas", f"La carpeta publicada «{c}/» no está "
                                      "en tools/publicables.txt.", rel_lista,
                                      f"añade «{c}» a tools/publicables.txt (ARQUITECTURA.md §8)."))
    for f in ficheros_raiz_web(raiz):
        if not montar_sitio.cubre(patrones, f):
            hallazgos.append(hallazgo(GRAVE, "carpetas", f"El fichero de la web «{f}» no está en "
                                      "tools/publicables.txt.", rel_lista,
                                      f"añade «{f}» a tools/publicables.txt (ARQUITECTURA.md §8)."))
    return hallazgos


# ---------------------------------------------------------------------------
# b) HTML generado
# ---------------------------------------------------------------------------

# Marcadores que nunca deben llegar a una página publicada. Se buscan fuera de
# <script> y <style> (el JavaScript usa «undefined» y «isNaN» con razón), pero
# sí dentro de los atributos y del JSON-LD, que se valida aparte.
MARCADORES = [
    ("{{", re.compile(r"\{\{")),
    ("}}", re.compile(r"\}\}")),
    ("__SSR_", re.compile(r"__SSR_[A-Z_]+__")),        # marcadores de template*.html
    ("None", re.compile(r"\bNone\b")),
    ("undefined", re.compile(r"\bundefined\b")),
    ("NaN", re.compile(r"\bNaN\b")),
    ("<EMAIL_DE_CONTACTO>", re.compile(r"(<|&lt;)EMAIL_DE_CONTACTO(>|&gt;)")),
]
RE_SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.S | re.I)
RE_STYLE = re.compile(r"<style\b[^>]*>.*?</style>", re.S | re.I)
RE_DOCUMENTO = re.compile(r"<!doctype html|<html[\s>]", re.I)
RE_TITLE = re.compile(r"<title>(.*?)</title>", re.S | re.I)
RE_META_DESC = re.compile(r"<meta\s+name=\"description\"\s+content=\"([^\"]*)\"", re.I)
RE_CANONICAL = re.compile(r"<link\s+rel=\"canonical\"\s+href=\"([^\"]*)\"", re.I)
RE_HREF = re.compile(r"\bhref=\"([^\"]*)\"", re.I)
# Máximo de hallazgos de enlaces rotos que se detallan (el resto se resume).
MAX_ENLACES_ROTOS = 40


def paginas_html(raiz: pathlib.Path) -> list[pathlib.Path]:
    paginas = [p for p in raiz.glob("*.html") if not HTML_RAIZ_IGNORADOS.match(p.name)]
    for c in carpetas_publicadas(raiz):
        paginas.extend(sorted((raiz / c).rglob("*.html")))
    return paginas


def destino_existe(raiz: pathlib.Path, ruta_url: str, cache: dict) -> bool:
    """¿Sirve GitHub Pages algo en esta ruta? (/x/ → x/index.html, /x → x, x.html o x/index.html)."""
    if ruta_url in cache:
        return cache[ruta_url]
    rel = ruta_url.lstrip("/")
    if rel == "" or rel.endswith("/"):
        candidatos = [rel + "index.html"]
    else:
        candidatos = [rel, rel + ".html", rel + "/index.html"]
    ok = any((raiz / c).is_file() for c in candidatos)
    cache[ruta_url] = ok
    return ok


def _ruta_interna(href: str, pagina_rel: str) -> str | None:
    """Ruta absoluta en el sitio de un href interno, o None si es externo o no se comprueba."""
    href = href.strip()
    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:", "//")):
        return None
    if href.startswith(SITIO):
        href = href[len(SITIO):] or "/"
    elif re.match(r"^[a-z][a-z0-9+.-]*:", href, re.I):
        return None
    href = re.split(r"[?#]", href, maxsplit=1)[0]
    if not href:
        return None
    if href.startswith("/"):
        return href
    base = pagina_rel.rsplit("/", 1)[0] + "/" if "/" in pagina_rel else ""
    partes: list[str] = []
    for trozo in (base + href).split("/"):
        if trozo == "..":
            if partes:
                partes.pop()
        elif trozo != ".":
            partes.append(trozo)
    return "/" + "/".join(partes)


def comprobar_html(raiz: pathlib.Path, paginas: list[pathlib.Path] | None = None) -> list[dict]:
    hallazgos: list[dict] = []
    cache: dict = {}
    rotos: dict[str, list[str]] = defaultdict(list)
    for p in (paginas if paginas is not None else paginas_html(raiz)):
        rel = _rel(raiz, p)
        try:
            texto = p.read_text(encoding="utf-8")
        except Exception as exc:                              # noqa: BLE001
            hallazgos.append(hallazgo(GRAVE, "html", f"No se puede leer: {exc}", rel,
                                      "regenera la página con build.py."))
            continue
        # JSON-LD: tiene que ser JSON estricto (sin NaN ni None de Python).
        for attrs, cuerpo in RE_SCRIPT.findall(texto):
            if "ld+json" in attrs:
                try:
                    json.loads(cuerpo, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
                except ValueError as exc:
                    hallazgos.append(hallazgo(GRAVE, "html", f"JSON-LD inválido ({exc}).", rel,
                                              "revisa el dato que llega a jsonld_script()."))
        visible = RE_STYLE.sub(" ", RE_SCRIPT.sub(" ", texto))
        # Un hallazgo por página con todos sus marcadores y el contexto del primero.
        encontrados = [(nombre, m) for nombre, patron in MARCADORES if (m := patron.search(visible))]
        if encontrados:
            m = min((m for _, m in encontrados), key=lambda x: x.start())
            ctx = re.sub(r"\s+", " ", visible[max(0, m.start() - 40):m.end() + 40])
            nombres = ", ".join(f"«{n}»" for n, _ in encontrados)
            hallazgos.append(hallazgo(GRAVE, "html", f"Marcador sin sustituir {nombres}: …{ctx}…",
                                      rel, "busca qué plantilla o función deja ese valor y "
                                      "corrígela; no parchees el HTML generado."))
        cab = texto[:20000]
        # Un fragmento que otra página incrusta (datos/votaciones-banner.html)
        # no es una página: no lleva <title>, description ni canonical.
        if RE_DOCUMENTO.search(cab[:500]):
            hallazgos.extend(_cabecera(cab, rel))
        for href in set(RE_HREF.findall(visible)):
            ruta = _ruta_interna(html_unescape(href), rel)
            if ruta and not destino_existe(raiz, ruta, cache):
                rotos[ruta].append(rel)
    for ruta, origen in sorted(rotos.items(), key=lambda x: (-len(x[1]), x[0]))[:MAX_ENLACES_ROTOS]:
        hallazgos.append(hallazgo(GRAVE, "html", f"Enlace interno roto a «{ruta}» desde "
                                  f"{len(origen)} página(s), p. ej. {sorted(origen)[0]}.",
                                  sorted(origen)[0], "corrige el enlace en la función que lo "
                                  "pinta o genera la página de destino."))
    if len(rotos) > MAX_ENLACES_ROTOS:
        hallazgos.append(hallazgo(GRAVE, "html", f"Y {len(rotos) - MAX_ENLACES_ROTOS} destinos "
                                  "rotos más.", "", "corrige primero los de arriba."))
    return hallazgos


def _cabecera(cab: str, rel: str) -> list[dict]:
    """<title>, meta description y canonical de una página completa."""
    salida = []
    t = RE_TITLE.search(cab)
    if not t or not t.group(1).strip():
        salida.append(hallazgo(GRAVE, "html", "Falta <title> o está vacío.", rel,
                               "rellena TITLE al pintar la página."))
    d = RE_META_DESC.search(cab)
    if not d or not d.group(1).strip():
        salida.append(hallazgo(GRAVE, "html", "Falta meta description o está vacía.", rel,
                               "rellena META_DESC al pintar la página."))
    c = RE_CANONICAL.search(cab)
    if not c or not c.group(1).startswith(SITIO + "/"):
        salida.append(hallazgo(GRAVE, "html", "Falta canonical con " + SITIO + ".", rel,
                               "rellena CANONICAL con la URL absoluta de la página."))
    return salida


def html_unescape(s: str) -> str:
    return s.replace("&amp;", "&").replace("&#x27;", "'").replace("&quot;", '"')


# ---------------------------------------------------------------------------
# c) sitemap.xml
# ---------------------------------------------------------------------------

MAX_URLS_SITEMAP = 50_000          # límite del protocolo sitemaps.org por fichero
NS_SITEMAP = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def comprobar_sitemap(raiz: pathlib.Path) -> list[dict]:
    hallazgos: list[dict] = []
    ficheros = sorted(raiz.glob("sitemap*.xml"))
    if not (raiz / "sitemap.xml").exists():
        return [hallazgo(GRAVE, "sitemap", "No existe sitemap.xml.", "sitemap.xml",
                         "revisa renderizar_sitemap() en build.py.")]
    vistas: dict[str, str] = {}
    cache: dict = {}
    for f in ficheros:
        rel = _rel(raiz, f)
        try:
            arbol = ET.parse(f).getroot()
        except ET.ParseError as exc:
            hallazgos.append(hallazgo(GRAVE, "sitemap", f"XML mal formado: {exc}.", rel,
                                      "revisa el escapado en renderizar_sitemap()."))
            continue
        locs = [(e.text or "").strip() for e in arbol.iter(NS_SITEMAP + "loc")]
        if arbol.tag == NS_SITEMAP + "urlset" and len(locs) > MAX_URLS_SITEMAP:
            hallazgos.append(hallazgo(GRAVE, "sitemap", f"{len(locs)} URL en un fichero "
                                      f"(máximo {MAX_URLS_SITEMAP}).", rel,
                                      "parte el sitemap en varios ficheros con un índice."))
        for loc in locs:
            if not loc.startswith(SITIO + "/"):
                hallazgos.append(hallazgo(GRAVE, "sitemap", f"URL fuera del dominio: {loc}", rel,
                                          "el sitemap solo puede listar URL de " + SITIO + "."))
                continue
            if loc in vistas:
                hallazgos.append(hallazgo(GRAVE, "sitemap", f"URL duplicada: {loc}", rel,
                                          "quita la entrada repetida en renderizar_sitemap()."))
                continue
            vistas[loc] = rel
            if not destino_existe(raiz, loc[len(SITIO):], cache):
                hallazgos.append(hallazgo(GRAVE, "sitemap", f"La URL no existe como fichero: {loc}",
                                          rel, "genera la página o no la pongas en el sitemap."))
    return hallazgos


# ---------------------------------------------------------------------------
# d) Índice del buscador
# ---------------------------------------------------------------------------

MAX_BYTES_INDICE = 1_000_000       # ARQUITECTURA.md §7: se parte al pasar de 1 MB


def comprobar_indice(raiz: pathlib.Path) -> list[dict]:
    hallazgos = []
    ficheros = sorted((raiz / "datos").glob("indice*.json"))
    if not ficheros:
        return [hallazgo(GRAVE, "indice", "No hay datos/indice*.json.", "datos/",
                         "revisa renderizar_buscador() en build.py.")]
    for f in ficheros:
        rel = _rel(raiz, f)
        try:
            json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:                              # noqa: BLE001
            hallazgos.append(hallazgo(GRAVE, "indice", f"JSON inválido: {exc}", rel,
                                      "revisa renderizar_buscador() en build.py."))
        tam = f.stat().st_size
        if tam >= MAX_BYTES_INDICE:
            hallazgos.append(hallazgo(GRAVE, "indice", f"Pesa {tam / 1e6:.2f} MB (límite 1 MB).",
                                      rel, "parte ese tipo por año o mes como indica "
                                      "ARQUITECTURA.md §7."))
    return hallazgos


# ---------------------------------------------------------------------------
# e) Titulares de una edición
# ---------------------------------------------------------------------------
#
# Cada heurística sale de un fallo real ya publicado. Si da un falso positivo,
# se corrige aquí con un test que lo cubra (AGENTS.md), no se silencia.

# Titular que termina (o termina un tramo antes de «:») en preposición,
# artículo o conjunción: se cortó el título.
#   Real (2026-09-22, Cortes): «SESIÓN DEL »
#   Real (2026-01-02, BOE): «SE PUBLICA LA ADENDA DE PRÓRROGA Y MODIFICACIÓN DEL: LA SECRETARÍA…»
#   Real (2026-01-17, BOE): «… CENTRO CRIPTOLÓGICO NACIONAL, POR LA QUE SE CERTIFICA LA…»
PALABRAS_DE_ENLACE = ("A AL ANTE BAJO CON CONTRA DE DEL DESDE EN ENTRE HACIA HASTA PARA POR "
                      "SEGÚN SIN SOBRE TRAS EL LA LO LOS LAS UN UNA UNOS UNAS Y E NI O U QUE "
                      "SU SUS").split()
RE_FIN_ENLACE = re.compile(r"(?:^|\s)(" + "|".join(PALABRAS_DE_ENLACE) + r")\s*(?:…|\.\.\.)?\s*(?::|$)",
                           re.I)
# Nombres de fichero o códigos internos en lugar de un titular.
#   Real (2026-09-18, Cortes): «REGISTRADO HOY: DSCD-15-PL-204.PDF»
#   Real (2026-09-18, Cortes): «REGISTRADO HOY: BOCG-15-A-113-1.PDF»
RE_FICHERO = re.compile(r"\bPDF\b|\bDSC[DGS]-\d|\bBOCG[-_]|\.(?:pdf|html?|json|xml)\b", re.I)
# Recuento pegado al titular en vez de un titular sobre el asunto principal.
#   Real (2026-09-19, Cortes): «VOX LLEVA AL PLENO LA DEFENSA NACIONAL, Y 4 ASUNTOS MÁS»
RE_ASUNTOS_MAS = re.compile(r"\bY\s+\d+\s+ASUNTOS?\s+MÁS\b", re.I)
# Longitud. El más corto bueno visto es «CLIMA DE GALICIA» (16); por debajo de
# 15 solo han salido cortes como «SESIÓN DEL » (11, 2026-09-22). El más largo
# bueno visto tiene 208 (una pregunta oral citada entera, 2026-09-28); por
# encima de LONGITUD_MAX es un aviso, no un error.
LONGITUD_MIN = 15
LONGITUD_MAX = 230
# Mayúsculas cortadas a media palabra: la última palabra no está en la fuente,
# pero sí una más larga que empieza igual.
#   Real (2026-09-24, Cortes): «EL PACTO DE TOLEDO ESCUCHA A FUNDACIÓN DE ESTUDIOS DE ECONOM»
RE_PALABRA = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")
MIN_LETRAS_CORTE = 3


def piezas_edicion(dia: dict) -> list[dict]:
    """Piezas de una edición: BOE y feed de Cortes, con su origen."""
    piezas = []
    for s in ((dia.get("boe") or {}).get("stories") or []):
        if isinstance(s, dict):
            piezas.append({"origen": "boe", **s})
    for s in ((dia.get("cortes") or {}).get("feed") or []):
        if isinstance(s, dict):
            piezas.append({"origen": "cortes", **s})
    return piezas


def _fuente_pieza(p: dict) -> str:
    partes = [p.get("titulo_oficial", ""), p.get("standfirst", ""),
              json.dumps(p.get("body", ""), ensure_ascii=False),
              json.dumps(p.get("quote", ""), ensure_ascii=False),
              json.dumps(p.get("source", ""), ensure_ascii=False)]
    return " ".join(str(x) for x in partes).upper()


def problemas_titular(titular: str, fuente: str = "") -> list[tuple[str, str]]:
    """[(nivel, motivo)] de un titular. `fuente` es el texto de la pieza
    (título oficial, entradilla, cuerpo) para detectar palabras cortadas."""
    t = (titular or "").strip()
    salida = []
    if not t:
        return [(GRAVE, "titular vacío")]
    if RE_FIN_ENLACE.search(t.rstrip(" .,;")) and not t.endswith(("»", "?", "!", '"', "”")):
        salida.append((GRAVE, "termina en preposición, artículo o conjunción"))
    if RE_FICHERO.search(t):
        salida.append((GRAVE, "contiene un nombre de fichero o un código"))
    if RE_ASUNTOS_MAS.search(t):
        salida.append((GRAVE, "recuento «Y N ASUNTOS MÁS» en el titular"))
    if len(titular) < LONGITUD_MIN:
        salida.append((GRAVE, f"demasiado corto ({len(titular)} caracteres)"))
    elif len(titular) > LONGITUD_MAX:
        salida.append((AVISO, f"muy largo ({len(titular)} caracteres)"))
    if fuente:
        palabras = RE_PALABRA.findall(t.upper())
        if palabras and not t.endswith(("»", '"', "”")):
            ultima = palabras[-1]
            vocab = set(RE_PALABRA.findall(fuente))
            if (len(ultima) >= MIN_LETRAS_CORTE and ultima not in vocab
                    and any(v.startswith(ultima) and len(v) > len(ultima) for v in vocab)):
                salida.append((GRAVE, f"palabra cortada al final («{ultima}»)"))
    return salida


def _leer_edicion(raiz: pathlib.Path, fecha: str) -> dict | None:
    f = raiz / "data" / f"{fecha}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def comprobar_titulares(raiz: pathlib.Path, fecha: str) -> list[dict]:
    rel = f"data/{fecha}.json"
    try:
        dia = _leer_edicion(raiz, fecha)
    except Exception as exc:                                  # noqa: BLE001
        return [hallazgo(GRAVE, "titulares", f"JSON ilegible: {exc}", rel,
                         "revisa la última escritura de construir_dia().")]
    if dia is None:
        return [hallazgo(AVISO, "titulares", f"No hay edición del {fecha}.", rel)]
    hallazgos = []
    for p in piezas_edicion(dia):
        for nivel, motivo in problemas_titular(p.get("headline", ""), _fuente_pieza(p)):
            hallazgos.append(hallazgo(
                nivel, "titulares", f"[{p['origen']}] «{p.get('headline', '')}»: {motivo}.", rel,
                "corrige la plantilla o el recorte que lo genera (o ponlo bien en curated/ "
                "si es un caso suelto)."))
    return hallazgos


# ---------------------------------------------------------------------------
# f) Duplicados respecto a los 7 días anteriores
# ---------------------------------------------------------------------------

DIAS_DUPLICADOS = 7


def identificador_pieza(p: dict) -> str:
    """BOE: la referencia BOE-A-…; Cortes: el documento oficial que cita.

    Las piezas que enlazan al propio sitio (el recuento diario de preguntas
    pendientes, que remite a /preguntas/#pendientes) son resúmenes que se
    repiten a propósito con cifras nuevas: no tienen identificador."""
    if p.get("origen") == "boe":
        return p.get("ref") or ""
    url = (p.get("source") or {}).get("url") or ""
    return "" if url.startswith(SITIO) else url


def comprobar_duplicados(raiz: pathlib.Path, fecha: str) -> list[dict]:
    rel = f"data/{fecha}.json"
    try:
        dia = _leer_edicion(raiz, fecha)
    except Exception:                                         # noqa: BLE001
        return []          # ya lo informa comprobar_titulares
    if dia is None:
        return []
    f0 = dt.date.fromisoformat(fecha)
    ids: dict[str, str] = {}
    titulares: dict[str, str] = {}
    for i in range(DIAS_DUPLICADOS, 0, -1):
        otra = (f0 - dt.timedelta(days=i)).isoformat()
        try:
            previo = _leer_edicion(raiz, otra)
        except Exception:                                     # noqa: BLE001
            continue
        for p in piezas_edicion(previo or {}):
            if identificador_pieza(p):
                ids[identificador_pieza(p)] = otra
            if p.get("headline"):
                titulares[p["headline"].strip()] = otra
    hallazgos = []
    for p in piezas_edicion(dia):
        ident, tit = identificador_pieza(p), (p.get("headline") or "").strip()
        if ident and ident in ids:
            hallazgos.append(hallazgo(
                GRAVE, "duplicados", f"[{p['origen']}] {ident} ya salió el {ids[ident]} "
                f"(«{tit}»).", rel, "revisa el registro de lo publicado de esa sección "
                "(piezas_hoy, publicadas) para que no repita."))
        elif tit and tit in titulares:
            # Mismo titular con otro documento: puede ser legítimo (las
            # resoluciones de precios del tabaco se titulan igual cada mes).
            hallazgos.append(hallazgo(
                AVISO, "duplicados", f"[{p['origen']}] titular repetido del {titulares[tit]}: "
                f"«{tit}».", rel))
    return hallazgos


# ---------------------------------------------------------------------------
# g) Tamaños
# ---------------------------------------------------------------------------

STATE_AVISO_BYTES = 10 * 1024 ** 2
STATE_GRAVE_BYTES = 25 * 1024 ** 2
GIT_AVISO_BYTES = 500 * 1024 ** 2       # historia de main
GIT_GRAVE_BYTES = 900 * 1024 ** 2
DATOS_AVISO_BYTES = 200 * 1024 ** 2     # historia de la rama datos
DATOS_GRAVE_BYTES = 500 * 1024 ** 2
# Número de ficheros publicados (lo que va a _site). En octubre de 2026 hay
# unos 7.000; el aviso deja margen de un orden de magnitud.
FICHEROS_AVISO = 60_000
FICHEROS_GRAVE = 150_000
# Tamaño publicado: el límite de GitHub Pages es 1 GB.
PUBLICADO_AVISO_BYTES = 600 * 1024 ** 2
PUBLICADO_GRAVE_BYTES = 900 * 1024 ** 2


def _git(raiz: pathlib.Path, *args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=raiz, check=True, capture_output=True,
                              text=True, timeout=120).stdout.strip()
    except Exception:                                         # noqa: BLE001
        return None


def tamano_ref(raiz: pathlib.Path, ref: str) -> int | None:
    """Bytes en disco de toda la historia alcanzable desde `ref`
    (`git rev-list --disk-usage --objects`). None si no se puede medir: sin
    repositorio, sin esa referencia o, para HEAD, con un clon superficial (solo
    tendría el último commit)."""
    if not (raiz / ".git").exists() or _git(raiz, "rev-parse", "--verify", "--quiet", ref) is None:
        return None
    if ref == "HEAD" and _git(raiz, "rev-parse", "--is-shallow-repository") == "true":
        return None
    salida = _git(raiz, "rev-list", "--disk-usage", "--objects", ref)
    return int(salida) if salida and salida.isdigit() else None


def _nivel_tamano(valor: int, aviso: int, grave: int) -> str | None:
    return GRAVE if valor >= grave else AVISO if valor >= aviso else None


def comprobar_tamanos(raiz: pathlib.Path, tam_main: int | None = None,
                      tam_datos: int | None = None) -> list[dict]:
    """(g) state/, historia de main, historia de la rama datos y lo publicado.

    `tam_main` y `tam_datos` (bytes) son para las pruebas; si no se pasan se
    miden con tamano_ref(): main en HEAD y datos en VERIFICAR_REF_DATOS (los
    workflows ponen origin/datos). Con un clon superficial de main (ci.yml) se
    usa REPO_TAMANO_KB, el tamaño de todo el repositorio que da la API: es una
    cota superior."""
    hallazgos = []
    for f in sorted((raiz / "state").rglob("*")) if (raiz / "state").exists() else []:
        if not f.is_file():
            continue
        tam = f.stat().st_size
        nivel = _nivel_tamano(tam, STATE_AVISO_BYTES, STATE_GRAVE_BYTES)
        if nivel:
            hallazgos.append(hallazgo(nivel, "tamanos", f"{_rel(raiz, f)} pesa "
                                      f"{tam / 1024 ** 2:.1f} MiB.", _rel(raiz, f),
                                      "pódalo por ventana o pártelo por año (ARQUITECTURA.md §7)."))
    origen = "historia de main"
    if tam_main is None:
        tam_main = tamano_ref(raiz, "HEAD")
        if tam_main is None and os.environ.get("REPO_TAMANO_KB", "").isdigit():
            tam_main, origen = int(os.environ["REPO_TAMANO_KB"]) * 1024, "repositorio entero (API)"
    if tam_main is not None:
        nivel = _nivel_tamano(tam_main, GIT_AVISO_BYTES, GIT_GRAVE_BYTES)
        if nivel:
            hallazgos.append(hallazgo(nivel, "tamanos", f"La {origen} ocupa "
                                      f"{tam_main / 1024 ** 2:.0f} MiB.", ".git",
                                      "main solo debería crecer con código: busca qué ficheros "
                                      "grandes se están commiteando."))
    if tam_datos is None and os.environ.get("VERIFICAR_REF_DATOS"):
        tam_datos = tamano_ref(raiz, os.environ["VERIFICAR_REF_DATOS"])
    if tam_datos is not None:
        nivel = _nivel_tamano(tam_datos, DATOS_AVISO_BYTES, DATOS_GRAVE_BYTES)
        if nivel:
            hallazgos.append(hallazgo(nivel, "tamanos", f"La historia de la rama datos ocupa "
                                      f"{tam_datos / 1024 ** 2:.0f} MiB.", "datos",
                                      "compacta la rama datos (ARQUITECTURA.md §8)."))
    import montar_sitio                                       # noqa: PLC0415
    n, total = 0, 0
    try:
        for patron, _ in _publicables():
            for r in montar_sitio.resolver(raiz, patron):
                a, b = montar_sitio.tamano(r)
                n, total = n + a, total + b
    except FileNotFoundError:
        pass                              # ya lo informa comprobar_carpetas
    nivel = _nivel_tamano(n, FICHEROS_AVISO, FICHEROS_GRAVE)
    if nivel:
        hallazgos.append(hallazgo(nivel, "tamanos", f"{n} ficheros publicados.", "",
                                  "revisa qué sección multiplica páginas y agrúpalas."))
    nivel = _nivel_tamano(total, PUBLICADO_AVISO_BYTES, PUBLICADO_GRAVE_BYTES)
    if nivel:
        hallazgos.append(hallazgo(nivel, "tamanos", f"Lo publicado ocupa {total / 1024 ** 2:.0f} MiB "
                                  "(límite de Pages: 1 GB).", "",
                                  "aplica las salidas de ARQUITECTURA.md §7."))
    return hallazgos


# ---------------------------------------------------------------------------
# Ejecución
# ---------------------------------------------------------------------------

def ultima_edicion(raiz: pathlib.Path) -> str | None:
    ids = sorted(p.stem for p in (raiz / "data").glob("*.json")
                 if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.stem))
    return ids[-1] if ids else None


# Comprobaciones sobre los datos de la edición (no sobre el código).
COMPROBACIONES_DE_DATOS = {"titulares", "duplicados"}


def ejecutar(raiz: pathlib.Path, modo: str, fecha: str | None = None) -> dict:
    """Corre todas las comprobaciones y devuelve el informe."""
    fecha = fecha or ultima_edicion(raiz)
    comprobaciones = [
        ("carpetas", lambda: comprobar_carpetas(raiz)),
        ("html", lambda: comprobar_html(raiz)),
        ("sitemap", lambda: comprobar_sitemap(raiz)),
        ("indice", lambda: comprobar_indice(raiz)),
        ("titulares", lambda: comprobar_titulares(raiz, fecha) if fecha else []),
        ("duplicados", lambda: comprobar_duplicados(raiz, fecha) if fecha else []),
        ("tamanos", lambda: comprobar_tamanos(raiz)),
    ]
    hallazgos: list[dict] = []
    for nombre, fn in comprobaciones:
        try:
            hallazgos.extend(fn())
        except Exception as exc:                              # noqa: BLE001
            # Un fallo del propio verificador es grave: si no, una comprobación
            # rota pasaría por verde.
            hallazgos.append(hallazgo(GRAVE, nombre, f"La comprobación falló: {exc!r}.",
                                      "tools/verificar.py", "corrige el verificador con un test."))
    if modo == "ci":
        # El CI juzga el código; los datos los juzga la salud diaria. (e) y (f)
        # miran la última edición de data/, que escribió el pase diario y que
        # ninguna PR puede corregir (la edición se rehace con el código nuevo
        # solo después de fusionar). Ahí un grave bloquearía cualquier PR, así
        # que en el CI pasan a aviso; en modo diario siguen siendo graves y
        # abren la incidencia. Decidido el 5-10-2026 con el mantenedor.
        for h in hallazgos:
            if h["nivel"] == GRAVE and h["comprobacion"] in COMPROBACIONES_DE_DATOS:
                h["nivel"] = AVISO
                h["detalle"] = "(datos: grave en la salud diaria, no bloquea el CI) " + h["detalle"]
    if os.environ.get("SALUD_FORZAR_GRAVE") == "1":
        # Solo para probar la apertura de la incidencia en una rama de pruebas.
        hallazgos.append(hallazgo(GRAVE, "forzado", "Hallazgo grave forzado con "
                                  "SALUD_FORZAR_GRAVE=1.", "", "quita la variable de entorno."))
    graves = sum(1 for h in hallazgos if h["nivel"] == GRAVE)
    # Sin marca de hora a propósito: debug/salud.json se commitea con la
    # edición y, si nada cambia, un segundo pase no debe dejar commit.
    return {"esquema": 1, "modo": modo, "fecha": fecha, "graves": graves, "avisos": len(hallazgos) - graves, "hallazgos": hallazgos}


def markdown(informe: dict) -> str:
    lineas = [f"### Salud de la edición {informe.get('fecha') or ''} ({informe['modo']})", "",
              f"**{informe['graves']} graves** · {informe['avisos']} avisos", ""]
    for nivel in (GRAVE, AVISO):
        lista = [h for h in informe["hallazgos"] if h["nivel"] == nivel]
        if not lista:
            continue
        lineas.append(f"#### {'Graves' if nivel == GRAVE else 'Avisos'}")
        for h in lista[:200]:
            donde = f" `{h['fichero']}`" if h["fichero"] else ""
            lineas.append(f"- **{h['comprobacion']}**{donde}: {h['detalle']}")
        if len(lista) > 200:
            lineas.append(f"- … y {len(lista) - 200} más (ver debug/salud.json).")
        lineas.append("")
    if not informe["hallazgos"]:
        lineas.append("Sin hallazgos.")
    return "\n".join(lineas) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    ap.add_argument("--modo", choices=["ci", "diario"], required=True)
    ap.add_argument("--fecha", help="edición a revisar en (e) y (f); por defecto, la última de data/")
    ap.add_argument("--raiz", default=str(RAIZ))
    ap.add_argument("--salida", help="JSON del informe (en modo diario, debug/salud.json)")
    ap.add_argument("--markdown", help="copia del resumen en Markdown (cuerpo de la incidencia)")
    args = ap.parse_args(argv)
    raiz = pathlib.Path(args.raiz).resolve()

    informe = ejecutar(raiz, args.modo, args.fecha)
    resumen = markdown(informe)
    print(resumen)

    salida = args.salida or (str(raiz / "debug" / "salud.json") if args.modo == "diario" else None)
    if salida:
        pathlib.Path(salida).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(salida).write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n",
                                        encoding="utf-8")
    if args.markdown:
        pathlib.Path(args.markdown).write_text(resumen, encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(resumen)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"graves={informe['graves']}\navisos={informe['avisos']}\n")

    # En modo diario nunca se falla: la edición se publica igual.
    return 1 if args.modo == "ci" and informe["graves"] else 0


if __name__ == "__main__":
    sys.exit(main())
