"""Nombramientos y ceses de cargos públicos publicados en el BOE.

La sección II.A del BOE («Autoridades y personal. Nombramientos, situaciones
e incidencias») es donde el Gobierno, los ministerios, el Consejo General del
Poder Judicial o las universidades publican quién entra y quién sale de cada
puesto. La edición diaria solo desarrolla las secciones I y III, así que esto
se capturaba y se tiraba. Aquí se guarda, con tres reglas:

1. Determinista: solo expresiones regulares sobre el título oficial. Ningún
   modelo, ninguna inferencia. Si el título no dice un nombre, no hay registro.
2. Conservador: se incluye solo lo que el título identifica con nombre y
   apellidos (precedido de «don», «doña», «D.» o «D.ª») y encaja en un patrón
   conocido. Lo que tiene nombre pero no encaja se descarta y queda en el log
   con su motivo, para ampliar los patrones a la vista y no a ciegas.
3. Idempotente: el estado va indexado por el identificador BOE-A-…, así que
   reprocesar un día nunca duplica nada.

Fuente: la API de datos abiertos del BOE (sumario en JSON). Da la sección con
su código («2A», «2B»), el departamento, el epígrafe y, sobre todo, un
elemento por disposición con su identificador y sus páginas. El HTML del
sumario queda de respaldo: sirve, pero fetch_boe() deduplica por los 120
primeros caracteres del título, y en la II.A eso junta a diez profesores
titulares de la misma universidad y el mismo día en uno solo.

Protección de datos: solo se guarda lo que el propio BOE publica en el título
de la disposición (nombre, cargo, órgano, fecha y enlace), y solo de cargos y
puestos públicos. Nada de DNI, domicilios ni el contenido de los PDF.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import time
import unicodedata

import congreso_datos as cd

RAIZ = pathlib.Path(__file__).resolve().parent
ESTADO = RAIZ / "state" / "nombramientos.json"
API_SUMARIO = "https://www.boe.es/datosabiertos/api/boe/sumario/{aaaammdd}"
VERSION = 1

# Días del índice /nombramientos/ y de la lista de «recientes».
DIAS_RECIENTES = 30


# ---------------------------------------------------------------- expresiones

# El tratamiento es lo que marca que el título nombra a una persona concreta.
# «D.ª» antes que «D.» para que no se quede con el punto.
TRATAMIENTO = r"(?:doña|don|D\.ª|Dña\.|D\.)"

# Un nombre propio: palabras que empiezan por mayúscula, con las partículas
# de los apellidos españoles y catalanes en medio («Gómez de la Torre»,
# «del Olmo», «i Puig») y apellidos compuestos con guion.
_MAY = r"[A-ZÁÉÍÓÚÑÜÀÈÒÇÏ]"
_PAL = rf"{_MAY}[\w'’\-]*\.?"
_PART = r"(?:de|del|la|las|los|y|i|e|da|das|do|dos|van|von|der|di|el)"
NOMBRE = rf"(?P<persona>{_PAL}(?:\s+(?:{_PART}\s+)*{_PAL})*)"

PERSONA = rf"{TRATAMIENTO}\s+{NOMBRE}"

# Rango de la disposición: la primera palabra del título.
RE_RANGO = re.compile(r"^(Real Decreto-ley|Real Decreto|Decreto|Orden|Resolución|Acuerdo|"
                      r"Instrucción|Circular|Ley Orgánica|Ley|Corrección)\b")

# Quién firma: «Resolución de 1 de septiembre de 2026, de la Universidad de
# Murcia, por la que…». Útil cuando el departamento es genérico (UNIVERSIDADES).
RE_EMISOR = re.compile(r"^[^,]+?,\s+(?:de\s+la|de\s+los|de\s+las|del|de)\s+(?!\d)(?P<emisor>[^,]+?),\s+por\s+(?:el|la)\s+que\b")

# Lo que va detrás de «por el/la que»: el acto en sí.
RE_ACTO = re.compile(r"\bpor\s+(?:el|la)\s+que\s+(?:,[^,]*,\s*)?(?P<acto>.+)$", re.S)

# Cada patrón es (acto, tipo, expresión). El orden importa: el primero que
# encaja gana. Todos se aplican a la parte del título que sigue a «por el/la
# que» y exigen un tratamiento + nombre.
PATRONES: list[tuple[str, str, re.Pattern]] = [
    # «se dispone el cese de doña X como Secretaria General de…»
    # «se dispone el cese, a petición propia, de don X como…»
    ("cese", "cese", re.compile(
        rf"^se\s+dispone\s+el\s+cese(?:,\s*[^,]+,)?\s+(?:en\s+el\s+cargo\s+)?de\s+{PERSONA}"
        rf"(?:,?\s+(?:como|en\s+el\s+cargo\s+de)\s+(?P<cargo>.+?))?\.?$")),
    # «se nombra Secretaria General de Transporte Terrestre a doña X»
    # «se nombra Catedrático de Universidad, con plaza vinculada, a don X»
    # «se nombra Notario Archivero de…, al notario de dicha localidad, don X»
    ("nombramiento", "nombramiento", re.compile(
        rf"^se\s+nombra\s+(?!a\s)(?P<cargo>.+?),?\s+(?:a|al\s+[^,]+,)\s+(?:(?:la|el)\s+[^,]*?\s+)?"
        rf"{PERSONA}\.?$")),
    # «se nombra a don X como / Director de…»
    ("nombramiento", "nombramiento", re.compile(
        rf"^se\s+nombra\s+a\s+{PERSONA},?\s+(?:como\s+)?(?P<cargo>.+?)\.?$")),
    # «se adjudica en propiedad la plaza de Magistrada de… a doña X»
    # «… a la Magistrada doña X»
    ("destino", "nombramiento", re.compile(
        rf"^se\s+adjudica\s+(?:en\s+propiedad\s+)?(?:la\s+)?(?P<cargo>plaza\s+.+?)\s+a\s+"
        rf"(?:(?:la|el)\s+[^,]*?\s+)?{PERSONA}\.?$")),
    # «se declara la jubilación voluntaria anticipada del Magistrado don X»
    # «se declara la jubilación del notario de Madrid don X»
    # «se declara la jubilación de doña X, registradora del Registro…»
    ("jubilación", "otro", re.compile(
        rf"^se\s+declara\s+la\s+jubilaci[oó]n(?:\s+(?:voluntaria|forzosa|anticipada|por\s+incapacidad(?:\s+permanente)?))*"
        rf"\s+(?:de\s+la|del|de)\s+(?:(?P<cargo_pre>[^,]*?)\s+)?{PERSONA}"
        rf"(?:,\s*(?P<cargo>.+?))?\.?$")),
    # «se declara en situación de excedencia voluntaria al notario de Alcorcón don X»
    ("excedencia", "otro", re.compile(
        rf"^se\s+declara\s+en\s+(?:la\s+)?situaci[oó]n\s+de\s+(?P<situacion>[^,]+?)\s+a(?:l|\s+la)?\s+"
        rf"(?:(?P<cargo_pre>[^,]*?)\s+)?{PERSONA}(?:,\s*(?P<cargo>.+?))?\.?$")),
    # «se dispone la toma de posesión de don X como…»
    ("toma de posesión", "nombramiento", re.compile(
        rf"^se\s+(?:dispone|publica)\s+la\s+toma\s+de\s+posesi[oó]n\s+de\s+{PERSONA}"
        rf"(?:,?\s+como\s+(?P<cargo>.+?))?\.?$")),
    # «se dispone el nombramiento de don X como…»
    ("nombramiento", "nombramiento", re.compile(
        rf"^se\s+dispone\s+el\s+nombramiento\s+de\s+{PERSONA}"
        rf"(?:,?\s+como\s+(?P<cargo>.+?))?\.?$")),
    # «se destina a don X al puesto de…»
    ("destino", "nombramiento", re.compile(
        rf"^se\s+destina\s+a\s+(?:(?:la|el)\s+[^,]*?\s+)?{PERSONA},?\s+(?:al?\s+)?(?P<cargo>.+?)\.?$")),
]

# Descartes que se miran antes que los patrones, sobre el título entero.
# Cada uno lleva su motivo, que es lo que sale en el log.
EXCLUSIONES: list[tuple[str, re.Pattern]] = [
    ("corrección de errores", re.compile(r"\bse\s+corrigen?\s+errores\b|^Corrección de errores", re.I)),
    ("nombramiento colectivo", re.compile(
        r"\bse\s+nombran\b|\bse\s+(?:disponen|declaran)\s+(?:los|las)\s+(?:ceses|jubilaciones)\b", re.I)),
    ("ingreso como funcionario de carrera", re.compile(
        r"\bfuncionari[oa]s?\s+de\s+carrera\b|\bpersonal\s+funcionario\b|\bpersonal\s+laboral\b", re.I)),
    ("convocatoria o concurso resuelto", re.compile(
        r"\bse\s+resuelve\b|\bconvocatoria\b|\bconcurso\b|\blibre\s+designaci[oó]n\b|\baprobados\b|"
        r"\bproceso\s+selectivo\b|\boposici[oó]n\b|\blista\b", re.I)),
    ("pérdida de la condición de funcionario", re.compile(
        r"\bp[eé]rdida\b[^.]*\bcondici[oó]n\s+de\s+funcionari", re.I)),
]

# Más de tantas páginas en el PDF es una lista, aunque el título nombre a
# alguien (por ejemplo, «… a doña X y otros»). Solo lo sabe la API.
MAX_PAGINAS = 3


def rango_de(titulo: str) -> str:
    m = RE_RANGO.match(titulo or "")
    return m.group(1) if m else ""


def emisor_de(titulo: str) -> str:
    m = RE_EMISOR.match(titulo or "")
    return " ".join(m.group("emisor").split()) if m else ""


def _limpia_cargo(c: str) -> str:
    c = " ".join((c or "").split()).strip(" ,.;")
    # Incisos que no son el cargo: «, con plaza vinculada», «, en régimen de…».
    c = re.sub(r",\s*con\s+plaza\s+vinculada\b", " (plaza vinculada)", c)
    return c[:1].upper() + c[1:] if c else ""


def analizar(titulo: str) -> tuple[dict | None, str]:
    """Lee un título y devuelve (registro parcial, motivo de descarte).

    Si hay registro, el motivo es "". Si no, el registro es None y el motivo
    dice por qué: es lo que se cuenta en el log. Separado de extraer() para
    poder probar las expresiones con títulos sueltos, sin sumario."""
    t = " ".join((titulo or "").split())
    if not re.search(rf"\b{TRATAMIENTO}\s+{_MAY}", t):
        return None, "sin nombre propio"
    for motivo, rx in EXCLUSIONES:
        if rx.search(t):
            return None, motivo
    m = RE_ACTO.search(t)
    if not m:
        return None, "nombre sin patrón reconocido"
    acto_txt = m.group("acto").strip()
    for acto, tipo, rx in PATRONES:
        mm = rx.match(acto_txt)
        if not mm:
            continue
        g = mm.groupdict()
        persona = " ".join((g.get("persona") or "").split()).rstrip(".")
        cargo = g.get("cargo") or ""
        pre = g.get("cargo_pre") or ""
        # En las jubilaciones y excedencias el cargo puede ir antes del nombre
        # («del Magistrado don X») o después («doña X, registradora de…»).
        if not cargo and pre:
            cargo = pre
        etiqueta = acto
        if acto == "excedencia" and g.get("situacion"):
            etiqueta = " ".join(g["situacion"].split())
        if len(persona.split()) < 2:
            return None, "nombre incompleto"
        return {"tipo": tipo, "acto": etiqueta, "persona": persona,
                "cargo": _limpia_cargo(cargo)}, ""
    return None, "nombre sin patrón reconocido"


def _es_2a(e: dict) -> bool:
    return (e.get("codigo") == "2A" or
            bool(re.match(r"^II\.\s*Autoridades y personal\.?\s*-?\s*A\b", e.get("seccion") or "")))


def _es_2b(e: dict) -> bool:
    return (e.get("codigo") == "2B" or
            bool(re.match(r"^II\.\s*Autoridades y personal\.?\s*-?\s*B\b", e.get("seccion") or "")))


def extraer(entradas: list[dict], fecha_boe, log=print) -> list[dict]:
    """Los nombramientos y ceses con nombre propio de un sumario.

    `entradas` son las de fetch_boe() o las de sumario_api(): cada una con
    seccion, dept, epigrafe, titulo, ident y url (y, si vienen de la API,
    codigo y paginas). La II.A entra entera en el filtro; de la II.B solo lo
    que nombre o cese a alguien con nombre, porque es la sección de
    oposiciones y concursos y casi todo son listas."""
    fecha = fecha_boe.isoformat() if hasattr(fecha_boe, "isoformat") else str(fecha_boe)
    salida, descartes = [], {}

    def descarta(motivo):
        descartes[motivo] = descartes.get(motivo, 0) + 1

    for e in entradas or []:
        a, b = _es_2a(e), _es_2b(e)
        if not (a or b):
            continue
        titulo = " ".join((e.get("titulo") or "").split())
        ident = e.get("ident") or ""
        if not re.fullmatch(r"BOE-A-\d{4}-\d+", ident):
            descarta("sin identificador BOE")
            continue
        reg, motivo = analizar(titulo)
        if not reg:
            descarta(("II.B: " if b else "") + motivo)
            continue
        if b and reg["tipo"] not in ("nombramiento", "cese"):
            descarta("II.B: no es nombramiento ni cese")
            continue
        if (e.get("paginas") or 0) > MAX_PAGINAS:
            descarta("lista de personas en el PDF")
            continue
        salida.append({
            "id": ident,
            "fecha": fecha,
            "tipo": reg["tipo"],
            "acto": reg["acto"],
            "persona": reg["persona"],
            "clave": cd.clave_nombre(reg["persona"]),
            "cargo": reg["cargo"],
            "organo": " ".join((e.get("dept") or "").split()),
            "emisor": emisor_de(titulo),
            "rango": rango_de(titulo),
            "titulo": titulo,
            "url": e.get("url") or f"https://www.boe.es/diario_boe/txt.php?id={ident}",
        })
    total = sum(1 for e in entradas or [] if _es_2a(e) or _es_2b(e))
    detalle = ", ".join(f"{k}: {v}" for k, v in sorted(descartes.items(), key=lambda x: -x[1]))
    log(f"nombramientos {fecha}: {len(salida)} incluidos de {total} en la sección II"
        + (f"; descartados — {detalle}" if detalle else ""))
    extraer.ultimos_descartes = descartes
    return salida


extraer.ultimos_descartes = {}


# ---------------------------------------------------------------------- fuente

def sumario_api(fecha: dt.date, get, log=print) -> list[dict] | None:
    """Las entradas de la sección II del sumario, leídas de la API de datos
    abiertos. None si la API no responde (y entonces se usa el HTML)."""
    r = get(API_SUMARIO.format(aaaammdd=fecha.strftime("%Y%m%d")), tries=2,
            headers={"Accept": "application/json"})
    if not r:
        return None
    try:
        datos = r.json()["data"]["sumario"]
    except Exception as exc:                                  # noqa: BLE001
        log(f"nombramientos: la API del BOE no devolvió JSON legible ({exc})")
        return None

    def lista(x):
        return x if isinstance(x, list) else ([x] if x else [])

    entradas = []
    for diario in lista(datos.get("diario")):
        for sec in lista(diario.get("seccion")):
            if sec.get("codigo") not in ("2A", "2B"):
                continue
            for dep in lista(sec.get("departamento")):
                # Los elementos pueden colgar del departamento o de un epígrafe.
                grupos = [(ep.get("nombre", ""), lista(ep.get("item")))
                          for ep in lista(dep.get("epigrafe"))]
                grupos.append(("", lista(dep.get("item"))))
                for epigrafe, items in grupos:
                    for it in items:
                        pdf = it.get("url_pdf") or {}
                        try:
                            paginas = int(pdf.get("pagina_final")) - int(pdf.get("pagina_inicial")) + 1
                        except (TypeError, ValueError):
                            paginas = 0
                        entradas.append({
                            "codigo": sec.get("codigo"),
                            "seccion": sec.get("nombre", ""),
                            "dept": dep.get("nombre", ""),
                            "epigrafe": epigrafe,
                            "titulo": it.get("titulo", ""),
                            "ident": it.get("identificador", ""),
                            "url": it.get("url_html") or "",
                            "paginas": paginas,
                        })
    return entradas


def de_un_dia(fecha: dt.date, get, log=print, entradas_html: list | None = None) -> tuple[list, str]:
    """Registros de un día y la fuente usada («api» o «html»)."""
    entradas = sumario_api(fecha, get, log)
    fuente = "api"
    if entradas is None:
        if entradas_html is None:
            return [], "ninguna"
        entradas, fuente = entradas_html, "html"
    return extraer(entradas, fecha, log), fuente


# ---------------------------------------------------------------------- estado

def cargar() -> dict:
    try:
        e = json.loads(ESTADO.read_text(encoding="utf-8"))
        if e.get("version") == VERSION:
            e.setdefault("registros", {})
            e.setdefault("dias", {})
            return e
    except Exception:                                         # noqa: BLE001
        pass
    return {"version": VERSION, "registros": {}, "dias": {}}


def guardar(e: dict) -> None:
    ESTADO.parent.mkdir(exist_ok=True)
    texto = json.dumps(e, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if not ESTADO.exists() or ESTADO.read_text(encoding="utf-8") != texto:
        ESTADO.write_text(texto, encoding="utf-8")


def incorporar(registros: list[dict], fecha, fuente: str = "") -> dict:
    """Mete los registros de un día en el estado. Por identificador: volver a
    procesar el mismo día sustituye, nunca duplica."""
    e = cargar()
    f = fecha.isoformat() if hasattr(fecha, "isoformat") else str(fecha)
    for r in registros:
        e["registros"][r["id"]] = {k: v for k, v in r.items() if k != "id"}
    e["dias"][f] = {"n": len(registros), "fuente": fuente,
                    "descartes": dict(getattr(extraer, "ultimos_descartes", {}) or {})}
    guardar(e)
    return e


def del_dia(fecha: str) -> list[dict]:
    """Registros publicados en el BOE de esa fecha, en orden de identificador."""
    e = cargar()
    return sorted(({"id": k, **v} for k, v in e["registros"].items() if v.get("fecha") == fecha),
                  key=lambda r: r["id"])


def reprocesar(desde: dt.date, hasta: dt.date, get, log=print, pausa: float = 1.5) -> dict:
    """Recorre el sumario de cada día y SOLO actualiza state/nombramientos.json.
    No toca data/ ni las ediciones: es para rellenar el histórico."""
    totales = {"dias": 0, "incluidos": 0, "sin_boe": 0, "descartes": {}}
    d = desde
    while d <= hasta:
        entradas = sumario_api(d, get, log)
        if entradas is None:
            log(f"nombramientos {d}: sin sumario (domingo, festivo o API caída)")
            totales["sin_boe"] += 1
        else:
            regs = extraer(entradas, d, log)
            incorporar(regs, d, "api")
            totales["dias"] += 1
            totales["incluidos"] += len(regs)
            for k, v in extraer.ultimos_descartes.items():
                totales["descartes"][k] = totales["descartes"].get(k, 0) + v
        time.sleep(pausa)
        d += dt.timedelta(days=1)
    e = cargar()
    # El índice por identificador ya impide duplicar un mismo acto; esto mira
    # además si el mismo acto aparece con dos identificadores distintos.
    firmas = [(v["fecha"], v["clave"], v["tipo"], _norm(v["cargo"])) for v in e["registros"].values()]
    totales["duplicados"] = len(firmas) - len(set(firmas))
    log(f"nombramientos: reprocesado {desde} → {hasta}: {totales['dias']} días leídos, "
        f"{totales['sin_boe']} sin sumario, {totales['incluidos']} incluidos; "
        f"descartes {totales['descartes']}; estado con {len(firmas)} registros, "
        f"{totales['duplicados']} con el mismo acto repetido")
    return totales


# ------------------------------------------------------------------ recuentos

def titular_bloque(regs: list[dict]) -> str:
    """Titular del bloque diario, sacado del recuento. «El Gobierno» solo
    cuando son reales decretos: es el Consejo de Ministros quien los aprueba.
    El resto lo firman ministerios, universidades o el CGPJ."""
    def n(x, s, p):
        return f"{x} {s if x == 1 else p}"
    # Solo nombramientos y ceses propiamente dichos: por real decreto también
    # se adjudican plazas de magistrado, y eso no es un alto cargo.
    rd = [r for r in regs if r["rango"] == "Real Decreto" and r.get("acto") in ("nombramiento", "cese")]
    nom_rd = sum(1 for r in rd if r["tipo"] == "nombramiento")
    ces_rd = sum(1 for r in rd if r["tipo"] == "cese")
    nom = sum(1 for r in regs if r["tipo"] == "nombramiento")
    ces = sum(1 for r in regs if r["tipo"] == "cese")
    otros = len(regs) - nom - ces
    if nom_rd or ces_rd:
        partes = []
        if nom_rd:
            partes.append(f"NOMBRA A {n(nom_rd, 'ALTO CARGO', 'ALTOS CARGOS')}")
        if ces_rd:
            partes.append(f"CESA A {ces_rd}" if nom_rd else f"CESA A {n(ces_rd, 'ALTO CARGO', 'ALTOS CARGOS')}")
        t = "EL GOBIERNO " + " Y ".join(partes)
        resto = len(regs) - len(rd)
        if resto:
            t += f", Y {n(resto, 'MOVIMIENTO MÁS', 'MOVIMIENTOS MÁS')} EN LA ADMINISTRACIÓN"
        return t
    partes = []
    if nom:
        partes.append(n(nom, "NOMBRAMIENTO", "NOMBRAMIENTOS"))
    if ces:
        partes.append(n(ces, "CESE", "CESES"))
    if otros:
        partes.append(n(otros, "JUBILACIÓN U OTRA SITUACIÓN", "JUBILACIONES Y OTRAS SITUACIONES"))
    if not partes:
        return ""
    return (", ".join(partes[:-1]) + " Y " + partes[-1] if len(partes) > 1 else partes[0]) + " EN EL BOE"


# ---------------------------------------------------------------------- páginas

NOTA_HOMONIMOS = ("Registros agrupados por nombre tal como aparece en el BOE; pueden "
                  "corresponder a personas distintas con el mismo nombre.")
NOTA_DATOS = ("Los datos proceden de disposiciones oficiales publicadas en el Boletín Oficial "
              "del Estado y se limitan a cargos y puestos públicos. Para solicitar su "
              "rectificación o retirada, escribe a <EMAIL_DE_CONTACTO>.")

ETIQUETA_TIPO = {"nombramiento": "Nombramiento", "cese": "Cese", "otro": "Otra situación"}


def etiqueta(r: dict) -> str:
    """«Nombramiento», «Cese» o el acto concreto: «Destino», «Jubilación»…"""
    acto = r.get("acto") or ""
    if acto in ("nombramiento", "cese") or not acto:
        return ETIQUETA_TIPO.get(r.get("tipo"), r.get("tipo") or "")
    return acto[:1].upper() + acto[1:]


def slug_persona(persona: str) -> str:
    return cd._slug(persona)


def slug_organo(organo: str) -> str:
    base = unicodedata.normalize("NFKD", organo or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")[:70] or "sin-organo"


def _norm(t: str) -> str:
    return cd.clave_nombre(t)


def trayectoria(regs: list[dict]) -> list[dict]:
    """Cada acto de una persona en orden, y el tiempo en el cargo cuando hay
    un nombramiento y, después, un cese (o jubilación) del mismo cargo."""
    regs = sorted(regs, key=lambda r: (r["fecha"], r["id"]))
    abiertos: dict = {}
    filas = []
    for r in regs:
        fila = dict(r)
        clave = _norm(r["cargo"])
        if r["tipo"] == "nombramiento" and clave:
            abiertos[clave] = fila
        elif r["tipo"] in ("cese", "otro"):
            origen = abiertos.pop(clave, None) if clave else None
            if origen:
                dias = (dt.date.fromisoformat(r["fecha"]) - dt.date.fromisoformat(origen["fecha"])).days
                origen["cese"] = r["fecha"]
                origen["dias"] = dias
                fila["dias"] = dias
                fila["desde"] = origen["fecha"]
        filas.append(fila)
    return filas


def duracion(dias: int) -> str:
    if dias < 60:
        return f"{dias} días"
    meses = round(dias / 30.44)
    if meses < 24:
        return f"{meses} meses"
    anios, resto = divmod(meses, 12)
    return f"{anios} años" + (f" y {resto} meses" if resto else "")


def generar_paginas(h: dict) -> list:
    """/personas/ y /nombramientos/. `h` trae las utilidades de build.py
    (escape, plantilla, fechas…) para no importarlo desde aquí."""
    e = cargar()
    if not e["registros"]:
        return []
    esc, attr, fecha = h["esc_html"], h["esc_attr"], h["fmt_date_es"]
    site, plantilla = h["site_url"], h["plantilla"]
    dir_per, dir_nom = h["carpeta_personas"], h["carpeta_nombramientos"]
    dir_per.mkdir(exist_ok=True)
    dir_nom.mkdir(exist_ok=True)
    diputados = h.get("diputados") or {}          # clave de nombre natural -> slug
    regs = [{"id": k, **v} for k, v in e["registros"].items()]
    salidas = []

    por_persona: dict = {}
    for r in regs:
        por_persona.setdefault(r["clave"], []).append(r)
    por_organo: dict = {}
    for r in regs:
        por_organo.setdefault(r["organo"] or "Sin órgano", []).append(r)

    # Un slug por clave de persona. Si dos claves distintas dan el mismo slug
    # (pasa muy poco: el slug se corta a 70 caracteres), la segunda lleva sufijo.
    slugs, usados = {}, set()
    for clave in sorted(por_persona):
        s = base = slug_persona(por_persona[clave][0]["persona"])
        n = 2
        while s in usados:
            s, n = f"{base}-{n}", n + 1
        usados.add(s)
        slugs[clave] = s

    def enlace_persona(r, prefijo="../personas/"):
        return f'<a href="{prefijo}{attr(slugs[r["clave"]])}.html">{esc(r["persona"])}</a>'

    def enlace_boe(r):
        return (f'<a class="srclink" href="{attr(r["url"])}" target="_blank" rel="noopener">'
                f'{esc(r["id"])} ↗</a>')

    def fila_lista(r, con_persona=True, con_organo=True, prefijo="../personas/"):
        partes = [f'<b>{esc(etiqueta(r))}</b>']
        if con_persona:
            partes.append(enlace_persona(r, prefijo))
        if r["cargo"]:
            partes.append(esc(r["cargo"]))
        org = r["emisor"] if r["emisor"] and r["organo"] in ("UNIVERSIDADES", "") else r["organo"]
        if con_organo and org:
            partes.append(f'<span class="ref">{esc(org)}</span>')
        return (f'<li>{" · ".join(partes)} <span class="ref">{esc(fecha(r["fecha"]))} · '
                f'{esc(r["rango"])}</span> {enlace_boe(r)}</li>')

    def pagina(carpeta, nombre, ruta, titulo, desc, h1, kicker, entradilla, ficha, cuerpo,
               lastmod, miga, jsonld, fuente):
        url = f"{site}{ruta}"
        h["pagina_suelta"](plantilla, carpeta, nombre, {
            "TITLE": esc(titulo),
            "META_DESC": attr(desc[:155]),
            "CANONICAL": url,
            "JSONLD": h["jsonld_script"](jsonld),
            "EDITION_DATE": esc(f"Datos al {fecha(lastmod)}"),
            "MIGA": miga,
            "KICKER": esc(kicker),
            "HEADLINE": esc(h1),
            "STANDFIRST": esc(entradilla),
            "FICHA": ficha,
            "CUERPO": cuerpo,
            "FUENTE": fuente,
            "RELACIONADAS": "", "RELACIONADAS_HIDDEN": "hidden",
        })
        salidas.append({"url": url, "lastmod": lastmod})

    fuente_pie = (f'Fuente: sección II del Boletín Oficial del Estado. '
                  f'<a class="srclink" href="/nombramientos/metodologia.html">Qué se incluye y qué no</a>. '
                  f'{esc(NOTA_DATOS)}')

    # ----------------------------------------------------------- fichas de persona
    for clave, rs in por_persona.items():
        filas = trayectoria(rs)
        nombre = rs[0]["persona"]
        slug = slugs[clave]
        ultima = max(r["fecha"] for r in rs)
        items = []
        for r in filas:
            extra = ""
            if r["tipo"] == "nombramiento" and r.get("cese"):
                extra = (f' <span class="nota">Hasta el {esc(fecha(r["cese"]))}: '
                         f'{esc(duracion(r["dias"]))} en el cargo.</span>')
            elif r.get("desde"):
                extra = (f' <span class="nota">Nombramiento del {esc(fecha(r["desde"]))}: '
                         f'{esc(duracion(r["dias"]))} en el cargo.</span>')
            items.append(fila_lista(r, con_persona=False).replace("</li>", extra + "</li>"))
        dip = diputados.get(clave)
        enlace_dip = (f'<p><a class="srclink" href="/diputados/{attr(dip)}.html">'
                      f'Su ficha como diputado o diputada en el Congreso →</a></p>' if dip else "")
        cargos = list(dict.fromkeys(r["cargo"] for r in filas if r["cargo"]))
        organos = list(dict.fromkeys(r["organo"] for r in filas if r["organo"]))
        cuerpo = (enlace_dip
                  + '<h2 class="rotulo">Trayectoria en el BOE</h2>'
                  + f'<ul class="indice">{"".join(items)}</ul>'
                  + f'<p class="rk-nota">{esc(NOTA_HOMONIMOS)}</p>')
        persona_ld = {"@type": "Person", "name": nombre}
        if cargos:
            persona_ld["jobTitle"] = cargos[:5] if len(cargos) > 1 else cargos[0]
        if organos:
            persona_ld["worksFor"] = [{"@type": "Organization", "name": o} for o in organos[:5]]
        resumen = "; ".join(cargos[:2]) or ETIQUETA_TIPO.get(filas[-1]["tipo"], "")
        pagina(dir_per, f"{slug}.html", f"personas/{slug}.html",
               f"{nombre}: cargos y nombramientos en el BOE",
               f"{nombre} en el BOE: {len(rs)} "
               f"{'acto publicado' if len(rs) == 1 else 'actos publicados'}"
               + (f" ({resumen})" if resumen else "") + ", con enlace a cada disposición.",
               nombre, "Nombramientos y ceses",
               f"Lo que el Boletín Oficial del Estado ha publicado sobre {nombre}: "
               "nombramientos, ceses y otras situaciones, con fecha y enlace.",
               (f"<dt>Actos publicados</dt><dd>{len(rs)}</dd>"
                f"<dt>Último</dt><dd>{esc(fecha(ultima))}</dd>"),
               cuerpo, ultima,
               ('<a href="../">Portada</a> › <a href="../nombramientos/">Nombramientos</a> › '
                f'<a href="./">Personas</a> › <span aria-current="page">{esc(nombre)}</span>'),
               [persona_ld], fuente_pie)

    # ------------------------------------------------ índice de personas por letra
    def letra(clave):
        c = (clave or "#")[0].upper()
        return c if c.isalpha() else "#"
    por_letra: dict = {}
    for clave in por_persona:
        por_letra.setdefault(letra(clave), []).append(clave)
    letras = sorted(por_letra)
    nav_letras = " · ".join(
        f'<a href="{"index" if l == letras[0] else "letra-" + l.lower()}.html">{esc(l)}</a>'
        for l in letras)
    for i, l in enumerate(letras):
        claves = sorted(por_letra[l])
        lis = "".join(
            f'<li><a href="{attr(slugs[c])}.html">{esc(por_persona[c][0]["persona"])}</a>'
            f'<span class="ref">{len(por_persona[c])} · {esc(fecha(max(r["fecha"] for r in por_persona[c])))}</span></li>'
            for c in claves)
        nombre_pag = "index.html" if i == 0 else f"letra-{l.lower()}.html"
        ultima = max(r["fecha"] for c in claves for r in por_persona[c])
        pagina(dir_per, nombre_pag, "personas/" + ("" if i == 0 else nombre_pag),
               f"Personas nombradas y cesadas en el BOE: {l} | La Tercera Cámara",
               f"Índice alfabético de las {len(por_persona)} personas con nombramientos, ceses u "
               f"otras situaciones publicadas en el BOE. Letra {l}.",
               f"Personas en el BOE: {l}", "Nombramientos y ceses",
               "Cada persona que el BOE nombra o cesa con nombre y apellidos, con su trayectoria.",
               f"<dt>Personas</dt><dd>{len(por_persona)}</dd><dt>Con la {esc(l)}</dt><dd>{len(claves)}</dd>",
               f'<p class="aside-note">{nav_letras}</p><ul class="indice">{lis}</ul>'
               f'<p class="rk-nota">{esc(NOTA_HOMONIMOS)} Ordenadas por el nombre tal como '
               f'aparece en el BOE, que va por el nombre de pila.</p>',
               ultima,
               ('<a href="../">Portada</a> › <a href="../nombramientos/">Nombramientos</a> › '
                '<span aria-current="page">Personas</span>'),
               [{"@type": "CollectionPage", "name": f"Personas en el BOE: {l}",
                 "url": f"{site}personas/" + ("" if i == 0 else nombre_pag), "inLanguage": "es-ES"}],
               fuente_pie)

    # --------------------------------------------------------- páginas por órgano
    slugs_org = {}
    for org, rs in sorted(por_organo.items()):
        so = slug_organo(org)
        if so in ("index", "metodologia"):
            so += "-organo"
        slugs_org[org] = so
        rs = sorted(rs, key=lambda r: (r["fecha"], r["id"]), reverse=True)
        ultima = rs[0]["fecha"]
        altas = [r for r in rs if r["tipo"] == "nombramiento"]
        bajas = [r for r in rs if r["tipo"] != "nombramiento"]
        # Cargos que han rotado: el mismo cargo con un cese y un nombramiento
        # de personas distintas.
        por_cargo: dict = {}
        for r in rs:
            if r["cargo"]:
                por_cargo.setdefault(_norm(r["cargo"]), []).append(r)
        rotados = []
        for k, lista_c in por_cargo.items():
            if (any(x["tipo"] == "nombramiento" for x in lista_c) and
                    any(x["tipo"] == "cese" for x in lista_c) and
                    len({x["clave"] for x in lista_c}) > 1):
                sal = sorted(lista_c, key=lambda x: (x["fecha"], x["id"]))
                pasos = " → ".join(
                    f'{"sale" if x["tipo"] == "cese" else "entra"} '
                    f'{enlace_persona(x)} ({esc(fecha(x["fecha"]))})' for x in sal)
                rotados.append(f'<li><b>{esc(sal[0]["cargo"])}</b>: {pasos}</li>')
        cuerpo = ""
        if rotados:
            cuerpo += f'<h2 class="rotulo">Cargos que han rotado</h2><ul class="indice">{"".join(rotados)}</ul>'
        cuerpo += (f'<h2 class="rotulo">Altas ({len(altas)})</h2><ul class="indice">'
                   + "".join(fila_lista(r, con_organo=False) for r in altas[:300]) + "</ul>"
                   + f'<h2 class="rotulo">Bajas y otras situaciones ({len(bajas)})</h2><ul class="indice">'
                   + "".join(fila_lista(r, con_organo=False) for r in bajas[:300]) + "</ul>")
        pagina(dir_nom, f"{so}.html", f"nombramientos/{so}.html",
               f"{org.title() if org.isupper() else org}: nombramientos y ceses | La Tercera Cámara",
               f"Nombramientos, ceses y otras situaciones de personal de {org} publicados en el "
               f"BOE: {len(altas)} altas y {len(bajas)} bajas.",
               org.title() if org.isupper() else org, "Nombramientos y ceses",
               "Quién entra y quién sale, según las disposiciones publicadas en el BOE.",
               f"<dt>Altas</dt><dd>{len(altas)}</dd><dt>Bajas y otras situaciones</dt><dd>{len(bajas)}</dd>",
               cuerpo, ultima,
               ('<a href="../">Portada</a> › <a href="./">Nombramientos</a> › '
                f'<span aria-current="page">{esc(org)}</span>'),
               [{"@type": "CollectionPage", "name": f"{org}: nombramientos y ceses",
                 "url": f"{site}nombramientos/{so}.html", "inLanguage": "es-ES"}],
               fuente_pie)

    # ---------------------------------------------------------- índice (30 días)
    fechas = sorted({r["fecha"] for r in regs}, reverse=True)
    ultima = fechas[0]
    corte = (dt.date.fromisoformat(ultima) - dt.timedelta(days=DIAS_RECIENTES)).isoformat()
    recientes = sorted((r for r in regs if r["fecha"] > corte),
                       key=lambda r: (r["fecha"], r["id"]), reverse=True)
    bloques, actual = [], None
    for r in recientes:
        if r["fecha"] != actual:
            if actual is not None:
                bloques.append("</ul>")
            bloques.append(f'<h2 class="rotulo">{esc(fecha(r["fecha"]))}</h2><ul class="indice">')
            actual = r["fecha"]
        bloques.append(fila_lista(r))
    if actual is not None:
        bloques.append("</ul>")
    organos = "".join(
        f'<li><a href="{attr(slugs_org[o])}.html">{esc(o)}</a><span class="ref">{len(rs)}</span></li>'
        for o, rs in sorted(por_organo.items(), key=lambda x: -len(x[1])))
    pagina(dir_nom, "index.html", "nombramientos/",
           "Nombramientos y ceses en el BOE, día a día | La Tercera Cámara",
           "Quién nombra y quién cesa el BOE: los nombramientos, ceses y jubilaciones de cargos "
           "públicos de los últimos 30 días, con enlace a cada disposición.",
           "Nombramientos y ceses", "Nombramientos y ceses",
           "Los últimos 30 días de nombramientos, ceses y otras situaciones de cargos públicos "
           "que el BOE publica con nombre y apellidos.",
           (f"<dt>Últimos {DIAS_RECIENTES} días</dt><dd>{len(recientes)}</dd>"
            f"<dt>En la base</dt><dd>{len(regs)}</dd><dt>Personas</dt><dd>{len(por_persona)}</dd>"),
           (f'<p class="aside-note"><a class="srclink" href="../personas/">Todas las personas, de la A a la Z</a> · '
            f'<a class="srclink" href="metodologia.html">Cómo se hace</a></p>'
            + ("".join(bloques) or "<p>No hay nombramientos en los últimos 30 días.</p>")
            + f'<h2 class="rotulo">Por ministerio u órgano</h2><ul class="provincias">{organos}</ul>'),
           ultima,
           '<a href="../">Portada</a> › <span aria-current="page">Nombramientos</span>',
           [{"@type": "CollectionPage", "name": "Nombramientos y ceses en el BOE",
             "url": f"{site}nombramientos/", "inLanguage": "es-ES", "dateModified": ultima}],
           fuente_pie)

    # ---------------------------------------------------------------- metodología
    motivos = {}
    for d in e["dias"].values():
        for k, v in (d.get("descartes") or {}).items():
            motivos[k] = motivos.get(k, 0) + v
    lis_mot = "".join(f"<li>{esc(k)}: {v}</li>" for k, v in sorted(motivos.items(), key=lambda x: -x[1]))
    cuerpo = (
        '<h2 class="rotulo">Fuente</h2>'
        '<p>El sumario diario del Boletín Oficial del Estado, leído de su API de datos abiertos '
        '(<code>/datosabiertos/api/boe/sumario/AAAAMMDD</code>), con el sumario en HTML como respaldo. '
        'Se lee la sección II.A («Autoridades y personal. Nombramientos, situaciones e incidencias») '
        'y, de la II.B («Oposiciones y concursos»), solo lo que nombre o cese a una persona concreta.</p>'
        '<h2 class="rotulo">Qué se incluye</h2>'
        '<p>Solo las disposiciones cuyo <b>título</b> identifica a una persona con nombre y apellidos '
        '(precedidos de «don», «doña», «D.» o «D.ª») y encaja en uno de estos actos: nombramiento '
        '(«se nombra … a doña X»), cese («se dispone el cese de don X como …»), adjudicación de plaza, '
        'toma de posesión, jubilación y excedencia.</p>'
        '<h2 class="rotulo">Qué no se incluye</h2>'
        '<p>Los nombramientos colectivos y las tomas de posesión de funcionarios de carrera, las '
        'resoluciones de oposiciones, concursos y libre designación (que remiten a listas en el PDF), '
        'las correcciones de errores y cualquier título que no nombre a nadie. Tampoco se lee nunca '
        'el contenido de los PDF.</p>'
        + (f'<p>Descartes acumulados por motivo:</p><ul class="indice">{lis_mot}</ul>' if lis_mot else "")
        + '<h2 class="rotulo">Limitaciones</h2>'
        '<p>Solo se sabe lo que el título del BOE dice. El cargo es el literal del título y el órgano, '
        'el departamento con el que el BOE agrupa la disposición. El tiempo en un cargo solo se calcula '
        'cuando hay en la base un nombramiento y un cese posterior del mismo cargo. '
        f'{esc(NOTA_HOMONIMOS)}</p>'
        '<h2 class="rotulo">Datos personales</h2>'
        f'<p>{esc(NOTA_DATOS)}</p>')
    pagina(dir_nom, "metodologia.html", "nombramientos/metodologia.html",
           "Nombramientos y ceses: metodología | La Tercera Cámara",
           "De dónde salen los nombramientos y ceses, qué se incluye, qué se descarta y qué "
           "limitaciones tiene: solo lo que el título del BOE identifica.",
           "Cómo se hacen los nombramientos y ceses", "Metodología",
           "Fuente, alcance y limitaciones de la base de nombramientos y ceses.",
           f"<dt>Registros</dt><dd>{len(regs)}</dd><dt>Días leídos</dt><dd>{len(e['dias'])}</dd>",
           cuerpo, ultima,
           ('<a href="../">Portada</a> › <a href="./">Nombramientos</a> › '
            '<span aria-current="page">Metodología</span>'),
           [{"@type": "WebPage", "name": "Nombramientos y ceses: metodología",
             "url": f"{site}nombramientos/metodologia.html", "inLanguage": "es-ES"}],
           f'Fuente: Boletín Oficial del Estado.')

    h["log"](f"personas/: {len(por_persona)} fichas · nombramientos/: {len(por_organo)} órganos")
    return salidas


def bloque_edicion(fecha: str, h: dict, prefijo: str = "/") -> str:
    """El bloque «Nombramientos y ceses» de la edición de un día. Vacío si no
    hay ninguno: el bloque no aparece."""
    regs = del_dia(fecha)
    if not regs:
        return ""
    esc, attr = h["esc_html"], h["esc_attr"]
    lis = []
    for r in regs:
        org = r["emisor"] if r["emisor"] and r["organo"] in ("UNIVERSIDADES", "") else r["organo"]
        partes = [f'<b>{esc(etiqueta(r))}</b>',
                  f'<a href="{prefijo}personas/{attr(slug_persona(r["persona"]))}.html">{esc(r["persona"])}</a>']
        if r["cargo"]:
            partes.append(esc(r["cargo"]))
        if org:
            partes.append(f'<span class="ref">{esc(org)}</span>')
        lis.append(f'<li>{" · ".join(partes)} '
                   f'<a class="srclink" href="{attr(r["url"])}" target="_blank" rel="noopener">BOE ↗</a></li>')
    return (f'<div class="nombramientos" id="nombramientos">'
            f'<h3 class="nb-t">Nombramientos y ceses</h3>'
            f'<p class="nb-tit">{esc(titular_bloque(regs))}</p>'
            f'<ul class="nb-l">{"".join(lis)}</ul>'
            f'<p class="aside-note"><a class="srclink" href="{prefijo}nombramientos/">Todos los '
            f'nombramientos y ceses →</a></p></div>')
