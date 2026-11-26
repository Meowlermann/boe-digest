"""«Tus senadores» en cada ficha de provincia, solo desde la proclamación de la JEC.

Única fuente: la relación de «Senadores proclamados electos» de la resolución
de la Presidencia de la Junta Electoral Central que publica en el BOE el
resumen de los resultados de las elecciones convocadas por el Real Decreto
806/2026 (art. 108.6 LOREG). Nunca senado.es ni otra web.

- curated/senadores_29n.json es la copia fija. Si no existe, no se pinta nada.
  Este módulo no crea el fichero.
- Nombre, formación y votos van tal como los escribe el BOE. No se calcula nada.
- Si una provincia no está clara, no se publica: encabezado que no casa con el
  real decreto de convocatoria, una línea que no se entiende (nombre partido en
  dos renglones, una nota de renuncia), una isla desconocida o un número de
  senadores distinto del que fija el artículo 165 de la LOREG. Su ficha sigue
  como antes. No se publica una provincia a medias.
- Solo los senadores elegidos en la provincia. Los que designan los
  parlamentos autonómicos no están en esa resolución y no se mencionan con
  nombre.

Formato del BOE (modelo de 2023, BOE-A-2023-18907): la relación es una imagen
en el XML y texto en el PDF; se lee con pdftotext -layout (poppler, en local).
Las provincias insulares llevan un encabezado por isla: «Balears (Illes):
MALLORCA». tools/generar_senadores.py hace la lectura.
"""
from __future__ import annotations

import html as _html
import json
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parent
DATOS = RAIZ / "curated" / "senadores_29n.json"

ANCLA = "tus-senadores"
TITULO_SECCION = "Relación de Senadores proclamados electos"
FIN = ("SENADO", "Relación de candidatos que no han obtenido escaño")

# Artículo 165 de la LOREG, texto consolidado vigente (BOE-A-1985-11672,
# https://www.boe.es/buscar/act.php?id=BOE-A-1985-11672#acientosesentaycinco):
# «1. En cada circunscripción provincial se eligen cuatro Senadores.
#  2. En cada circunscripción insular se elige el siguiente número de Senadores:
#  tres en Gran Canaria, Mallorca y Tenerife; uno en Ibiza, Formentera, Menorca,
#  Fuerteventura, La Gomera, El Hierro, Lanzarote y La Palma.
#  3. Las poblaciones de Ceuta y Melilla eligen cada una de ellas dos Senadores.»
# El apartado 2 lo redacta así la Ley Orgánica 2/2026, de 30 de junio
# (BOE-A-2026-14329, en vigor desde el 3-7-2026,
# https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-14329), que separa Ibiza y
# Formentera: hasta entonces eran una sola circunscripción («EIVISSA-FORMENTERA»
# en la proclamación de 2023). Total: 47 × 4 + 17 insulares + 2 × 2 = 209.
# Solo sirve para comprobar la lectura, no se publica.
SENADORES_PROVINCIA = 4
SENADORES_CIUDAD = {"Ceuta": 2, "Melilla": 2}
ISLAS = {
    "Balears (Illes)": {"MALLORCA": 3, "MENORCA": 1, "IBIZA": 1, "FORMENTERA": 1},
    "Palmas (Las)": {"GRAN CANARIA": 3, "FUERTEVENTURA": 1, "LANZAROTE": 1},
    "Santa Cruz de Tenerife": {"TENERIFE": 3, "LA PALMA": 1, "LA GOMERA": 1, "EL HIERRO": 1},
}
# El encabezado de isla del BOE puede ir en catalán: en 2023 escribió «EIVISSA».
ALIAS_ISLA = {"EIVISSA": "IBIZA"}


def isla_ley(isla):
    """El nombre de la isla en la tabla de la ley (art. 165.2)."""
    return ALIAS_ISLA.get(isla, isla)


_PIE = re.compile(r"^(BOLETÍN OFICIAL DEL ESTADO|Núm\. \d+\b.*Pág\.|cve: BOE-|Verificable en|D\. L\.|ISSN)")
_PERSONA = re.compile(r"^(Don|Doña) (\S.*?\S)\s{2,}(\S.*?\S)\s{2,}(\d{1,3}(?:\.\d{3})*)$")


def url_boe(ident: str) -> str:
    return f"https://www.boe.es/diario_boe/txt.php?id={ident}"


def _esc(t) -> str:
    return _html.escape(str(t if t is not None else ""), quote=True)


def _bloque(texto: str) -> list:
    lineas = texto.splitlines()
    ini = None
    for i, l in enumerate(lineas):
        if l.strip() == TITULO_SECCION:
            ini = i + 1
    if ini is None:
        return []
    out = []
    for l in lineas[ini:]:
        if l.strip() in FIN:
            break
        out.append(l)
    return out


def parsear(texto_pdf: str, provincias_rd: list) -> tuple[dict, dict]:
    """Relación de senadores electos del PDF.

    Devuelve ({provincia: [{"isla": str | None, "senadores": [{"nombre",
    "formacion", "votos"}]}]}, {provincia: motivo}) solo con las provincias
    claras. Las claves son los nombres del real decreto de convocatoria."""
    validas = set(provincias_rd)
    lectura: dict = {}
    dudosas: dict = {}
    actual = None                       # (provincia, isla)
    for l in _bloque(texto_pdf):
        s = l.strip()
        if not s or _PIE.match(s) or s == "Votos" or s.startswith("Elecciones Generales de"):
            continue
        m = _PERSONA.match(s)
        if m:
            if actual is None:
                dudosas.setdefault("(antes del primer encabezado)", f"línea sin provincia: «{s}»")
                continue
            prov, isla = actual
            grupos = lectura.setdefault(prov, [])
            if not grupos or grupos[-1]["isla"] != isla:
                grupos.append({"isla": isla, "senadores": []})
            grupos[-1]["senadores"].append({"nombre": f"{m.group(1)} {m.group(2)}",
                                            "formacion": m.group(3).strip(), "votos": m.group(4)})
            continue
        prov, _, isla = (p.strip() for p in s.partition(":"))
        if prov in validas and not re.search(r"\s{2,}", s):
            actual = (prov, isla or None)
            lectura.setdefault(prov, [])
            if isla and prov not in ISLAS:
                dudosas.setdefault(prov, f"isla en una provincia no insular: «{s}»")
            continue
        if actual:
            dudosas.setdefault(actual[0], f"línea no reconocida: «{s}»")
        else:
            dudosas.setdefault("(antes del primer encabezado)", f"línea no reconocida: «{s}»")
    claras = {}
    for prov in provincias_rd:
        grupos = lectura.get(prov)
        if not grupos:
            dudosas.setdefault(prov, "no aparece en la relación")
            continue
        if prov in dudosas:
            continue
        motivo = _comprobar(prov, grupos)
        if motivo:
            dudosas[prov] = motivo
            continue
        claras[prov] = grupos
    return claras, dudosas


def _comprobar(prov: str, grupos: list) -> str:
    if prov in ISLAS:
        esperado = ISLAS[prov]
        vistas = [isla_ley(g["isla"]) for g in grupos]
        if sorted(vistas) != sorted(esperado) or len(set(vistas)) != len(vistas):
            return f"islas leídas {[g['isla'] for g in grupos]}, esperadas {sorted(esperado)}"
        for g in grupos:
            if len(g["senadores"]) != esperado[isla_ley(g["isla"])]:
                return f"{g['isla']}: {len(g['senadores'])} senadores, esperados {esperado[isla_ley(g['isla'])]}"
        return ""
    if len(grupos) != 1 or grupos[0]["isla"] is not None:
        return "encabezados repetidos o con isla"
    n = SENADORES_CIUDAD.get(prov, SENADORES_PROVINCIA)
    if len(grupos[0]["senadores"]) != n:
        return f"{len(grupos[0]['senadores'])} senadores, esperados {n}"
    return ""


def paginas_por_provincia(texto_pdf: str, provincias_rd: list) -> dict:
    """Páginas del BOE donde está cada provincia en la relación de senadores
    electos («… Pág. N» de la cabecera), para curar a mano las dudosas."""
    validas = set(provincias_rd)
    lineas = texto_pdf.splitlines()
    pag, dentro, actual, out = None, False, None, {}
    for l in lineas:
        s = l.strip()
        mp = re.search(r"Pág\. (\d+)\s*$", s)
        if mp:
            pag = mp.group(1)
        if s == TITULO_SECCION:
            dentro, actual, out = True, None, {}
            continue
        if not dentro:
            continue
        if s in FIN:
            dentro = False
            continue
        prov = s.partition(":")[0].strip()
        if prov in validas and not re.search(r"\s{2,}", s):
            actual = prov
        if actual and pag and pag not in out.setdefault(actual, []):
            out[actual].append(pag)
    return out


# ------------------------------------------------------------------- copia fija
# Solo la proclamación de estas elecciones: una copia de otras (por ejemplo, la
# de 2023 que se usa para las capturas de prueba) no pasa la validación y no se
# pinta nunca.
CONVOCATORIA = "Real Decreto 806/2026"
MARCA_PRUEBA = "DATOS DE PRUEBA"
DATOS_MANUAL = RAIZ / "curated" / "senadores_29n_manual.json"


def _senadores_ok(grupos) -> str:
    for g in grupos or []:
        for s in g.get("senadores") or []:
            if not (s.get("nombre") and s.get("formacion") and s.get("votos")):
                return "senador sin nombre, formación o votos"
    return ""


def validar(datos) -> list:
    err = []
    if not isinstance(datos, dict):
        return ["no es un objeto"]
    f = datos.get("fuente") or {}
    if not re.fullmatch(r"BOE-A-\d{4}-\d+", str(f.get("id") or "")):
        err.append("fuente.id no es un identificador del BOE")
    if not f.get("literal"):
        err.append("falta fuente.literal")
    if CONVOCATORIA not in str(f.get("titulo") or ""):
        err.append(f"fuente.titulo no es la proclamación de las elecciones del {CONVOCATORIA}")
    if MARCA_PRUEBA in json.dumps(datos, ensure_ascii=False):
        err.append("lleva la marca de datos de prueba")
    for prov, grupos in (datos.get("provincias") or {}).items():
        motivo = _comprobar(prov, grupos) or _senadores_ok(grupos)
        if motivo:
            err.append(f"{prov}: {motivo}")
    return err


def validar_manual(prov: str, d, fuente: dict, provincias_rd) -> str:
    """Motivo por el que una provincia curada a mano no se publica, o vacío.

    Se copia literal del PDF del BOE, con el mismo identificador de la
    proclamación y la página como fuente, y tiene que tener los senadores que
    fija el artículo 165 de la LOREG, igual que la automática."""
    if provincias_rd is not None and prov not in provincias_rd:
        return "nombre que no casa con el real decreto de convocatoria"
    if not isinstance(d, dict):
        return "no es un objeto"
    fm = d.get("fuente") or {}
    if fm.get("id") != fuente.get("id"):
        return "la fuente no es la misma proclamación"
    if not re.fullmatch(r"\d+(?:(?:, | y |-)\d+)*", str(fm.get("pagina") or "")):
        return "falta la página del BOE"
    if MARCA_PRUEBA in json.dumps(d, ensure_ascii=False):
        return "lleva la marca de datos de prueba"
    grupos = d.get("grupos") or []
    return _senadores_ok(grupos) or _comprobar(prov, grupos)


def combinar(datos: dict, manual: dict | None, provincias_rd=None) -> dict:
    """Añade las provincias curadas a mano que la automática dejó fuera. Si la
    automática ya la tiene, manda la automática. La que siga sin estar clara no
    se publica (motivo en «manual_descartadas»)."""
    if not manual:
        return datos
    out = {**datos, "provincias": dict(datos.get("provincias") or {}), "manual_descartadas": {},
           "manual": {}}
    for prov, d in (manual.get("provincias") or {}).items():
        if prov in out["provincias"]:
            out["manual_descartadas"][prov] = "ya está en la copia automática"
            continue
        motivo = validar_manual(prov, d, datos.get("fuente") or {}, provincias_rd)
        if motivo:
            out["manual_descartadas"][prov] = motivo
            continue
        out["provincias"][prov] = d["grupos"]
        out["manual"][prov] = d["fuente"]["pagina"]
    return out


def _provincias_rd():
    try:
        import elecciones as el
        return {c["circunscripcion"] for c in el.cargar()["circunscripciones"]}
    except Exception:                                         # noqa: BLE001
        return None


def cargar(ruta: pathlib.Path = DATOS, ruta_manual: pathlib.Path = DATOS_MANUAL) -> dict | None:
    """La copia fija (más las provincias curadas a mano), o None si no existe o
    no es válida: entonces no se pinta nada. La manual sola no se usa."""
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if validar(datos):
        return None
    try:
        manual = json.loads(ruta_manual.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manual = None
    return combinar(datos, manual, _provincias_rd())


def _entero(t) -> int:
    """«27.056» → 27056. Solo para ordenar; lo que se pinta es el literal."""
    try:
        return int(str(t or "0").replace(".", ""))
    except ValueError:
        return 0


def ordenados(senadores: list) -> list:
    """Por votos, de más a menos (el Senado es mayoritario: todos los de la
    lista son electos). A igualdad de votos, el orden del BOE (informe 48)."""
    return sorted(senadores or [], key=lambda s: -_entero(s.get("votos")))


# --- cómo se vota (informe 50) --------------------------------------------------
# Artículo 166.1.a) de la LOREG (Ley Orgánica 5/1985, BOE-A-1985-11672, texto
# consolidado, consultado el 26-11-2026 en
# https://www.boe.es/buscar/act.php?id=BOE-A-1985-11672#acientosesentayseis):
# «Los electores pueden dar su voto a un máximo de tres candidatos en las
# circunscripciones provinciales, dos en Gran Canaria, Mallorca, Tenerife, Ceuta
# y Melilla, y uno en las restantes circunscripciones insulares.»
# La LO 2/2026 no lo cambió (solo los arts. 161.2 y 165.2): Ibiza y Formentera
# caen en «las restantes circunscripciones insulares», uno cada una.
# El informe 50 hablaba de «hasta tres nombres» en general, sin Ceuta ni
# Melilla; manda la ley: tres en las provinciales, dos en Ceuta y Melilla.
# Lo que sale de los datos: la circunscripción, sus islas y cuántos senadores
# elige cada una (los de la proclamación). Lo único fijo es este máximo.
VOTOS_MAXIMOS_PROVINCIA = 3
VOTOS_MAXIMOS_CIUDAD = {"Ceuta": 2, "Melilla": 2}
VOTOS_MAXIMOS_ISLA = {"GRAN CANARIA": 2, "MALLORCA": 2, "TENERIFE": 2}
VOTOS_MAXIMOS_OTRA_ISLA = 1
# Cómo se escribe cada isla en una frase (el encabezado del BOE va en mayúsculas).
# «EIVISSA-FORMENTERA» solo para leer proclamaciones anteriores a la LO 2/2026.
NOMBRE_ISLA = {"MALLORCA": "Mallorca", "MENORCA": "Menorca", "IBIZA": "Ibiza", "EIVISSA": "Eivissa",
               "FORMENTERA": "Formentera", "EIVISSA-FORMENTERA": "Eivissa-Formentera",
               "GRAN CANARIA": "Gran Canaria", "FUERTEVENTURA": "Fuerteventura", "LANZAROTE": "Lanzarote",
               "TENERIFE": "Tenerife", "LA PALMA": "La Palma", "LA GOMERA": "La Gomera", "EL HIERRO": "El Hierro"}
_NUM = {1: "uno", 2: "dos", 3: "tres", 4: "cuatro"}


def votos_maximos(prov: str, isla: str | None) -> int:
    if isla:
        return VOTOS_MAXIMOS_ISLA.get(isla_ley(isla), VOTOS_MAXIMOS_OTRA_ISLA)
    return VOTOS_MAXIMOS_CIUDAD.get(prov, VOTOS_MAXIMOS_PROVINCIA)


def _y(xs: list) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " y " + xs[-1]


def _marca(n: int) -> str:
    return "un nombre" if n == 1 else f"hasta {_NUM[n]} nombres"


def _salen(n: int) -> str:
    return "sale el más votado" if n == 1 else f"salen los {_NUM[n]} más votados"


def _por_islas(grupos: list) -> list:
    """[(senadores, máximo, [islas])] en el orden del BOE, juntando las islas
    que eligen lo mismo; primero las que eligen más."""
    juntas: dict = {}
    for g in grupos:
        k = len(g["senadores"])
        juntas.setdefault((k, votos_maximos("", g["isla"])), []).append(NOMBRE_ISLA.get(g["isla"], g["isla"]))
    return sorted(((k, m, islas) for (k, m), islas in juntas.items()), key=lambda x: -x[0])


def islas_texto(grupos: list) -> str:
    """«Aquí se vota por islas: 3 senadores en Tenerife y 1 en La Palma, La
    Gomera y El Hierro.» Vacío si la circunscripción no va por islas."""
    if not any(g.get("isla") for g in grupos):
        return ""
    partes = [f"{k} {'senador' if k == 1 else 'senadores'} en {_y(islas)}" if i == 0 else f"{k} en {_y(islas)}"
              for i, (k, _m, islas) in enumerate(_por_islas(grupos))]
    return f"Aquí se vota por islas: {_y(partes)}."


def como_se_vota(prov: str, grupos: list) -> str:
    """Cómo se vota en esta circunscripción, según su tipo (art. 166.1.a LOREG)
    y los senadores que elige según la proclamación."""
    if any(g.get("isla") for g in grupos):
        trozos = []
        for i, (k, m, islas) in enumerate(_por_islas(grupos)):
            trozos.append(f"en {_y(islas)} cada votante marca {_marca(m)} y {_salen(k)}" if i == 0 else
                          f"en {_y(islas)} marca {_marca(m)} y {_salen(k)}")
        frase = "; ".join(trozos)
        return f"{islas_texto(grupos)} {frase[0].upper()}{frase[1:]}."
    k = sum(len(g["senadores"]) for g in grupos)
    return f"Cada votante marca {_marca(votos_maximos(prov, None))}; {_salen(k)}."


def eleccion_texto(fuente: dict) -> str:
    """« en las elecciones generales del 23 de julio de 2023»: la fecha tal
    como la cita el título de la proclamación cargada («… y celebradas el …»).
    Si el título no la trae, nada: no se supone ninguna elección."""
    m = re.search(r"celebradas el (\d{1,2} de [a-záéíóú]+ de \d{4})", str(fuente.get("titulo") or ""))
    return f" en las elecciones generales del {m.group(1)}" if m else ""


def hay_bloque(datos: dict | None, prov_rd: str) -> bool:
    return bool(datos and (datos.get("provincias") or {}).get(prov_rd))


def bloque_html(datos: dict | None, prov_rd: str, nombre: str) -> str:
    """«Tus senadores» de una provincia. Vacío si no hay copia fija o la
    provincia no está en ella. Lista simple, sin tarjetas ni subrayados."""
    if not datos or not prov_rd:
        return ""
    grupos = (datos.get("provincias") or {}).get(prov_rd)
    if not grupos:
        return ""
    f = datos["fuente"]

    def lista(ss):
        return ('<ul class="sen-lista">' + "".join(
            f'<li>{_esc(s["nombre"])}'
            + (f'<span class="sen-nota">{_esc(s["nota"])}</span>' if s.get("nota") else "")
            + f'<span class="sen-det">{_esc(s["formacion"])} · {_esc(s["votos"])} votos</span></li>'
            for s in ordenados(ss)) + "</ul>")
    cuerpo = "".join(
        (f'<h3>{_esc(g["isla"])}</h3>' if g.get("isla") else "") + lista(g["senadores"]) for g in grupos)
    pg = str((datos.get("manual") or {}).get(prov_rd) or "")
    pagina = f", {'páginas' if re.search(r'[ ,-]', pg) else 'página'} {_esc(pg)}" if pg else ""
    return (
        f'<section class="sen-29n" id="{ANCLA}" aria-labelledby="sen-tit">'
        f'<h2 id="sen-tit">Tus senadores</h2>'
        f'<p class="sen-intro">Senadores proclamados electos por {_esc(nombre)}{_esc(eleccion_texto(f))}, '
        f'tal como los publica la Junta Electoral Central en el BOE. No incluye '
        f'a los senadores que designan los parlamentos autonómicos.</p>'
        + f'<p class="sen-como">{_esc(como_se_vota(prov_rd, grupos))}</p>'
        + cuerpo
        + f'<p class="sen-fuente">Fuente: <a href="{_esc(url_boe(f["id"]))}">{_esc(f.get("titulo") or f["id"])}</a> '
          f'({_esc(f["literal"])}{pagina}).</p></section>')
