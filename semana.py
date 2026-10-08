"""La semana en las Cortes y el BOE: un resumen semanal determinista.

`construir(semana_iso)` agrega lo ocurrido de lunes a domingo de una semana ISO
(«2026-W40» o «2026-S40») a partir de lo que ya guarda el sitio:

    data/AAAA-MM-DD.json          leyes y reales decretos del BOE de cada edición
    state/congreso.json           votaciones con detalle nominal («detalle»)
    state/preguntas_escritas.json preguntas escritas (registro, plazo, contestación)
    state/respuestas/AAAA.json    preguntas orales de control y citas de las respuestas
    state/tramitacion.json        pasos de cada iniciativa y plazos de enmiendas
    state/nombramientos.json      nombramientos y ceses de la sección II.A

Secciones (cada una solo si tiene datos), con un enlace en cada elemento:

  normas         Leyes, leyes orgánicas, reales decretos-leyes, reales decretos
                 legislativos y reales decretos publicados en el BOE en la
                 semana. El titular de la casa redactado con Gemini para la
                 edición diaria (caché de redaccion.py) se reutiliza tal cual y
                 se marca como editorial; el título oficial va siempre.
  votaciones     Las MAX_AJUSTADAS votaciones del Pleno con menos diferencia
                 entre síes y noes (desempate: más reciente primero) y las
                 votaciones en las que algún diputado votó distinto que la
                 mayoría de su grupo, con su nombre (sin el Grupo Mixto, que
                 reúne partidos distintos: mismo criterio que /rankings/).
  preguntas      Orales: el texto literal de las preguntas de las sesiones de
                 control de la semana, por orden de la sesión (hasta
                 MAX_ORALES; primero las dirigidas al presidente del Gobierno).
                 Escritas contestadas en la semana, de la que más tardó a la
                 que menos (hasta MAX_CONTESTADAS), con la cita literal si ya se
                 leyó el PDF. Pendientes: las que al cierre del domingo tenían
                 la fecha límite de la ficha oficial superada y ninguna
                 contestación registrada, con la misma redacción prudente que
                 /preguntas/ (no se presenta como incumplimiento).
  tramitacion    Pasos de tramitación que empiezan en la semana y ampliaciones
                 del plazo de enmiendas: un plazo que vencía en la semana y se
                 amplió (el Congreso no publica la fecha del acuerdo).
  nombramientos  Nombramientos y ceses por real decreto, orden o acuerdo (altos
                 cargos) y el recuento del resto (resoluciones).
  cifra          «La cifra de la semana», con REGLAS_CIFRA: la primera regla que
                 se cumple da la cifra. Sin valoraciones.

Mismo trato para todos los grupos: nada se ordena ni se filtra por grupo.

El resumen de una semana CERRADA se congela en data/semanas/AAAA-Snn.json la
primera vez que se construye (asegurar(), en el pase diario: el del lunes,
o el primero después si ese falla) y desde entonces se pinta desde ese
fichero. Así lanzar el pase dos veces da lo mismo (idempotente) y una semana
publicada no cambia aunque luego se pode el estado. Para rehacerlas todas tras
cambiar este módulo, se sube VERSION.

Las páginas (/semana/AAAA-Snn.html, /semana/index.html y /semana/feed.xml) las
pinta generar_paginas(h), con el contrato de los módulos de páginas
(ARQUITECTURA.md §4). La versión para correo la hace tools/semana_email.py con
el mismo JSON. Sin red: todo sale de ficheros locales.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).parent
DATA = ROOT / "data"
DIR = DATA / "semanas"
VERSION = 1

MAX_AJUSTADAS = 5
MAX_DISIDENCIAS = 8
MAX_ORALES = 12
MAX_CONTESTADAS = 10
MAX_PENDIENTES = 8
MAX_TRAMITACION = 30
MAX_NOMBRAMIENTOS = 30
# Primera semana con edición de Cortes completa (antes, las ediciones de
# archivo solo tienen el BOE; las secciones de Cortes salen igual si el
# estado tiene hechos de esas fechas).
PRIMERA = "2026-W01"

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
RANGOS = [("Ley Orgánica", r"Ley Orgánica \d+/\d{4}"),
          ("Real Decreto-ley", r"Real Decreto-ley \d+/\d{4}"),
          ("Real Decreto Legislativo", r"Real Decreto Legislativo \d+/\d{4}"),
          ("Ley", r"Ley \d+/\d{4}"),
          ("Real Decreto", r"Real Decreto \d+/\d{4}")]
RANGOS_NOMBRAMIENTO = ("Real Decreto", "Orden", "Acuerdo")
GRUPOS_SIN_DISCIPLINA = {"GMx"}
RE_REF_BOE = re.compile(r"^BOE-[A-Z]-\d{4}-\d+$")

# «La cifra de la semana»: la primera que se cumple. Se publican con la cifra
# para que se vea por qué es esa y no otra.
MARGEN_AJUSTADA = 10
REGLAS_CIFRA = [
    f"1. La votación más ajustada del Pleno, si se decidió por {MARGEN_AJUSTADA} votos o menos.",
    "2. Si no, las preguntas escritas con la fecha límite superada y sin contestación "
    "registrada al cierre de la semana.",
    "3. Si no, el número de leyes y reales decretos publicados en el BOE.",
    "4. Si no, el número de nombramientos y ceses publicados en el BOE.",
]


# ------------------------------------------------------------------ fechas

def lunes_de(semana_iso: str) -> dt.date:
    """«2026-W40» o «2026-S40» -> lunes de esa semana ISO."""
    m = re.fullmatch(r"(\d{4})-[WS](\d{1,2})", semana_iso or "")
    if not m:
        raise ValueError(f"semana ISO no válida: {semana_iso!r}")
    return dt.date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1)


def id_semana(d: dt.date) -> str:
    """Fecha -> «AAAA-Snn» (año y semana ISO; S de semana)."""
    a, s, _ = d.isocalendar()
    return f"{a}-S{s:02d}"


def ultima_cerrada(hoy: dt.date) -> str:
    """La semana ISO que terminó el domingo anterior a `hoy`."""
    return id_semana(hoy - dt.timedelta(days=hoy.weekday() + 1))


def rango_texto(desde: dt.date, hasta: dt.date) -> str:
    """«del 28 de septiembre al 4 de octubre de 2026» / «del 5 al 11 de octubre de 2026»."""
    if desde.month == hasta.month:
        return f"del {desde.day} al {hasta.day} de {MESES[hasta.month - 1]} de {hasta.year}"
    a1 = f" de {desde.year}" if desde.year != hasta.year else ""
    return (f"del {desde.day} de {MESES[desde.month - 1]}{a1} al {hasta.day} de "
            f"{MESES[hasta.month - 1]} de {hasta.year}")


def titulo(sem: dict) -> str:
    return (f"La semana en las Cortes y el BOE ("
            f"{rango_texto(dt.date.fromisoformat(sem['desde']), dt.date.fromisoformat(sem['hasta']))})")


def _en(f: str | None, desde: str, hasta: str) -> bool:
    return bool(f) and desde <= f[:10] <= hasta


def _cargar_json(ruta: pathlib.Path, vacio):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except Exception:                                         # noqa: BLE001
        return vacio


# ------------------------------------------------------------------ secciones

def _normas(desde: str, hasta: str) -> list:
    cache = (_cargar_json(ROOT / "state" / "redaccion.json", {}).get("piezas") or {})
    salida, vistos = [], set()
    d0 = dt.date.fromisoformat(desde)
    # El BOE de la semana puede salir en la edición del lunes siguiente.
    for i in range(0, 9):
        f = (d0 + dt.timedelta(days=i)).isoformat()
        dia = _cargar_json(DATA / f"{f}.json", None)
        if not dia:
            continue
        boe = dia.get("boe") or {}
        fecha_boe = (boe.get("fechaISO") or "")[:10]
        if not _en(fecha_boe, desde, hasta):
            continue
        for s in boe.get("stories") or []:
            oficial = s.get("titulo_oficial") or s.get("standfirst") or ""
            rango = next((r for r, patron in RANGOS if re.match(patron, oficial)), "")
            ref = s.get("ref") or ""
            if not rango or (ref or oficial) in vistos:
                continue
            vistos.add(ref or oficial)
            ia = (cache.get(ref) or {}).get("titular") if ref else ""
            salida.append({
                "ref": ref, "rango": rango, "titulo": oficial, "fecha": fecha_boe,
                "titular": s.get("headline", ""), "editorial": ia or "",
                "url": f"/normas/{ref}.html" if RE_REF_BOE.match(ref) else f"/ediciones/{f}.html",
                "fuente": s.get("url") or (f"https://www.boe.es/diario_boe/txt.php?id={ref}" if ref else ""),
            })
    orden = [r for r, _p in RANGOS]
    return sorted(salida, key=lambda x: (orden.index(x["rango"]), x["fecha"], x["ref"]))


def _votaciones(desde: str, hasta: str, congreso: dict) -> dict:
    import congreso_datos as cd
    todo = congreso.get("detalle") or {}
    det = [{"url": u, **d} for u, d in todo.items() if _en(d.get("f"), desde, hasta)]
    # El detalle nominal guarda las últimas votaciones (congreso_datos.DETALLE_MAX):
    # una semana solo se resume si está entera dentro, para no dar recuentos cortos.
    if not det or min(d.get("f") or "9" for d in todo.values()) >= desde:
        return {}
    nombres = congreso.get("det_nombres") or []
    censo = congreso.get("censo") or {}
    # Un grupo puede tener dos códigos en el dato oficial (Sumar: «GSUMAR» y
    # «GPlu»): se usa el que aparezca en cada votación.
    cods_de_largo: dict = {}
    for cod, largo in cd.COD_GRUPO.items():
        cods_de_largo.setdefault(largo, []).append(cod)

    def fila(d):
        tot = (d.get("tot") or [0, 0, 0, 0]) + [0, 0, 0, 0]
        return {"f": d["f"], "s": d.get("s"), "n": d.get("n"), "asunto": d.get("a") or d.get("t") or "",
                "titulo": d.get("t") or "", "sub": d.get("sub") or "", "tot": tot[:4],
                "margen": abs((tot[0] or 0) - (tot[1] or 0)), "asent": bool(d.get("asent")),
                "url": f"/votaciones/{d['f']}-v{d.get('s') or 0}-{d.get('n') or 0}.html",
                "fuente": d.get("url", "")}

    votadas = [d for d in det if not d.get("asent")]
    ajustadas = sorted(votadas, key=lambda d: (abs((d["tot"][0] or 0) - (d["tot"][1] or 0)),
                                               _clave_reciente(d)))[:MAX_AJUSTADAS]
    disid = []
    for d in sorted(det, key=_clave_reciente):
        mayoria = {}
        for cod, c in (d.get("g") or {}).items():
            cuenta = {"S": c[0], "N": c[1], "A": c[2]}
            top = max(cuenta.values())
            # Sin mayoría clara (empate dentro del grupo) no hay «disidente».
            ganadores = [k for k, n in cuenta.items() if n == top and top > 0]
            mayoria[cod] = ganadores[0] if len(ganadores) == 1 else None
        personas = []
        for i, voto in enumerate(d.get("v") or ""):
            if voto not in "SNA" or i >= len(nombres):
                continue
            p = censo.get(nombres[i]) or {}
            cod = next((c for c in cods_de_largo.get(p.get("grupo") or "", []) if c in mayoria), None)
            # El Grupo Mixto reúne partidos distintos que no votan como un
            # bloque (el mismo criterio que /rankings/): no hay «su grupo».
            if cod and cod not in GRUPOS_SIN_DISCIPLINA and mayoria.get(cod) and voto != mayoria[cod]:
                personas.append({"nombre": p.get("natural") or nombres[i], "slug": p.get("slug", ""),
                                 "grupo": cd.GRUPO_CORTO.get(p.get("grupo"), cod),
                                 "voto": voto, "voto_grupo": mayoria[cod]})
        if personas:
            disid.append({**fila(d), "personas": sorted(personas, key=lambda x: x["nombre"])})
    salida = {"total": len(det), "ajustadas": [fila(d) for d in ajustadas]}
    if disid:
        salida["disidencias"] = disid[:MAX_DISIDENCIAS]
        salida["n_disidencias"] = len(disid)
    return salida


def _clave_reciente(d: dict) -> tuple:
    """Para ordenar de la más reciente a la más antigua con sort() ascendente."""
    f = dt.date.fromisoformat(d["f"]).toordinal()
    return (-f, -(d.get("s") or 0), -(d.get("n") or 0))


# Las pendientes al cierre solo se cuentan al congelar la semana recién
# cerrada: el estado de preguntas escritas guarda una ventana de 365 días
# (preguntas.VENTANA_DIAS) y no recuerda cuándo se vio cada contestación, así
# que reconstruirlas para una semana antigua podría dar una cifra corta.
DIAS_PENDIENTES = 8


def _preguntas(desde: str, hasta: str, hoy: dt.date | None = None) -> dict:
    import preguntas as pq
    import respuestas as rp
    salida: dict = {}
    orales = []
    for a in rp.anios():
        for exp, r in (rp.cargar(a).get("orales") or {}).items():
            if _en(r.get("s"), desde, hasta):
                orales.append((exp, r))
    if orales:
        orales.sort(key=lambda x: (0 if re.match(r"(?i)president[ea] del gobierno", x[1].get("cargo") or "") else 1,
                                   x[1].get("s") or "", x[1].get("h") or "", x[0]))
        salida["orales"] = [{"exp": exp, "s": r.get("s"), "autor": r.get("a", ""),
                             "grupo": pq.grupo_corto(r["g"]) if r.get("g") else "",
                             "texto": r.get("t", ""), "contesta": r.get("gob", ""),
                             "cargo": r.get("cargo", ""), "url": f"/sesiones/{r.get('s')}.html",
                             "cita": r.get("c1", "")}
                            for exp, r in orales[:MAX_ORALES]]
        salida["n_orales"] = len(orales)
    e = pq.cargar_escritas()
    exp_ = e.get("exp") or {}
    contestadas = [(k, v) for k, v in exp_.items() if _en(v.get("c"), desde, hasta)]
    if contestadas:
        contestadas.sort(key=lambda x: (-(pq._dias(x[1].get("p"), x[1]["c"]) or 0), x[0]))
        filas = []
        for k, v in contestadas[:MAX_CONTESTADAS]:
            r = rp.escrita(k) or {}
            filas.append({"exp": k, "titulo": v.get("t", ""), "autores": v.get("a") or [],
                          "grupo": ", ".join(pq.grupo_corto(g) for g in v.get("g") or []),
                          "publicada": v.get("p"), "contestada": v["c"],
                          "dias": pq._dias(v.get("p"), v["c"]), "cita": r.get("cita", ""),
                          "pdf": r.get("pdf", ""), "url": pq.url_ficha(k)})
        salida["contestadas"] = filas
        salida["n_contestadas"] = len(contestadas)
    hoy = hoy or dt.date.today()
    if pq.datos_completos(e) and (hoy - dt.date.fromisoformat(hasta)).days <= DIAS_PENDIENTES:
        vencidas = []
        for k, v in exp_.items():
            if v.get("res") or not v.get("p") or v["p"] > hasta:
                continue
            if v.get("c") and v["c"] <= hasta:
                continue
            lim = v.get("lim")
            if lim and lim < hasta:
                vencidas.append((k, v))
        if vencidas:
            vencidas.sort(key=lambda x: (x[1]["p"], x[0]))
            salida["pendientes"] = {
                "total": len(vencidas),
                "vencieron_en_la_semana": sum(1 for _k, v in vencidas if _en(v.get("lim"), desde, hasta)),
                "lista": [{"exp": k, "titulo": v.get("t", ""),
                           "grupo": ", ".join(pq.grupo_corto(g) for g in v.get("g") or []),
                           "publicada": v["p"], "limite": v.get("lim"), "url": pq.url_ficha(k)}
                          for k, v in vencidas[:MAX_PENDIENTES]],
            }
    return salida


def _tramitacion(desde: str, hasta: str) -> list:
    import tramitacion as tr
    salida = []
    for exp, v in (tr.cargar().get("ini") or {}).items():
        base = {"exp": exp, "titulo": (v.get("t") or exp).rstrip("."), "tipo": tr.tipo_corto(v.get("tipo", "")),
                "url": f"/tramitacion/{tr.slug(exp)}.html", "fuente": tr.url_ficha(exp)}
        for paso in v.get("pasos") or []:
            if len(paso) > 1 and _en(paso[1], desde, hasta):
                salida.append({**base, "clase": "paso", "f": paso[1], "hito": paso[0],
                               "hasta": paso[2] if len(paso) > 2 else ""})
        de_enm = [p for p in v.get("plazos") or [] if re.search(r"enmienda", p[2], re.I)]
        for anterior, p in zip(de_enm, de_enm[1:]):
            if re.search(r"ampliaci", p[2], re.I) and _en(anterior[0], desde, hasta):
                salida.append({**base, "clase": "ampliacion", "f": anterior[0],
                               "hito": f"{p[2]}: el plazo que vencía el {anterior[0]} se amplía hasta el {p[0]}",
                               "hasta": p[0]})
    salida.sort(key=lambda x: (x["f"], x["exp"], x["hito"]))
    return salida


def _nombramientos(desde: str, hasta: str) -> dict:
    import nombramientos as nb
    regs = [{"id": k, **v} for k, v in nb.cargar()["registros"].items()]
    por_persona: dict = {}
    for r in sorted(regs, key=lambda r: r["fecha"]):
        por_persona.setdefault(r["clave"], []).append(r)
    slugs = nb.slugs_personas(por_persona)
    semana = [r for r in regs if _en(r.get("fecha"), desde, hasta)]
    if not semana:
        return {}
    altos = sorted((r for r in semana if r.get("rango") in RANGOS_NOMBRAMIENTO),
                   key=lambda r: (r["fecha"], r["id"]))
    return {
        "total": len(semana),
        "nombramientos": sum(1 for r in semana if r.get("acto") == "nombramiento"),
        "ceses": sum(1 for r in semana if r.get("acto") == "cese"),
        "lista": [{"persona": r.get("persona", ""), "acto": r.get("acto", ""), "cargo": r.get("cargo", ""),
                   "emisor": r.get("emisor") or r.get("organo", ""), "fecha": r["fecha"],
                   "rango": r.get("rango", ""), "url": f"/personas/{slugs.get(r['clave'], '')}.html",
                   "fuente": r.get("url", "")} for r in altos[:MAX_NOMBRAMIENTOS]],
        "resto": len(semana) - min(len(altos), MAX_NOMBRAMIENTOS),
    }


def _cifra(sec: dict) -> dict | None:
    aj = ((sec.get("votaciones") or {}).get("ajustadas") or [])
    if aj and aj[0]["margen"] <= MARGEN_AJUSTADA:
        v = aj[0]
        return {"regla": 1, "valor": v["margen"],
                "texto": (f"votos de diferencia: la votación más ajustada del Pleno acabó en empate, "
                          f"{v['tot'][0]} a favor y {v['tot'][1]} en contra" if v["margen"] == 0 else
                          ("voto de diferencia decidió la " if v["margen"] == 1 else
                           "votos de diferencia decidieron la ") +
                          f"votación más ajustada del Pleno: {v['tot'][0]} a favor y {v['tot'][1]} "
                          f"en contra"), "asunto": v["asunto"].rstrip(". "), "url": v["url"], "fuente": v["fuente"]}
    pend = (sec.get("preguntas") or {}).get("pendientes")
    if pend and pend["total"]:
        return {"regla": 2, "valor": pend["total"],
                "texto": ("preguntas escritas con la fecha límite de la ficha oficial superada y sin "
                          "contestación registrada al cierre de la semana"),
                "asunto": "", "url": "/preguntas/#pendientes", "fuente": ""}
    if sec.get("normas"):
        return {"regla": 3, "valor": len(sec["normas"]),
                "texto": "leyes y reales decretos publicados en el BOE", "asunto": "", "url": "", "fuente": ""}
    nb = sec.get("nombramientos") or {}
    if nb.get("total"):
        return {"regla": 4, "valor": nb["total"], "texto": "nombramientos y ceses publicados en el BOE",
                "asunto": "", "url": "/nombramientos/", "fuente": ""}
    return None


def construir(semana_iso: str, hoy: dt.date | None = None) -> dict:
    """El resumen de la semana ISO `semana_iso`. Cada sección en su try: un
    fallo deja la semana sin esa sección y lo anota en «errores»."""
    lunes = lunes_de(semana_iso)
    desde, hasta = lunes.isoformat(), (lunes + dt.timedelta(days=6)).isoformat()
    congreso = _cargar_json(ROOT / "state" / "congreso.json", {})
    sec: dict = {}
    errores = []
    for nombre, fn in [("normas", lambda: _normas(desde, hasta)),
                       ("votaciones", lambda: _votaciones(desde, hasta, congreso)),
                       ("preguntas", lambda: _preguntas(desde, hasta, hoy)),
                       ("tramitacion", lambda: _tramitacion(desde, hasta)[:MAX_TRAMITACION]),
                       ("nombramientos", lambda: _nombramientos(desde, hasta))]:
        try:
            valor = fn()
            if valor:
                sec[nombre] = valor
        except Exception as exc:                              # noqa: BLE001
            errores.append(f"{nombre}: {exc}")
    cifra = _cifra(sec)
    if cifra:
        sec["cifra"] = cifra
    return {"esquema": 1, "version": VERSION, "semana": id_semana(lunes), "desde": desde,
            "hasta": hasta, "generada": (hoy or dt.date.today()).isoformat(),
            "secciones": sec, "errores": errores}


# ------------------------------------------------------------------ estado

def ruta(semana: str) -> pathlib.Path:
    return DIR / f"{semana}.json"


def cargar(semana: str) -> dict | None:
    return _cargar_json(ruta(semana), None)


def todas() -> list:
    """Las semanas congeladas, de la más reciente a la más antigua."""
    salida = []
    for p in sorted(DIR.glob("*-S*.json"), reverse=True):
        s = _cargar_json(p, None)
        if s and s.get("semana"):
            salida.append(s)
    return salida


def pendientes_de_construir(hoy: dt.date) -> list:
    """Semanas cerradas desde PRIMERA hasta la anterior a `hoy` que faltan o
    son de una VERSION anterior."""
    ultima = lunes_de(ultima_cerrada(hoy).replace("S", "W"))
    d = lunes_de(PRIMERA)
    salida = []
    while d <= ultima:
        sid = id_semana(d)
        s = cargar(sid)
        if not s or s.get("version") != VERSION:
            salida.append(sid)
        d += dt.timedelta(days=7)
    return salida


def asegurar(hoy: dt.date | None = None, log=print) -> list:
    """Congela las semanas cerradas que faltan. Se llama en el pase diario: el
    del lunes construye la semana que acaba de cerrar; los demás no hacen nada
    (idempotente). La primera vez construye el archivo entero."""
    hoy = hoy or dt.date.today()
    hechas = []
    for sid in pendientes_de_construir(hoy):
        # Solo semanas con alguna edición: antes de la primera no hay nada.
        lunes = lunes_de(sid)
        # (hasta el lunes siguiente, que puede traer el BOE del sábado)
        if not any((DATA / f"{(lunes + dt.timedelta(days=i)).isoformat()}.json").exists() for i in range(8)):
            continue
        s = construir(sid, hoy)
        DIR.mkdir(parents=True, exist_ok=True)
        ruta(sid).write_text(json.dumps(s, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                             encoding="utf-8")
        hechas.append(sid)
        if s["errores"]:
            log(f"  semana {sid}: secciones con error: {s['errores']}")
    if hechas:
        log(f"semana: {len(hechas)} semana(s) congelada(s): {hechas[0]} … {hechas[-1]}")
    return hechas


# ------------------------------------------------------------------ páginas

VOTO = {"S": "sí", "N": "no", "A": "abstención"}


def _fecha_corta(iso: str) -> str:
    d = dt.date.fromisoformat(iso[:10])
    return f"{d.day} de {MESES[d.month - 1]}"


def cuerpo_html(sem: dict, esc, attr, enlace) -> str:
    """El cuerpo de la página de una semana. `enlace(url_sitio, fuente)` da el
    destino: la página del sitio si existe y, si no, la fuente oficial."""
    s = sem["secciones"]
    partes = []

    def a(url, fuente, texto):
        destino = enlace(url, fuente)
        if not destino:
            return esc(texto)
        externo = destino.startswith("http")
        return (f'<a href="{attr(destino)}"' + (' rel="noopener" target="_blank"' if externo else "")
                + f">{esc(texto)}</a>")

    c = s.get("cifra")
    if c:
        partes.append(
            f'<section class="semana-cifra"><h2 class="rotulo" id="cifra">La cifra de la semana</h2>'
            f'<p class="sc-num">{c["valor"]}</p><p class="sc-txt">{esc(c["texto"])}'
            + (f': {a(c["url"], c.get("fuente", ""), "«" + c["asunto"] + "»")}' if c.get("asunto") else
               (f' ({a(c["url"], "", "ver")})' if c.get("url") else ""))
            + f'.</p><p class="rk-nota">Cómo se elige: <a href="#reglas">reglas fijas</a>, '
              f'la primera que se cumple (regla {c["regla"]}).</p></section>')
    if s.get("normas"):
        filas = "".join(
            f'<li>{a(n["url"], n["fuente"], n["titulo"])}<span class="ref">{esc(n["rango"])} · '
            f'BOE del {esc(_fecha_corta(n["fecha"]))}{" · " + esc(n["ref"]) if n["ref"] else ""}</span>'
            + (f'<span class="ref">Titular editorial (IA): «{esc(n["editorial"])}»</span>' if n.get("editorial") else "")
            + '</li>' for n in s["normas"])
        partes.append(f'<h2 class="rotulo" id="normas">Leyes y reales decretos en el BOE</h2>'
                      f'<ul class="indice">{filas}</ul>')
    vt = s.get("votaciones") or {}
    if vt.get("ajustadas"):
        filas = "".join(
            f'<li>{a(v["url"], v["fuente"], v["asunto"])}<span class="ref">{esc(_fecha_corta(v["f"]))} · '
            f'{v["tot"][0]} sí, {v["tot"][1]} no, {v["tot"][2]} abstenciones · diferencia de '
            f'{v["margen"]} voto{"s" if v["margen"] != 1 else ""}</span></li>' for v in vt["ajustadas"])
        partes.append(f'<h2 class="rotulo" id="votaciones">Las votaciones más ajustadas</h2>'
                      f'<p class="rk-nota">De las {vt["total"]} votaciones del Pleno con detalle nominal, '
                      f'las de menor diferencia entre síes y noes.</p><ul class="indice">{filas}</ul>')
    if vt.get("disidencias"):
        filas = []
        for v in vt["disidencias"]:
            gente = "; ".join(
                f'{a("/diputados/" + p["slug"] + ".html" if p["slug"] else "", "", p["nombre"])} '
                f'({esc(p["grupo"])}): {VOTO[p["voto"]]}, su grupo {VOTO[p["voto_grupo"]]}'
                for p in v["personas"][:12])
            mas = f' y {len(v["personas"]) - 12} más' if len(v["personas"]) > 12 else ""
            filas.append(f'<li>{a(v["url"], v["fuente"], v["asunto"])}<span class="ref">'
                         f'{esc(_fecha_corta(v["f"]))} · {gente}{esc(mas)}</span></li>')
        partes.append(f'<h2 class="rotulo" id="disidencias">Votos distintos a los de su grupo</h2>'
                      f'<p class="rk-nota">Diputados que votaron distinto que la mayoría de su grupo '
                      f'({vt["n_disidencias"]} votaciones en la semana).</p><ul class="indice">{"".join(filas)}</ul>')
    pr = s.get("preguntas") or {}
    if pr.get("orales"):
        filas = "".join(
            f'<li><blockquote class="pull"><p>«{esc(o["texto"])}»</p><cite>{esc(o["autor"])}'
            f'{" (" + esc(o["grupo"]) + ")" if o["grupo"] else ""} · contesta {esc(o["contesta"])}'
            f'{", " + esc(o["cargo"]) if o["cargo"] else ""} · {a(o["url"], "", "sesión del " + _fecha_corta(o["s"]))}'
            f'</cite></blockquote></li>' for o in pr["orales"])
        partes.append(f'<h2 class="rotulo" id="orales">Lo que se preguntó en la sesión de control</h2>'
                      f'<p class="rk-nota">Preguntas orales tal como se formularon ({pr["n_orales"]} en la '
                      f'semana; se muestran hasta {MAX_ORALES}, primero las dirigidas al presidente del '
                      f'Gobierno y después por orden de la sesión).</p><ul class="indice">{filas}</ul>')
    if pr.get("contestadas"):
        filas = "".join(
            f'<li>{a(q["url"], "", q["titulo"])}<span class="ref">{esc(q["exp"])} · {esc(q["grupo"])} · '
            f'contestada el {esc(_fecha_corta(q["contestada"]))}'
            + (f', {q["dias"]} días después de publicarse' if q.get("dias") is not None else "")
            + '</span>'
            + (f'<blockquote class="pull"><p>«{esc(q["cita"])}»</p><cite>Respuesta del Gobierno · '
               f'{a("", q["pdf"], "texto completo (PDF)")}</cite></blockquote>' if q.get("cita") else "")
            + '</li>' for q in pr["contestadas"])
        partes.append(f'<h2 class="rotulo" id="contestadas">Respuestas escritas publicadas</h2>'
                      f'<p class="rk-nota">{pr["n_contestadas"]} contestaciones registradas en la semana; '
                      f'aquí, las que más tardaron.</p><ul class="indice">{filas}</ul>')
    if pr.get("pendientes"):
        p = pr["pendientes"]
        filas = "".join(
            f'<li>{a(q["url"], "", q["titulo"])}<span class="ref">{esc(q["exp"])} · {esc(q["grupo"])} · '
            f'publicada el {esc(_fecha_corta(q["publicada"]))} · fecha límite {esc(_fecha_corta(q["limite"]))}'
            f'</span></li>' for q in p["lista"])
        partes.append(
            f'<h2 class="rotulo" id="pendientes">Pendientes con el plazo superado</h2>'
            f'<p class="rk-nota">Al cierre del domingo, {p["total"]} preguntas escritas publicadas en el BOCG '
            f'tenían la fecha límite que figura en la ficha oficial ya superada y ninguna contestación '
            f'registrada ({p["vencieron_en_la_semana"]} vencieron esta semana). No se presenta como un '
            f'incumplimiento: puede haber prórrogas o contestaciones pendientes de reflejarse. Las más '
            f'antiguas:</p><ul class="indice">{filas}</ul>')
    if s.get("tramitacion"):
        filas = "".join(
            f'<li>{a(t["url"], t["fuente"], t["tipo"] + ": " + t["titulo"])}<span class="ref">'
            f'{esc(t["exp"])} · {esc(_fecha_corta(t["f"]))} · {esc(t["hito"])}</span></li>'
            for t in s["tramitacion"])
        partes.append(f'<h2 class="rotulo" id="tramitacion">Cambios en la tramitación</h2>'
                      f'<p class="rk-nota">Pasos que empiezan en la semana y plazos de enmiendas que '
                      f'vencían en ella y se ampliaron (el Congreso no publica la fecha del acuerdo).</p>'
                      f'<ul class="indice">{filas}</ul>')
    nb = s.get("nombramientos") or {}
    if nb.get("lista") or nb.get("total"):
        filas = "".join(
            f'<li>{a(n["url"], n["fuente"], n["persona"])}<span class="ref">{esc(n["acto"].capitalize())} · '
            f'{esc(n["cargo"])}{" · " + esc(n["emisor"]) if n["emisor"] else ""} · {esc(n["rango"])} · '
            f'BOE del {esc(_fecha_corta(n["fecha"]))}</span></li>' for n in nb.get("lista") or [])
        partes.append(
            f'<h2 class="rotulo" id="nombramientos">Nombramientos y ceses</h2>'
            f'<p class="rk-nota">{nb["total"]} en el BOE de la semana ({nb["nombramientos"]} nombramientos y '
            f'{nb["ceses"]} ceses). Aquí, los de real decreto, orden o acuerdo'
            + (f'; los otros {nb["resto"]}, en <a href="/nombramientos/">Nombramientos</a>' if nb.get("resto") else "")
            + f'.</p><ul class="indice">{filas}</ul>')
    if not partes:
        partes.append("<p>No hay hechos registrados en las fuentes que seguimos para esta semana.</p>")
    partes.append(
        '<h2 class="rotulo" id="reglas">Cómo se hace este resumen</h2>'
        '<p class="rk-nota">Se construye solo, con reglas fijas, a partir de las publicaciones oficiales '
        'que ya recoge el sitio, y se congela al cerrar la semana. Mismo trato para todos los grupos: nada '
        'se ordena ni se filtra por grupo. Lo que va entre comillas es literal de la fuente. «La cifra de la '
        'semana» sale de la primera de estas reglas que se cumple:</p><ol class="rk-nota">'
        + "".join(f"<li>{esc(r[3:])}</li>" for r in REGLAS_CIFRA) + "</ol>")
    return "".join(partes)


def descripcion(sem: dict) -> str:
    s = sem["secciones"]
    trozos = []

    def n(cuantos, uno, varios):
        if cuantos:
            trozos.append(f"{cuantos} {uno if cuantos == 1 else varios}")

    n(len(s.get("normas") or []), "ley o real decreto", "leyes y reales decretos")
    n((s.get("votaciones") or {}).get("total"), "votación", "votaciones")
    n((s.get("preguntas") or {}).get("n_contestadas"), "respuesta escrita", "respuestas escritas")
    n((s.get("nombramientos") or {}).get("total"), "nombramiento o cese", "nombramientos y ceses")
    base = f"Resumen de la semana {rango_texto(dt.date.fromisoformat(sem['desde']), dt.date.fromisoformat(sem['hasta']))}"
    return (base + ": " + ", ".join(trozos) + ", con enlace a cada fuente oficial.") if trozos else base + "."


def jsonld(sem: dict, url: str) -> dict:
    """Report y no NewsArticle: es un informe periódico generado con reglas
    fijas sobre datos oficiales, sin autoría periodística ni valoraciones.
    Google solo da resultados enriquecidos de artículo a NewsArticle, pero
    presentarlo como noticia sería afirmar algo que no es."""
    return {"@type": "Report", "name": titulo(sem), "headline": titulo(sem)[:110], "url": url,
            "inLanguage": "es-ES", "datePublished": sem["generada"], "dateModified": sem["generada"],
            "temporalCoverage": f"{sem['desde']}/{sem['hasta']}",
            "description": descripcion(sem),
            "publisher": {"@type": "Organization", "name": "La Tercera Cámara", "url": "https://terceracamara.es/"},
            "isBasedOn": ["https://www.boe.es/", "https://www.congreso.es/"]}


def generar_paginas(h: dict) -> list:
    """/semana/AAAA-Snn.html, /semana/index.html y /semana/feed.xml."""
    import feeds as fd
    semanas = todas()
    if not semanas:
        return []
    esc, attr = h["esc_html"], h["esc_attr"]
    carpeta, site, raiz = h["carpeta"], h["site_url"], h["raiz"]
    carpeta.mkdir(exist_ok=True)
    form = h.get("formulario", "")

    def existe(url_sitio: str) -> bool:
        rel = url_sitio.split("#", 1)[0].lstrip("/")
        if not rel or rel.endswith("/"):
            rel += "index.html"
        return (raiz / rel).is_file()

    def enlace(url_sitio: str, fuente: str) -> str:
        if url_sitio and existe(url_sitio):
            return url_sitio
        return fuente or ""

    # El canal se anuncia en el índice y en cada semana: se registra antes de pintar.
    registrar = h.get("registrar_feed") or (lambda *_a: None)
    registrar("index.html", "feed.xml", "La semana en las Cortes y el BOE")
    for sem in semanas:
        registrar(f"{sem['semana']}.html", "feed.xml", "La semana en las Cortes y el BOE")

    salidas = []
    for i, sem in enumerate(semanas):
        nombre = f"{sem['semana']}.html"
        url = f"{site}semana/{nombre}"
        vecinas = []
        if i + 1 < len(semanas):
            vecinas.append(f'<a class="srclink" href="{semanas[i + 1]["semana"]}.html">← Semana anterior</a>')
        if i > 0:
            vecinas.append(f'<a class="srclink" href="{semanas[i - 1]["semana"]}.html">Semana siguiente →</a>')
        h["pagina_suelta"](h["plantilla"], carpeta, nombre, {
            "TITLE": esc(titulo(sem)),
            "META_DESC": attr(descripcion(sem)[:155]),
            "CANONICAL": url,
            "JSONLD": h["jsonld_script"]([jsonld(sem, url), {
                "@type": "BreadcrumbList", "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Portada", "item": site},
                    {"@type": "ListItem", "position": 2, "name": "La semana", "item": f"{site}semana/"},
                    {"@type": "ListItem", "position": 3, "name": sem["semana"], "item": url}]}]),
            "EDITION_DATE": esc(f"Semana {sem['semana'].split('-S')[1]} de {sem['semana'][:4]}"),
            "MIGA": (f'<a href="../">Portada</a> › <a href="./">La semana</a> › '
                     f'<span aria-current="page">{esc(sem["semana"])}</span>'),
            "KICKER": "La semana",
            "HEADLINE": esc(titulo(sem)),
            "STANDFIRST": esc("Lo que publicó el BOE y lo que pasó en el Congreso de lunes a domingo, "
                              "con reglas fijas y un enlace a cada fuente."),
            "FICHA": (f"<dt>Semana</dt><dd>{esc(sem['semana'])}</dd>"
                      f"<dt>Del</dt><dd>{esc(_fecha_corta(sem['desde']))}</dd>"
                      f"<dt>Al</dt><dd>{esc(_fecha_corta(sem['hasta']))} de {sem['hasta'][:4]}</dd>"),
            "CUERPO": cuerpo_html(sem, esc, attr, enlace) + form,
            "FUENTE": ("Fuentes: Boletín Oficial del Estado y Congreso de los Diputados. "
                       + " ".join(vecinas)),
            "RELACIONADAS": "", "RELACIONADAS_HIDDEN": "hidden",
        })
        salidas.append({"url": url, "lastmod": sem["generada"]})

    filas = "".join(
        f'<li><a href="{attr(s_["semana"])}.html">{esc(titulo(s_))}</a>'
        f'<span class="ref">{esc(descripcion(s_).split(": ", 1)[-1])}</span></li>' for s_ in semanas)
    url = f"{site}semana/"
    h["pagina_suelta"](h["plantilla"], carpeta, "index.html", {
        "TITLE": esc("La semana en las Cortes y el BOE: archivo | La Tercera Cámara"),
        "META_DESC": attr("Cada lunes, el resumen de la semana anterior: leyes y reales decretos, "
                          "votaciones ajustadas, preguntas al Gobierno, tramitación y nombramientos."),
        "CANONICAL": url,
        "JSONLD": h["jsonld_script"]([{"@type": "CollectionPage", "name": "La semana", "url": url,
                                       "inLanguage": "es-ES", "dateModified": semanas[0]["generada"]}]),
        "EDITION_DATE": esc(f"Última: {semanas[0]['semana']}"),
        "MIGA": '<a href="../">Portada</a> › <span aria-current="page">La semana</span>',
        "KICKER": "Resumen semanal",
        "HEADLINE": "La semana en las Cortes y el BOE",
        "STANDFIRST": esc("Cada lunes, la semana anterior en una página: lo que publicó el BOE y lo que "
                          "pasó en el Congreso, con reglas fijas y sin adjetivos."),
        "FICHA": f"<dt>Semanas</dt><dd>{len(semanas)}</dd>",
        "CUERPO": form + f'<h2 class="rotulo">Archivo</h2><ul class="indice">{filas}</ul>',
        "FUENTE": "Fuentes: Boletín Oficial del Estado y Congreso de los Diputados.",
        "RELACIONADAS": "", "RELACIONADAS_HIDDEN": "hidden",
    })
    salidas.append({"url": url, "lastmod": semanas[0]["generada"]})

    ents = [fd.entrada(f"semana:{s_['semana']}", titulo(s_), s_["generada"],
                       f"{site}semana/{s_['semana']}.html", descripcion(s_)) for s_ in semanas]
    texto = fd.atom("La semana en las Cortes y el BOE — La Tercera Cámara",
                    "El resumen semanal de La Tercera Cámara, cada lunes.",
                    f"{site}semana/feed.xml", url, fd.ordenar(ents))
    if texto:
        h["escribir"](carpeta / "feed.xml", texto)
    return salidas
