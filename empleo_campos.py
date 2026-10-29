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
    # Provisión: puesto, nivel y localidad validados (25 documentos, 258 filas,
    # 0 erróneos) pero APAGADOS hasta que el mantenedor decida. Para encender:
    #   "provision": frozenset({"puesto", "nivel", "localidad"}),
    # «plazas» no está validado: no se enciende.
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


# ---------------------------------------------------------------- Provisión
#
# Formato comprobado a mano el 28/29-10-2026 sobre 26 + 26 provisiones del BOE
# II.B (txt.php, octubre de 2026). Los anexos de puestos llegan como tablas
# HTML; cada celda trae una línea por <p>. Cabeceras vistas:
#   - «Denominación del puesto» | «Nivel» | «Localidad» (columna propia);
#   - una sola celda «Centro directivo - Unidad - Puesto de trabajo» con la
#     unidad en unas líneas y el puesto en la que acaba en «(código)», o en la
#     anterior a «Código del puesto: N», o (AEAT) en la última línea;
#   - Interior/Defensa: filas de encabezado de unidad sin nivel ni localidad
#     entre las filas de puesto (se saltan).
# Los puestos «a resultas» no son vacantes: se descartan todas las tablas que
# siguen a un anexo cuyo título dice «resultas» (22466, 22472) o que la prosa
# señala como tal («anexos I-A y I-B (resultas)», 22559), hasta el siguiente
# anexo, y cualquier fila que diga «a resultas».
# No cubre: el puesto solo en prosa (Osakidetza, 21564), la tabla del CGPJ con
# «Cuerpo» como puesto y sin nivel (21702), tablas sin cabecera reconocible.
# En esos casos no se extrae nada y la tarjeta queda como antes.

_COLS = (("puesto", r"^denominacion|^puestos? de trabajo$|^puesto$"),
         ("merge", r"centro directivo.*(?:puesto|denominacion)|^centro\s*/\s*(?:denominacion )?puesto"),
         ("nivel", r"^nivel|^nv\b|^c\.? ?d\.?$|^comp(?:lem(?:ento)?)?\.? (?:de )?destino"),
         ("localidad", r"localidad"),
         ("plazas", r"^n\.?\s?o?\.? ?(?:de )?(?:plazas|puestos)$|^numero de (?:plazas|puestos)$"))
_SKIP = r"apellido|dni|destino actual|unidad de que depende|posesion|grado consol|adjudicad"
_CODIGO = re.compile(r"\(\s*\d{5,8}\s*\)\.?$|^\d{5,8}\.?$")
_RE_COD_PUESTO = re.compile(r"codigo de(?:l)? puesto")
_ANEXO = re.compile(r"^anexo\s+([ivx]+(?:\s*-\s*[a-z0-9]\b|\s+[a-z]\b)?)")
_ID_ANEXO = r"[ivx]+(?:\s*-\s*[a-z0-9]\b|\s+[a-z]\b)?\)?"
# «anexos I-A y I-B (resultas)» (22559); «anexo I B), que solo podrán ser
# adjudicados en el caso que queden vacantes tras…» (20937).
_ANEXO_RESULTAS = (
    re.compile(rf"anexos?\s+((?:{_ID_ANEXO})(?:\s*(?:,|y)\s*{_ID_ANEXO})*)\s*"
               r"\(\s*(?:puestos\s+)?(?:a\s+)?resultas\s*\)"),
    re.compile(rf"anexos?\s+({_ID_ANEXO}),?\s+que solo podran ser adjudicad\w+ (?:en el caso )?(?:de )?que queden vacantes"),
)
MAX_PUESTO = 160


def _cl(s: str) -> str:
    return " ".join((s or "").split())


def _lineas_celda(td) -> list[str]:
    ps = td.find_all("p")
    ls = [_cl(p.get_text(" ")) for p in ps] if ps else [_cl(td.get_text(" "))]
    return [x for x in ls if x]


def _expandir(tr) -> list:
    """Celdas de una fila con cada colspan repetido: así casan las columnas
    de cabeceras a dos niveles («Adscripción» sobre Admón./Grupo)."""
    out = []
    for c in tr.find_all(["td", "th"], recursive=False) or tr.find_all(["td", "th"]):
        try:
            n = max(1, min(20, int(c.get("colspan") or 1)))
        except ValueError:
            n = 1
        out.extend([c] * n)
    return out


def _id_anexo(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", plano(s))


def _anexos_resultas(prosa: str) -> set:
    out = set()
    for rx in _ANEXO_RESULTAS:
        for m in rx.finditer(plano(prosa)):
            ids = re.split(r"\s*(?:,|\by\b)\s*", m.group(1))
            out.add(_id_anexo(ids[-1]))
    return out


def _puesto_fila(cs, m, con_nivel: bool = False) -> str | None:
    """Denominación del puesto; "" si la fila es un encabezado de unidad;
    None si la fila debería traer puesto y no se entiende. `con_nivel`: la
    fila trae nivel (22346: filas sin n.º de orden, que sí son puestos)."""
    num = con_nivel or bool(re.match(r"\d", _cl(cs[0].get_text(" "))))
    if "merge" in m:
        ls = _lineas_celda(cs[m["merge"]])
        cod = [x for x in ls if _CODIGO.search(x)]
        ic = [i for i, x in enumerate(ls) if _RE_COD_PUESTO.match(plano(x))]
        if len(cod) == 1:
            p = _CODIGO.sub("", cod[0]).strip(" .")
            # «Subdirector Adjunto/…» y «(5680246).» en dos <p> (21817).
            if not p and ls.index(cod[0]) > 0:
                p = ls[ls.index(cod[0]) - 1]
        elif cod:
            return None
        elif len(ic) == 1 and ic[0] > 0:
            p = ls[ic[0] - 1]
        elif num and ls:
            p = ls[-1]
        else:
            return ""
    else:
        # Columna «Denominación»/«Puestos de trabajo»: una línea, o unidades +
        # puesto + «Código de puesto: N» (20486). Varias líneas sin esa marca
        # pueden ser un nombre partido o unidad + puesto: no se adivina.
        ls = _lineas_celda(cs[m["puesto"]])
        ic = [i for i, x in enumerate(ls) if _RE_COD_PUESTO.match(plano(x))]
        if len(ic) == 1 and ic[0] > 0:
            p = ls[ic[0] - 1]
        elif len(ls) == 1:
            p = ls[0]
        elif not num:
            return ""
        else:
            return None
    # «Consejero/a (1).»: llamada a nota al pie fuera.
    p = re.sub(r"\s*\(\d\)\s*\.?$", "", _cl(p))
    p = re.sub(r"\s*/\s*", "/", p).strip(" .–-")
    if num and not re.search(r"[^\W\d_]{3}", p):
        return None                                       # código o número suelto
    return p


_PROV_TERMINOS: dict | None = None


_PROV_BILINGUES: dict = {}


def _terminos_prov() -> dict:
    """plano(nombre) -> forma con tildes, de curated/provincias.json:
    provincias, variantes bilingües y capitales."""
    global _PROV_TERMINOS
    if _PROV_TERMINOS is None:
        import json
        import pathlib
        d = json.loads((pathlib.Path(__file__).parent / "curated" / "provincias.json").read_text("utf-8"))
        t: dict = {}
        for p in d["provincias"]:
            for n in [p["nombre"], p.get("capital", ""), p.get("circunscripcion", "")] + list(p.get("variantes") or []):
                for x in [n] + n.split("/"):
                    if x.strip():
                        t.setdefault(plano(x), x.strip())
                if n.count("/") == 1:
                    a, b = (plano(x) for x in n.split("/"))
                    _PROV_BILINGUES.setdefault(frozenset((a, b)), n.strip())
        _PROV_TERMINOS = t
    return _PROV_TERMINOS


def _bilingues() -> dict:
    """{plano(A), plano(B)} -> «A/B» oficial («Pamplona/Iruña»)."""
    _terminos_prov()
    return _PROV_BILINGUES


def _dist(a: str, b: str) -> int:
    if abs(len(a) - len(b)) > 2:
        return 3
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


_MINUS = {"de", "del", "la", "las", "los", "el", "y", "i", "d", "da", "do", "das", "dos"}


def _titulo(s: str) -> str:
    m = re.fullmatch(r"(.+),\s*(a|o|el|la|los|las|l')", s, re.I)
    if m:
        s = f"{m.group(2)} {m.group(1)}"
    ps = s.lower().split()
    return " ".join(p if (i and p in _MINUS) else p[:1].upper() + p[1:] for i, p in enumerate(ps))


def limpia_localidad(s: str) -> str:
    """Localidad legible o "" si no es limpia. Formatos del BOE: «MADRID»,
    «MADRID - MADRID», «- A CORUÑA - CORUÑA, A», «PONTEVEDRA/ VIGO»,
    «MADRID-MADRID». Se toma el último tramo; se enseña si es una provincia o
    capital conocida (con su forma oficial) o si va detrás de una provincia
    conocida. Nunca se corrige: «MADRID/ MADRD» (errata) se descarta, igual
    que el extranjero o un tramo suelto que no se puede comprobar."""
    s = re.sub(r"\.(?=\s|$)", "", _cl(s)).strip(" .-–")
    if not s or "extranjero" in plano(s) or len(s) > 80:
        return ""
    t = _terminos_prov()
    # «PALMAS DE GRAN CANARIA (LAS)» -> «LAS PALMAS DE GRAN CANARIA».
    s = re.sub(r"^(.+?)\s*\((las|los|la|el|a|o)\)$", r"\2 \1", s, flags=re.I)
    # «Armilla (Granada)»: municipio y provincia conocida entre paréntesis.
    m = re.fullmatch(r"([^\W\d_][\w' .]{1,50}?)\s*\(([^)]+)\)", s)
    if m:
        if plano(m.group(2)) in t and not _errata(plano(m.group(1)), t):
            return f"{_titulo(m.group(1)) if m.group(1).isupper() else m.group(1)} ({t[plano(m.group(2))]})"
        return ""
    segs = [x.strip() for x in re.split(r"\s*[-–]+\s+|\s+[-–]+\s*|\s*/\s*", s) if x.strip(" -–")]
    segs = [m.group(1) if (m := re.fullmatch(r"(.+?)\s*-\s*(.+)", x)) and plano(m.group(1)) == plano(m.group(2)) else x
            for x in segs]
    if not segs or any(not re.fullmatch(r"[^\W\d_][\w' .,]*", x) for x in segs):
        return ""
    planos = [plano(x) for x in segs]
    if any(_errata(x, t) for x in planos):
        return ""
    ult = planos[-1]
    # «PAMPLONA/IRUÑA», «ALACANT/ALICANTE»: nombre bilingüe pegado, entero.
    if len(segs) >= 2 and (bil := _bilingues().get(frozenset(planos[-2:]))):
        return bil
    if ult in t:
        return t[ult]
    if len(segs) >= 2 and planos[-2] in t and len(ult) >= 3:
        # «PAMPLONA/IRUÑA»: nombre bilingüe pegado, se enseña entero.
        if re.search(re.escape(segs[-2]) + r"/" + re.escape(segs[-1]) + r"$", s):
            return f"{t[planos[-2]]}/{_titulo(segs[-1])}"
        return _titulo(segs[-1]) if segs[-1].isupper() else segs[-1]
    return ""


def _errata(x: str, t: dict) -> bool:
    """Un tramo a una letra (dos si es largo) de un nombre conocido sin
    serlo: «MADRD». Vigo/Lugo (dos letras, nombres cortos) no cuenta."""
    if x in t or len(x) < 4:
        return False
    tope = 2 if len(x) >= 8 else 1
    return any(_dist(x, k) <= tope for k in t if len(k) >= 4)


def campos_provision(texto: str, html: str = "") -> dict:
    """{'puestos': [{puesto, nivel?, localidad?, plazas?}], 'n_puestos': N,
    'resultas': M} desde las tablas del anexo; {} si no hay tabla de puestos
    reconocible o si una fila de puesto no se entiende (comprobación por
    documento: mejor nada que una lista a medias)."""
    if not html:
        return {}
    from bs4 import BeautifulSoup
    s = BeautifulSoup(html, "html.parser")
    prosa = " ".join(p.get_text(" ") for p in s.find_all("p") if not p.find_parent("table"))
    res_ids = _anexos_resultas(prosa)
    anexo, resultas, mirar = "", False, 0
    puestos, n_res, vista = [], 0, False
    for el in s.find_all(["p", "h2", "h3", "h4", "h5", "table"]):
        if el.name != "table":
            if el.find_parent("table"):
                continue
            t = plano(el.get_text(" "))
            m = _ANEXO.match(t)
            if m and len(t) < 120:
                anexo = _id_anexo(m.group(1))
                resultas, mirar = anexo in res_ids or "resultas" in t, 3
            elif mirar:
                mirar -= 1
                if len(t) < 120 and "resultas" in t:
                    resultas = True
            continue
        mirar = 0
        filas = el.find_all("tr")
        hdr, datos = None, []
        for tr in filas:
            cs = _expandir(tr)
            if hdr is None:
                if len(cs) >= 4:
                    hdr = [plano(c.get_text(" ")) for c in cs]
                continue
            datos.append(cs)
        if not hdr or re.search(_SKIP, " ".join(hdr)):
            continue
        m: dict = {}
        for i, c in enumerate(hdr):
            for k, rx in _COLS:
                if k not in m and re.search(rx, c):
                    m[k] = i
                    break
        if not (("puesto" in m or "merge" in m) and ("nivel" in m or "localidad" in m)):
            continue
        vista = True
        for cs in datos:
            if len({id(c) for c in cs}) == 1:
                continue                                  # nota a todo lo ancho
            if len(cs) != len(hdr):
                if re.match(r"\d", _cl(cs[0].get_text(" "))):
                    return {}
                continue
            col = m.get("merge", m.get("puesto"))
            if any(id(cs[m[k]]) == id(cs[col]) for k in ("nivel", "localidad") if k in m):
                continue                                  # unidad con colspan (20937)
            g = (lambda k: _cl(cs[m[k]].get_text(" ")) if k in m else "")
            nv, pl = g("nivel"), g("plazas")
            # «Madrid.» / «Madrid.» en dos <p> (provincia y localidad).
            lo = " - ".join(x.rstrip(".") for x in _lineas_celda(cs[m["localidad"]])) if "localidad" in m else ""
            if not (re.fullmatch(r"\d{1,2}", nv) or lo):
                continue                                  # encabezado de unidad
            if resultas or "a resultas" in plano(" ".join(c.get_text(" ") for c in cs)):
                n_res += 1
                continue
            p = _puesto_fila(cs, m, bool(re.fullmatch(r"\d{1,2}", nv)))
            if not p or len(p) > MAX_PUESTO:
                return {}
            x: dict = {"puesto": p}
            if re.fullmatch(r"\d{1,2}", nv) and 1 <= int(nv) <= 30:
                x["nivel"] = int(nv)
            if (loc := limpia_localidad(lo)):
                x["localidad"] = loc
            if re.fullmatch(r"\d{1,3}", pl) and int(pl) > 0:
                x["plazas"] = int(pl)
            puestos.append(x)
    if not vista or not puestos:
        return {}
    n = sum(x["plazas"] for x in puestos) if all("plazas" in x for x in puestos) else len(puestos)
    return {"puestos": puestos, "n_puestos": n, **({"resultas": n_res} if n_res else {})}


def puestos_activos(reg: dict) -> list[dict]:
    """Puestos de una provisión con solo los subcampos activos. Vacío si
    «puesto» no está activo, si es una no-oferta o si no hay lista."""
    ok = CAMPOS_ACTIVOS.get("provision", frozenset())
    if reg.get("no_oferta") or familia(reg) != "provision" or "puesto" not in ok:
        return []
    ps = (reg.get("campos") or {}).get("puestos") or []
    return [{k: v for k, v in x.items() if k in ok} for x in ps if x.get("puesto")]


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
