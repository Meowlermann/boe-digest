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

ROOT = pathlib.Path(__file__).parent
ESTADO = ROOT / "state" / "empleo.json"
VERSION = 1
SECCIONES = ("2B",)              # código de la II.B en la API de datos abiertos
VENTANA_ESTADO = 400             # días que guarda el estado (regla 7: nada crece sin límite)
VENTANA_PAGINAS = 90             # días que enseñan las fichas
DIAS_PORTADA = 14                # días que enseña /empleo/
MAX_FILAS = 300                  # tope de filas por página

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


def nombre_dept(dept: str) -> str:
    """«MINISTERIO DEL INTERIOR» -> «Ministerio del Interior»."""
    menores = {"de", "del", "la", "las", "el", "los", "y", "e", "para", "con", "en", "a"}
    palabras = " ".join((dept or "").split()).lower().split(" ")
    out = [p if (i and p in menores) else p[:1].upper() + p[1:] for i, p in enumerate(palabras)]
    return " ".join(out)


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
    incorporar(regs, fecha, fuente)
    return len(regs), dict(extraer.ultimos_descartes)


# --------------------------------------------------------------------- páginas

def _regs(estado: dict, hoy: str, dias: int) -> list[dict]:
    corte = (dt.date.fromisoformat(hoy) - dt.timedelta(days=dias)).isoformat()
    regs = [{"id": k, **v} for k, v in estado["registros"].items() if v.get("fecha", "") >= corte]
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

    def fila(r: dict, con_dept: bool = True) -> str:
        enlace = r.get("url") or url_boe(r["id"])
        dept = f" · {esc(nombre_dept(r['dept']))}" if con_dept and r.get("dept") else ""
        epi = f" · {esc(r['epi'])}" if r.get("epi") else ""
        return (f'<li><a href="{attr(enlace)}" target="_blank" rel="noopener">{esc(r["titulo"])}</a>'
                f'<span class="ref">{esc(r["id"])} · {esc(fecha_es(r["fecha"]))} · '
                f'{esc(ETIQUETA_TIPO.get(r["tipo"], ""))}{dept}{epi}</span></li>')

    def por_tipo(filas: list, con_dept: bool = True) -> str:
        html = ""
        for t, et, _rx in TIPOS:
            xs = [r for r in filas if r["tipo"] == t][:MAX_FILAS]
            if xs:
                html += (f'<h2 id="t-{t}">{esc(et)} ({len(xs)})</h2>'
                         f'<ul class="ix-lista">{"".join(fila(r, con_dept) for r in xs)}</ul>')
        return html

    def recuento(filas: list) -> str:
        return "".join(f"<dt>{esc(et)}</dt><dd>{n}</dd>" for t, et, _ in TIPOS
                       if (n := sum(1 for r in filas if r["tipo"] == t)))

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
            "FICHA": f"<dt>Disposiciones</dt><dd>{len(filas)}</dd>" + recuento(filas),
            "CUERPO": cuerpo,
            "FUENTE": ('Fuente: sumario del Boletín Oficial del Estado, sección II.B «Oposiciones y '
                       'concursos» (API de datos abiertos). Cada disposición enlaza a su texto en el BOE, '
                       'que es el único que da fe: plazos y requisitos, allí.'),
            "RELACIONADAS": "", "RELACIONADAS_HIDDEN": "hidden",
        })
        salidas.append({"url": url, "lastmod": lastmod})

    # Fichas por departamento.
    enlaces_dept = []
    for s, (nombre, filas) in sorted(por_dept.items(), key=lambda x: x[1][0]):
        pagina(f"{s}.html", f"Empleo público: {nombre}",
               f"Oposiciones, concursos y listas de {nombre} publicadas en el BOE en los últimos "
               f"{VENTANA_PAGINAS} días, con enlace a cada disposición.",
               nombre, f"Lo que {nombre} ha publicado en la sección II.B del BOE (oposiciones y "
               f"concursos) en los últimos {VENTANA_PAGINAS} días.",
               filas, por_tipo(filas, con_dept=False), nombre)
        enlaces_dept.append(f'<li><a href="{attr(s)}.html">{esc(nombre)}</a>'
                            f'<span class="ref">{len(filas)}</span></li>')
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
    # Índice.
    corte = (dt.date.fromisoformat(hoy) - dt.timedelta(days=DIAS_PORTADA)).isoformat()
    recientes = [r for r in regs if r["fecha"] >= corte] or regs[:MAX_FILAS]
    cuerpo = (f'<p>Disposiciones de los últimos {DIAS_PORTADA} días. Por organismo y por provincia, '
              f'los últimos {VENTANA_PAGINAS}.</p>' + (por_tipo(recientes) or
              '<p>Aún no hay disposiciones recogidas: la sección se llena con cada BOE nuevo.</p>')
              + f'<h2 id="organismos">Por organismo convocante</h2><ul class="ix-lista">{"".join(enlaces_dept)}</ul>'
              + (f'<h2 id="provincias">Por provincia</h2><ul class="ix-lista">{"".join(enlaces_prov)}</ul>'
                 if enlaces_prov else "")
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
