"""Rankings del Congreso: clasificaciones de diputados y grupos.

Todo sale de datos que el pipeline ya descarga y guarda en state/congreso.json
(ver congreso_datos.py). No hay red, ni modelos, ni dependencias nuevas: son
cuentas sobre contadores y sobre el voto nominal de las últimas votaciones.

Dos fuentes con alcances distintos, y cada tabla dice cuál usa:

  - personas[clave]: contadores ACUMULADOS de toda la legislatura (votos por
    sentido, «no vota», disidencias). Sirven para participación y disidencia
    individual.
  - detalle[url]: voto nominal de las últimas ~400 votaciones (se poda). Sirve
    para lo que necesita saber qué votó cada grupo en cada votación: cohesión,
    afinidad y votaciones ajustadas. Todo lo que sale de aquí lleva su ventana
    («últimas N votaciones, del X al Y»).

Semántica de las letras, confirmada en congreso_datos.py:
  - «X» = «No vota» en el acta. Consta tanto estando presente como ausente
    (acumular() no lo cuenta como asistencia), así que se trata como «no
    participó», no como ausencia.
  - «-» = el diputado no figura en esa votación (no era diputado todavía o ya
    no lo era). No cuenta para nada.
  - La postura de un grupo solo existe si al menos el 70 % de sus votos
    emitidos (S/N/A, sin «no vota») coinciden: postura_grupos() y
    _postura_del_grupo(). Por debajo, el grupo está dividido.

Neutralidad: quien vota menos por su cargo (Presidencia del Gobierno,
ministros, Presidencia de la Cámara) o está de baja no se excluye en silencio.
Se le pone una etiqueta visible leída de curated/cargos_rankings.json, que se
edita a mano.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib

import congreso_datos as cd

ROOT = pathlib.Path(__file__).parent
CARGOS = ROOT / "curated" / "cargos_rankings.json"

# Por debajo de este número de votaciones una persona entra en las tablas de
# porcentajes con cifras poco representativas (altas recientes, sustituciones).
UMBRAL_VOTACIONES = 200
TOP_RESUMEN = 10

PAGINAS = [
    # (fichero, título corto, descripción para el índice)
    ("participacion.html", "Participación en votaciones",
     "Los diez que menos votan; la tabla completa va de más a menos."),
    ("disidencia.html", "Votos contra el propio grupo",
     "Quién se aparta más de la postura de su grupo, y la cohesión de cada grupo. "
     "El Grupo Mixto reúne a partidos distintos: sus cifras no son comparables."),
    ("intervenciones.html", "Intervenciones",
     "Quién interviene más en el Pleno y en comisiones."),
    ("afinidad.html", "Afinidad entre grupos",
     "Cuántas veces coincide la postura de cada par de grupos."),
    ("ajustadas.html", "Votaciones más ajustadas",
     "Las votaciones con menos diferencia entre síes y noes."),
    ("provincias.html", "Participación por circunscripción",
     "La participación media de los diputados de cada provincia."),
    ("preguntas.html", "Preguntas escritas registradas",
     "Quién firma más preguntas con respuesta escrita al Gobierno en el último año."),
]


# ---------------------------------------------------------------- utilidades

def cargar_etiquetas() -> dict:
    """{clave_nombre: etiqueta}. Las claves que empiezan por «_» son notas."""
    try:
        datos = json.loads(CARGOS.read_text(encoding="utf-8"))
    except Exception:                                          # noqa: BLE001
        return {}
    return {k: str(v) for k, v in datos.items() if not k.startswith("_") and v}


def pct(x: float) -> str:
    """0.9534 -> «95,3 %». Coma decimal, como se escribe en español."""
    return f"{x * 100:.1f}".replace(".", ",") + " %"


def fecha_es(iso: str, fmt_date_es) -> str:
    return fmt_date_es(iso) if iso else ""


def corto_grupo(cod_o_largo: str) -> str:
    largo = cd.COD_GRUPO.get(cod_o_largo, cod_o_largo)
    return cd.GRUPO_CORTO.get(largo, cod_o_largo)


def ventana_detalle(estado: dict) -> dict:
    """Primera y última votación del detalle, para decir de dónde sale cada
    cifra calculada con él."""
    det = cd.detalle_ordenado(estado)
    if not det:
        return {"n": 0, "desde": "", "hasta": "", "sesion": None}
    return {"n": len(det), "desde": det[-1]["f"], "hasta": det[0]["f"],
            "sesion": det[0].get("s")}


# ------------------------------------------------------------------- cálculo

def filas_personas(estado: dict, fichas: list, etiquetas: dict) -> list:
    """Una fila por diputado en activo con sus contadores de legislatura.

    Solo el censo actual: quien ya no es diputado no tiene ficha a la que
    enlazar. `fichas` trae la clave (congreso_datos.fusionar) y el slug."""
    personas = estado.get("personas") or {}
    intervs = estado.get("intervenciones") or {}
    filas = []
    for f in fichas:
        clave = f.get("clave")
        if not clave:
            continue
        p = personas.get(clave) or {}
        vot = p.get("votaciones", 0)
        filas.append({
            "clave": clave,
            "nombre": f.get("natural") or f.get("nombre", ""),
            "slug": f.get("slug", ""),
            "grupo": corto_grupo(f.get("grupo", "")),
            "color": cd.GRUPO_COLOR.get(f.get("grupo", ""), "#8d8d8d"),
            "circ": f.get("circunscripcion", ""),
            "votaciones": vot,
            "no_vota": p.get("no_vota", 0),
            "disidencias": p.get("disidencias", 0),
            "participacion": (1 - p.get("no_vota", 0) / vot) if vot else None,
            "disidencia": (p.get("disidencias", 0) / vot) if vot else None,
            "intervenciones": (intervs.get(clave) or {}).get("total", 0),
            "organos": (intervs.get(clave) or {}).get("organos", {}) or {},
            "etiqueta": etiquetas.get(clave, ""),
        })
    return filas


def cohesion_grupos(estado: dict) -> list:
    """Cohesión media de cada grupo en la ventana del detalle: en cada
    votación, qué parte de sus votos emitidos coincide con el sentido más
    votado dentro del grupo. 100 % = todos votaron igual siempre."""
    suma: dict = {}
    for d in (estado.get("detalle") or {}).values():
        for cod, c in (d.get("g") or {}).items():
            emitidos = c[0] + c[1] + c[2]
            if emitidos < 3:
                continue
            largo = cd.COD_GRUPO.get(cod, cod)
            s = suma.setdefault(largo, [0.0, 0])
            s[0] += max(c[0], c[1], c[2]) / emitidos
            s[1] += 1
    salida = [{"grupo": cd.GRUPO_CORTO.get(g, g), "largo": g, "cohesion": s / n, "n": n}
              for g, (s, n) in suma.items() if n]
    return sorted(salida, key=lambda r: -r["cohesion"])


def matriz_afinidad(estado: dict) -> tuple[list, dict]:
    """Para cada par de grupos, en qué porcentaje de las votaciones en que los
    dos tuvieron postura (≥70 % de sus votos iguales) esa postura coincidió.

    Se agrupa por nombre largo porque SUMAR aparece con dos códigos."""
    coinc: dict = {}
    for d in (estado.get("detalle") or {}).values():
        postura = {}
        for cod, letra in cd.postura_grupos(d.get("g")).items():
            postura[cd.COD_GRUPO.get(cod, cod)] = letra
        claves = list(postura)
        for a in claves:
            for b in claves:
                c = coinc.setdefault((a, b), [0, 0])
                c[1] += 1
                if postura[a] == postura[b]:
                    c[0] += 1
    grupos = [g for g, *_r in cd.GRUPOS if any(k[0] == g for k in coinc)]
    return grupos, coinc


def votaciones_ajustadas(estado: dict, n: int = 60) -> list:
    """Menor diferencia entre síes y noes. Las de asentimiento no cuentan:
    ahí no hay recuento."""
    filas = []
    for d in cd.detalle_ordenado(estado):
        if d.get("asent"):
            continue
        si, no = [(x or 0) for x in (d.get("tot") or [0, 0])[:2]]
        if si + no == 0:
            continue
        filas.append((abs(si - no), d))
    filas.sort(key=lambda x: (x[0], x[1]["f"]), reverse=False)
    return [d for _m, d in filas[:n]]


def participacion_provincias(filas: list) -> list:
    """Media simple de la participación de los diputados de cada provincia que
    superan el umbral. Media de personas, no de votos: cada escaño pesa uno."""
    por: dict = {}
    for f in filas:
        if f["participacion"] is None or f["votaciones"] < UMBRAL_VOTACIONES or not f["circ"]:
            continue
        por.setdefault(f["circ"], []).append(f["participacion"])
    salida = [{"circ": c, "media": sum(v) / len(v), "n": len(v)} for c, v in por.items()]
    return sorted(salida, key=lambda r: (-r["media"], r["circ"]))


# ------------------------------------------------------------------ HTML

class Pintor:
    """Las utilidades de build.py que hacen falta para escribir páginas. Se
    pasan desde fuera para no importar build (se ejecuta como __main__ y
    reimportarlo duplicaría su estado)."""

    def __init__(self, h: dict):
        self.esc = h["esc_html"]
        self.attr = h["esc_attr"]
        self.fecha = h["fmt_date_es"]
        self.jsonld = h["jsonld_script"]
        self.pagina = h["pagina_suelta"]
        self.plantilla = h["plantilla"]
        self.site = h["site_url"]
        self.slug_txt = h["slug_txt"]
        self.pag_votacion = h["pagina_votacion"]
        self.carpeta = h["carpeta"]

    def nombre(self, f: dict) -> str:
        etiqueta = (f' <span class="rk-etq">{self.esc(f["etiqueta"])}</span>'
                    if f.get("etiqueta") else "")
        return (f'<a href="../diputados/{self.attr(f["slug"])}.html">{self.esc(f["nombre"])}</a>'
                f'{etiqueta}')

    def celda_nombre(self, f: dict) -> tuple:
        """Nombre con el fondo teñido del color de su grupo: la tabla se lee
        de un vistazo por bloques sin tener que mirar la columna del grupo."""
        return (self.nombre(f), None, f.get("color") or "#8d8d8d")

    def celda_grupo(self, corto: str, color: str) -> str:
        return (f'<span class="rk-g"><i style="background:{self.attr(color)}"></i>'
                f'{self.esc(corto)}</span>')

    def tabla(self, cabeceras: list, filas: list, numericas: set = frozenset()) -> str:
        """Tabla estática. Las columnas numéricas llevan data-n con el valor
        crudo para que el script de ordenar no dependa del formato."""
        num = ' class="num"'
        th = "".join(f'<th scope="col"{num if i in numericas else ""}>'
                     f'{self.esc(c)}</th>' for i, c in enumerate(cabeceras))
        cuerpo = []
        for fila in filas:
            celdas = []
            for i, celda in enumerate(fila):
                if not isinstance(celda, tuple):
                    celda = (celda, None)
                html, valor = celda[0], celda[1]
                color = celda[2] if len(celda) > 2 else None
                dn = f' data-n="{valor}"' if valor is not None else ""
                clases = (["num"] if i in numericas else []) + (["rk-nom"] if color else [])
                cl = f' class="{" ".join(clases)}"' if clases else ""
                st = f' style="--g:{self.attr(color)}"' if color else ""
                celdas.append(f"<td{cl}{st}{dn}>{html}</td>")
            cuerpo.append("<tr>" + "".join(celdas) + "</tr>")
        return (f'<div class="rk-tabla"><table class="rk ordenable"><thead><tr>{th}</tr></thead>'
                f'<tbody>{"".join(cuerpo)}</tbody></table></div>')

    def itemlist(self, url: str, nombre: str, elementos: list) -> dict:
        return {"@type": "ItemList", "name": nombre, "url": url,
                "numberOfItems": len(elementos),
                "itemListElement": [{"@type": "ListItem", "position": i + 1,
                                     "name": n, "url": u}
                                    for i, (n, u) in enumerate(elementos)]}

    def escribir(self, nombre: str, titulo: str, desc: str, h1: str, entradilla: str,
                 cuerpo: str, pie_datos: str, jsonld: list, lastmod: str) -> dict:
        url = f"{self.site}rankings/{'' if nombre == 'index.html' else nombre}"
        miga = ('<a href="../">Portada</a> › <a href="../diputados/">Parlamento</a> › '
                + ('<span aria-current="page">Rankings</span>' if nombre == "index.html" else
                   f'<a href="./">Rankings</a> › <span aria-current="page">{self.esc(h1)}</span>'))
        self.pagina(self.plantilla, self.carpeta, nombre, {
            "TITLE": self.esc(f"{titulo} | La Tercera Cámara"),
            "META_DESC": self.attr(desc),
            "CANONICAL": url,
            "JSONLD": self.jsonld([{"@type": "WebPage", "url": url, "name": titulo,
                                    "inLanguage": "es-ES", "dateModified": lastmod}] + jsonld),
            "EDITION_DATE": self.esc(pie_datos),
            "MIGA": miga,
            "KICKER": "Rankings del Congreso",
            "HEADLINE": self.esc(h1),
            "STANDFIRST": self.esc(entradilla),
            "FICHA": f"<dt>Datos</dt><dd>{self.esc(pie_datos)}</dd>",
            "CUERPO": cuerpo + ORDENAR_JS,
            "FUENTE": ('Fuente: datos abiertos del Congreso de los Diputados. '
                       '<a class="srclink" href="metodologia.html">Cómo se calcula</a>.'),
            "RELACIONADAS": "", "RELACIONADAS_HIDDEN": "hidden",
        })
        return {"url": url, "lastmod": lastmod}


# Ordenar columnas al pulsar la cabecera. Opcional: sin script la tabla se lee
# igual, ya ordenada por el criterio del ranking.
ORDENAR_JS = """<script>
document.querySelectorAll("table.ordenable th").forEach(function(th){
  var i=th.cellIndex;th.tabIndex=0;th.style.cursor="pointer";
  function ordenar(){var t=th.closest("table"),b=t.tBodies[0],f=[].slice.call(b.rows),
    asc=th.dataset.o!=="a";th.dataset.o=asc?"a":"d";
    f.sort(function(x,y){var a=x.cells[i],c=y.cells[i],
      va=a.dataset.n!==undefined?+a.dataset.n:a.textContent.trim(),
      vc=c.dataset.n!==undefined?+c.dataset.n:c.textContent.trim();
      var r=typeof va==="number"?va-vc:String(va).localeCompare(vc,"es");return asc?r:-r;});
    f.forEach(function(r){b.appendChild(r);});}
  th.addEventListener("click",ordenar);
  th.addEventListener("keydown",function(e){if(e.key==="Enter")ordenar();});
});
</script>"""


# ------------------------------------------------------------------ páginas

def _pag_participacion(P: Pintor, filas: list, pie: str, lastmod: str):
    validas = [f for f in filas if f["participacion"] is not None
               and f["votaciones"] >= UMBRAL_VOTACIONES]
    orden = sorted(validas, key=lambda f: (-f["participacion"], f["nombre"]))
    fuera = [f for f in filas if f["votaciones"] < UMBRAL_VOTACIONES]

    def tabla(lista, desde=1):
        return P.tabla(
            ["#", "Diputado", "Grupo", "Participación", "Votaciones", "No vota"],
            [[(str(desde + i), desde + i), P.celda_nombre(f), P.celda_grupo(f["grupo"], f["color"]),
              (pct(f["participacion"]), round(f["participacion"], 5)),
              (str(f["votaciones"]), f["votaciones"]), (str(f["no_vota"]), f["no_vota"])]
             for i, f in enumerate(lista)], numericas={0, 3, 4, 5})

    menos = list(reversed(orden))
    cuerpo = (
        f'<p class="rk-nota">Participación = 1 − («no vota» ÷ votaciones en que figura). '
        f'Solo diputados en activo con al menos {UMBRAL_VOTACIONES} votaciones. Las etiquetas '
        f'señalan cargos que explican una participación menor.</p>'
        f'<h2 class="rotulo" id="menos">Los que menos participan</h2>{tabla(menos[:25])}'
        f'<h2 class="rotulo" id="todos">Clasificación completa</h2>{tabla(orden)}'
        + (f'<p class="rk-nota">Fuera de la tabla por no llegar al umbral: '
           + ", ".join(P.nombre(f) for f in fuera) + '.</p>' if fuera else ""))
    url = f"{P.site}rankings/participacion.html"
    return P.escribir(
        "participacion.html",
        "Diputados que más faltan a las votaciones del Congreso",
        "Participación de cada diputado en las votaciones del Pleno en esta legislatura: "
        "quién vota más y quién menos, con los cargos que lo explican señalados.",
        "Participación en las votaciones",
        "Qué parte de las votaciones del Pleno vota cada diputado. Recuento sobre toda la "
        "legislatura.", cuerpo, pie,
        [P.itemlist(url, "Diputados por participación en votaciones (de menos a más)",
                    [(f["nombre"], f'{P.site}diputados/{f["slug"]}.html') for f in menos[:50]])],
        lastmod), orden


def _pag_disidencia(P: Pintor, filas: list, cohesion: list, vent: dict, pie: str,
                    lastmod: str):
    validas = [f for f in filas if f["disidencia"] is not None
               and f["votaciones"] >= UMBRAL_VOTACIONES]
    orden = sorted(validas, key=lambda f: (-f["disidencia"], f["nombre"]))
    t_pers = P.tabla(
        ["#", "Diputado", "Grupo", "Contra su grupo", "Votos distintos", "Votaciones"],
        [[(str(i + 1), i + 1), P.celda_nombre(f), P.celda_grupo(f["grupo"], f["color"]),
          (pct(f["disidencia"]), round(f["disidencia"], 5)),
          (str(f["disidencias"]), f["disidencias"]), (str(f["votaciones"]), f["votaciones"])]
         for i, f in enumerate(orden)], numericas={0, 3, 4, 5})
    t_grupos = P.tabla(
        ["Grupo", "Cohesión media", "Votaciones analizadas"],
        [[P.celda_grupo(c["grupo"], cd.GRUPO_COLOR.get(c["largo"], "#8d8d8d")), (pct(c["cohesion"]), round(c["cohesion"], 5)),
          (str(c["n"]), c["n"])] for c in cohesion], numericas={1, 2})
    ventana = _texto_ventana(P, vent)
    cuerpo = (
        f'<p class="rk-nota">Un voto cuenta como «contra su grupo» cuando el diputado vota sí, '
        f'no o abstención y su grupo tenía postura (al menos el 70 % de sus votos iguales) '
        f'distinta. «No vota» nunca cuenta como voto en contra. Recuento de toda la '
        f'legislatura, solo diputados con al menos {UMBRAL_VOTACIONES} votaciones.</p>'
        f'<p class="rk-nota">El Grupo Mixto reúne a partidos distintos que no votan como un '
        f'bloque: los porcentajes de sus diputados no son comparables con los del resto.</p>'
        f'<h2 class="rotulo" id="grupos">Cohesión de cada grupo</h2>'
        f'<p class="rk-nota">En cada votación, qué parte de los votos emitidos del grupo '
        f'coincide con su sentido más votado; media sobre {ventana}.</p>{t_grupos}'
        f'<h2 class="rotulo" id="diputados">Diputados que más votan contra su grupo</h2>{t_pers}')
    url = f"{P.site}rankings/disidencia.html"
    return P.escribir(
        "disidencia.html",
        "Diputados que votan contra su grupo en el Congreso",
        "Qué diputados se apartan más a menudo de la postura de su grupo parlamentario y "
        "qué grupos votan más unidos. Datos del Congreso.",
        "Votos contra el propio grupo",
        "Cuántas veces vota cada diputado distinto que su grupo, y lo unido que vota cada "
        "grupo.", cuerpo, pie,
        [P.itemlist(url, "Diputados que más votan contra su grupo",
                    [(f["nombre"], f'{P.site}diputados/{f["slug"]}.html') for f in orden[:50]])],
        lastmod), orden


def _pag_intervenciones(P: Pintor, filas: list, pie: str, lastmod: str):
    orden = sorted(filas, key=lambda f: (-f["intervenciones"], f["nombre"]))

    def desglose(org: dict) -> str:
        top = sorted(org.items(), key=lambda x: -x[1])[:3]
        resto = sum(org.values()) - sum(n for _o, n in top)
        txt = " · ".join(f"{P.esc(o)} {n}" for o, n in top)
        return txt + (f" · otros {resto}" if resto else "")

    t = P.tabla(
        ["#", "Diputado", "Grupo", "Intervenciones", "Dónde (órganos principales)"],
        [[(str(i + 1), i + 1), P.celda_nombre(f), P.celda_grupo(f["grupo"], f["color"]),
          (str(f["intervenciones"]), f["intervenciones"]),
          f'<span class="rk-org">{desglose(f["organos"])}</span>']
         for i, f in enumerate(orden)], numericas={0, 3})
    cuerpo = ('<p class="rk-nota">Intervenciones publicadas por el Congreso en toda la '
              'legislatura, en el Pleno, la Diputación Permanente y las comisiones. Cuenta '
              'cada intervención registrada, sin medir su duración.</p>' + t)
    url = f"{P.site}rankings/intervenciones.html"
    return P.escribir(
        "intervenciones.html",
        "Diputados que más intervienen en el Congreso",
        "Ranking de intervenciones de cada diputado en el Pleno y en comisiones del "
        "Congreso en esta legislatura, con el desglose por órgano.",
        "Intervenciones de cada diputado",
        "Cuántas veces ha intervenido cada diputado y en qué órganos.", cuerpo, pie,
        [P.itemlist(url, "Diputados que más intervienen",
                    [(f["nombre"], f'{P.site}diputados/{f["slug"]}.html') for f in orden[:50]])],
        lastmod), orden


def _pag_afinidad(P: Pintor, grupos: list, coinc: dict, vent: dict, pie: str, lastmod: str):
    cortos = [cd.GRUPO_CORTO.get(g, g) for g in grupos]
    cab = "".join(f'<th scope="col">{P.esc(c)}</th>' for c in cortos)
    filas = []
    pares = []
    for a in grupos:
        celdas = []
        for b in grupos:
            si, n = coinc.get((a, b), [0, 0])
            if a == b or not n:
                celdas.append('<td class="num rk-diag">—</td>')
                continue
            v = si / n
            # Tono del fondo proporcional a la coincidencia; el número está
            # siempre escrito, el color solo ayuda a leer la tabla.
            celdas.append(f'<td class="num" style="--a:{v:.2f}" title="{si} de {n}">'
                          f'{P.esc(pct(v))}</td>')
            if grupos.index(a) < grupos.index(b):
                pares.append((v, a, b, si, n))
        filas.append(f'<tr><th scope="row">'
                     f'{P.celda_grupo(cd.GRUPO_CORTO.get(a, a), cd.GRUPO_COLOR.get(a, "#8d8d8d"))}</th>'
                     f'{"".join(celdas)}</tr>')
    matriz = (f'<div class="rk-tabla"><table class="rk rk-matriz"><thead><tr><th></th>{cab}'
              f'</tr></thead><tbody>{"".join(filas)}</tbody></table></div>')
    pares.sort(key=lambda x: -x[0])
    t_pares = P.tabla(
        ["Par de grupos", "Coincidencia", "Votaciones con postura de ambos"],
        [[P.esc(f"{cd.GRUPO_CORTO.get(a, a)} – {cd.GRUPO_CORTO.get(b, b)}"),
          (pct(v), round(v, 5)), (f"{si} de {n}", n)] for v, a, b, si, n in pares],
        numericas={1, 2})
    ventana = _texto_ventana(P, vent)
    cuerpo = (f'<p class="rk-nota">Porcentaje de votaciones en que la postura mayoritaria de '
              f'los dos grupos coincide, sobre {ventana}. Solo cuentan las votaciones en que '
              f'ambos grupos tuvieron postura (al menos el 70 % de sus votos iguales).</p>'
              f'{matriz}<h2 class="rotulo" id="pares">Todos los pares, de más a menos '
              f'coincidencia</h2>{t_pares}')
    url = f"{P.site}rankings/afinidad.html"
    return P.escribir(
        "afinidad.html",
        "Qué grupos votan juntos en el Congreso",
        "Matriz de coincidencia de voto entre los grupos parlamentarios del Congreso: "
        "cuántas veces vota igual cada par de grupos.",
        "Afinidad de voto entre grupos",
        "Con qué frecuencia coincide lo que vota cada grupo con lo que vota cada uno de "
        "los demás.", cuerpo, pie,
        [P.itemlist(url, "Pares de grupos por coincidencia de voto",
                    [(f"{cd.GRUPO_CORTO.get(a, a)} – {cd.GRUPO_CORTO.get(b, b)}",
                      f"{url}#pares") for _v, a, b, _s, _n in pares[:30]])],
        lastmod), pares


def _pag_ajustadas(P: Pintor, lista: list, vent: dict, pie: str, lastmod: str):
    filas = []
    for i, d in enumerate(lista):
        si, no = [(x or 0) for x in (d.get("tot") or [0, 0])[:2]]
        asunto = d.get("a") or d.get("t") or "Votación"
        sub = f'<span class="rk-org">{P.esc(d["sub"])}</span>' if d.get("sub") else ""
        filas.append([
            (str(i + 1), i + 1),
            f'<a href="../votaciones/{P.attr(P.pag_votacion(d))}">{P.esc(asunto[:220])}</a>{sub}',
            (P.esc(P.fecha(d["f"])), int(d["f"].replace("-", ""))),
            (f"{si} – {no}", si - no),
            (str(abs(si - no)), abs(si - no)),
        ])
    t = P.tabla(["#", "Votación", "Fecha", "Sí – No", "Margen"], filas, numericas={0, 3, 4})
    cuerpo = (f'<p class="rk-nota">Margen = diferencia entre síes y noes. Sobre '
              f'{_texto_ventana(P, vent)}; no incluye las aprobadas por asentimiento.</p>' + t)
    url = f"{P.site}rankings/ajustadas.html"
    return P.escribir(
        "ajustadas.html",
        "Las votaciones más ajustadas del Congreso",
        "Las votaciones del Pleno del Congreso que se decidieron por menos votos, con "
        "enlace a lo que votó cada diputado.",
        "Votaciones más ajustadas",
        "Las votaciones del Pleno con menos diferencia entre síes y noes.", cuerpo, pie,
        [P.itemlist(url, "Votaciones más ajustadas",
                    [((d.get("a") or d.get("t") or "Votación")[:110],
                      f'{P.site}votaciones/{P.pag_votacion(d)}') for d in lista[:50]])],
        lastmod), lista


def _pag_provincias(P: Pintor, provs: list, pie: str, lastmod: str):
    t = P.tabla(
        ["#", "Circunscripción", "Participación media", "Diputados"],
        [[(str(i + 1), i + 1),
          f'<a href="../diputados/provincia-{P.attr(P.slug_txt(r["circ"]))}.html">'
          f'{P.esc(r["circ"])}</a>',
          (pct(r["media"]), round(r["media"], 5)), (str(r["n"]), r["n"])]
         for i, r in enumerate(provs)], numericas={0, 2, 3})
    cuerpo = (f'<p class="rk-nota">Media simple de la participación de los diputados de cada '
              f'circunscripción con al menos {UMBRAL_VOTACIONES} votaciones: cada escaño pesa '
              f'lo mismo. En las circunscripciones con pocos escaños, una sola persona mueve '
              f'mucho la media.</p>' + t)
    url = f"{P.site}rankings/provincias.html"
    return P.escribir(
        "provincias.html",
        "Participación de los diputados por provincia",
        "Qué provincias tienen diputados que votan más en el Congreso: participación "
        "media en las votaciones del Pleno por circunscripción.",
        "Participación por circunscripción",
        "La participación media en las votaciones de los diputados elegidos en cada "
        "provincia.", cuerpo, pie,
        [P.itemlist(url, "Circunscripciones por participación media",
                    [(r["circ"], f'{P.site}diputados/provincia-{P.slug_txt(r["circ"])}.html')
                     for r in provs])],
        lastmod), provs


def _pag_preguntas(P: Pintor, filas: list, pie: str, lastmod: str):
    """Preguntas escritas firmadas por cada diputado en el último año, con
    cuántas tienen contestación. Sale del estado de preguntas.py; si aún no
    hay datos, la página explica que se están recopilando."""
    try:
        import preguntas as pq
        resumen = pq.resumen_diputados(pq.cargar_escritas())
    except Exception:                                          # noqa: BLE001
        resumen = {}
    con = [(f, resumen.get(f["clave"]) or {}) for f in filas]
    orden = sorted([x for x in con if x[1].get("total")],
                   key=lambda x: (-x[1]["total"], x[0]["nombre"]))
    t = P.tabla(
        ["#", "Diputado", "Grupo", "Preguntas", "Con contestación", "Días medios"],
        [[(str(i + 1), i + 1), P.celda_nombre(f), P.celda_grupo(f["grupo"], f["color"]),
          (str(r["total"]), r["total"]), (str(r["contestadas"]), r["contestadas"]),
          (str(r["media_dias"]) if r.get("media_dias") is not None else "—",
           r.get("media_dias") or 0)]
         for i, (f, r) in enumerate(orden)], numericas={0, 3, 4, 5})
    cuerpo = ('<p class="rk-nota">Preguntas con respuesta escrita presentadas en los últimos '
              'doce meses; una pregunta firmada por varios diputados cuenta para cada uno. '
              '«Días medios»: días naturales entre la publicación en el BOCG y la contestación '
              'registrada. <a class="srclink" href="../preguntas/metodologia.html">Cómo se '
              'cuentan</a>.</p>' + (t if orden else
              '<p class="rk-nota">Los datos se están recopilando.</p>'))
    url = f"{P.site}rankings/preguntas.html"
    return P.escribir(
        "preguntas.html", "Diputados que más preguntas escritas hacen al Gobierno",
        "Ranking de preguntas con respuesta escrita registradas por cada diputado en el "
        "Congreso en el último año, con cuántas han sido contestadas.",
        "Preguntas escritas registradas",
        "Cuántas preguntas con respuesta escrita firma cada diputado.", cuerpo, pie,
        [P.itemlist(url, "Diputados con más preguntas escritas",
                    [(f["nombre"], f'{P.site}diputados/{f["slug"]}.html')
                     for f, _r in orden[:50]])],
        lastmod), orden


def _texto_ventana(P: Pintor, vent: dict) -> str:
    if not vent["n"]:
        return "las votaciones disponibles"
    return (f'las últimas {vent["n"]} votaciones, del {P.fecha(vent["desde"])} al '
            f'{P.fecha(vent["hasta"])}')


def _pag_metodologia(P: Pintor, vent: dict, etiquetas: dict, pie: str, lastmod: str):
    usadas = sorted(set(etiquetas.values()))
    cuerpo = f"""
<h2 class="rotulo">Fuente</h2>
<p>Datos abiertos del Congreso de los Diputados: censo de diputados, votaciones del Pleno
(el acta nominal de cada votación) e intervenciones. Se descargan a diario y se acumulan.
Solo aparecen los diputados en activo, que son los que tienen ficha en este sitio.</p>
<h2 class="rotulo">Dos alcances distintos</h2>
<p>Participación, disidencia individual e intervenciones usan contadores de <b>toda la
legislatura</b>. Cohesión de los grupos, afinidad y votaciones ajustadas necesitan saber qué
votó cada grupo en cada votación, y ese detalle se guarda solo para <b>{P.esc(_texto_ventana(P, vent))}</b>.
Cada tabla dice cuál usa.</p>
<h2 class="rotulo">Fórmulas</h2>
<p><b>Participación</b> = 1 − («no vota» ÷ votaciones en que figura el diputado). «No vota»
es lo que consta en el acta del Congreso; figura tanto si el diputado estaba presente sin
votar como si estaba ausente. Umbral: {UMBRAL_VOTACIONES} votaciones, para que las altas
recientes no aparezcan con porcentajes poco representativos.</p>
<p><b>Postura de un grupo</b>: existe cuando al menos el 70 % de sus votos emitidos (sí, no,
abstención) coinciden. Si no llega, el grupo está dividido en esa votación y no se le
atribuye postura.</p>
<p><b>Voto contra el propio grupo</b>: el diputado vota sí, no o abstención y su grupo tenía
una postura distinta. «No vota» nunca cuenta como voto en contra. Se expresa sobre el total
de votaciones en que figura.</p>
<p><b>Cohesión de un grupo</b>: en cada votación, votos emitidos del grupo que coinciden con
su sentido más votado ÷ votos emitidos del grupo; media de todas las votaciones de la
ventana en que el grupo emitió al menos tres votos.</p>
<p><b>Afinidad entre dos grupos</b>: votaciones en que las posturas de ambos coinciden ÷
votaciones en que los dos tuvieron postura.</p>
<p><b>Margen de una votación</b>: |síes − noes|. Las votaciones por asentimiento no tienen
recuento y no entran.</p>
<p><b>Participación por circunscripción</b>: media simple de la participación de sus
diputados que superan el umbral.</p>
<h2 class="rotulo">Etiquetas de cargo</h2>
<p>La Presidencia del Gobierno, los ministros y la Presidencia de la Cámara votan menos por
razón de su cargo, y hay diputados de baja o suspendidos. No se les excluye: aparecen en las
tablas con una etiqueta visible. La lista se revisa a mano y se publica tal cual.
Etiquetas en uso: {P.esc(", ".join(usadas) or "ninguna")}.</p>
<h2 class="rotulo">Qué no mide</h2>
<p>Ninguna de estas cifras valora el trabajo de un diputado: no mide el trabajo en ponencias,
la preparación de iniciativas ni la duración o el contenido de las intervenciones. Son
recuentos sobre publicaciones oficiales, calculados igual para todos los grupos.</p>"""
    return P.escribir(
        "metodologia.html", "Cómo se calculan los rankings del Congreso",
        "Fórmulas, umbrales, ventanas de datos y fuentes de los rankings de diputados y "
        "grupos de La Tercera Cámara.",
        "Metodología de los rankings",
        "Qué se cuenta, cómo y con qué datos.", cuerpo, pie, [], lastmod)


def _pag_indice(P: Pintor, tops: dict, vent: dict, pie: str, lastmod: str):
    bloques = []
    for fichero, titulo, desc in PAGINAS:
        filas = tops.get(fichero, "")
        bloques.append(
            f'<section class="rk-bloque"><h2 class="rotulo"><a href="{fichero}">'
            f'{P.esc(titulo)}</a></h2><p class="rk-nota">{P.esc(desc)}</p>{filas}'
            f'<p><a class="srclink" href="{fichero}">Ver la tabla completa →</a></p></section>')
    cuerpo = ("".join(bloques) +
              '<p><a class="srclink" href="metodologia.html">Metodología: fórmulas, umbrales '
              'y etiquetas →</a></p>')
    url = f"{P.site}rankings/"
    return P.escribir(
        "index.html", "Rankings del Congreso: diputados y grupos",
        "Clasificaciones de los diputados y grupos del Congreso: participación en "
        "votaciones, votos contra el propio grupo, intervenciones y afinidad entre grupos.",
        "Rankings del Congreso",
        "Clasificaciones de diputados y grupos calculadas con los datos abiertos del "
        "Congreso. Mismo criterio para todos.", cuerpo, pie,
        [P.itemlist(url, "Rankings del Congreso",
                    [(t, f"{url}{f}") for f, t, _d in PAGINAS])],
        lastmod)


def _top(P: Pintor, cab: list, filas: list, numericas: set) -> str:
    return P.tabla(cab, filas[:TOP_RESUMEN], numericas).replace(" ordenable", "")


# ----------------------------------------------------------------- entrada

def generar(fichas: list, estado: dict, herramientas: dict) -> list:
    """Escribe rankings/*.html y devuelve [{url, lastmod}] para el sitemap."""
    P = Pintor(herramientas)
    P.carpeta.mkdir(exist_ok=True)
    etiquetas = cargar_etiquetas()
    vent = ventana_detalle(estado)
    lastmod = vent["hasta"] or dt.date.today().isoformat()
    pie = (f'Datos hasta la sesión {vent["sesion"]} ({P.fecha(vent["hasta"])})'
           if vent["sesion"] else "Datos del Congreso")

    filas = filas_personas(estado, fichas, etiquetas)
    salidas, tops = [], {}

    s, orden = _pag_participacion(P, filas, pie, lastmod)
    salidas.append(s)
    menos = list(reversed(orden))
    tops["participacion.html"] = _top(
        P, ["#", "Diputado", "Grupo", "Participación"],
        [[str(i + 1), P.celda_nombre(f), P.celda_grupo(f["grupo"], f["color"]), pct(f["participacion"])]
         for i, f in enumerate(menos)], {0, 3})

    s, orden = _pag_disidencia(P, filas, cohesion_grupos(estado), vent, pie, lastmod)
    salidas.append(s)
    tops["disidencia.html"] = _top(
        P, ["#", "Diputado", "Grupo", "Contra su grupo"],
        [[str(i + 1), P.celda_nombre(f), P.celda_grupo(f["grupo"], f["color"]), pct(f["disidencia"])]
         for i, f in enumerate(orden)], {0, 3})

    s, orden = _pag_intervenciones(P, filas, pie, lastmod)
    salidas.append(s)
    tops["intervenciones.html"] = _top(
        P, ["#", "Diputado", "Grupo", "Intervenciones"],
        [[str(i + 1), P.celda_nombre(f), P.celda_grupo(f["grupo"], f["color"]), str(f["intervenciones"])]
         for i, f in enumerate(orden)], {0, 3})

    grupos, coinc = matriz_afinidad(estado)
    s, pares = _pag_afinidad(P, grupos, coinc, vent, pie, lastmod)
    salidas.append(s)
    tops["afinidad.html"] = _top(
        P, ["Par de grupos", "Coincidencia"],
        [[P.esc(f"{cd.GRUPO_CORTO.get(a, a)} – {cd.GRUPO_CORTO.get(b, b)}"), pct(v)]
         for v, a, b, _s, _n in pares], {1})

    lista = votaciones_ajustadas(estado)
    s, _l = _pag_ajustadas(P, lista, vent, pie, lastmod)
    salidas.append(s)
    tops["ajustadas.html"] = _top(
        P, ["Votación", "Sí – No"],
        [[f'<a href="../votaciones/{P.attr(P.pag_votacion(d))}">'
          f'{P.esc((d.get("a") or d.get("t") or "Votación")[:120])}</a>',
          f'{(d.get("tot") or [0, 0])[0] or 0} – {(d.get("tot") or [0, 0])[1] or 0}']
         for d in lista], {1})

    provs = participacion_provincias(filas)
    s, _p = _pag_provincias(P, provs, pie, lastmod)
    salidas.append(s)
    tops["provincias.html"] = _top(
        P, ["#", "Circunscripción", "Participación media"],
        [[str(i + 1), f'<a href="../diputados/provincia-{P.attr(P.slug_txt(r["circ"]))}.html">'
          f'{P.esc(r["circ"])}</a>', pct(r["media"])] for i, r in enumerate(provs)], {0, 2})

    s, orden_pq = _pag_preguntas(P, filas, pie, lastmod)
    salidas.append(s)
    tops["preguntas.html"] = _top(
        P, ["#", "Diputado", "Grupo", "Preguntas"],
        [[str(i + 1), P.celda_nombre(f), P.celda_grupo(f["grupo"], f["color"]), str(r["total"])]
         for i, (f, r) in enumerate(orden_pq)], {0, 3})

    salidas.append(_pag_metodologia(P, vent, etiquetas, pie, lastmod))
    salidas.append(_pag_indice(P, tops, vent, pie, lastmod))
    return salidas
