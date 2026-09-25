"""Datos abiertos del Congreso: quién vota qué, quién habla y de qué.

El BOE cuenta lo que ya es obligatorio. Esto cuenta lo otro: qué hace cada
diputado con su escaño. El Congreso publica tres cosas que, juntas, permiten
seguir a una persona concreta:

  · Diputados y Diputadas — el censo completo, regenerado cada madrugada.
  · Intervenciones — todas las de la legislatura, con orador, órgano, fase,
    hora y enlace al vídeo y al texto íntegro.
  · Votaciones — el detalle nominal de cada votación: para cada diputado, si
    votó sí, no, se abstuvo o no votó.

Las dos primeras son volcados completos y se pueden leer de una vez. La tercera
va por sesión, y el portal no deja listar directorios, así que se cosecha cada
día la sesión publicada y se acumula en state/. Eso significa que las cifras de
votación empiezan hoy y crecen; las de intervenciones nacen ya completas.

Nada de lo que hay aquí es una valoración: son recuentos de actos públicos de
cargos públicos, cada uno con su enlace a la fuente oficial. La métrica más
delicada —cuántas veces alguien vota distinto que su grupo— se calcula solo
cuando hay una mayoría clara en el grupo, y se publica como número, no como
adjetivo.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata

CONGRESO = "https://www.congreso.es"
PAG_DIPUTADOS = f"{CONGRESO}/es/opendata/diputados"
PAG_VOTACIONES = f"{CONGRESO}/es/opendata/votaciones"
PAG_INTERVENCIONES = f"{CONGRESO}/es/opendata/intervenciones"

# Los ficheros llevan una marca de tiempo en el nombre («DiputadosActivos__
# 20260922050011.json»), así que no se pueden construir: hay que leerlos de la
# página, que es la que sabe cuál es el vigente.
RE_JSON = re.compile(r'href="([^"]*/webpublica/opendata/[^"]+\.json)"', re.I)

SIGLAS = {
    "GS": "PSOE", "GP": "PP", "GVOX": "VOX", "GSUMAR": "SUMAR", "GR": "ERC",
    "GV (EAJ-PNV)": "PNV", "GEH Bildu": "EH Bildu", "GMx": "Grupo Mixto",
    "GJxCAT": "Junts", "GPlu": "SUMAR",
}


# Orden de izquierda a derecha del hemiciclo y color de cada grupo. El color
# es el de cada formación, no decoración nuestra: en un hemiciclo la gente los
# reconoce, y usar la paleta de la casa haría el gráfico ilegible. Están
# rebajados en saturación para que convivan con el papel del resto del sitio.
GRUPOS = [
    ("Grupo Parlamentario Euskal Herria Bildu",      "EH Bildu", "bildu",  "#5aa02c"),
    ("Grupo Parlamentario Republicano",              "ERC",      "erc",    "#d4a017"),
    ("Grupo Parlamentario Plurinacional SUMAR",      "Sumar",    "sumar",  "#c4267b"),
    ("Grupo Parlamentario Socialista",               "PSOE",     "psoe",   "#c8352f"),
    ("Grupo Parlamentario Mixto",                    "Mixto",    "mixto",  "#8d8d8d"),
    ("Grupo Parlamentario Vasco (EAJ-PNV)",          "PNV",      "pnv",    "#1f7a5a"),
    ("Grupo Parlamentario Junts per Catalunya",      "Junts",    "junts",  "#2a9d9b"),
    ("Grupo Parlamentario Popular en el Congreso",   "PP",       "pp",     "#2b5fa8"),
    ("Grupo Parlamentario VOX",                      "Vox",      "vox",    "#4d8b2f"),
]
GRUPO_CORTO = {largo: corto for largo, corto, _s, _c in GRUPOS}
GRUPO_SLUG = {largo: slug for largo, _c, slug, _col in GRUPOS}
GRUPO_COLOR = {largo: color for largo, _c, _s, color in GRUPOS}
ORDEN_GRUPO = {largo: i for i, (largo, *_r) in enumerate(GRUPOS)}
# Las votaciones nombran al grupo por su código; el censo, por su nombre.
COD_GRUPO = {
    "GEH Bildu": "Grupo Parlamentario Euskal Herria Bildu",
    "GR": "Grupo Parlamentario Republicano",
    "GSUMAR": "Grupo Parlamentario Plurinacional SUMAR",
    "GPlu": "Grupo Parlamentario Plurinacional SUMAR",
    "GS": "Grupo Parlamentario Socialista",
    "GMx": "Grupo Parlamentario Mixto",
    "GV (EAJ-PNV)": "Grupo Parlamentario Vasco (EAJ-PNV)",
    "GJxCAT": "Grupo Parlamentario Junts per Catalunya",
    "GP": "Grupo Parlamentario Popular en el Congreso",
    "GVOX": "Grupo Parlamentario VOX",
}


def postura_grupos(g: dict) -> dict:
    """{código de grupo: [S, N, A, X]} -> {código: letra mayoritaria}, solo
    cuando al menos el 70 % de los que votaron lo hicieron igual."""
    salida = {}
    for cod, c in (g or {}).items():
        emitidos = c[0] + c[1] + c[2]
        if emitidos < 3:
            continue
        k = max(range(3), key=lambda i: c[i])
        if c[k] / emitidos >= 0.7:
            salida[cod] = "SNA"[k]
    return salida


def detalle_ordenado(estado: dict) -> list:
    """Las votaciones con detalle, de la más reciente a la más antigua."""
    det = estado.get("detalle") or {}
    return sorted(({"url": u, **d} for u, d in det.items()),
                  key=lambda d: (d["f"], d.get("s") or 0, d.get("n") or 0), reverse=True)


def ancla_votacion(d: dict) -> str:
    return f"v{d.get('s') or 0}-{d.get('n') or 0}"


def _slug(nombre: str) -> str:
    """«Cobo Pérez, Noelia» -> «noelia-cobo-perez». El apellido va delante en
    el dato oficial; en una URL manda el nombre, que es como se busca."""
    if "," in nombre:
        apellidos, pila = [p.strip() for p in nombre.split(",", 1)]
        nombre = f"{pila} {apellidos}"
    base = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-zA-Z0-9]+", "-", base).strip("-").lower()
    return base[:70] or "sin-nombre"


def clave_nombre(nombre: str) -> str:
    """La misma persona aparece escrita de dos formas distintas según el
    fichero: el censo dice «Rego Candamil, Néstor» y las intervenciones dicen
    «Rego Candamil, Néstor (GMx)». Sin normalizar, el 97 % de las
    intervenciones no casaba con nadie y las fichas salían a cero."""
    n = re.sub(r"\s*\([^)]*\)\s*$", "", (nombre or "").strip())
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", n.lower()).strip()


def nombre_natural(nombre: str) -> str:
    if "," not in nombre:
        return nombre.strip()
    apellidos, pila = [p.strip() for p in nombre.split(",", 1)]
    return f"{pila} {apellidos}"


def _urls_json(html: str) -> list:
    return [u if u.startswith("http") else CONGRESO + u for u in RE_JSON.findall(html or "")]


def _elegir(urls: list, nombre: str) -> str:
    return next((u for u in urls if nombre.lower() in u.lower()), "")


# ---------------------------------------------------------------------------
# Cosecha
# ---------------------------------------------------------------------------

def censo(get, log) -> dict:
    """Los diputados en activo, por nombre oficial."""
    r = get(PAG_DIPUTADOS, tries=2)
    if not r:
        return {}
    url = _elegir(_urls_json(r.text), "DiputadosActivos")
    if not url:
        log("  no aparece el fichero de diputados activos")
        return {}
    d = get(url, tries=2)
    if not d:
        return {}
    try:
        filas = d.json()
    except Exception as exc:                                   # noqa: BLE001
        log(f"  censo ilegible: {exc}")
        return {}
    salida = {}
    for f in filas:
        nombre = (f.get("NOMBRE") or "").strip()
        if not nombre:
            continue
        salida[clave_nombre(nombre)] = {
            "nombre": nombre,
            "natural": nombre_natural(nombre),
            "slug": _slug(nombre),
            "circunscripcion": (f.get("CIRCUNSCRIPCION") or "").strip(),
            "partido": (f.get("FORMACIONELECTORAL") or "").strip(),
            "grupo": (f.get("GRUPOPARLAMENTARIO") or "").strip(),
            "alta": (f.get("FECHAALTA") or "").strip(),
        }
    log(f"  censo: {len(salida)} diputados en activo")
    return salida


def intervenciones(get, log, limite_por_persona: int = 12) -> dict:
    """Recuento de intervenciones por orador, con las últimas en detalle.

    El volcado es de la legislatura entera y pesa decenas de megas: se lee una
    vez y se reduce aquí a lo que cabe en el repositorio."""
    r = get(PAG_INTERVENCIONES, tries=2)
    if not r:
        return {}
    url = _elegir(_urls_json(r.text), "IntervencionesCronologicamente")
    if not url:
        log("  no aparece el fichero de intervenciones")
        return {}
    d = get(url, tries=2)
    if not d:
        return {}
    try:
        filas = d.json()
    except Exception as exc:                                   # noqa: BLE001
        log(f"  intervenciones ilegibles: {exc}")
        return {}

    por_persona: dict = {}
    for f in filas:
        orador = (f.get("ORADOR") or "").strip()
        if not orador:
            continue
        p = por_persona.setdefault(clave_nombre(orador),
                                   {"total": 0, "organos": {}, "ultimas": []})
        p["total"] += 1
        organo = (f.get("ORGANO") or "").strip() or "Sin órgano"
        p["organos"][organo] = p["organos"].get(organo, 0) + 1
        p["ultimas"].append({
            "fecha": (f.get("SESION") or "").strip(),
            "organo": organo,
            "asunto": (f.get("OBJETOINICIATIVA") or "").strip()[:200],
            "fase": (f.get("FASE") or "").strip(),
            "video": (f.get("ENLACEDIFERIDO") or "").strip(),
        })

    def _clave(x):
        f = x.get("fecha", "")
        m = re.match(r"(\d{2})/(\d{2})/(\d{4})", f)
        return f"{m.group(3)}{m.group(2)}{m.group(1)}" if m else ""

    for p in por_persona.values():
        p["ultimas"] = sorted(p["ultimas"], key=_clave, reverse=True)[:limite_por_persona]
    log(f"  intervenciones: {len(filas)} de {len(por_persona)} oradores")
    return por_persona


# El calendario del portal navega por GET: con targetDate se puede pedir
# cualquier día de cualquier legislatura. Ahí estaba la puerta al histórico,
# que parecía cerrada porque no hay listado de directorios ni API.
VOT_DIA = (CONGRESO + "/es/opendata/votaciones?p_p_id=votaciones&p_p_lifecycle=0"
           "&p_p_state=normal&p_p_mode=view&targetLegislatura={leg}&targetDate={fecha}")

def votaciones_de_dia(get, log, fecha: str, leg: str = "XV", tope: int = 80) -> list:
    """Las votaciones nominales de un día concreto."""
    r = get(VOT_DIA.format(leg=leg, fecha=fecha), tries=2)
    if not r:
        return []
    urls = [u for u in _urls_json(r.text) if "/votaciones/" in u][:tope]
    salida = []
    for u in urls:
        d = get(u, tries=1)
        if not d:
            continue
        try:
            salida.append({"url": u, "datos": d.json()})
        except Exception:                                      # noqa: BLE001
            continue
    return salida


def votaciones_publicadas(get, log) -> list:
    """Las votaciones de la sesión que el portal muestra hoy.

    No hay listado de directorios ni API de histórico: la página sirve la
    última sesión y de ahí salen las URLs de cada votación. Por eso esto se
    ejecuta a diario y se acumula: es la única forma de construir la serie."""
    r = get(PAG_VOTACIONES, tries=2)
    if not r:
        return []
    urls = [u for u in _urls_json(r.text) if "/votaciones/" in u]
    salida = []
    for u in urls[:60]:
        d = get(u, tries=1)
        if not d:
            continue
        try:
            salida.append({"url": u, "datos": d.json()})
        except Exception:                                      # noqa: BLE001
            continue
    log(f"  votaciones: {len(salida)} publicadas en la sesión en curso")
    return salida


# ---------------------------------------------------------------------------
# Agregación
# ---------------------------------------------------------------------------

VOTOS = {"Sí": "si", "Si": "si", "No": "no", "Abstención": "abstencion",
         "Abstencion": "abstencion", "No vota": "no_vota"}


def _postura_del_grupo(votos: list) -> dict:
    """Qué votó cada grupo. Solo se considera que un grupo «tuvo postura» si
    al menos el 70 % de los suyos votó lo mismo; por debajo de ahí el grupo
    estaba dividido y apartarse de él no significa nada."""
    conteo: dict = {}
    for v in votos:
        g = (v.get("grupo") or "").strip()
        voto = VOTOS.get((v.get("voto") or "").strip(), "")
        if not g or voto == "no_vota":
            continue
        conteo.setdefault(g, {}).setdefault(voto, 0)
        conteo[g][voto] += 1
    postura = {}
    for g, c in conteo.items():
        total = sum(c.values())
        if total < 3:
            continue
        mayoritario, n = max(c.items(), key=lambda x: x[1])
        if n / total >= 0.7:
            postura[g] = mayoritario
    return postura


# ---------------------------------------------------------------------------
# Detalle de cada votación: quién votó qué
# ---------------------------------------------------------------------------
#
# Los contadores de arriba dicen cuántas veces vota cada uno a favor o en
# contra, pero no QUÉ votó en CADA votación, que es lo que se quiere ver. Se
# guarda el voto nominal de las últimas DETALLE_MAX votaciones en forma
# compacta: una lista de nombres común y, por votación, una cadena con una
# letra por diputado (S, N, A, X = no vota; «-» = no estaba en la Cámara).
# Cuatrocientas votaciones ocupan unos 170 KB en vez de varios megas.

DETALLE_MAX = 400
VOTO_COD = {"si": "S", "no": "N", "abstencion": "A", "no_vota": "X"}
COD_VOTO = {v: k for k, v in VOTO_COD.items()}


def fecha_iso(f: str) -> str:
    """«23/9/2026» -> «2026-09-23». Vacío si no se entiende."""
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})", f or "")
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else ""


def guardar_detalle(estado: dict, url: str, d: dict) -> bool:
    info = d.get("informacion") or {}
    votos = d.get("votaciones") or []
    fecha = fecha_iso(info.get("fecha") or "")
    if not votos or not fecha:
        return False
    nombres = estado.setdefault("det_nombres", [])
    indice = {n: i for i, n in enumerate(nombres)}
    letras: dict = {}
    grupos: dict = {}
    for x in votos:
        nombre = (x.get("diputado") or "").strip()
        voto = VOTOS.get((x.get("voto") or "").strip(), "")
        if not nombre or not voto:
            continue
        clave = clave_nombre(nombre)
        if clave not in indice:
            indice[clave] = len(nombres)
            nombres.append(clave)
        letras[indice[clave]] = VOTO_COD[voto]
        g = (x.get("grupo") or "").strip()
        cuenta = grupos.setdefault(g, [0, 0, 0, 0])
        cuenta["SNAX".index(VOTO_COD[voto])] += 1
    cadena = "".join(letras.get(i, "-") for i in range(len(nombres)))
    tot = d.get("totales") or {}
    estado.setdefault("detalle", {})[url] = {
        "f": fecha,
        "s": info.get("sesion"),
        "n": info.get("numeroVotacion"),
        "t": " ".join((info.get("titulo") or "").split())[:300],
        "a": " ".join((info.get("textoExpediente") or "").split())[:600],
        "sub": " ".join(" ".join(filter(None, [info.get("tituloSubGrupo"),
                                              info.get("textoSubGrupo")])).split())[:300],
        "tot": [tot.get("afavor"), tot.get("enContra"), tot.get("abstenciones"),
                tot.get("noVotan")],
        "asent": bool(tot.get("asentimiento") and str(tot.get("asentimiento")).lower()
                      not in ("no", "false", "0")),
        "g": grupos,
        "v": cadena,
    }
    return True


def _podar_detalle(estado: dict) -> None:
    det = estado.get("detalle") or {}
    if len(det) <= DETALLE_MAX:
        return
    orden = sorted(det.items(), key=lambda kv: (kv[1]["f"], kv[1].get("s") or 0,
                                                kv[1].get("n") or 0), reverse=True)
    estado["detalle"] = dict(orden[:DETALLE_MAX])


def completar_detalle(get, log, estado: dict, presupuesto: int = 160) -> int:
    """Las votaciones que ya se habían contado antes de guardar el detalle no
    vuelven a pasar por acumular(). Aquí se piden otra vez, de la más reciente
    a la más antigua, hasta tener el voto nominal de las últimas
    DETALLE_MAX."""
    det = estado.setdefault("detalle", {})
    cand = []
    for u in estado.get("vistas") or []:
        m = re.search(r"/(\d{8})/Votacion(\d+)", u)
        if m:
            cand.append((m.group(1), int(m.group(2)), u))
    cand.sort(reverse=True)
    faltan = [u for _f, _n, u in cand[:DETALLE_MAX] if u not in det]
    hechas = 0
    for u in faltan[:presupuesto]:
        r = get(u, tries=1)
        if not r:
            continue
        try:
            if guardar_detalle(estado, u, r.json()):
                hechas += 1
        except Exception:                                      # noqa: BLE001
            continue
    _podar_detalle(estado)
    if faltan:
        log(f"  detalle de votaciones: {hechas} recuperadas, "
            f"{max(0, len(faltan) - presupuesto)} pendientes")
    return hechas


def acumular(estado: dict, votaciones: list, log) -> dict:
    """Suma las votaciones nuevas al estado. Idempotente: una votación ya
    contada no se vuelve a contar aunque se reprocese la misma sesión."""
    estado.setdefault("vistas", [])
    estado.setdefault("personas", {})
    estado.setdefault("recientes", [])
    vistas = set(estado["vistas"])
    nuevas = 0

    for v in votaciones:
        url = v["url"]
        if url in vistas:
            continue
        d = v["datos"]
        info = d.get("informacion") or {}
        votos = d.get("votaciones") or []
        if not votos:
            continue
        postura = _postura_del_grupo(votos)
        sesion_id = f"{info.get('sesion')}|{(info.get('fecha') or '').strip()}"
        estado.setdefault("sesiones", [])
        if sesion_id not in estado["sesiones"]:
            estado["sesiones"].append(sesion_id)
        titulo = (info.get("titulo") or "").strip()
        texto = " ".join((info.get("textoExpediente") or "").split())
        totales = d.get("totales") or {}

        for x in votos:
            nombre = (x.get("diputado") or "").strip()
            if not nombre:
                continue
            voto = VOTOS.get((x.get("voto") or "").strip(), "")
            if not voto:
                continue
            p = estado["personas"].setdefault(clave_nombre(nombre), {
                "si": 0, "no": 0, "abstencion": 0, "no_vota": 0,
                "votaciones": 0, "disidencias": 0, "grupo": "",
                "nombre": nombre, "sesiones": [], "ultimas": []})
            p.setdefault("sesiones", [])
            p["grupo"] = (x.get("grupo") or p["grupo"]).strip()
            p["votaciones"] += 1
            p[voto] += 1
            # Asistencia: se cuenta la sesión si emitió algún voto en ella.
            # «No vota» consta en el acta estando presente o ausente, así que
            # solo un voto efectivo prueba la presencia.
            if voto != "no_vota" and sesion_id and sesion_id not in p["sesiones"]:
                p["sesiones"].append(sesion_id)
            g = (x.get("grupo") or "").strip()
            disiente = (voto != "no_vota" and g in postura and postura[g] != voto)
            if disiente:
                p["disidencias"] += 1
            p["ultimas"].insert(0, {
                "fecha": (info.get("fecha") or "").strip(),
                "asunto": texto[:220] or titulo,
                "voto": voto,
                "con_su_grupo": not disiente,
            })
            del p["ultimas"][14:]

        guardar_detalle(estado, url, d)
        estado["recientes"].insert(0, {
            "fecha": (info.get("fecha") or "").strip(),
            "sesion": info.get("sesion"),
            "numero": info.get("numeroVotacion"),
            "titulo": titulo,
            "asunto": texto[:300],
            "afavor": totales.get("afavor"), "encontra": totales.get("enContra"),
            "abstenciones": totales.get("abstenciones"), "novotan": totales.get("noVotan"),
            "url": url,
        })
        del estado["recientes"][60:]
        vistas.add(url)
        nuevas += 1

    # «recientes» se ordena por fecha: la cosecha del histórico mete votaciones
    # de 2023 después de las de ayer, y la lista acababa enseñando las viejas.
    estado["recientes"].sort(key=lambda r: (fecha_iso(r.get("fecha", "")), r.get("sesion") or 0,
                                            r.get("numero") or 0), reverse=True)
    del estado["recientes"][60:]
    _podar_detalle(estado)
    estado["vistas"] = sorted(vistas)[-20000:]
    if nuevas:
        log(f"  votaciones nuevas incorporadas: {nuevas}")
    return estado


def fusionar(censo_actual: dict, estado: dict, intervs: dict) -> list:
    """Una ficha por diputado, con lo que se sepa de cada fuente."""
    fichas = []
    detalle = detalle_ordenado(estado)
    nombres = {n: i for i, n in enumerate(estado.get("det_nombres") or [])}
    posturas = [postura_grupos(d.get("g")) for d in detalle]
    for clave, base in censo_actual.items():
        v = (estado.get("personas") or {}).get(clave) or {}
        i = intervs.get(clave) or {}
        emitidos = v.get("si", 0) + v.get("no", 0) + v.get("abstencion", 0)
        sesiones_totales = len(estado.get("sesiones") or [])
        asistidas = len(v.get("sesiones") or [])
        # Sus votos, votación a votación, del detalle nominal: ordenados por
        # fecha (el acumulado antiguo iba por orden de cosecha y enseñaba 2023
        # antes que la semana pasada) y con enlace a la votación.
        ultimos = []
        i_nom = nombres.get(clave)
        if i_nom is not None:
            cods = [c for c, largo in COD_GRUPO.items() if largo == base.get("grupo")]
            for d, pg in zip(detalle, posturas):
                cod_grupo = next((c for c in cods if c in (d.get("g") or {})), "")
                letra = d["v"][i_nom] if i_nom < len(d["v"]) else "-"
                if letra == "-":
                    continue
                ultimos.append({
                    "fecha": d["f"], "asunto": d.get("a") or d.get("t") or "",
                    "que": d.get("sub") or d.get("t") or "",
                    "voto": COD_VOTO[letra],
                    "grupo_voto": COD_VOTO.get(pg.get(cod_grupo, ""), ""),
                    "con_su_grupo": letra == "X" or pg.get(cod_grupo) in (None, letra),
                    "enlace": f"{d['f']}.html#{ancla_votacion(d)}",
                })
                if len(ultimos) >= 20:
                    break
        ficha = dict(base)
        ficha["clave"] = clave
        ficha.update({
            "sigla": SIGLAS.get(v.get("grupo", ""), base.get("partido", "")),
            "votaciones": v.get("votaciones", 0),
            "si": v.get("si", 0), "no": v.get("no", 0),
            "abstencion": v.get("abstencion", 0), "no_vota": v.get("no_vota", 0),
            "emitidos": emitidos,
            "disidencias": v.get("disidencias", 0),
            "sesiones_asistidas": asistidas,
            "sesiones_totales": sesiones_totales,
            "ultimos_votos": ultimos or v.get("ultimas", []),
            "intervenciones": i.get("total", 0),
            "organos": i.get("organos", {}),
            "ultimas_intervenciones": i.get("ultimas", []),
        })
        fichas.append(ficha)
    return sorted(fichas, key=lambda f: (-f["intervenciones"], f["natural"]))


# ---------------------------------------------------------------------------
# Cosecha del histórico, a plazos
# ---------------------------------------------------------------------------
#
# El portal no publica índice de sesiones y el calendario que las marca lo
# dibuja JavaScript, así que desde un script no hay forma de preguntar «qué
# días hubo votación». Lo que sí funciona es pedir un día concreto: si hubo
# pleno, la página trae los enlaces a sus votaciones; si no, viene vacía.
#
# Así que se recorren los días laborables de la legislatura, unos ochocientos,
# a razón de un trozo por ejecución. El estado recuerda qué días ya se miraron
# —incluidos los vacíos— para no repetir ni una petición.

INICIO_LEG15 = dt.date(2023, 8, 17)


def _dias_laborables(desde: dt.date, hasta: dt.date) -> list:
    """Del más reciente al más antiguo: interesa primero lo de ahora."""
    dias, d = [], hasta
    while d >= desde:
        if d.weekday() < 5:          # el Pleno no vota sábados ni domingos
            dias.append(d.strftime("%d/%m/%Y"))
        d -= dt.timedelta(days=1)
    return dias


def cosechar_historico(get, log, estado: dict, presupuesto: int = 400) -> list:
    """Recupera votaciones antiguas poco a poco.

    El presupuesto cuenta PETICIONES, no días: un día sin pleno cuesta una y un
    día con pleno cuesta una más una por cada votación, que pueden ser sesenta.
    Contar solo los días hacía que una ejecución se fuera a veinte minutos sin
    que se notara. Con cuatrocientas peticiones por ejecución y dos ejecuciones
    al día, la legislatura entera queda cubierta en menos de una semana."""
    mirados = set(estado.get("dias_mirados") or [])
    hoy = dt.date.today()
    pendientes = [d for d in _dias_laborables(INICIO_LEG15, hoy) if d not in mirados]
    if not pendientes:
        log("  histórico: legislatura completa, nada que recuperar")
        estado["dias_pendientes"] = 0
        return []

    nuevas, gastado, dias = [], 0, 0
    for fecha in pendientes:
        if gastado >= presupuesto:
            break
        v = votaciones_de_dia(get, log, fecha)
        gastado += 1 + len(v)
        dias += 1
        mirados.add(fecha)
        if v:
            nuevas.extend(v)
            log(f"  {fecha}: {len(v)} votaciones")

    estado["dias_mirados"] = sorted(mirados)
    estado["dias_pendientes"] = len(pendientes) - dias
    log(f"  histórico: {len(nuevas)} votaciones de {dias} días revisados "
        f"({gastado} peticiones); quedan {estado['dias_pendientes']} días")
    return nuevas


# ---------------------------------------------------------------------------
# El hemiciclo
# ---------------------------------------------------------------------------

def orden_hemiciclo(fichas: list) -> list:
    """Los escaños, de la izquierda del hemiciclo a la derecha.

    Dentro de cada grupo el orden es alfabético y no corresponde al asiento
    real de nadie: el Congreso no publica el plano de escaños. La página lo
    dice, porque una silla concreta invita a creer que es «la suya»."""
    def clave(f):
        return (ORDEN_GRUPO.get(f.get("grupo", ""), 99), f.get("natural", ""))
    return sorted(fichas, key=clave)


def hemiciclo_svg(orden: list, ancho: int = 720, filas: int = 11) -> str:
    """El semicírculo de escaños, dibujado en el servidor.

    Se genera como SVG en el build y no con JavaScript en el navegador: así lo
    ve quien llega sin scripts, lo lee un rastreador y no hay un segundo de
    pantalla en blanco. La capa interactiva se monta encima, sobre este mismo
    dibujo, en vez de sustituirlo por un hueco vacío.

    Cada escaño lleva el identificador de su diputado, que es lo que permite
    que al pasar el ratón salga su ficha sin volver a calcular nada."""
    total = len(orden)
    if not total:
        return ""
    alto = ancho // 2 + 26
    cx, cy = ancho / 2, ancho / 2 + 6
    circulos = []
    for (x, y, rp), f in zip(hemiciclo_puntos(total, ancho, filas), orden):
        color = GRUPO_COLOR.get(f.get("grupo", ""), "#8d8d8d")
        corto = GRUPO_CORTO.get(f.get("grupo", ""), "")
        nombre = (f.get("natural") or "").replace("&", "&amp;").replace("<", "&lt;")
        circulos.append(
            f'<circle class="escano" data-d="{f.get("slug", "")}" '
            f'cx="{x:.1f}" cy="{y:.1f}" r="{rp:.1f}" fill="{color}">'
            f'<title>{nombre} ({corto})</title></circle>')

    return (f'<svg id="hemiciclo" class="hemiciclo" viewBox="0 0 {ancho} {alto}" '
            f'role="img" aria-label="Distribución de los {total} escaños por grupo '
            f'parlamentario" xmlns="http://www.w3.org/2000/svg">'
            f'<text x="{cx:.0f}" y="{cy - 14:.0f}" text-anchor="middle" '
            f'class="hemi-total">{total}</text>'
            f'<text x="{cx:.0f}" y="{cy + 4:.0f}" text-anchor="middle" '
            f'class="hemi-pie">escaños</text>'
            + "".join(circulos) + '</svg>')


def hemiciclo_puntos(total: int, ancho: int = 720, filas: int = 11) -> list:
    """Coordenadas (x, y, radio) de cada escaño, de izquierda a derecha."""
    import math

    r_int, r_ext = 0.42, 1.0
    pesos = [r_int + (r_ext - r_int) * i / (filas - 1) for i in range(filas)]
    suma = sum(pesos)
    reparto = [max(1, round(total * w / suma)) for w in pesos]
    while sum(reparto) > total:
        reparto[reparto.index(max(reparto))] -= 1
    while sum(reparto) < total:
        reparto[reparto.index(min(reparto))] += 1

    puntos = []
    for radio, n in zip(pesos, reparto):
        for k in range(n):
            ang = math.pi * (1 - (k + 0.5) / n)
            puntos.append((ang, radio))
    puntos.sort(key=lambda p: (-p[0], p[1]))

    escala = (ancho / 2) - 14
    cx, cy = ancho / 2, ancho / 2 + 6
    rp = max(2.4, escala / (filas * 3.4))
    return [(cx + math.cos(ang) * radio * escala, cy - math.sin(ang) * radio * escala, rp)
            for ang, radio in puntos]
