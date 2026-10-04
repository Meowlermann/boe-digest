"""Seguimiento de la tramitación de las iniciativas legislativas del Congreso.

Hasta ahora la web solo veía una ley cuando llegaba al BOE, ya aprobada. Lo
que pasa antes —quién la presenta, si se toma en consideración, cuántas veces
se amplía el plazo de enmiendas, si pasa al Senado o se retira— no aparecía,
y buscar un tema de actualidad parlamentaria no devolvía nada.

Fuentes, por este orden:

(a) Los datos abiertos de iniciativas del Congreso
    (https://www.congreso.es/es/opendata/iniciativas), regenerados cada día:
    ProyectosDeLey, ProposicionesDeLey y PropuestasDeReforma (una fila por
    iniciativa de la legislatura) e IniciativasLegislativasAprobadas (las
    leyes ya publicadas). Campos que se usan, comprobados en los ficheros
    reales: NUMEXPEDIENTE, OBJETO, TIPO, AUTOR, FECHAPRESENTACION,
    FECHACALIFICACION, SITUACIONACTUAL, RESULTADOTRAMITACION,
    COMISIONCOMPETENTE, TIPOTRAMITACION, PLAZOS, PONENTES,
    TRAMITACIONSEGUIDA, INICIATIVASRELACIONADAS y ENLACESBOCG; de las leyes,
    TITULO_LEY, NUMERO_LEY, NUMERO_BOLETIN, FECHA_BOLETIN, FECHA_LEY y PDF.
(b) La ficha del buscador de iniciativas (mostrarDetalle), solo para las que
    llegan sin tramitación seguida en (a). La URL y la limpieza del HTML son
    las mismas que usan las preguntas escritas (congreso_datos).
(c) Los reales decretos-ley no están en esos ficheros: su convalidación o
    derogación se toma de la votación del Pleno que ya guarda
    state/congreso.json.

Todo determinista: no se resume ni se interpreta nada. Lo único que se
«calcula» es el estado normalizado (ver ESTADOS y estado_de) y las
expresiones más repetidas del texto publicado, para el buscador.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import re
import time
import unicodedata

import congreso_datos as cd

RAIZ = pathlib.Path(__file__).resolve().parent
ESTADO = RAIZ / "state" / "tramitacion.json"
PAG_INICIATIVAS = f"{cd.CONGRESO}/es/opendata/iniciativas"
FICHEROS = ("ProyectosDeLey", "ProposicionesDeLey", "PropuestasDeReforma")
APROBADAS = "IniciativasLegislativasAprobadas"
VERSION = 1
MAX_FICHAS = 20            # fichas mostrarDetalle por ejecución, como respaldo
MAX_PIEZAS = 8             # piezas de tramitación por edición
DIAS_NOVEDADES = 30

# ------------------------------------------------------------------ estados
#
# Estados normalizados y de qué textos oficiales salen. La «situación actual»
# del Congreso es «órgano · fase» («Comisión de Justicia · Enmiendas») y el
# «resultado de la tramitación», cuando la iniciativa está cerrada,
# «Aprobado con modificaciones», «Retirado», «Caducado»…
#
#   slug                  etiqueta                  sale de
ESTADOS = [
    ("presentada", "Presentada",
     "Publicación, calificación de la Mesa o criterio del Gobierno (antes de debatirse)"),
    ("toma-en-consideracion", "Toma en consideración",
     "«Pleno · Toma en consideración»"),
    ("plazo-de-enmiendas", "Plazo de enmiendas",
     "«Comisión … · Enmiendas» (incluye sus ampliaciones)"),
    ("ponencia-comision", "Ponencia / comisión",
     "«Comisión … · Informe», «· Dictamen», «· Ponencia», competencia legislativa plena"),
    ("pleno", "Pleno",
     "«Pleno · Debate de totalidad», «Pleno · Aprobación», «Pleno · Enmiendas o veto del Senado»"),
    ("senado", "Senado", "«Senado»"),
    ("aprobada", "Aprobada", "Resultado «Aprobado…»"),
    ("rechazada", "Rechazada", "Resultado «Rechazado…» o «Inadmitido…»"),
    ("retirada", "Retirada", "Resultado «Retirado…»"),
    ("caducada", "Caducada", "Resultado «Caducado», «Decaído» o «Subsumido en otra iniciativa»"),
    ("convalidado", "Convalidado", "Real decreto-ley con más síes que noes en su votación de convalidación"),
    ("derogado", "Derogado", "Real decreto-ley con más noes que síes en esa votación"),
]
ETIQUETA = {s: e for s, e, _d in ESTADOS}
ABIERTOS = {"presentada", "toma-en-consideracion", "plazo-de-enmiendas", "ponencia-comision",
            "pleno", "senado"}
# Cambios que se cuentan en «Las Cortes hoy».
CAMINO = ["presentada", "toma-en-consideracion", "plazo-de-enmiendas", "ponencia-comision",
          "pleno", "senado", "aprobada"]
RELEVANTES = {"aprobada", "rechazada", "senado", "convalidado", "derogado"}

# Votaciones que tratan iniciativas legislativas: solo con estos títulos se
# intenta el cruce, para no enlazar una moción que cita una ley de pasada.
TITULOS_LEGISLATIVOS = ("Dictámenes de Comisiones sobre iniciativas legislativas",
                        "Enmiendas del Senado", "Toma en consideración de Proposiciones de Ley",
                        "Debates de totalidad de iniciativas legislativas",
                        "Dictamen de la Comisión del Estatuto",
                        "Toma en consideración de Proposición de reforma")


# ------------------------------------------------------------------ utilidades

def _txt(v) -> str:
    return " ".join(str(v or "").split())


def _lineas(v) -> str:
    """«Comisión de Justicia\\nEnmiendas» -> «Comisión de Justicia · Enmiendas»."""
    return " · ".join(_txt(l) for l in str(v or "").splitlines() if _txt(l))


def _fecha(v: str) -> str:
    """«23/12/2025» -> «2025-12-23»; "" si no hay fecha."""
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", v or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def exp_corto(exp: str) -> str:
    """«122/000231/0000» -> «122/000231», que es como lo cita el Congreso."""
    m = re.match(r"(\d{3}/\d{6})", exp or "")
    return m.group(1) if m else (exp or "")


def slug(exp: str) -> str:
    if exp.startswith("RDL "):
        return "rdl-" + exp[4:].replace("/", "-")
    return exp_corto(exp).replace("/", "-")


def url_ficha(exp: str) -> str:
    return "" if exp.startswith("RDL ") else cd.ficha_iniciativa_url(exp)


def nucleo(objeto: str) -> str:
    """El tema sin el tipo delante ni la procedencia detrás: sirve para casar
    la iniciativa con la ley aprobada y con las votaciones, que la citan con
    otras palabras alrededor."""
    t = _txt(objeto)
    t = re.sub(r"^(Proyecto|Proposición)\s+de\s+Ley(\s+Orgánica)?\s*", "", t, flags=re.I)
    t = re.sub(r"^(Propuesta\s+de\s+reforma\s+del?\s+)", "", t, flags=re.I)
    t = re.sub(r"\s*\(procedente del[^)]*\)\.?\s*$", "", t, flags=re.I)
    return t.rstrip(". ")


def pasos(texto: str) -> list[list[str]]:
    """TRAMITACIONSEGUIDA en pasos [órgano · fase, desde, hasta].

    El campo viene en líneas: una o dos con el órgano y la fase y después
    «desde dd/mm/aaaa [hasta dd/mm/aaaa]». Hay pasos con una sola etiqueta
    («Senado», «Concluido - (Aprobado con modificaciones)»)."""
    salida, etiqueta = [], []
    for linea in (texto or "").splitlines():
        linea = _txt(linea)
        if not linea:
            continue
        m = re.match(r"^desde\s+(\d{2}/\d{2}/\d{4})(?:\s+hasta\s+(\d{2}/\d{2}/\d{4}))?", linea)
        if m:
            salida.append([" · ".join(etiqueta), _fecha(m.group(1)), _fecha(m.group(2) or "")])
            etiqueta = []
        else:
            etiqueta.append(linea)
    if etiqueta:
        salida.append([" · ".join(etiqueta), "", ""])
    return salida


def pasos_de_ficha(texto: str) -> list[list[str]]:
    """Lo mismo, desde el texto plano de la ficha mostrarDetalle, donde las
    líneas llegan juntas: «Comisión de Justicia Enmiendas desde … hasta …»."""
    m = re.search(r"Tramitación seguida\s+(.+?)(?:\s+(?:Ponentes|Iniciativas relacionadas|"
                  r"Enlaces|Boletines|Diarios)\b|$)", texto or "")
    if not m:
        return []
    return [[_txt(e), _fecha(d), _fecha(h or "")] for e, d, h in re.findall(
        r"(.+?)\s+desde\s+(\d{2}/\d{2}/\d{4})(?:\s+hasta\s+(\d{2}/\d{2}/\d{4}))?\s*", m.group(1))]


def plazos(texto: str) -> list[list[str]]:
    """«Hasta: 05/10/2026 (18:00) De enmiendas Hasta: …» -> [[fecha, hora, qué]]."""
    t = _txt(texto)
    return [[_fecha(m.group(1)), m.group(2) or "", _txt(m.group(3))] for m in re.finditer(
        r"Hasta:\s*(\d{2}/\d{2}/\d{4})(?:\s*\((\d{1,2}:\d{2})\))?\s*(.*?)(?=\s*Hasta:|$)", t)]


def resultado_texto(v: dict) -> str:
    """Cómo acabó, en palabras del Congreso: «Aprobado con modificaciones»…"""
    if v.get("res"):
        return re.sub(r"\s*\d{2}/\d{2}/\d{4}.*$", "", v["res"]).strip()
    for p in reversed(v.get("pasos") or []):
        m = re.search(r"Concluido\s*-\s*\(([^)]+)\)", p[0])
        if m:
            return m.group(1)
    return ""


def estado_de(v: dict) -> str:
    """El estado normalizado. La correspondencia está en ESTADOS."""
    if v.get("tipo") == "Real Decreto-ley":
        return v.get("est") or "convalidado"
    if v.get("cerrado"):
        r = _norm(resultado_texto(v))
        if r.startswith("aprobad"):
            return "aprobada"
        if r.startswith(("rechazad", "inadmitid", "no tomad", "desestimad")):
            return "rechazada"
        if r.startswith("retirad"):
            return "retirada"
        return "caducada"
    s = v.get("sit") or ""
    if re.search(r"\bSenado\b", s) and not re.search(r"Pleno\s*·\s*Enmiendas o veto", s):
        return "senado"
    if re.search(r"Toma en consideración", s):
        return "toma-en-consideracion"
    if s.startswith("Pleno"):
        return "pleno"
    if re.search(r"·\s*Enmiendas\b", s):
        return "plazo-de-enmiendas"
    if re.search(r"Informe|Dictamen|Ponencia|Competencia|Debate de totalidad|Comparecencia", s):
        return "pleno" if "Debate de totalidad" in s and s.startswith("Pleno") else "ponencia-comision"
    return "presentada"


def hitos(v: dict) -> list[dict]:
    """La tramitación seguida como hitos {fecha, hito}, en orden."""
    return [{"f": p[1], "h": p[0]} for p in v.get("pasos") or [] if p[1]]


def enmiendas(v: dict) -> tuple[str, int]:
    """(fin del plazo de enmiendas vigente, veces que se ha ampliado)."""
    de_enm = [p for p in v.get("plazos") or [] if re.search(r"enmienda", p[2], re.I)]
    amp = sum(1 for p in de_enm if re.search(r"ampliaci", p[2], re.I))
    return (max((p[0] for p in de_enm), default=""), amp)


def ultima_fecha(v: dict) -> str:
    fechas = [h["f"] for h in hitos(v)] + [v.get("fp") or ""]
    return max(fechas) if any(fechas) else ""


def tipo_corto(t: str) -> str:
    t = t or ""
    if t.startswith("Proyecto"):
        return "Proyecto de ley"
    if "Orgánica" in t:
        return "Proposición de ley orgánica"
    if t.startswith("Proposición"):
        return "Proposición de ley"
    if t.startswith("Propuesta"):
        return "Reforma de Estatuto"
    return t or "Iniciativa"


def grupo_corto(autor: str) -> str:
    return re.sub(r"^Grupo Parlamentario\s+", "", autor or "").replace(" en el Congreso", "")


def slug_autor(autor: str) -> str:
    """Slug de la página de un autor. Las autorías conjuntas largas se cortaban
    a 60 caracteres y dos distintas acababan en la misma URL (sitemap con la
    URL duplicada y una página pisando a la otra, octubre de 2026). Si hay que
    cortar, se añade un resumen corto del nombre completo para distinguirlas."""
    nombre = grupo_corto(autor) or "sin-autor"
    base = cd._slug(nombre)
    if len(base) <= 60:
        return base
    return base[:51].rstrip("-") + "-" + hashlib.sha1(nombre.encode("utf-8")).hexdigest()[:8]



# ------------------------------------------------------------ de qué trata

# El título oficial no siempre dice de qué va una ley: la que recorta la
# acusación popular se llama «de garantía y protección de los derechos
# fundamentales frente al acoso derivado de acciones judiciales abusivas».
# Para que el buscador la encuentre por el nombre con el que se conoce, se
# leen las expresiones que más se repiten en el texto publicado en el Boletín
# de las Cortes. Sin modelo: solo se cuentan pares de palabras.
_VACIAS = set("""a al ante bajo cabe con contra de del desde durante en entre hacia hasta mediante
para por segun sin so sobre tras y e o u ni que el la los las lo un una unos unas su sus se es son
ser sera seran fue han ha haber hay como mas muy tambien este esta estos estas ese esa esos esas aquel
dicho dicha dichos dichas cual cuales cuyo cuya donde cuando asi otro otra otros otras todo toda todos
todas cada mismo misma mismos mismas sino pero porque pues ya no si le les nos sera podra podran debe
deberan puede pueden sera siendo sido tiene tienen presente presentes primero segundo tercero
articulo articulos apartado apartados parrafo letra disposicion disposiciones adicional transitoria
final derogatoria ley leyes organica proposicion proyecto texto redaccion modifica modificacion
queda quedan redactado redactada siguiente siguientes siguiente numero punto
cve bocg pag num serie generales oficial cortes congreso diputados senado boletin
enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre""".split())
_MUERTOS = {"boletin oficial", "cortes generales", "congreso diputados", "grupo parlamentario",
            "mesa camara", "diario sesiones", "oficial estado", "entrada vigor", "boletin cortes",
            "serie proposiciones", "diputados serie", "palacio congreso", "portavoz grupo",
            "reglamento camara", "exposicion motivos", "lengua espanola"}


KW_V = 2      # sube cuando cambia terminos(): obliga a releer los boletines


def terminos(texto: str, maximo: int = 25) -> list[str]:
    """Las expresiones de dos palabras más repetidas del texto, sin las
    fórmulas de cualquier ley («entrada en vigor», «Boletín Oficial»…)."""
    palabras = re.findall(r"[a-záéíóúñü]+", (texto or "").lower())
    utiles = [(w, _norm(w)) for w in palabras]
    # Más de tres letras: fuera artículos sueltos y los restos de palabras que
    # el PDF parte cuando no sabe leer un acento («aut noma», «mat ria»).
    utiles = [(w, n) for w, n in utiles if len(n) > 3 and n not in _VACIAS]
    cuenta: dict = {}
    forma: dict = {}
    for (w1, n1), (w2, n2) in zip(utiles, utiles[1:]):
        clave = f"{n1} {n2}"
        if clave in _MUERTOS or n1 == n2:
            continue
        cuenta[clave] = cuenta.get(clave, 0) + 1
        forma.setdefault(clave, f"{w1} {w2}")
    top = sorted((c for c in cuenta.items() if c[1] >= 3), key=lambda x: (-x[1], x[0]))
    return [forma[k] for k, _n in top[:maximo]]


def kw_limpios(v: dict) -> list[str]:
    """Los términos guardados, pasados otra vez por el filtro actual: si el
    filtro mejora, no hace falta volver a descargar los PDF."""
    salida = []
    for t in v.get("kw") or []:
        ns = _norm(t).split()
        if len(ns) == 2 and all(len(n) > 3 and n not in _VACIAS for n in ns) and " ".join(ns) not in _MUERTOS:
            salida.append(t)
    return salida


# ------------------------------------------------ dónde está y por qué
#
# La etiqueta del estado («Toma en consideración») no dice si una iniciativa
# avanza o lleva meses parada, ni de quién depende que se mueva. situacion()
# lo explica con los datos oficiales: desde cuándo está en la fase actual y
# qué tiene que pasar para salir de ella. Las reglas que se citan son del
# Reglamento del Congreso (art. 126: criterio del Gobierno; art. 91:
# ampliación de plazos por la Mesa) y de la Constitución (art. 90: plazos del
# Senado).

# A partir de aquí, una iniciativa en plazo de enmiendas se considera «en el
# congelador»: la Mesa ha ampliado el plazo al menos estas veces y lleva al
# menos estos días sin pasar a ponencia. Con ampliaciones semanales, unos
# tres meses.
CONGELADOR_AMP = 10
CONGELADOR_DIAS = 90

# Rótulos oficiales de la tramitación que no se entienden solos.
NOTA_PASO = {
    "Gobierno · Contestación": "plazo del Gobierno para dar su criterio sobre la proposición, art. 126 del Reglamento",
    "Mesa del Congreso · Requerimiento de aclaración": "la Mesa pide al autor que aclare o corrija la iniciativa",
    "Mesa del Congreso · Acuerdo subsiguiente a la toma en consideración": "la Mesa decide a qué comisión va y cómo se tramita",
}


def _dias_entre(a: str | None, b: str) -> int | None:
    try:
        return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days if a else None
    except ValueError:
        return None


def congelada(v: dict, hoy: str | None = None) -> bool:
    hoy = hoy or dt.date.today().isoformat()
    if v.get("est") != "plazo-de-enmiendas" or (v.get("amp") or 0) < CONGELADOR_AMP:
        return False
    pasos = v.get("pasos") or []
    desde = pasos[-1][1] if pasos else v.get("fp")
    return (_dias_entre(desde, hoy) or 0) >= CONGELADOR_DIAS


def situacion(v: dict, hoy: str | None = None) -> dict | None:
    """{"titulo", "texto", "desde", "dias"} para las abiertas; None para las
    cerradas, que ya lo dicen con su resultado."""
    hoy = hoy or dt.date.today().isoformat()
    est = v.get("est")
    if est not in ABIERTOS:
        return None
    pasos = v.get("pasos") or []
    ult = pasos[-1] if pasos else None
    paso = ult[0] if ult else ""
    desde = (ult[1] if ult else None) or v.get("fp")
    dias = _dias_entre(desde, hoy)
    cuanto = f" desde el {_fecha_txt(desde)} (hace {dias} días)" if desde and dias is not None else ""
    amp = v.get("amp") or 0
    if est == "presentada":
        if paso == "Gobierno · Contestación":
            plazo = next((p[0] for p in reversed(v.get("plazos") or []) if "criterio" in _norm(p[2] or "")), None)
            return {"titulo": "Esperando el criterio del Gobierno",
                    "texto": (f"El Gobierno tiene treinta días para decir si está de acuerdo con que se tramite"
                              f"{' (hasta el ' + _fecha_txt(plazo) + ')' if plazo else ''}. Pasado ese plazo "
                              "sin oposición expresa, la proposición puede incluirse en el orden del día del "
                              "Pleno para su toma en consideración (art. 126 del Reglamento)."),
                    "desde": desde, "dias": dias}
        if "aclaraci" in _norm(paso):
            return {"titulo": "La Mesa ha pedido una aclaración",
                    "texto": f"La Mesa del Congreso ha pedido al autor que aclare o corrija la iniciativa{cuanto}. "
                             "Hasta que lo haga, no se tramita.", "desde": desde, "dias": dias}
        return {"titulo": "Recién presentada",
                "texto": f"Registrada y pendiente de los primeros trámites de la Mesa{cuanto}.",
                "desde": desde, "dias": dias}
    if est == "toma-en-consideracion":
        return {"titulo": "Pendiente de debate en el Pleno",
                "texto": (f"Lista para el debate de toma en consideración{cuanto}: el plazo del Gobierno ya "
                          "pasó. Falta que se incluya en el orden del día de un Pleno, que fija la Presidencia "
                          "de acuerdo con la Junta de Portavoces; en la práctica, cada grupo decide cuándo "
                          "lleva sus proposiciones dentro del cupo de iniciativas que le corresponde. Hasta "
                          "entonces no avanza."),
                "desde": desde, "dias": dias}
    if est == "plazo-de-enmiendas":
        if congelada(v, hoy):
            return {"titulo": f"En el «congelador»: plazo de enmiendas ampliado {amp} veces",
                    "texto": (f"{'Está' if (v.get('tipo') or '').startswith('Proyecto') else 'Ya se tomó en consideración y está'}"
                              f" en plazo de enmiendas{cuanto}. La Mesa del "
                              f"Congreso ha ampliado ese plazo {amp} veces, normalmente semana a semana (art. 91 "
                              "del Reglamento). Mientras se siga ampliando, el texto no pasa a la ponencia y la "
                              "tramitación no avanza: es lo que en el lenguaje parlamentario se llama "
                              "«congelador»."),
                    "desde": desde, "dias": dias, "congelada": True}
        fe = v.get("fe")
        return {"titulo": "En plazo de enmiendas",
                "texto": (f"Los grupos pueden presentar enmiendas{' hasta el ' + _fecha_txt(fe) if fe else ''}"
                          f"{'; el plazo se ha ampliado ' + str(amp) + (' vez' if amp == 1 else ' veces') if amp else ''}. "
                          "Cuando se cierre, el texto pasa a la ponencia y a la comisión."),
                "desde": desde, "dias": dias}
    if est == "ponencia-comision":
        donde = paso or (f"Comisión de {v['com']}" if v.get("com") else "la comisión")
        return {"titulo": "En la comisión",
                "texto": (f"{donde}{cuanto}. La ponencia estudia las enmiendas y redacta un informe; la "
                          "comisión aprueba su dictamen, que va al Pleno, o directamente al Senado si la "
                          "comisión tiene competencia legislativa plena."),
                "desde": desde, "dias": dias}
    if est == "pleno":
        return {"titulo": "En el Pleno", "texto": f"{paso or 'Pleno'}{cuanto}.", "desde": desde, "dias": dias}
    if est == "senado":
        return {"titulo": "En el Senado",
                "texto": (f"Aprobada por el Congreso y enviada al Senado{cuanto}. El Senado tiene dos meses "
                          "para aprobarla, enmendarla o vetarla (veinte días naturales si es urgente; art. 90 "
                          "de la Constitución). Si la enmienda o la veta, vuelve al Congreso."),
                "desde": desde, "dias": dias}
    return None


def _fecha_txt(iso: str | None) -> str:
    """«3 de septiembre de 2026»."""
    try:
        d = dt.date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or ""
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
             "septiembre", "octubre", "noviembre", "diciembre"]
    return f"{d.day} de {meses[d.month - 1]} de {d.year}"


# ------------------------------------------------- de qué trata el texto
#
# Las palabras más repetidas («impuesto sucesiones, base imponible…») no
# decían de qué va una ley. Del mismo boletín se sacan dos cosas que sí lo
# dicen, las dos literales:
#   - «em»: la frase de la exposición de motivos en la que el autor explica
#     qué hace el texto. Primero la del objeto («tiene por objeto…», «la
#     presente ley modifica…»); si no hay, la que describe su estructura («La
#     presente norma consta de 36 artículos…, mediante las cuales se
#     configura…»); si tampoco, el arranque de la exposición. Se presenta
#     como palabras del autor, no como resumen nuestro.
#   - «art»: los títulos de los artículos y disposiciones («Artículo 4. Hecho
#     imponible.», «Artículo único. Modificación de la Ley 37/1992…»). Los que
#     van entre comillas son el texto que se modifica, no la estructura, y se
#     saltan.
# Formato comprobado en BOCG-15-B-335-1 (122/000283) el 2 de octubre de 2026.

CONT_V = 1    # sube cuando cambia contenido(): obliga a releer los boletines
LARGO_EM = 600
MAX_ART = 14

_OBJETO = re.compile(
    r"(tiene (?:por|como) (?:objeto|finalidad)|el objeto de (?:esta|la presente)|"
    r"(?:esta|la presente) (?:ley|norma|proposición(?: de ley)?|reforma) (?:pretende|persigue|"
    r"propone|modifica|crea|regula|establece|introduce|incorpora))", re.I)
_ESTRUCTURA = re.compile(r"\b(consta de|se estructura en|se compone de|se divide en|se articula en)\b", re.I)
_CABECERA = re.compile(r"BOLET[ÍI]N OFICIAL\s+DE LAS CORTES GENERALES.{0,220}?P[áa]g\.\s*\d+", re.S)
_TITULO_ART = re.compile(
    r"(?<![«\"“])\b((?:Art[íi]culo (?:\d+(?: bis| ter)?|único|primero|segundo|tercero)|"
    r"Disposici[óo]n (?:adicional|transitoria|derogatoria|final)(?: [a-záéíóú]+)?)\.\s+"
    r"[A-ZÁÉÍÓÚÑ][^.«»]{2,140}\.)")


def _plano(texto: str) -> str:
    t = re.sub(r"(\w)-\n(\w)", r"\1\2", texto or "")
    t = _CABECERA.sub(" ", t)
    t = re.sub(r"cve:\s*\S+", " ", t)
    t = " ".join(t.split())
    try:
        import respuestas as rp
        t = rp.reparar_partidas(t)
    except Exception:                                          # noqa: BLE001
        pass
    return t


def _frases_desde(texto: str, pos: int, largo: int = LARGO_EM) -> str:
    """Desde el principio de la frase que contiene `pos`, frases enteras hasta
    `largo` caracteres; «[…]» si sigue."""
    ini = max(texto.rfind(". ", 0, pos) + 2, 0) if texto.rfind(". ", 0, pos) >= 0 else 0
    resto = texto[ini:]
    frases = re.split(r"(?<=[.;])\s+(?=[A-ZÁÉÍÓÚÑ¿«])", resto)
    salida = ""
    for f in frases:
        if salida and len(salida) + len(f) + 1 > largo:
            break
        salida = f"{salida} {f}".strip()
        if len(salida) >= largo:
            break
    if len(salida) > largo + 200:
        salida = salida[:largo].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    elif len(salida) < len(resto.strip()):
        salida += " […]"
    return salida


def contenido(texto: str) -> dict:
    """{"em": cita de la exposición de motivos, "art": [títulos], "n": total}.
    Vacío si el boletín no tiene exposición de motivos reconocible."""
    t = _plano(texto)
    m = re.search(r"Exposici[óo]n de motivos", t, re.I)
    if not m:
        return {}
    cuerpo_ini = re.search(r"(?<![«\"“])\bArt[íi]culo (?:1|primero|único)\.\s", t[m.end():])
    fin = m.end() + cuerpo_ini.start() if cuerpo_ini else min(len(t), m.end() + 20_000)
    em = t[m.end():fin]
    # Los números romanos de las secciones («I», «V») no son texto.
    em = re.sub(r"(^|\s)(?:I{1,3}|IV|VI{0,3}|IX|XI{0,3})\s+(?=[A-ZÁÉÍÓÚÑ])", " ", em).strip()
    salida: dict = {}
    for patron in (_OBJETO, _ESTRUCTURA):
        mm = patron.search(em)
        if mm:
            salida["em"] = _frases_desde(em, mm.start())
            break
    if "em" not in salida and em:
        salida["em"] = _frases_desde(em, 0)
    titulos, vistos = [], set()
    for mt in _TITULO_ART.finditer(t[fin:]):
        tit = mt.group(1).strip()
        clave = tit.split(".")[0].lower()
        if clave in vistos:
            continue
        vistos.add(clave)
        titulos.append(tit[:160])
    salida["n"] = len(titulos)
    salida["art"] = titulos[:MAX_ART]
    return {k: v for k, v in salida.items() if v}


def completar_terminos(e: dict, pdf_text, log, maximo: int = 400) -> int:
    """Lee el primer boletín de cada iniciativa que aún no tenga términos. Por
    tandas: la primera vez son cientos de PDF, y cada edición completa unos
    pocos. Lo más reciente primero, que es lo que se busca."""
    hechas = 0
    pendientes = sorted(((v.get("fp") or "", k) for k, v in (e.get("ini") or {}).items()
                         if v.get("bocg") and (v.get("kw_src") != v["bocg"][0] or v.get("kw_v") != KW_V
                                               or v.get("cont_v") != CONT_V)),
                        reverse=True)
    for _f, k in pendientes[:maximo]:
        v = e["ini"][k]
        try:
            texto = pdf_text(v["bocg"][0], max_chars=80_000)
        except Exception as exc:                              # noqa: BLE001
            log(f"tramitación: no se pudo leer el boletín de {k} ({exc})")
            continue
        if not texto:
            continue
        v["kw"] = terminos(texto)          # solo para el buscador
        v["kw_src"] = v["bocg"][0]
        v["kw_v"] = KW_V
        v["cont"] = contenido(texto)
        v["cont_v"] = CONT_V
        hechas += 1
    if hechas:
        guardar(e)
    log(f"tramitación: términos leídos de {hechas} boletines; "
        f"{max(0, len(pendientes) - hechas)} pendientes")
    return hechas


# ---------------------------------------------------------------------- estado

def cargar() -> dict:
    try:
        e = json.loads(ESTADO.read_text(encoding="utf-8"))
        if e.get("version") == VERSION:
            e.setdefault("publicado", {})
            return e
    except Exception:                                         # noqa: BLE001
        pass
    return {"version": VERSION, "ini": {}, "leyes": [], "publicado": {}, "actualizado": ""}


def guardar(e: dict) -> None:
    ESTADO.parent.mkdir(exist_ok=True)
    texto = json.dumps(e, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if not ESTADO.exists() or ESTADO.read_text(encoding="utf-8") != texto:
        ESTADO.write_text(texto, encoding="utf-8")


def _registro(x: dict) -> dict:
    sit = _lineas(x.get("SITUACIONACTUAL"))
    v = {
        "t": _txt(x.get("OBJETO")),
        "tipo": _txt(x.get("TIPO")),
        "a": _txt(x.get("AUTOR")),
        "fp": _fecha(x.get("FECHAPRESENTACION") or ""),
        "fc": _fecha(x.get("FECHACALIFICACION") or ""),
        "sit": sit,
        "cerrado": sit.startswith(("Cerrado", "Concluido")),
        "res": _txt(x.get("RESULTADOTRAMITACION")),
        "com": _txt(x.get("COMISIONCOMPETENTE")),
        "trt": _txt(x.get("TIPOTRAMITACION")),
        "pon": _txt(x.get("PONENTES")),
        "pasos": pasos(x.get("TRAMITACIONSEGUIDA") or ""),
        "plazos": plazos(x.get("PLAZOS") or ""),
        "bocg": [u.split("#")[0] for u in re.findall(r"https?://\S+?\.PDF(?:#page=\d+)?",
                                                    x.get("ENLACESBOCG") or "", re.I)][:30],
        "rel": sorted(set(re.findall(r"\d{3}/\d{6}", x.get("INICIATIVASRELACIONADAS") or ""))),
    }
    return completar_derivados(v)


def completar_derivados(v: dict) -> dict:
    """Los campos que se calculan de los oficiales: estado, hitos, plazo de
    enmiendas y ampliaciones. Se guardan para que las páginas y el buscador
    no tengan que recalcularlos."""
    v["est"] = estado_de(v)
    v["hitos"] = hitos(v)
    v["fe"], v["amp"] = enmiendas(v)
    return v


def ley_de(v: dict, leyes: list) -> dict | None:
    """La ley aprobada que sale de esta iniciativa, si el título casa entero.
    Si no casa, no se enlaza nada: mejor sin enlace que con uno equivocado."""
    if v.get("est") != "aprobada":
        return None
    clave = _norm(nucleo(v["t"]))[:90]
    if len(clave) < 20:
        return None
    for l in leyes or []:
        if clave in _norm(l.get("titulo")):
            return l
    return None


def rdl_de_votaciones(detalle: list) -> dict:
    """Reales decretos-ley convalidados o derogados, desde las votaciones del
    Pleno ya guardadas. El asunto votado es el título del real decreto-ley."""
    salida = {}
    for d in detalle or []:
        if not (d.get("t") or "").startswith("Convalidación o derogación de Reales Decretos-leyes"):
            continue
        a = _txt(d.get("a"))
        m = re.match(r"Real Decreto-ley (\d+)/(\d{4})", a)
        if not m:
            continue            # «Tramitación como proyecto de ley…» es otra votación
        try:
            tot = json.loads(d.get("tot") or "[]") if isinstance(d.get("tot"), str) else (d.get("tot") or [])
        except Exception:                                     # noqa: BLE001
            tot = []
        if len(tot) < 2:
            continue
        exp = f"RDL {m.group(1)}/{m.group(2)}"
        salida[exp] = completar_derivados({
            "t": a.rstrip("."), "tipo": "Real Decreto-ley", "a": "Gobierno", "fp": "", "fc": "",
            "sit": "Pleno · Convalidación o derogación", "cerrado": True,
            "res": "Convalidado" if tot[0] > tot[1] else "Derogado",
            "est": "convalidado" if tot[0] > tot[1] else "derogado",
            "com": "", "trt": "", "pon": "", "plazos": [], "bocg": [], "rel": [],
            "pasos": [["Pleno · Convalidación o derogación", d["f"], d["f"]]],
            "vot": [d["url"]] if d.get("url") else [],
        })
    return salida


def actualizar(get, log, detalle: list | None = None) -> tuple[dict, dict]:
    """Descarga los ficheros del día y devuelve (estado nuevo, estado anterior).
    El anterior sirve para saber qué ha cambiado: es lo que alimenta las
    piezas de «Las Cortes hoy»."""
    e = cargar()
    anterior = json.loads(json.dumps(e))
    r = get(PAG_INICIATIVAS, tries=2)
    if not r:
        log("tramitación: la página de datos abiertos no responde; se sigue con el estado")
        return e, anterior
    urls = cd._urls_json(r.text)
    nuevos: dict = {}
    for nombre in FICHEROS:
        u = cd._elegir(urls, nombre + "__") or cd._elegir(urls, nombre)
        d = get(u, tries=2) if u else None
        try:
            filas = d.json() if d else []
        except Exception as exc:                              # noqa: BLE001
            log(f"tramitación: {nombre} ilegible ({exc})")
            filas = []
        filas = filas if isinstance(filas, list) else []
        for x in filas:
            exp = exp_corto(x.get("NUMEXPEDIENTE") or "")
            if exp:
                nuevos[exp] = _registro(x)
        log(f"tramitación: {nombre}: {len(filas)} filas")
    if not nuevos:
        log("tramitación: ningún fichero legible; se conserva el estado anterior")
        return e, anterior

    # (b) Respaldo: las que llegan sin tramitación seguida, desde su ficha.
    # Lo leído de una ficha otro día se reutiliza mientras el fichero siga sin
    # traer la tramitación y la situación no haya cambiado.
    for k, v in nuevos.items():
        antes = (e.get("ini") or {}).get(k) or {}
        if not v["pasos"] and antes.get("pasos") and antes.get("sit") == v["sit"]:
            v["pasos"] = antes["pasos"]
            completar_derivados(v)
    sin_pasos = [k for k, v in nuevos.items() if not v["pasos"]][:MAX_FICHAS]
    for k in sin_pasos:
        time.sleep(cd.PAUSA_BUSCADOR)
        rr = get(cd.ficha_iniciativa_url(k), tries=1)
        if rr:
            ps = pasos_de_ficha(cd.texto_html(rr.text))
            if ps:
                nuevos[k]["pasos"] = ps
                completar_derivados(nuevos[k])
    if sin_pasos:
        log(f"tramitación: {len(sin_pasos)} fichas leídas por falta de tramitación seguida")

    u = cd._elegir(urls, APROBADAS)
    d = get(u, tries=2) if u else None
    try:
        leyes = d.json() if d else []
    except Exception:                                         # noqa: BLE001
        leyes = []
    if isinstance(leyes, list) and leyes:
        e["leyes"] = [{"tipo": _txt(l.get("TIPO")), "num": _txt(l.get("NUMERO_LEY")),
                       "titulo": _txt(l.get("TITULO_LEY")), "fl": _fecha(l.get("FECHA_LEY") or ""),
                       "boe": _txt(l.get("NUMERO_BOLETIN")), "fb": _fecha(l.get("FECHA_BOLETIN") or ""),
                       "pdf": _txt(l.get("PDF"))} for l in leyes]
    for v in nuevos.values():
        v["ley"] = ley_de(v, e["leyes"])
    nuevos.update(rdl_de_votaciones(detalle))

    # Los términos cuestan un PDF cada uno: se conservan mientras el boletín
    # del que salieron sea el mismo.
    for exp, v in nuevos.items():
        antes = (e.get("ini") or {}).get(exp) or {}
        if antes.get("kw_src") and v.get("bocg") and antes["kw_src"] == v["bocg"][0]:
            v["kw"], v["kw_src"], v["kw_v"] = antes.get("kw") or [], antes["kw_src"], antes.get("kw_v")
            if antes.get("cont_v"):
                v["cont"], v["cont_v"] = antes.get("cont") or {}, antes["cont_v"]
    e["ini"] = nuevos
    e["actualizado"] = dt.date.today().isoformat()
    guardar(e)
    cuenta: dict = {}
    for v in nuevos.values():
        cuenta[v["est"]] = cuenta.get(v["est"], 0) + 1
    log(f"tramitación: {len(nuevos)} iniciativas; por estado {cuenta}")
    return e, anterior


# ------------------------------------------------------------------ cruces

def votaciones_de(v: dict, detalle: list) -> list:
    """Votaciones del Pleno sobre esta iniciativa. Solo se cruza con votaciones
    de títulos legislativos y si el tema entero aparece en el asunto votado;
    si el cruce no es seguro, no se enlaza."""
    if v.get("vot"):
        return [d for d in detalle or [] if d.get("url") in v["vot"]]
    clave = _norm(nucleo(v["t"]))
    if len(clave) < 30:
        return []
    return [d for d in detalle or []
            if (d.get("t") or "").startswith(TITULOS_LEGISLATIVOS) and clave in _norm(d.get("a"))]


# ---------------------------------------------------------- «Las Cortes hoy»

# Dónde se puede cortar un título oficial sin cambiar lo que dice: lo que
# viene detrás es la segunda parte de una ley «ómnibus» o el origen del texto.
_CORTES = (r",\s+y\s+por\s+(?:el|la)\s+que\s", r",\s+por\s+(?:el|la)\s+que\s+se\s+modifica",
           r"\s+\(procedente\s", r",\s+y\s+se\s", r";\s")
MAX_CORTO = 150


def titulo_corto(exp: str, t: str, maximo: int = MAX_CORTO) -> str:
    """El titular de una iniciativa. Primero el escrito a mano en
    curated/nombres_populares.json; si no hay, el oficial cortado en la primera
    subordinada que añade otra materia («, y por el que se modifica…»); si aún
    es largo, en la última coma o «y» antes de `maximo`. El título oficial
    completo se sigue mostrando en la página."""
    try:
        import nombres
        mano = nombres.corto(exp)
        if mano:
            return mano
    except Exception:                                         # noqa: BLE001
        pass
    t = _txt(t).rstrip(".")
    fin = min((m.start() for rx in _CORTES for m in [re.search(rx, t)] if m and m.start() > 30),
              default=len(t))
    t = t[:fin].rstrip(" ,;")
    if len(t) <= maximo:
        return t
    # Se corta en una coma, pero nunca en las de una fecha («8/2015, de 30 de
    # octubre, …»): el lector se quedaría sin saber qué se modifica.
    def buena(m):
        antes, despues = t[:m.start()], t[m.end():]
        return (m.start() > 40 and not re.match(r"de \d{1,2} de ", despues)
                and not re.search(r"\bde \d{1,2} de [a-z]+$", antes))
    m = max((m.start() for m in re.finditer(r",\s", t[:maximo]) if buena(m)), default=0)
    return (t[:m] if m else t[:maximo].rsplit(" ", 1)[0]).rstrip(" ,;") + "…"


def _cita(t: str, n: int = 120) -> str:
    t = _txt(t).rstrip(".")
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


def feed(e: dict, anterior: dict, hoy: str, fmt_date_es, site_url: str) -> list:
    """Piezas «Tramitación» para la edición: iniciativas nuevas, cambios de
    estado relevantes y plazos de enmiendas que terminan esta semana.

    Cada pieza se apunta en e["publicado"] con una clave estable y no se
    vuelve a publicar. La primera vez no hay estado anterior: no se sabe qué
    es nuevo, así que se apunta todo como visto y no se publica nada de
    altas ni cambios (sí los plazos de la semana)."""
    ini, antes = e.get("ini") or {}, (anterior.get("ini") or {})
    pub = e.setdefault("publicado", {})
    primera = not antes
    piezas = []

    def pieza(clave, titular, entradilla, cuerpo, exp):
        if clave in pub:
            return
        pub[clave] = hoy
        if primera and not clave.startswith("plazos|"):
            return
        piezas.append({
            "chamber": "congreso", "type": "Tramitación", "date": fmt_date_es(hoy),
            "headline": " ".join(titular.split()), "standfirst": entradilla, "body": cuerpo,
            "source": {"label": f"Tramitación de {exp}", "url": f"{site_url}tramitacion/{slug(exp)}.html"}
                      if exp else {"label": "Qué se tramita", "url": f"{site_url}tramitacion/"},
        })

    for exp, v in sorted(ini.items(), key=lambda x: ultima_fecha(x[1]), reverse=True):
        t = _cita(v["t"]).upper()
        prev = antes.get(exp)
        if prev is None:
            if v["tipo"] == "Real Decreto-ley":
                verbo = "CONVALIDA" if v["est"] == "convalidado" else "DEROGA"
                pieza(f"estado|{exp}|{v['est']}", f"EL CONGRESO {verbo} EL «{t}»",
                      f"Votación del Pleno del {fmt_date_es(v['hitos'][0]['f'])}." if v["hitos"] else "",
                      [f"Resultado: {ETIQUETA[v['est']].lower()}."], exp)
            else:
                pieza(f"nueva|{exp}", f"NUEVA {tipo_corto(v['tipo']).upper()}: «{t}»",
                      f"Presentada por {v['a']}" + (f" el {fmt_date_es(v['fp'])}." if v.get("fp") else "."),
                      [f"Expediente {exp}. Situación: {v['sit'] or ETIQUETA[v['est']]}."], exp)
            continue
        if prev.get("est") == v["est"]:
            continue
        if prev.get("est") == "toma-en-consideracion" and v["est"] in ("plazo-de-enmiendas", "ponencia-comision"):
            pieza(f"estado|{exp}|tomada", f"EL CONGRESO TOMA EN CONSIDERACIÓN «{t}»",
                  f"La iniciativa de {v['a']} sigue su tramitación en comisión.",
                  [f"Expediente {exp}. Situación: {v['sit']}."], exp)
        elif v["est"] in RELEVANTES:
            titular = {"aprobada": f"APROBADA «{t}»", "rechazada": f"RECHAZADA «{t}»",
                       "senado": f"«{t}» PASA AL SENADO"}.get(v["est"], f"«{t}»: {ETIQUETA[v['est']].upper()}")
            pieza(f"estado|{exp}|{v['est']}", titular,
                  f"{tipo_corto(v['tipo'])} de {v['a']}. Antes: {ETIQUETA.get(prev.get('est'), '—').lower()}.",
                  [f"Expediente {exp}. " + (f"Resultado: {resultado_texto(v)}." if v.get("cerrado") else f"Situación: {v['sit']}.")],
                  exp)

    # Plazos de enmiendas que terminan en los próximos siete días. Los que
    # vencen tras una ampliación se renuevan casi siempre cada semana (el
    # «congelador»): se cuentan aparte y no hacen pieza por sí solos.
    fin = (dt.date.fromisoformat(hoy) + dt.timedelta(days=7)).isoformat()
    semana = [(v["fe"], exp, v) for exp, v in ini.items()
              if v["est"] == "plazo-de-enmiendas" and v.get("fe") and hoy <= v["fe"] <= fin
              and f"plazo|{exp}|{v['fe']}" not in pub]
    def ampliado(v):
        ult = [p for p in v.get("plazos") or [] if p[0] == v["fe"]]
        return any("ampliaci" in _norm(p[2]) for p in ult)
    nuevos_pl = sorted(x for x in semana if not ampliado(x[2]))
    ampliados = [x for x in semana if ampliado(x[2])]
    if nuevos_pl:
        for _f, exp, v in semana:
            pub[f"plazo|{exp}|{v['fe']}"] = hoy
        n = len(nuevos_pl)
        pieza(f"plazos|{hoy}", f"{n} {'PLAZO' if n == 1 else 'PLAZOS'} DE ENMIENDAS "
              f"{'TERMINA' if n == 1 else 'TERMINAN'} ANTES DEL {fmt_date_es(fin).upper()}",
              "Hasta esa fecha los grupos pueden presentar enmiendas a estas iniciativas.",
              [f"«{_cita(v['t'], 140)}» ({exp}): hasta el {fmt_date_es(f)}."
               for f, exp, v in nuevos_pl[:12]]
              + ([f"Otras {len(ampliados)} iniciativas tienen un plazo ampliado que vence esta semana; "
                  "la lista de las que más ampliaciones acumulan está en tramitacion/ampliaciones.html."]
                 if ampliados else []), "")
    # Una segunda ejecución el mismo día no repite nada, pero tampoco puede
    # vaciar la edición: rehace data/<hoy>.json desde cero, así que se
    # devuelven también las piezas que ya salieron hoy.
    previas = e.get("piezas_hoy") or {}
    if previas.get("fecha") == hoy:
        piezas = previas.get("piezas", []) + piezas
    piezas = piezas[:MAX_PIEZAS]
    e["piezas_hoy"] = {"fecha": hoy, "piezas": piezas}
    guardar(e)
    return piezas


def novedades(e: dict | None = None, n: int = 5) -> list[tuple[str, str, str]]:
    """(fecha, texto, ruta) de los últimos hitos, para la portada de Seguimiento."""
    e = e or cargar()
    filas = []
    for exp, v in (e.get("ini") or {}).items():
        if v.get("hitos"):
            h = v["hitos"][-1]
            filas.append((h["f"], f"{_cita(v['t'], 110)} — {h['h']}", f"tramitacion/{slug(exp)}.html"))
    return sorted(filas, reverse=True)[:n]


# ---------------------------------------------------------------------- páginas

def generar_paginas(h: dict) -> list:
    """/tramitacion/: una página por iniciativa, índice por estados, una página
    por estado y por autor, las listas de ampliaciones y de antigüedad y la
    metodología. `h` trae las utilidades de build.py."""
    e = cargar()
    ini = e.get("ini") or {}
    if not ini:
        return []
    esc, attr, fecha = h["esc_html"], h["esc_attr"], h["fmt_date_es"]
    site, plantilla, carpeta = h["site_url"], h["plantilla"], h["carpeta"]
    carpeta.mkdir(exist_ok=True)
    detalle = h.get("detalle") or []
    pag_vot = h.get("pagina_votacion")
    normas = h.get("normas_por_ley") or {}          # «Ley 3/2026» -> ruta normas/…
    hoy = dt.date.today().isoformat()
    salidas = []
    fuente = ('Fuente: datos abiertos de iniciativas del Congreso de los Diputados. '
              '<a class="srclink" href="/tramitacion/metodologia.html">Cómo se hace</a>.')

    def pagina(nombre, titulo, desc, h1, kicker, entradilla, ficha, cuerpo, lastmod, miga, jsonld):
        url = f"{site}tramitacion/{'' if nombre == 'index.html' else nombre}"
        h["pagina_suelta"](plantilla, carpeta, nombre, {
            "TITLE": esc(titulo), "META_DESC": attr(desc[:155]), "CANONICAL": url,
            "JSONLD": h["jsonld_script"](jsonld),
            "EDITION_DATE": esc(f"Último movimiento: {fecha(lastmod or hoy)}"),
            "MIGA": miga, "KICKER": esc(kicker), "HEADLINE": esc(h1),
            "STANDFIRST": esc(entradilla), "FICHA": ficha, "CUERPO": cuerpo, "FUENTE": fuente,
            "RELACIONADAS": "", "RELACIONADAS_HIDDEN": "hidden",
        })
        salidas.append({"url": url, "lastmod": lastmod or hoy})

    def miga(*partes):
        m = '<a href="../">Portada</a> › <a href="../seguimiento/">Seguimiento</a> › '
        if partes:
            m += '<a href="./">Tramitación</a> › '
        return m + f'<span aria-current="page">{esc(partes[-1] if partes else "Tramitación")}</span>'

    def fila(exp, v, extra=""):
        return (f'<li><a href="/tramitacion/{attr(slug(exp))}.html">{esc(titulo_corto(exp, v["t"]))}</a>'
                f'<span class="ref">{esc(ETIQUETA[v["est"]])} · {esc(tipo_corto(v["tipo"]))} · '
                f'{esc(grupo_corto(v["a"]))} · {esc(exp)}{extra}</span></li>')

    def ley_ruta(v):
        ley = v.get("ley")
        if not ley:
            return None, None
        m = re.match(r"(Ley(?: Orgánica)? \d+/\d{4})", ley["titulo"])
        return ley, (normas.get(m.group(1)) if m else None)

    def fases(est, tipo):
        """El recorrido habitual de una ley, con la fase actual resaltada. Las
        cerradas sin aprobar y los decretos-ley no siguen ese camino: solo badge."""
        if tipo == "Real Decreto-ley" or est not in CAMINO:
            return ""
        i = CAMINO.index(est)
        return ('<ol class="tr-fases" aria-label="Fases de la tramitación">' + "".join(
            f'<li class="{"hecha" if n < i else "actual" if n == i else "pendiente"}"'
            + (' aria-current="step"' if n == i else "") + f'>{esc(ETIQUETA[f])}</li>'
            for n, f in enumerate(CAMINO)) + '</ol>')

    # ------------------------------------------------------ una por iniciativa
    for exp, v in ini.items():
        lm = ultima_fecha(v) or hoy
        hs = v.get("pasos") or []
        linea = "".join(
            f'<li><b>{esc(p[0])}</b>'
            + (f' <span class="tr-nota">({esc(NOTA_PASO[p[0]])})</span>' if p[0] in NOTA_PASO else "")
            + ' <span class="ref">'
            + (f'{esc(fecha(p[1]))}' if p[1] else "")
            + (f' – {esc(fecha(p[2]))}' if p[2] else (" · en curso" if p[1] and v["est"] in ABIERTOS and i == len(hs) - 1 else ""))
            + '</span></li>' for i, p in enumerate(hs))
        plz = "".join(
            f'<li>{esc(p[2] or "Plazo")}: hasta el {esc(fecha(p[0]))}{(" a las " + esc(p[1])) if p[1] else ""}'
            f' <span class="ref">{"abierto" if p[0] >= hoy else "terminado"}</span></li>'
            for p in (v.get("plazos") or [])[-6:])
        enm = ""
        if v.get("fe"):
            enm = (f'<p>Fin del plazo de enmiendas: <b>{esc(fecha(v["fe"]))}</b>'
                   f'{" (abierto)" if v["fe"] >= hoy else ""}.</p>')
        if v.get("amp"):
            enm += f'<p>El plazo de enmiendas se ha ampliado {v["amp"]} {"vez" if v["amp"] == 1 else "veces"}.</p>'
        vots = votaciones_de(v, detalle)
        vots_html = "".join(
            f'<li><a href="/votaciones/{attr(pag_vot(d))}">{esc(d.get("t") or "Votación")}</a>'
            f'<span class="ref">{esc(fecha(d["f"]))}{(" · " + esc(d["sub"])) if d.get("sub") else ""}</span></li>'
            for d in vots[:20]) if pag_vot else ""
        ley, ruta_norma = ley_ruta(v)
        if v["tipo"] == "Real Decreto-ley":
            m = re.match(r"(Real Decreto-ley \d+/\d{4})", v["t"])
            ruta_norma = normas.get(m.group(1)) if m else None
        ley_html = ""
        if ley:
            ley_html = (f'<h2 class="rotulo">Ley resultante</h2><p>{esc(ley["titulo"])} '
                        f'<span class="ref">BOE núm. {esc(ley["boe"])} del {esc(fecha(ley["fb"]))}</span></p>'
                        + (f'<p><a class="srclink" href="{attr(ley["pdf"])}" target="_blank" rel="noopener">Texto de la ley ↗</a></p>' if ley.get("pdf") else ""))
        if ruta_norma:
            ley_html += f'<p><a class="srclink" href="/{attr(ruta_norma)}">Ficha de la norma en el BOE →</a></p>'
        rel = "".join(f'<li><a href="/tramitacion/{attr(slug(r))}.html">{esc(ini[r]["t"].rstrip("."))}</a>'
                      f'<span class="ref">{esc(r)}</span></li>' for r in v.get("rel") or [] if r in ini and r != exp)
        bocg = "".join(f'<li><a href="{attr(u)}" target="_blank" rel="noopener">{esc(u.rsplit("/", 1)[-1])}</a></li>'
                       for u in v.get("bocg") or [])
        sit = situacion(v, hoy)
        sit_html = ""
        if sit:
            sit_html = (f'<div class="tr-situacion{" tr-congelada" if sit.get("congelada") else ""}">'
                        f'<p class="tr-sit-t">Dónde está ahora: {esc(sit["titulo"])}</p>'
                        f'<p>{esc(sit["texto"])}</p></div>')
        cont = v.get("cont") or {}
        cont_html = ""
        if cont.get("em") or cont.get("art"):
            cont_html = '<h2 class="rotulo">De qué trata</h2>'
            if cont.get("em"):
                cont_html += (f'<blockquote class="pull"><p>«{esc(cont["em"])}»</p>'
                              f'<cite>Exposición de motivos · {esc(v["a"])}</cite></blockquote>')
            if cont.get("art"):
                resto = (cont.get("n") or 0) - len(cont["art"])
                cont_html += (f'<p class="rk-nota">Qué contiene el texto presentado:</p><ul class="indice">'
                              + "".join(f'<li>{esc(a)}</li>' for a in cont["art"])
                              + (f'<li class="ref">y {resto} más</li>' if resto > 0 else "") + '</ul>')
        cuerpo = (
            f'<p class="tr-estado tr-{attr(v["est"])}{" tr-congelada" if sit and sit.get("congelada") else ""}">'
            f'{esc(ETIQUETA[v["est"]])}{" · congelador" if sit and sit.get("congelada") else ""}</p>'
            + fases(v["est"], v["tipo"])
            + sit_html
            + cont_html
            + (f'<p class="rk-nota">Situación oficial: {esc(v["sit"])}'
               + (f' · Resultado: {esc(resultado_texto(v))}' if v.get("cerrado") and resultado_texto(v) else "")
               + '</p>')
            + enm
            + (f'<h2 class="rotulo">Plazos</h2><ul class="indice">{plz}</ul>' if plz else "")
            + (f'<h2 class="rotulo">Tramitación</h2><ol class="indice tr-linea">{linea}</ol>' if linea else "")
            + ley_html
            + (f'<h2 class="rotulo">Votaciones en el Pleno</h2><ul class="indice">{vots_html}</ul>' if vots_html else "")
            + (f'<h2 class="rotulo">Iniciativas relacionadas</h2><ul class="indice">{rel}</ul>' if rel else "")
            + (f'<h2 class="rotulo">Publicaciones en el Boletín de las Cortes</h2><ul class="indice">{bocg}</ul>' if bocg else "")
            + (f'<p><a class="srclink" href="{attr(url_ficha(exp))}" target="_blank" rel="noopener">Ficha oficial en el Congreso ↗</a></p>' if url_ficha(exp) else ""))
        ficha = (f"<dt>Estado</dt><dd>{esc(ETIQUETA[v['est']])}</dd>"
                 f"<dt>Tipo</dt><dd>{esc(v['tipo'])}</dd><dt>Autor</dt><dd>{esc(v['a'])}</dd>"
                 f"<dt>Expediente</dt><dd>{esc(exp)}</dd>"
                 + (f"<dt>Presentada</dt><dd>{esc(fecha(v['fp']))}</dd>" if v.get("fp") else "")
                 + (f"<dt>Comisión</dt><dd>{esc(v['com'])}</dd>" if v.get("com") else "")
                 + (f"<dt>Procedimiento</dt><dd>{esc(v['trt'])}</dd>" if v.get("trt") else "")
                 + (f"<dt>Ponentes</dt><dd>{esc(v['pon'])}</dd>" if v.get("pon") else ""))
        corto = titulo_corto(exp, v["t"])
        if corto != _txt(v["t"]).rstrip("."):
            # El titular es el corto; el oficial va entero, en letra normal,
            # para citar y buscar.
            cuerpo = (f'<p class="titulo-oficial"><span>Título oficial</span>{esc(_txt(v["t"]))}</p>'
                      + cuerpo)
        ld = {"@type": "Legislation", "name": v["t"], "legislationIdentifier": exp,
              "url": f"{site}tramitacion/{slug(exp)}.html", "inLanguage": "es-ES",
              "legislationJurisdiction": "ES"}
        if v.get("fp"):
            ld["legislationDate"] = v["fp"]
        pagina(f"{slug(exp)}.html", f"{_cita(corto, 90)}: en qué punto está su tramitación",
               f"{v['t']} Estado: {ETIQUETA[v['est']].lower()}. Presentada por {v['a']}.",
               corto, tipo_corto(v["tipo"]),
               f"{ETIQUETA[v['est']]}. Presentada por {v['a']}"
               + (f" el {fecha(v['fp'])}." if v.get("fp") else "."),
               ficha, cuerpo, lm, miga(exp), [ld])

    # ------------------------------------------------------------ por estado
    por_estado: dict = {}
    for exp, v in ini.items():
        por_estado.setdefault(v["est"], []).append((exp, v))
    lm_total = max((ultima_fecha(v) for v in ini.values()), default=hoy) or hoy
    for s, etiqueta, desc in ESTADOS:
        lista = sorted(por_estado.get(s, []), key=lambda x: ultima_fecha(x[1]), reverse=True)
        cuerpo = (f'<p class="rk-nota">{esc(desc)}.</p><ul class="indice">'
                  + "".join(fila(k, v, f' · {esc(fecha(ultima_fecha(v)))}') for k, v in lista)
                  + '</ul>' if lista else f'<p class="rk-nota">{esc(desc)}.</p><p>Ninguna ahora mismo.</p>')
        pagina(f"estado-{s}.html", f"Iniciativas en estado «{etiqueta}» | La Tercera Cámara",
               f"Las {len(lista)} iniciativas legislativas del Congreso en estado «{etiqueta.lower()}».",
               etiqueta, "Tramitación", f"{len(lista)} iniciativas en este estado.",
               f"<dt>Iniciativas</dt><dd>{len(lista)}</dd>", cuerpo,
               max((ultima_fecha(v) for _k, v in lista), default=lm_total) or lm_total,
               miga(etiqueta),
               [{"@type": "CollectionPage", "name": f"Iniciativas: {etiqueta}",
                 "url": f"{site}tramitacion/estado-{s}.html", "inLanguage": "es-ES"}])

    # ------------------------------------------------------------- por autor
    autores: dict = {}
    for exp, v in ini.items():
        autores.setdefault(v["a"] or "Sin autor", []).append((exp, v))
    for a, lista in autores.items():
        lista = sorted(lista, key=lambda x: ultima_fecha(x[1]), reverse=True)
        cuenta = {}
        for _k, v in lista:
            cuenta[v["est"]] = cuenta.get(v["est"], 0) + 1
        resumen = "".join(f"<dt>{esc(ETIQUETA[s])}</dt><dd>{cuenta[s]}</dd>" for s, _e, _d in ESTADOS if cuenta.get(s))
        pagina(f"autor-{slug_autor(a)}.html", f"Iniciativas de {grupo_corto(a)}: en qué punto están | La Tercera Cámara",
               f"Las {len(lista)} iniciativas legislativas presentadas por {a} en la legislatura y su estado.",
               grupo_corto(a), "Tramitación", f"Lo que ha presentado {a} y en qué punto está cada iniciativa.",
               resumen, '<ul class="indice">' + "".join(fila(k, v) for k, v in lista) + "</ul>",
               max((ultima_fecha(v) for _k, v in lista), default=lm_total) or lm_total,
               miga(grupo_corto(a)),
               [{"@type": "CollectionPage", "name": f"Iniciativas de {a}",
                 "url": f"{site}tramitacion/autor-{slug_autor(a)}.html", "inLanguage": "es-ES"}])

    # ------------------------------------------- ampliaciones y antigüedad
    amp = sorted(((v["amp"], k, v) for k, v in ini.items() if v.get("amp")), key=lambda x: (-x[0], x[1]))
    pagina("ampliaciones.html", "Iniciativas con más ampliaciones del plazo de enmiendas | La Tercera Cámara",
           "Las iniciativas legislativas cuyo plazo de enmiendas se ha ampliado más veces.",
           "Más ampliaciones del plazo de enmiendas", "Tramitación",
           ("Cada ampliación la acuerda la Mesa del Congreso. Mientras se amplía, el texto no pasa a la "
            "ponencia: es el «congelador». Se cuentan las que figuran en los plazos oficiales."),
           f"<dt>Con alguna ampliación</dt><dd>{len(amp)}</dd>"
           f"<dt>En el congelador</dt><dd>{sum(1 for _n, _k, v in amp if congelada(v, hoy))}</dd>",
           '<ul class="indice">' + "".join(
               fila(k, v, f' · el plazo de enmiendas se ha ampliado {n} {"vez" if n == 1 else "veces"}')
               for n, k, v in amp[:100]) + "</ul>", lm_total, miga("Ampliaciones"),
           [{"@type": "CollectionPage", "name": "Más ampliaciones del plazo de enmiendas",
             "url": f"{site}tramitacion/ampliaciones.html"}])
    abiertas = sorted(((k, v) for k, v in ini.items() if v["est"] in ABIERTOS and v.get("fp")),
                      key=lambda x: x[1]["fp"])
    pagina("antiguedad.html", "Iniciativas que llevan más tiempo en tramitación | La Tercera Cámara",
           "Las iniciativas legislativas abiertas ordenadas por el tiempo que llevan en tramitación.",
           "Más tiempo en tramitación", "Tramitación",
           "Iniciativas todavía abiertas, de la presentada hace más tiempo a la más reciente.",
           f"<dt>Abiertas</dt><dd>{len(abiertas)}</dd>",
           '<ul class="indice">' + "".join(
               fila(k, v, f' · {(dt.date.fromisoformat(hoy) - dt.date.fromisoformat(v["fp"])).days} días desde su presentación')
               for k, v in abiertas[:100]) + "</ul>", lm_total, miga("Antigüedad"),
           [{"@type": "CollectionPage", "name": "Más tiempo en tramitación",
             "url": f"{site}tramitacion/antiguedad.html"}])

    # ----------------------------------------------------------------- índice
    resumen = "".join(
        f'<li><a href="estado-{s}.html">{esc(e_)}</a><span class="ref">{len(por_estado.get(s, []))}</span></li>'
        for s, e_, _d in ESTADOS)
    aut = "".join(f'<li><a href="autor-{attr(slug_autor(a))}.html">{esc(grupo_corto(a))}</a>'
                  f'<span class="ref">{len(l)}</span></li>' for a, l in sorted(autores.items(), key=lambda x: -len(x[1])))
    recientes = "".join(f'<li><a href="/{attr(r)}">{esc(t)}</a><span class="ref">{esc(fecha(f))}</span></li>'
                        for f, t, r in novedades(e, 30))
    abiertas_n = sum(len(por_estado.get(s, [])) for s in ABIERTOS)
    pagina("index.html", "Qué se tramita en el Congreso y en qué punto está | La Tercera Cámara",
           f"Seguimiento de las {len(ini)} iniciativas legislativas de la legislatura: {abiertas_n} abiertas, "
           "en qué estado está cada una, plazos de enmiendas y leyes resultantes.",
           "Qué se tramita", "Seguimiento",
           "Cada proyecto y proposición de ley de la legislatura, y los reales decretos-ley votados: "
           "en qué estado está, qué plazos tiene y cómo acaba.",
           f"<dt>Iniciativas</dt><dd>{len(ini)}</dd><dt>Abiertas</dt><dd>{abiertas_n}</dd>"
           f"<dt>En el congelador</dt><dd>{sum(1 for v in ini.values() if congelada(v, hoy))}</dd>"
           f"<dt>Leyes aprobadas</dt><dd>{len(e.get('leyes') or [])}</dd>",
           (f'<h2 class="rotulo">Por estado</h2><ul class="provincias">{resumen}</ul>'
            f'<p class="aside-note"><a class="srclink" href="ampliaciones.html">En el congelador: más ampliaciones del plazo de enmiendas</a> · '
            f'<a class="srclink" href="antiguedad.html">Más tiempo en tramitación</a> · '
            f'<a class="srclink" href="metodologia.html">Cómo se hace</a></p>'
            f'<h2 class="rotulo">Últimos movimientos</h2><ul class="indice">{recientes}</ul>'
            f'<h2 class="rotulo">Por autor</h2><ul class="provincias">{aut}</ul>'),
           lm_total, miga(),
           [{"@type": "CollectionPage", "name": "Qué se tramita en el Congreso",
             "url": f"{site}tramitacion/", "inLanguage": "es-ES", "dateModified": lm_total}])

    # ------------------------------------------------------------ metodología
    tabla = "".join(f"<tr><td>{esc(e_)}</td><td>{esc(d)}</td></tr>" for _s, e_, d in ESTADOS)
    pagina("metodologia.html", "Seguimiento de la tramitación: metodología | La Tercera Cámara",
           "Fuentes, correspondencia de estados y limitaciones del seguimiento de la tramitación.",
           "Cómo se hace el seguimiento de la tramitación", "Metodología",
           "Fuentes, estados y limitaciones.",
           f"<dt>Iniciativas</dt><dd>{len(ini)}</dd><dt>Actualizado</dt><dd>{esc(fecha(e.get('actualizado') or hoy))}</dd>",
           ('<h2 class="rotulo">Fuentes</h2><p>Los ficheros de datos abiertos de iniciativas del Congreso '
            '(proyectos de ley, proposiciones de ley, propuestas de reforma de Estatutos y leyes aprobadas), '
            'que el Congreso regenera cada día. Para las iniciativas que llegan sin tramitación seguida, la '
            'ficha oficial del buscador de iniciativas. Los reales decretos-ley, que no están en esos ficheros, '
            'salen de la votación de convalidación o derogación del Pleno.</p>'
            '<h2 class="rotulo">Estados</h2><p>El estado de cada iniciativa se deduce de su situación oficial o, '
            'si está cerrada, de su resultado:</p><table class="rk"><thead><tr><th>Estado</th><th>Sale de</th>'
            f'</tr></thead><tbody>{tabla}</tbody></table>'
            '<h2 class="rotulo">Plazo de enmiendas</h2><p>El fin del plazo es la fecha más tardía de los plazos '
            'de enmiendas publicados; las ampliaciones son los plazos cuyo texto oficial dice «ampliación».</p>'
            f'<h2 class="rotulo">«Congelador»</h2><p>Se marca así una iniciativa en plazo de enmiendas cuyo plazo '
            f'se ha ampliado al menos {CONGELADOR_AMP} veces y que lleva al menos {CONGELADOR_DIAS} días sin pasar a '
            'la ponencia. Las ampliaciones las acuerda la Mesa del Congreso (art. 91 del Reglamento). Es un '
            'recuento sobre los plazos oficiales, no una valoración de los motivos.</p>'
            '<h2 class="rotulo">Dónde está ahora</h2><p>Cada ficha abierta explica la fase actual con los datos '
            'oficiales: desde cuándo está en ella y qué tiene que pasar para salir. Las reglas que se citan son las '
            'del Reglamento del Congreso y la Constitución.</p>'
            '<h2 class="rotulo">De qué trata</h2><p>La cita es literal de la exposición de motivos del texto '
            'publicado en el Boletín de las Cortes: la frase en la que el autor dice qué hace la iniciativa o cómo se '
            'estructura. Son palabras del autor, no un resumen nuestro. Debajo, los títulos de sus artículos y '
            'disposiciones, tal como aparecen en el texto presentado (no en el que se apruebe).</p>'
            '<h2 class="rotulo">Limitaciones</h2><p>Solo el Congreso: la tramitación en el Senado aparece como '
            'una fase, sin su detalle. Las votaciones se relacionan por el texto del asunto votado y solo en '
            'votaciones de carácter legislativo; si el tema no aparece entero, no se enlaza. La ley resultante '
            'se casa por el título. No se resume ni se interpreta el contenido: se cita y el texto completo está '
            'en el Boletín de las Cortes, enlazado en cada ficha.</p>'
            '<h2 class="rotulo">Contacto</h2><p>Para comunicar un error: '
            '<a class="srclink" href="mailto:datos@terceracamara.es">datos@terceracamara.es</a>.</p>'),
           e.get("actualizado") or hoy, miga("Metodología"),
           [{"@type": "WebPage", "name": "Seguimiento de la tramitación: metodología",
             "url": f"{site}tramitacion/metodologia.html"}])

    h["log"](f"tramitacion/: {len(ini)} fichas, {len(autores)} autores")
    return salidas


def entradas_buscador(entrada, e: dict | None = None) -> list:
    """Filas del índice del buscador: título, estado, autor y términos."""
    e = e or cargar()
    filas = []
    for exp, v in (e.get("ini") or {}).items():
        f = entrada(titulo_corto(exp, v["t"]),
                    f"{ETIQUETA[v['est']]} · {tipo_corto(v['tipo'])} · {grupo_corto(v['a'])}",
                    f"tramitacion/{slug(exp)}.html", "iniciativa", ultima_fecha(v),
                    f"{exp} {v['a']} {' '.join(kw_limpios(v)[:20])}", largo=420)
        # El título oficial entero y los términos, solo para casar nombres
        # populares en build.py; no viaja al índice.
        f["_texto"] = f"{v['t']} {' '.join(v.get('kw') or [])}"
        filas.append(f)
    return filas
