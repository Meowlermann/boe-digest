"""Preguntas al Gobierno: las orales de la sesión de control y las escritas.

Dos fuentes oficiales del Congreso, ninguna nueva dependencia:

(A) Preguntas orales en Pleno. Salen del volcado de intervenciones que ya se
    descarga para las fichas de diputados (congreso_datos.preguntas_orales).
    El volcado va con retraso: por eso cada pieza lleva la fecha REAL de la
    sesión, y una sesión ya publicada no se vuelve a presentar como nueva.

(B) Preguntas con respuesta escrita (expedientes 184/…). El Congreso no ofrece
    un conjunto de datos abierto con ellas (comprobado en
    congreso.es/es/opendata/iniciativas en septiembre de 2026: solo hay
    iniciativas legislativas, proyectos, proposiciones y propuestas de
    reforma). Y los BOCG de la serie D ya no las traen todas: varios números
    consecutivos de septiembre de 2026 no contienen ningún 184/. Lo que sí es
    completo es el buscador de iniciativas del propio Congreso:
      - el listado (POST filtrarListado, 25 por página, de la más reciente a
        la más antigua): expediente, título, autor, fechas de presentación y
        calificación;
      - la ficha de cada iniciativa (GET mostrarDetalle, HTML servido): fecha
        de publicación en el BOCG, fecha de contestación del Gobierno, plazo
        vigente («Plazos Hasta: dd/mm/aaaa») y boletín de la contestación.
    Se guarda un estado compacto, sin textos completos, en
    state/preguntas_escritas.json.

Nada de lo que va entre comillas en los titulares es nuestro: la pregunta oral
y el título de la iniciativa se copian tal cual de la fuente.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import re

import congreso_datos as cd

ROOT = pathlib.Path(__file__).parent
ESTADO_ESCRITAS = ROOT / "state" / "preguntas_escritas.json"
ESTADO_ORALES = ROOT / "state" / "preguntas_orales.json"

BUSCADOR = "https://www.congreso.es/es/busqueda-de-iniciativas"
LISTADO = (BUSCADOR + "?p_p_id=iniciativas&p_p_lifecycle=2&p_p_state=normal&p_p_mode=view"
           "&p_p_resource_id=filtrarListado&p_p_cacheability=cacheLevelPage"
           "&_iniciativas_mode=verListadoIndice&_iniciativas_tipo=184&_iniciativas_legislatura=15")
DETALLE = (BUSCADOR + "?p_p_id=iniciativas&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view"
           "&_iniciativas_mode=mostrarDetalle&_iniciativas_legislatura=XV&_iniciativas_id={exp}")

# Plazo de contestación. Artículo 190.1 del Reglamento del Congreso: «La
# contestación por escrito a las preguntas deberá realizarse dentro de los
# veinte días siguientes a su publicación, pudiendo prorrogarse este plazo a
# petición motivada del Gobierno y por acuerdo de la Mesa del Congreso, por
# otro plazo de hasta veinte días más». Artículo 90: los plazos por días se
# cuentan en días HÁBILES y se excluyen los periodos sin sesiones (salvo que
# el asunto esté incluido en el orden del día de una sesión extraordinaria).
#
# Como contar días hábiles bien exige el calendario de sesiones y de festivos,
# que no tenemos, la fecha límite que se usa es la que publica el propio
# Congreso en la ficha de cada pregunta («Plazos Hasta»), que ya incorpora
# prórrogas y periodos inhábiles. PLAZO_DIAS_HABILES solo sirve de respaldo
# cuando esa fecha no aparece y para explicarlo en la metodología.
PLAZO_DIAS_HABILES = 20

# Presupuesto de peticiones por ejecución: la edición no puede tardar horas.
MAX_PAGINAS_LISTADO = 30        # 25 preguntas por página
MAX_FICHAS = 300                # fichas de detalle
# Solo se conserva un año de preguntas: con unas 40 al día son ~15.000
# expedientes, ~2,5 MB en state/. Más atrás no aporta a «hoy» ni a pendientes.
VENTANA_DIAS = 365

MAX_RESPUESTAS_EN_PORTADA = 6


# ------------------------------------------------------------------ utilidades

def _iso(ddmmaaaa: str) -> str | None:
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})", ddmmaaaa or "")
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else None


def _dias(desde: str | None, hasta: str | None) -> int | None:
    if not desde or not hasta:
        return None
    return (dt.date.fromisoformat(hasta) - dt.date.fromisoformat(desde)).days


def dias_habiles(desde: str | None, hasta: str | None) -> int | None:
    """Lunes a viernes entre dos fechas, sin enero, julio ni agosto (fuera del
    periodo de sesiones, art. 73.1 del Reglamento). No descuenta festivos: es
    una aproximación y así se dice en la metodología."""
    if not desde or not hasta:
        return None
    a, b = dt.date.fromisoformat(desde), dt.date.fromisoformat(hasta)
    n, d = 0, a
    while d < b:
        d += dt.timedelta(days=1)
        if d.weekday() < 5 and d.month not in (1, 7, 8):
            n += 1
    return n


def url_ficha(exp: str) -> str:
    return DETALLE.format(exp=exp.replace("/", "%2F"))


def autores_de(texto: str) -> list:
    """«Fúnez de Gregorio, Carmen (GP) Velasco Morillo, Elvira (GP)» ->
    [("Fúnez de Gregorio, Carmen", "GP"), ("Velasco Morillo, Elvira", "GP")]."""
    return [(" ".join(n.split()), g.strip())
            for n, g in re.findall(r"([^(),]+?,\s*[^(),]+?)\s*\(([^)]+)\)", texto or "")]


def _texto_html(html: str) -> str:
    html = re.sub(r"<script[\s\S]*?</script>", " ", html)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def parsear_ficha(html: str) -> dict:
    """Los datos de una ficha de pregunta escrita. Formatos comprobados en
    fichas reales de 2023 y 2026 (contestadas, pendientes y recién
    publicadas)."""
    t = _texto_html(html)
    d: dict = {}
    m = re.search(r"respuesta escrita\.\s*(.+?)\s*\((184/\d{6})\)", t)
    if m:
        d["t"] = m.group(1).strip()[:220]
    m = re.search(r"Presentado el (\d\d/\d\d/\d{4})", t)
    if m:
        d["pr"] = _iso(m.group(1))
    m = re.search(r"Autore?s?\s+(.+?)\s+(?:Situación actual|Resultado tramitación|"
                  r"Tramitación seguida)", t)
    if m:
        d["a"] = [n for n, _g in autores_de(m.group(1))]
        d["g"] = sorted({g for _n, g in autores_de(m.group(1))})
    # Publicación: la fecha del boletín en que salió la pregunta.
    m = re.search(r"Núm\.\s*D-\d+\s+de\s+(\d\d/\d\d/\d{4})\s+Iniciativa", t)
    if not m:
        m = re.search(r"Publicación desde \d\d/\d\d/\d{4} hasta (\d\d/\d\d/\d{4})", t)
    if m:
        d["p"] = _iso(m.group(1))
    # Contestación del Gobierno: el tramo «Gobierno Contestación» se cierra
    # («hasta») cuando llega la respuesta.
    m = re.search(r"Gobierno Contestación desde \d\d/\d\d/\d{4} hasta (\d\d/\d\d/\d{4})", t)
    d["c"] = _iso(m.group(1)) if m else None
    m = re.search(r"Núm\.\s*(D-\d+)\s+de\s+(\d\d/\d\d/\d{4})\s+Contestación del Gobierno", t)
    d["cb"] = f"{m.group(1)}|{_iso(m.group(2))}" if m else None
    m = re.search(r"Plazos\s+Hasta:\s*(\d\d/\d\d/\d{4})", t)
    d["lim"] = _iso(m.group(1)) if m else None
    m = re.search(r"Resultado tramitación\s+(.+?)\s+Tramitación seguida", t)
    d["res"] = m.group(1).strip()[:80] if m else None
    return d


# --------------------------------------------------------------------- estado

def _cargar(ruta: pathlib.Path, vacio: dict) -> dict:
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except Exception:                                          # noqa: BLE001
        return vacio


def cargar_escritas() -> dict:
    e = _cargar(ESTADO_ESCRITAS, {})
    e.setdefault("esquema", 1)
    e.setdefault("exp", {})
    e.setdefault("listado", {"siguiente": 1, "completo": False})
    return e


def _guardar(ruta: pathlib.Path, e: dict) -> None:
    ruta.parent.mkdir(exist_ok=True)
    ruta.write_text(json.dumps(e, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


# ----------------------------------------------------------- descarga (B)

def _pagina_listado(post, n: int) -> list:
    r = post(LISTADO, {"_iniciativas_legislatura": "15", "_iniciativas_tipo": "184",
                       "_iniciativas_paginaActual": str(n)})
    if not r:
        return []
    try:
        lista = (r.json().get("lista_iniciativas") or {}).values()
    except Exception:                                          # noqa: BLE001
        return []
    return [x for x in lista if isinstance(x, dict) and x.get("id_iniciativa")]


def _alta(e: dict, x: dict, hoy: str | None) -> bool:
    """Registra una pregunta del listado. `hoy` marca las novedades del día
    (para el marcador); las que entran al recorrer el histórico van sin fecha
    de alta, porque no son de hoy aunque las leamos hoy."""
    exp = x["id_iniciativa"].strip()
    if exp in e["exp"]:
        return False
    autores = autores_de(x.get("autor", ""))
    e["exp"][exp] = {
        "a": [n for n, _g in autores] or [" ".join((x.get("autor") or "").split())],
        "g": sorted({g for _n, g in autores}),
        "t": " ".join((x.get("titulo") or "").split())[:220],
        "pr": _iso(x.get("fecha_presentado", "")),
        "p": None, "c": None, "cb": None, "lim": None, "res": None,
        "alta": hoy, "rev": None,
    }
    return True


def actualizar_escritas(get, post, log) -> dict:
    """Pone al día el estado: preguntas nuevas del listado y fichas de detalle
    de las que faltan o siguen pendientes. Devuelve lo que ha cambiado hoy."""
    e = cargar_escritas()
    hoy = dt.date.today().isoformat()
    # En la primera ejecución todo es histórico: nada cuenta como «de hoy».
    primera_vez = not e["exp"]
    corte = (dt.date.today() - dt.timedelta(days=VENTANA_DIAS)).isoformat()
    cambios = {"nuevas": [], "contestadas": []}
    paginas = 0

    # 1) Novedades: desde la primera página hasta encontrar una sin nada nuevo.
    n, ultima_leida = 1, 0
    while paginas < MAX_PAGINAS_LISTADO:
        lista = _pagina_listado(post, n)
        paginas += 1
        ultima_leida = n
        if not lista:
            break
        altas = [x["id_iniciativa"] for x in lista
                 if _alta(e, x, None if primera_vez else hoy)]
        cambios["nuevas"] += altas
        if not altas:
            break
        n += 1

    # 2) Histórico, a plazos, hasta cubrir la ventana. Las páginas que ya se
    #    han leído arriba cuentan: el puntero sigue desde ahí. (Si entran
    #    preguntas nuevas, las antiguas se desplazan a páginas posteriores y
    #    alguna página se relee; nunca se salta ninguna.)
    lst = e["listado"]
    if not lst.get("completo"):
        lst["siguiente"] = max(lst.get("siguiente", 1), ultima_leida + 1)
    while not lst.get("completo") and paginas < MAX_PAGINAS_LISTADO:
        lista = _pagina_listado(post, lst.get("siguiente", 1))
        paginas += 1
        if not lista:
            lst["completo"] = True
            break
        for x in lista:
            _alta(e, x, None)
        lst["siguiente"] = lst.get("siguiente", 1) + 1
        if all((_iso(x.get("fecha_presentado", "")) or hoy) < corte for x in lista):
            lst["completo"] = True

    # 3) Fichas: primero las nunca leídas (de la más nueva a la más antigua),
    #    después las pendientes que llevan más tiempo sin revisar.
    sin_leer = sorted((k for k, v in e["exp"].items() if not v.get("rev")), reverse=True)
    pendientes = sorted((k for k, v in e["exp"].items() if v.get("rev") and not v.get("c")
                         and not v.get("res")),
                        key=lambda k: e["exp"][k]["rev"])
    # Reparto del presupuesto: mientras se completa el histórico, sin reservar
    # sitio para revisar pendientes ninguna contestación se detectaría durante
    # semanas. Lo que una parte no gasta, lo usa la otra.
    cupo_rev = min(len(pendientes), MAX_FICHAS * 2 // 5)
    cupo_nuevas = min(len(sin_leer), MAX_FICHAS - cupo_rev)
    cupo_rev = min(len(pendientes), MAX_FICHAS - cupo_nuevas)
    leidas = 0
    for exp in sin_leer[:cupo_nuevas] + pendientes[:cupo_rev]:
        r = get(url_ficha(exp), tries=1)
        if not r:
            continue
        datos = parsear_ficha(r.text)
        if not datos.get("t") and not datos.get("pr"):
            continue                        # ficha vacía o formato inesperado
        v = e["exp"][exp]
        contestaba = v.get("c")
        # Solo es «contestada hoy» si ya la habíamos visto pendiente: la
        # primera lectura de una pregunta antigua ya contestada no es noticia.
        vista_pendiente = bool(v.get("rev")) and not contestaba
        for k in ("t", "pr", "a", "g"):
            if datos.get(k):
                v[k] = datos[k]
        for k in ("p", "c", "cb", "lim", "res"):
            v[k] = datos.get(k)
        v["rev"] = hoy
        leidas += 1
        if v.get("c") and vista_pendiente:
            v["vista_c"] = hoy
            cambios["contestadas"].append(exp)

    # 4) Poda: fuera lo presentado antes de la ventana.
    for k in [k for k, v in e["exp"].items() if (v.get("pr") or hoy) < corte]:
        del e["exp"][k]

    e["actualizado"] = hoy
    _guardar(ESTADO_ESCRITAS, e)
    log(f"preguntas escritas: {len(cambios['nuevas'])} nuevas, "
        f"{len(cambios['contestadas'])} contestadas detectadas, {leidas} fichas, "
        f"{paginas} páginas de listado, {len(e['exp'])} en el estado "
        f"({ESTADO_ESCRITAS.stat().st_size // 1024} KB)")
    return cambios


# ------------------------------------------------------------------ cálculos

def pendientes_vencidas(e: dict, hoy: str | None = None) -> list:
    """Publicadas, sin contestación registrada y con el plazo vencido. Plazo:
    el que publica el Congreso en la ficha; si no aparece, 20 días hábiles
    desde la publicación (art. 190.1)."""
    hoy = hoy or dt.date.today().isoformat()
    salida = []
    for exp, v in e["exp"].items():
        if v.get("c") or v.get("res") or not v.get("p"):
            continue
        limite = v.get("lim")
        vencida = (limite < hoy) if limite else (
            (dias_habiles(v["p"], hoy) or 0) > PLAZO_DIAS_HABILES)
        if vencida:
            salida.append((exp, v))
    return sorted(salida, key=lambda x: x[1]["p"])


def contestadas_hoy(e: dict, hoy: str | None = None) -> list:
    hoy = hoy or dt.date.today().isoformat()
    return sorted(((k, v) for k, v in e["exp"].items() if v.get("vista_c") == hoy),
                  key=lambda x: -(_dias(x[1].get("p"), x[1].get("c")) or 0))


def por_grupo(items) -> list:
    cuenta: dict = {}
    for _k, v in items:
        for g in v.get("g") or ["Sin grupo"]:
            cuenta[g] = cuenta.get(g, 0) + 1
    return sorted(({"g": grupo_corto(g), "n": n} for g, n in cuenta.items()),
                  key=lambda r: (-r["n"], r["g"]))


# ------------------------------------------------------------ piezas del feed

def grupo_corto(codigo: str) -> str:
    """«GP» -> «PP», «GMx» -> «Mixto»: el nombre corto que usa todo el sitio."""
    largo = cd.COD_GRUPO.get(codigo)
    return cd.GRUPO_CORTO.get(largo, cd.SIGLAS.get(codigo, codigo)) if largo else \
        cd.SIGLAS.get(codigo, codigo)


def _apellidos(nombre: str) -> str:
    return (nombre.split(",")[0] if "," in nombre else nombre).strip().upper()


def _recortar(t: str, n: int) -> str:
    t = " ".join((t or "").split())
    if len(t) <= n:
        return t
    corte = t[:n].rsplit(" ", 1)[0].rstrip(" ,;:")
    return corte + "…"


def _cargo_titular(cargo: str) -> str:
    """«Vicepresidente Primero del Gobierno y Ministro de Economía…» -> «AL
    MINISTRO DE ECONOMÍA, COMERCIO Y EMPRESA». El cargo es el que figura en el
    volcado; solo se elige la parte ministerial cuando hay dos."""
    c = " ".join((cargo or "").split())
    if not c:
        return "AL GOBIERNO"
    m = re.search(r"\b(Ministr[oa]\b.*)$", c)
    if m and " y " in c:
        c = m.group(1)
    art = "A LA" if re.match(r"(Ministra|Vicepresidenta|Presidenta)\b", c) else "AL"
    return f"{art} {c.upper()}"


def _fecha_larga(iso: str, fmt_date_es) -> str:
    """«miércoles 23 de septiembre de 2026», sin la coma de fmt_date_es."""
    return fmt_date_es(iso).replace(",", "") if iso else ""


def piezas_orales(ses: dict, fmt_date_es, site_url: str) -> list:
    fecha_txt = _fecha_larga(ses["fecha"], fmt_date_es)
    piezas = []
    for p in ses["preguntas"]:
        grupo = grupo_corto(p["grupo"])
        titular = (f'{_apellidos(p["autor"])} ({grupo}) {_cargo_titular(p["cargo"])}: '
                   f'«{_recortar(p["texto"], 150)}»')
        cuerpo = [f'Pregunta: {p["autor_natural"]} ({grupo}). Expediente {p["expediente"]}.',
                  f'Texto registrado: «{p["texto"]}»']
        cuerpo.append(f'Contesta: {cd.nombre_natural(p["contesta"])}, {p["cargo"]}.'
                      if p["contesta"] else
                      "El volcado del Congreso no registra contestación del Gobierno.")
        if p["video"]:
            cuerpo.append(f'Ver en vídeo: {p["video"]}')
        enlaces = []
        if p.get("slug"):
            enlaces.append({"label": f'Ficha de {p["autor_natural"]}',
                            "url": f'{site_url}diputados/{p["slug"]}.html'})
        piezas.append({
            "chamber": "congreso",
            "type": "Pregunta oral",
            "date": fecha_txt,
            "headline": titular,
            "standfirst": f"Sesión de control del {fecha_txt} · Pleno del Congreso",
            "quote": {"text": p["texto"], "author": f'{p["autor_natural"]} ({grupo})'},
            "body": cuerpo,
            "source": ({"label": "Ver en vídeo", "url": p["video"]} if p["video"] else
                       {"label": "Intervenciones del Congreso",
                        "url": cd.PAG_INTERVENCIONES}),
            "links": enlaces,
            "expediente": p["expediente"],
        })
    return piezas


def aviso_sin_sesion(ultima: dict, fmt_date_es, site_url: str) -> dict:
    fecha_txt = _fecha_larga(ultima["fecha"], fmt_date_es)
    ed = ultima.get("edicion", "")
    return {
        "chamber": "congreso",
        "type": "Preguntas orales",
        "date": fecha_txt,
        "headline": f"Sin sesión de control nueva desde el {fecha_txt}",
        "standfirst": ("El volcado de intervenciones del Congreso no trae ninguna sesión de "
                       "control posterior. Las preguntas de esa sesión ya se publicaron."),
        "body": [f"La última sesión de control publicada es la del {fecha_txt}, en la edición "
                 f"del {_fecha_larga(ed, fmt_date_es)}.",
                 "El Congreso publica las intervenciones con algunos días de retraso."],
        "source": {"label": f"Edición del {_fecha_larga(ed, fmt_date_es)}",
                   "url": f"{site_url}ediciones/{ed}.html#cortes-1"},
    }


def feed_orales(filas: list, censo: dict, hoy: str, fmt_date_es, site_url: str) -> list:
    """Piezas de preguntas orales para la edición de hoy, sin republicar como
    nueva una sesión que ya salió en una edición anterior."""
    ses = cd.preguntas_orales(filas, censo)
    estado = _cargar(ESTADO_ORALES, {"publicadas": {}, "ultima": None})
    if not ses:
        ult = estado.get("ultima")
        return [aviso_sin_sesion(ult, fmt_date_es, site_url)] if ult else []
    publicada_en = estado["publicadas"].get(ses["fecha"])
    if publicada_en and publicada_en != hoy:
        return [aviso_sin_sesion({"fecha": ses["fecha"], "edicion": publicada_en},
                                 fmt_date_es, site_url)]
    estado["publicadas"][ses["fecha"]] = hoy
    estado["ultima"] = {"fecha": ses["fecha"], "edicion": hoy,
                        "expedientes": [p["expediente"] for p in ses["preguntas"]]}
    _guardar(ESTADO_ORALES, estado)
    return piezas_orales(ses, fmt_date_es, site_url)


def feed_escritas(e: dict, fmt_date_es, site_url: str) -> tuple[list, dict | None]:
    """Respuestas registradas hoy (las de más tardanza primero), el contador de
    pendientes y el marcador por grupo."""
    piezas = []
    hoy = dt.date.today().isoformat()
    contestadas = contestadas_hoy(e, hoy)
    for exp, v in contestadas[:MAX_RESPUESTAS_EN_PORTADA]:
        autor = (v.get("a") or ["—"])[0]
        grupo = ", ".join(grupo_corto(g) for g in v.get("g") or []) or "—"
        naturales = _dias(v.get("p"), v.get("c"))
        habiles = dias_habiles(v.get("p"), v.get("c"))
        otros = f" y {len(v['a']) - 1} más" if len(v.get("a") or []) > 1 else ""
        piezas.append({
            "chamber": "congreso",
            "type": "Respuesta escrita",
            "date": _fecha_larga(v.get("c"), fmt_date_es),
            "headline": (f'EL GOBIERNO CONTESTA A {_apellidos(autor)} ({grupo}) '
                         f'{naturales} DÍAS DESPUÉS: «{_recortar(v.get("t", ""), 140)}»'),
            "standfirst": (f"Pregunta {exp}, publicada el {_fecha_larga(v.get('p'), fmt_date_es)}; "
                           f"contestación registrada el {_fecha_larga(v.get('c'), fmt_date_es)}."),
            "body": [f"Pregunta de {cd.nombre_natural(autor)}{otros} ({grupo}).",
                     f"Título de la iniciativa: «{v.get('t', '')}»",
                     f"Entre la publicación en el BOCG y la contestación: {naturales} días "
                     f"naturales, unos {habiles} hábiles.",
                     "Las contestaciones escritas las remite el Gobierno en su conjunto; la "
                     "ficha oficial no indica qué ministerio la redacta."],
            "source": {"label": f"Ficha oficial de la pregunta {exp}", "url": url_ficha(exp)},
        })
    if len(contestadas) > len(piezas):
        piezas.append({
            "chamber": "congreso", "type": "Respuestas escritas",
            "date": _fecha_larga(hoy, fmt_date_es),
            "headline": f"{len(contestadas)} contestaciones del Gobierno registradas hoy",
            "standfirst": "Aquí van las que más tardaron; el resto, en la sección de preguntas.",
            "body": [f"{len(contestadas)} preguntas escritas han pasado hoy a tener "
                     "contestación registrada en su ficha oficial."],
            "source": {"label": "Todas las preguntas", "url": f"{site_url}preguntas/"},
        })

    vencidas = pendientes_vencidas(e, hoy)
    if vencidas:
        mas_antigua = vencidas[0][1]
        piezas.append({
            "chamber": "congreso",
            "type": "Preguntas pendientes",
            "date": _fecha_larga(hoy, fmt_date_es),
            "headline": (f"{len(vencidas)} preguntas escritas llevan más de "
                         f"{PLAZO_DIAS_HABILES} días hábiles desde su publicación sin "
                         f"contestación registrada"),
            "standfirst": ("Recuento sobre las preguntas del último año con la fecha límite que "
                           "publica el Congreso ya superada. Puede haber prórrogas o respuestas "
                           "aún no reflejadas en la ficha."),
            "body": [f"La más antigua se publicó el {_fecha_larga(mas_antigua['p'], fmt_date_es)}.",
                     "Por grupo de quien pregunta: " + ", ".join(
                         f"{r['g']} {r['n']}" for r in por_grupo(vencidas)) + "."],
            "source": {"label": "Pendientes más antiguas", "url": f"{site_url}preguntas/#pendientes"},
        })

    nuevas = [(k, v) for k, v in e["exp"].items() if v.get("alta") == hoy]
    scoreboard = None
    if nuevas:
        scoreboard = {"note": (f"Preguntas escritas registradas desde la última edición "
                               f"({len(nuevas)}), por grupo de quien pregunta."),
                      "rows": por_grupo(nuevas)[:10]}
    elif vencidas:
        scoreboard = {"note": ("Preguntas escritas con el plazo superado y sin contestación "
                               "registrada, por grupo de quien pregunta."),
                      "rows": por_grupo(vencidas)[:10]}
    return piezas, scoreboard


# ------------------------------------------------------------------ páginas

def resumen_diputados(e: dict) -> dict:
    """{clave_nombre: {"total", "contestadas", "media_dias", "ultimas": [...]}}
    para la sección #preguntas de cada ficha."""
    salida: dict = {}
    for exp, v in e.get("exp", {}).items():
        for autor in v.get("a") or []:
            s = salida.setdefault(cd.clave_nombre(autor),
                                  {"total": 0, "contestadas": 0, "dias": [], "ultimas": []})
            s["total"] += 1
            if v.get("c"):
                s["contestadas"] += 1
                d = _dias(v.get("p"), v.get("c"))
                if d is not None:
                    s["dias"].append(d)
            s["ultimas"].append((exp, v))
    for s in salida.values():
        s["media_dias"] = round(sum(s["dias"]) / len(s["dias"])) if s["dias"] else None
        s["ultimas"] = sorted(s["ultimas"], key=lambda x: x[1].get("pr") or "", reverse=True)[:10]
        del s["dias"]
    return salida


def seccion_diputado(resumen: dict | None, esc, fmt_date_es) -> str:
    if not resumen or not resumen["total"]:
        return ""
    filas = []
    for exp, v in resumen["ultimas"]:
        estado = (f"contestada el {fmt_date_es(v['c'])} ({_dias(v.get('p'), v['c'])} días)"
                  if v.get("c") else (v.get("res") or "sin contestación registrada"))
        filas.append(f'<li><a href="{esc(url_ficha(exp))}" rel="noopener" target="_blank">'
                     f'{esc(v.get("t", exp))}</a><span class="ref">{esc(exp)} · '
                     f'{esc(estado)}</span></li>')
    media = (f" Tiempo medio hasta la contestación: {resumen['media_dias']} días naturales."
             if resumen.get("media_dias") is not None else "")
    return (f'<h2 class="rotulo" id="preguntas">Preguntas escritas</h2>'
            f'<p class="rk-nota">En los últimos doce meses ha firmado {resumen["total"]} preguntas '
            f'con respuesta escrita; {resumen["contestadas"]} tienen contestación registrada.'
            f'{esc(media)}</p><ul class="indice">{"".join(filas)}</ul>'
            f'<p><a class="srclink" href="../preguntas/">Todas las preguntas escritas</a></p>')


def generar_paginas(h: dict) -> list:
    """/preguntas/index.html, una página por grupo y la metodología."""
    e = cargar_escritas()
    if not e["exp"]:
        return []
    esc, attr, fecha = h["esc_html"], h["esc_attr"], h["fmt_date_es"]
    carpeta, site = h["carpeta"], h["site_url"]
    carpeta.mkdir(exist_ok=True)
    hoy = dt.date.today().isoformat()
    lastmod = e.get("actualizado") or hoy
    items = list(e["exp"].items())
    contestadas = sorted((x for x in items if x[1].get("c")),
                         key=lambda x: x[1]["c"], reverse=True)
    registradas = sorted(items, key=lambda x: x[1].get("pr") or "", reverse=True)
    vencidas = pendientes_vencidas(e, hoy)
    salidas = []

    def fila(exp, v, extra=""):
        autores = ", ".join(cd.nombre_natural(a) for a in (v.get("a") or [])[:3])
        if len(v.get("a") or []) > 3:
            autores += f" y {len(v['a']) - 3} más"
        grupo = ", ".join(grupo_corto(g) for g in v.get("g") or [])
        return (f'<li><a href="{attr(url_ficha(exp))}" target="_blank" rel="noopener">'
                f'{esc(v.get("t") or exp)}</a><span class="ref">{esc(exp)} · {esc(autores)}'
                f'{" (" + esc(grupo) + ")" if grupo else ""}{extra}</span></li>')

    def pagina(nombre, titulo, desc, h1, entradilla, cuerpo, jsonld_extra=()):
        url = f"{site}preguntas/{'' if nombre == 'index.html' else nombre}"
        miga = ('<a href="../">Portada</a> › <a href="../diputados/">Parlamento</a> › '
                + ('<span aria-current="page">Preguntas</span>' if nombre == "index.html" else
                   f'<a href="./">Preguntas</a> › <span aria-current="page">{esc(h1)}</span>'))
        h["pagina_suelta"](h["plantilla"], carpeta, nombre, {
            "TITLE": esc(f"{titulo} | La Tercera Cámara"),
            "META_DESC": attr(desc),
            "CANONICAL": url,
            "JSONLD": h["jsonld_script"]([{"@type": "WebPage", "url": url, "name": titulo,
                                           "inLanguage": "es-ES", "dateModified": lastmod},
                                          *jsonld_extra]),
            "EDITION_DATE": esc(f"Datos al {fecha(lastmod)}"),
            "MIGA": miga,
            "KICKER": "Control al Gobierno",
            "HEADLINE": esc(h1),
            "STANDFIRST": esc(entradilla),
            "FICHA": (f"<dt>Preguntas en el último año</dt><dd>{len(items)}</dd>"
                      f"<dt>Con contestación</dt><dd>{len(contestadas)}</dd>"
                      f"<dt>Plazo superado sin contestación</dt><dd>{len(vencidas)}</dd>"),
            "CUERPO": cuerpo,
            "FUENTE": ('Fuente: buscador de iniciativas del Congreso de los Diputados. '
                       '<a class="srclink" href="metodologia.html">Cómo se cuenta</a>.'),
            "RELACIONADAS": "", "RELACIONADAS_HIDDEN": "hidden",
        })
        salidas.append({"url": url, "lastmod": lastmod})

    grupos = por_grupo(items)
    enlaces_grupo = "".join(
        f'<li><a href="grupo-{attr(_slug_grupo(r["g"]))}.html">{esc(r["g"])}</a>'
        f'<span class="ref">{r["n"]}</span></li>' for r in grupos)
    cuerpo = (
        f'<h2 class="rotulo" id="respuestas">Últimas contestaciones</h2>'
        f'<ul class="indice">' + "".join(
            fila(k, v, f' · contestada el {esc(fecha(v["c"]))} '
                       f'({_dias(v.get("p"), v["c"])} días)') for k, v in contestadas[:40])
        + '</ul><h2 class="rotulo" id="registradas">Últimas preguntas registradas</h2>'
        f'<ul class="indice">' + "".join(
            fila(k, v, f' · presentada el {esc(fecha(v["pr"]))}' if v.get("pr") else "")
            for k, v in registradas[:40])
        + '</ul><h2 class="rotulo" id="pendientes">Pendientes más antiguas</h2>'
        f'<p class="rk-nota">Publicadas en el BOCG, con la fecha límite que figura en la ficha '
        f'oficial ya superada y sin contestación registrada. La fecha límite incorpora el '
        f'plazo de {PLAZO_DIAS_HABILES} días hábiles del artículo 190 del Reglamento y sus '
        f'prórrogas.</p><ul class="indice">' + "".join(
            fila(k, v, f' · publicada el {esc(fecha(v["p"]))}') for k, v in vencidas[:60])
        + f'</ul><h2 class="rotulo" id="grupos">Por grupo de quien pregunta</h2>'
          f'<ul class="provincias">{enlaces_grupo}</ul>')
    pagina("index.html", "Preguntas escritas al Gobierno: respuestas y pendientes",
           "Las preguntas con respuesta escrita que los diputados dirigen al Gobierno: "
           "últimas contestaciones, últimas registradas y las que siguen sin respuesta.",
           "Lo que el Gobierno contesta… y lo que calla",
           "Preguntas con respuesta escrita del último año en el Congreso: qué se pregunta, "
           "cuándo se contesta y qué sigue pendiente.", cuerpo)

    for r in grupos:
        propias = [(k, v) for k, v in items
                   if r["g"] in [grupo_corto(g) for g in v.get("g") or ["Sin grupo"]]]
        c_prop = [x for x in propias if x[1].get("c")]
        v_prop = [x for x in vencidas if x in propias]
        tiempos = [_dias(v.get("p"), v["c"]) for _k, v in c_prop if v.get("p")]
        media = round(sum(tiempos) / len(tiempos)) if tiempos else None
        cuerpo = (
            f'<p class="rk-nota">{len(propias)} preguntas en el último año; {len(c_prop)} con '
            f'contestación registrada; {len(v_prop)} con el plazo superado sin contestación.'
            + (f' Tiempo medio hasta la contestación: {media} días naturales.' if media else "")
            + '</p><h2 class="rotulo">Últimas preguntas</h2><ul class="indice">'
            + "".join(fila(k, v) for k, v in sorted(
                propias, key=lambda x: x[1].get("pr") or "", reverse=True)[:80]) + '</ul>')
        pagina(f"grupo-{_slug_grupo(r['g'])}.html",
               f"Preguntas escritas de {r['g']} al Gobierno",
               f"Preguntas con respuesta escrita registradas por diputados de {r['g']} en el "
               f"Congreso: contestadas, pendientes y tiempo medio de respuesta.",
               f"Preguntas escritas de {r['g']}", "Mismo recuento para todos los grupos.", cuerpo)

    metod = f"""
<h2 class="rotulo">Fuentes</h2>
<p><b>Preguntas orales</b>: volcado de intervenciones de los datos abiertos del Congreso
(IntervencionesCronologicamente). Se toma la sesión de control más reciente del Pleno; cada
pregunta junta en una pieza su formulación, la contestación y las réplicas.</p>
<p><b>Preguntas escritas</b>: el Congreso no ofrece un conjunto de datos abierto con ellas.
Se usa su buscador de iniciativas (tipo 184, «Pregunta al Gobierno con respuesta escrita»): el
listado da expediente, título, autor y fechas; la ficha de cada pregunta da la fecha de
publicación en el BOCG, la de contestación del Gobierno y la fecha límite vigente.</p>
<h2 class="rotulo">Plazo</h2>
<p>Artículo 190.1 del Reglamento del Congreso: veinte días siguientes a la publicación,
prorrogables otros veinte a petición motivada del Gobierno y por acuerdo de la Mesa. El artículo
90 establece que se cuentan en días hábiles y que se excluyen los periodos sin sesiones. Para
no calcularlo mal, se usa la fecha límite que publica el propio Congreso en cada ficha, que ya
tiene en cuenta prórrogas y periodos inhábiles. Solo cuando esa fecha no aparece se cuentan
{PLAZO_DIAS_HABILES} días hábiles aproximados (lunes a viernes, sin enero, julio ni agosto, y
sin descontar festivos).</p>
<h2 class="rotulo">Cómo se cuentan los días</h2>
<p>El «tiempo hasta la contestación» son días naturales entre la publicación de la pregunta en
el BOCG y el registro de la contestación del Gobierno. Donde se indica, se da también una
aproximación en días hábiles.</p>
<h2 class="rotulo">Limitaciones</h2>
<p>El volcado de intervenciones se publica con varios días de retraso: por eso cada pieza de
preguntas orales lleva la fecha real de la sesión, y una sesión ya publicada no se presenta
otra vez como nueva. Las fichas de preguntas escritas se revisan por tandas: una contestación
puede tardar algunos días en aparecer aquí. Las preguntas retiradas, decaídas o convertidas en
orales no cuentan como pendientes. Las contestaciones escritas las remite el Gobierno en su
conjunto y la ficha no dice qué ministerio las redacta, así que no se atribuyen a ninguno.
Se conservan las preguntas presentadas en los últimos {VENTANA_DIAS} días.</p>
<h2 class="rotulo">Qué no se afirma</h2>
<p>Superar la fecha límite sin contestación registrada no se presenta como un incumplimiento:
puede haber prórrogas, contestaciones pendientes de reflejarse o preguntas que se tramitan de
otra forma (art. 190.2).</p>"""
    pagina("metodologia.html", "Cómo contamos las preguntas al Gobierno",
           "Fuentes, plazo del artículo 190 del Reglamento del Congreso, cómputo de días y "
           "limitaciones de la sección de preguntas de La Tercera Cámara.",
           "Metodología de las preguntas", "Qué se cuenta, de dónde sale y qué no se afirma.",
           metod)
    return salidas


def _slug_grupo(g: str) -> str:
    return cd._slug(g) if hasattr(cd, "_slug") else re.sub(r"[^a-z0-9]+", "-", g.lower())
