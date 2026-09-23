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

# En el calendario, los días con votación llevan la clase «pleno».
RE_DIA_PLENO = re.compile(r'<td[^>]*class="[^"]*\bpleno\b[^"]*"[^>]*>\s*(\d{1,2})\s*<', re.I)


def dias_con_votaciones(get, log, anio: int, mes: int, leg: str = "XV") -> list:
    """Qué días de ese mes tuvieron votación, según el propio calendario.
    Una petición por mes en vez de una por día: 38 en vez de 1.150."""
    r = get(VOT_DIA.format(leg=leg, fecha=f"01/{mes:02d}/{anio}"), tries=2)
    if not r:
        return []
    dias = sorted({int(d) for d in RE_DIA_PLENO.findall(r.text)})
    return [f"{d:02d}/{mes:02d}/{anio}" for d in dias]


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

    estado["vistas"] = sorted(vistas)[-20000:]
    if nuevas:
        log(f"  votaciones nuevas incorporadas: {nuevas}")
    return estado


def fusionar(censo_actual: dict, estado: dict, intervs: dict) -> list:
    """Una ficha por diputado, con lo que se sepa de cada fuente."""
    fichas = []
    for clave, base in censo_actual.items():
        v = (estado.get("personas") or {}).get(clave) or {}
        i = intervs.get(clave) or {}
        emitidos = v.get("si", 0) + v.get("no", 0) + v.get("abstencion", 0)
        sesiones_totales = len(estado.get("sesiones") or [])
        asistidas = len(v.get("sesiones") or [])
        ficha = dict(base)
        ficha.update({
            "sigla": SIGLAS.get(v.get("grupo", ""), base.get("partido", "")),
            "votaciones": v.get("votaciones", 0),
            "si": v.get("si", 0), "no": v.get("no", 0),
            "abstencion": v.get("abstencion", 0), "no_vota": v.get("no_vota", 0),
            "emitidos": emitidos,
            "disidencias": v.get("disidencias", 0),
            "sesiones_asistidas": asistidas,
            "sesiones_totales": sesiones_totales,
            "ultimos_votos": v.get("ultimas", []),
            "intervenciones": i.get("total", 0),
            "organos": i.get("organos", {}),
            "ultimas_intervenciones": i.get("ultimas", []),
        })
        fichas.append(ficha)
    return sorted(fichas, key=lambda f: (-f["intervenciones"], f["natural"]))


# ---------------------------------------------------------------------------
# Cosecha del histórico, a plazos
# ---------------------------------------------------------------------------

INICIO_LEG15 = (2023, 8)


def _meses_hacia_atras(desde_anio: int, desde_mes: int, hasta=INICIO_LEG15) -> list:
    """Del mes actual hacia atrás hasta el inicio de la legislatura."""
    meses, a, m = [], desde_anio, desde_mes
    while (a, m) >= hasta:
        meses.append((a, m))
        m -= 1
        if m == 0:
            a, m = a - 1, 12
    return meses


def cosechar_historico(get, log, estado: dict, presupuesto: int = 220) -> list:
    """Recupera votaciones antiguas poco a poco.

    Bajar la legislatura entera de golpe son más de mil ficheros y unos cuantos
    minutos de portal ajeno. Como esto se ejecuta cada día, se coge un trozo por
    ejecución y en una semana está completo; después solo hay que mantenerlo.
    El estado recuerda qué días ya se miraron, así que nada se pide dos veces."""
    hechos = set(estado.get("dias_hechos") or [])
    meses_hechos = set(estado.get("meses_hechos") or [])
    hoy = __import__("datetime").date.today()

    gastado, nuevas = 0, []
    for anio, mes in _meses_hacia_atras(hoy.year, hoy.month):
        clave_mes = f"{anio}-{mes:02d}"
        # El mes en curso se vuelve a mirar siempre: aún puede crecer.
        if clave_mes in meses_hechos and clave_mes != f"{hoy.year}-{hoy.month:02d}":
            continue
        if gastado >= presupuesto:
            break
        dias = dias_con_votaciones(get, log, anio, mes)
        gastado += 1
        pendientes = [d for d in dias if d not in hechos]
        if not pendientes:
            meses_hechos.add(clave_mes)
            continue
        log(f"  {clave_mes}: {len(pendientes)} sesiones por cosechar")
        for fecha in pendientes:
            if gastado >= presupuesto:
                break
            v = votaciones_de_dia(get, log, fecha)
            gastado += 1 + len(v)
            nuevas.extend(v)
            hechos.add(fecha)
        if all(d in hechos for d in dias):
            meses_hechos.add(clave_mes)

    estado["dias_hechos"] = sorted(hechos)
    estado["meses_hechos"] = sorted(meses_hechos)
    restantes = len([1 for a, m in _meses_hacia_atras(hoy.year, hoy.month)
                     if f"{a}-{m:02d}" not in meses_hechos])
    estado["meses_pendientes"] = restantes
    if nuevas:
        log(f"  histórico: {len(nuevas)} votaciones recuperadas "
            f"({restantes} meses aún por recorrer)")
    elif restantes:
        log(f"  histórico: nada nuevo, quedan {restantes} meses por recorrer")
    else:
        log("  histórico: legislatura completa")
    return nuevas
