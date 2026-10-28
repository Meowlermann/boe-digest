"""Campos estructurados de las convocatorias de empleo (TC-013, iteración 2).

Determinista, sin red, sin LLM: reglas sobre el texto de txt.php que ya lee
empleo.enriquecer(). Cada campo sale de un patrón que tiene que casar
EXACTAMENTE; si no casa, el campo no existe (nunca «—» ni suposiciones).

Formato comprobado a mano el 28-10-2026 sobre dos muestras del BOE II.B
(70 + 123 textos de septiembre-octubre de 2026):

- Administración Local: fórmula fija. «En el «Boletín Oficial de …» número
  …, se han publicado las bases … para proveer:» + una línea por grupo de
  plazas («Dos plazas de X, pertenecientes a la escala …, por el sistema de
  oposición, en turno libre.») + «El plazo de presentación de solicitudes será
  de …» + firma. La localidad sale del título («del Ayuntamiento de X (Prov)»),
  no de la firma: una entidad local menor firma a veces en otro municipio, y
  la firma lleva nombres de cargos que no se guardan.
- Estado, universidades y provisión: redacción heterogénea. Solo se activan
  los campos que pasan el umbral (ver CAMPOS_ACTIVOS).

Regla de publicación (decisión del mantenedor, 28-10-2026): un campo se
enseña solo si su regla, para esa familia de documento, dio ≥95 % de acierto y
0 valores erróneos en una validación manual de ≥20 documentos. La lista de
campos activos por familia es CAMPOS_ACTIVOS; lo que no está ahí se extrae (o
no) pero no se pinta. Las correcciones, modificaciones, desiertas y
anulaciones no son ofertas: llevan solo una etiqueta, sin cifras.

No cubre: grupo/subgrupo y titulación en Local (están en las bases del
boletín provincial, no en el BOE); erratas del BOE (se copian tal cual).
"""

from __future__ import annotations

import re
import unicodedata

# Familia -> campos que se pueden ENSEÑAR. Validación: /workspace (fuera del
# repo) y resumen en la PR. Cambiar esta tabla exige re-medir.
CAMPOS_ACTIVOS: dict[str, frozenset] = {
    "local": frozenset({"plazas", "lineas", "turnos", "sistema", "localidad", "boletin"}),
    "universidad": frozenset(),
    "estado": frozenset(),
    "provision": frozenset(),
}

# Familias en las que se rotula una disposición que no es oferta nueva
# (corrección, modificación, desierta, anulación). Solo la etiqueta: nunca
# cifras de lo corregido.
# universidad y provision: validadas en la segunda muestra (25 y 38 textos,
# 0 falsas, sin omisiones). estado NO: 2 de 28 no-ofertas sin detectar (92,9 %).
NO_OFERTA_ACTIVA: frozenset = frozenset({"local", "universidad", "provision"})

ETIQUETA_NO_OFERTA = {
    "correccion": "Corrección",
    "modificacion": "Modificación",
    "desierta": "Desierta",
    "anulacion": "Anulación",
}

_UNIDADES = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
             "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13,
             "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17, "dieciocho": 18,
             "diecinueve": 19, "veinte": 20, "veintiun": 21, "veintiuna": 21, "veintiuno": 21,
             "veintidos": 22, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25,
             "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29}
_DECENAS = {"treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70,
            "ochenta": 80, "noventa": 90}
_CIENTOS = {"cien": 100, "ciento": 100, "doscientas": 200, "doscientos": 200, "trescientas": 300,
            "trescientos": 300, "cuatrocientas": 400, "cuatrocientos": 400, "quinientas": 500,
            "quinientos": 500}


def plano(t: str) -> str:
    base = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return " ".join(base.split()).lower()


# Un número en letra (hasta 599) o en cifra, con «(2)» opcional detrás.
_PAL = "|".join(sorted(list(_UNIDADES) + list(_DECENAS) + list(_CIENTOS), key=len, reverse=True))
RE_NUM = re.compile(rf"(?:\d{{1,4}}|(?:(?:{_PAL})(?:\s+y\s+|\s+)?)+?)(?:\s*\(\d{{1,4}}\))?", re.I)


def numero(s: str) -> int | None:
    """«Setenta y seis» -> 76; «dos (2)» -> 2; «14» -> 14. None si no se entiende
    o si la cifra entre paréntesis contradice a la letra."""
    s = plano(s).strip()
    m = re.fullmatch(r"(.*?)\s*\((\d{1,4})\)", s)
    entre = int(m.group(2)) if m else None
    if m:
        s = m.group(1).strip()
    if re.fullmatch(r"\d{1,4}", s):
        v = int(s)
    else:
        v, partes = 0, [p for p in re.split(r"\s+y\s+|\s+", s) if p]
        if not partes:
            return entre
        for p in partes:
            if p in _CIENTOS:
                v += _CIENTOS[p]
            elif p in _DECENAS:
                v += _DECENAS[p]
            elif p in _UNIDADES:
                v += _UNIDADES[p]
            else:
                return None
    if entre is not None and entre != v:
        return None
    return v or None


# ---------------------------------------------------------- no es una oferta

RE_CORRECCION = re.compile(r"correccion de (?:errores|erratas)|se corrigen? (?:errores|erratas)|corrige")
RE_MODIFICACION = re.compile(r"\bse modifica|por la que se modifica|\bmodifica(?:n|ndo)?\b|amplia(?:cion)? (?:el|del|de) (?:numero|plazo)|"
                             r"ampliacion de plazas|se amplia")
RE_DESIERTA = re.compile(r"desiert[oa]s?")
RE_ANULACION = re.compile(r"deja(?:n)? sin efecto|\banula\b|se anula|suspende|revoca|desistimiento|desiste")
RE_CONCLUIDO = re.compile(r"declara concluido")


def no_oferta(titulo: str, texto: str = "") -> str:
    """Clave de ETIQUETA_NO_OFERTA si la disposición NO es una oferta nueva
    (corrección, modificación, desierta, anulación); cadena vacía si lo es.
    Se mira el título y, para la desierta, también el arranque del texto
    (21554: título neutro y «se declara desierto» en el texto)."""
    t = plano(titulo)
    if RE_CORRECCION.search(t):
        return "correccion"
    if RE_DESIERTA.search(t) or RE_CONCLUIDO.search(t):
        return "desierta"
    if RE_ANULACION.search(t):
        return "anulacion"
    if RE_MODIFICACION.search(t):
        return "modificacion"
    x = plano(texto[:1500])
    if re.search(r"(?:se )?declar\w* desiert", x):
        return "desierta"
    return ""


def familia(reg: dict) -> str:
    """local (toda la Administración Local, también sus puestos: misma
    fórmula), universidad, provision (resto de provisión de puestos) o estado."""
    d = (reg.get("dept") or "").upper()
    if d == "ADMINISTRACIÓN LOCAL":
        return "local"
    if reg.get("tipo") == "provision":
        return "provision"
    if d == "UNIVERSIDADES":
        return "universidad"
    return "estado"


# ------------------------------------------------------------------- Local

RE_LINEA_LOCAL = re.compile(
    r"^(?P<n>[^\s].{0,60}?)\s+(?P<clase>plazas?|puestos?(?: de trabajo)?)\s+de\s+(?P<cuerpo>.+?)"
    r"(?=,\s*pertenecientes?\b|\s+de la plantilla\b|,?\s+(?:por|mediante) el sistema\b|,\s*(?:por|mediante)\s+"
    r"(?:concurso|oposici)|,\s*en turno\b|\.$)(?P<resto>.*)$", re.I)
RE_SISTEMA = re.compile(r"(?:por|mediante) (?:el )?(?:sistema|procedimiento)(?: selectivo)? de "
                        r"(concurso-oposicion|oposicion libre|oposicion|concurso de meritos|concurso|libre designacion)"
                        r"|(?:por|mediante)\s+(concurso-oposicion|oposicion|concurso|libre designacion)\b")
SISTEMAS = {"concurso-oposicion": "Concurso-oposición", "oposicion": "Oposición",
            "oposicion libre": "Oposición", "concurso": "Concurso", "concurso de meritos": "Concurso",
            "libre designacion": "Libre designación"}
RE_BOLETIN = re.compile(r"^En el «([^»]{5,90})»")


def _turno(resto: str) -> str | None:
    r = plano(resto)
    if re.search(r"discapacidad|diversidad funcional", r):
        return "discapacidad"
    if re.search(r"promocion interna", r):
        return "promocion interna"
    if re.search(r"movilidad", r):
        return "movilidad"
    if re.search(r"(?:turno|acceso)(?: de acceso)? libre|en turno libre", r):
        return "libre"
    return None


def lineas_texto(texto: str) -> list[str]:
    return [" ".join(l.split()) for l in (texto or "").split("\n") if l.strip()]


def campos_local(texto: str) -> dict:
    """Campos de la fórmula de Administración Local. Solo si TODAS las líneas
    de plazas casan con la regla se dan plazas/turnos; si una no se entiende,
    ni total ni turnos (evita totales parciales)."""
    ls = lineas_texto(texto)
    out: dict = {}
    if ls:
        m = RE_BOLETIN.match(ls[0])
        if m and re.search(r"Bolet[ií]n|Diari|Diario", m.group(1)):
            out["boletin"] = m.group(1)
    try:
        i = next(i for i, l in enumerate(ls) if re.search(r"para proveer\b.*:$|siguientes? plazas?.*:$|"
                                                         r"convocatoria (?:para|de)\b.*:$", l))
    except StopIteration:
        i = None
    lineas, malas = [], 0
    if i is not None:
        for l in ls[i + 1:]:
            # Se acaba la lista en la primera línea que no es «N plaza(s)/puesto(s) de»
            # («Dichas bases fueron rectificadas…», «Se ha publicado, asimismo…»).
            if not re.match(r"^\S.{0,60}?\s(?:plazas?|puestos?)(?: de trabajo)? de\s", l, re.I):
                break
            m = RE_LINEA_LOCAL.match(l)
            n = numero(m.group("n")) if m else None
            if not m or n is None or len(m.group("cuerpo")) > 160:
                malas += 1
                continue
            cuerpo = m.group("cuerpo").strip().rstrip(",.")
            pr = plano(m.group("resto") + " " + l[:0])
            s = RE_SISTEMA.search(plano(l))
            lineas.append({"n": n, "cuerpo": cuerpo,
                           "clase": "puesto" if m.group("clase").lower().startswith("puesto") else "plaza",
                           **({"sistema": SISTEMAS[next(g for g in s.groups() if g)]} if s else {}),
                           **({"turno": t} if (t := _turno(pr)) else {})})
    # Cabecera «para proveer por concurso:» (Vigo): el sistema va arriba.
    if lineas and i is not None:
        s = RE_SISTEMA.search(plano(ls[i]))
        if s:
            for x in lineas:
                x.setdefault("sistema", SISTEMAS[next(g for g in s.groups() if g)])
    if lineas and not malas:
        out["lineas"] = lineas
        out["plazas"] = sum(x["n"] for x in lineas)
        turnos: dict = {}
        if all("turno" in x for x in lineas):
            for x in lineas:
                turnos[x["turno"]] = turnos.get(x["turno"], 0) + x["n"]
            out["turnos"] = turnos
        sis = {x.get("sistema") for x in lineas}
        if len(sis) == 1 and None not in sis:
            out["sistema"] = sis.pop()
    return out


# --------------------------------------------------------- Estado/universidad

def campos_estado(texto: str, titulo: str = "") -> dict:
    """Reglas de Estado y universidades (PR B). Hoy ningún campo pasa el
    umbral: ver CAMPOS_ACTIVOS."""
    return {}


def campos_provision(texto: str, html: str = "") -> dict:
    return {}


# ----------------------------------------------------------------- interfaz

def extraer_campos(reg: dict, texto: str, html: str = "") -> dict:
    """{'no_oferta': clave} o {'campos': {...}} (todo lo extraído, aún sin
    filtrar por CAMPOS_ACTIVOS: el filtro se aplica al pintar)."""
    no = no_oferta(reg.get("titulo", ""), texto)
    if no:
        return {"no_oferta": no}
    fam = familia(reg)
    if fam == "local":
        c = campos_local(texto)
        if lugar(reg):
            c["localidad"] = lugar(reg)
    elif fam == "provision":
        c = campos_provision(texto, html)
    else:
        c = campos_estado(texto, reg.get("titulo", ""))
    return {"campos": c} if c else {}


def activos(reg: dict) -> dict:
    """Solo los campos que se pueden enseñar para la familia del registro."""
    if reg.get("no_oferta"):
        return {}
    ok = CAMPOS_ACTIVOS.get(familia(reg), frozenset())
    return {k: v for k, v in (reg.get("campos") or {}).items() if k in ok}


def _plural(n: int, clase: str) -> str:
    if clase == "puesto":
        return f"{n} puesto" if n == 1 else f"{n} puestos"
    return f"{n} plaza" if n == 1 else f"{n} plazas"


RE_ORGANO_LOCAL = re.compile(r"\bdel? (?:la )?(Ayuntamiento|Concello|Ajuntament|Diputaci[oó]n Provincial|"
                             r"Mancomunitat(?: de Municipis)?|Mancomunidad de Municipios|Consell Insular|Cabildo Insular|Mancomunidad|Comarca|Consorcio|"
                             r"Entidad Local Aut[oó]noma)(?: de)? ([^,(]+?)(?: \(|,)")


def lugar(reg: dict) -> str:
    """«Tamarite de Litera» para un ayuntamiento; para el resto, el órgano
    del título («Diputación Provincial de Palencia»)."""
    m = RE_ORGANO_LOCAL.search(reg.get("titulo") or "")
    if not m:
        return ""
    tipo_org, nombre = m.group(1), m.group(2).strip()
    if tipo_org in ("Ayuntamiento", "Concello", "Ajuntament"):
        return nombre
    return f"{tipo_org} de {nombre}" if not nombre.lower().startswith("de ") else f"{tipo_org} {nombre}"


def titular(reg: dict, maximo: int = 120) -> str:
    """Titular generado («2 plazas de Operario/a de brigada · Tamarite de
    Litera») solo con campos activos; cadena vacía si no hay datos fiables
    (entonces se usa el titular corto de siempre)."""
    c = activos(reg)
    ls, lg = c.get("lineas"), c.get("localidad", "")
    if not ls or "plazas" not in c or not lg:
        return ""
    # Hasta la primera coma: «Psicólogo/a, jornada parcial de 15 horas…».
    cuerpos = list(dict.fromkeys(x["cuerpo"].split(",")[0].strip() for x in ls))
    # «Operario/a de brigada» y «Operario/a de brigada mediante contrato de
    # relevo»: se nombra la parte común si una es el principio de la otra.
    cuerpos = [c for c in cuerpos if not any(o != c and c.startswith(o + " ") for o in cuerpos)]
    clase = "puesto" if all(x["clase"] == "puesto" for x in ls) else "plaza"
    total = _plural(c["plazas"], clase)
    if len(cuerpos) == 1:
        t = f"{total} de {cuerpos[0]} · {lg}"
    else:
        t = f"{total} de {', '.join(cuerpos[:-1])} y {cuerpos[-1]} · {lg}"
        if len(t) > maximo:
            t = f"{total} ({len(cuerpos)} categorías) · {lg}"
    return t if len(t) <= maximo else ""


TURNOS = {"libre": "Turno libre", "promocion interna": "Promoción interna",
          "discapacidad": "Reserva discapacidad", "movilidad": "Movilidad"}


def chips(reg: dict) -> list[str]:
    """Etiquetas cortas de la tarjeta, solo de campos activos."""
    c = activos(reg)
    out = []
    t = c.get("turnos") or {}
    if t:
        out.append(" · ".join(f"{TURNOS.get(k, k)} {v}" for k, v in t.items()))
    # El sistema ya sale en la línea de la tarjeta si empleo.proceso lo dio.
    if c.get("sistema") and c["sistema"] != reg.get("proc"):
        out.append(c["sistema"])
    return out


def bases(reg: dict) -> str:
    """«Bases en el Boletín Oficial de la Provincia de Huesca» o ""."""
    b = activos(reg).get("boletin")
    return f"Bases en el «{b}»" if b else ""


def etiqueta_no_oferta(reg: dict) -> str:
    """«Corrección», «Desierta»… si la familia lo tiene activo; si no, ""."""
    # Las correcciones y desiertas no se leen (empleo.es_convocatoria): basta
    # el título, con la misma regla que se aplica al texto.
    no = reg.get("no_oferta") or no_oferta(reg.get("titulo", ""), "")
    if not no or familia(reg) not in NO_OFERTA_ACTIVA:
        return ""
    return ETIQUETA_NO_OFERTA.get(no, "")


def fuera_de_abiertos(reg: dict) -> bool:
    """Una desierta (familia activa) no es una oferta abierta: se saca de los
    bloques de convocatorias y provisión y pasa a «Otras disposiciones»."""
    return etiqueta_no_oferta(reg) == ETIQUETA_NO_OFERTA["desierta"]
