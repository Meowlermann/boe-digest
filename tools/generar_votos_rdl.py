"""Genera curated/votos_rdl.json, la copia fija de «¿Quién votó qué en tu
provincia?» (votos_rdl.py).

Se ejecuta a mano y el JSON se commitea: el build no lo regenera ni usa la red.

    python tools/generar_votos_rdl.py [--sin-red]

1. Elige las votaciones con el criterio de votos_rdl.seleccionar() a partir de
   state/congreso.json (detalle nominal de los datos abiertos del Congreso).
2. Con red, abre el JSON oficial de cada votación y comprueba que la fecha y el
   texto coinciden con el estado; si no, para sin escribir nada. Del listado
   oficial de votaciones del día (congreso.es) toma el PDF de detalle y el
   número de expediente de esa misma votación, y de la ficha oficial del
   expediente, el campo «Resultado tramitación» tal cual. Lo que no encuentra
   queda vacío y no se muestra.
3. Sustitutos: en cada votación, quien no figura y tiene una fecha de alta
   posterior (censo del Congreso) va en «antes_alta».
4. Bajas: quien votó y ya no está en el censo se busca en el fichero oficial de
   diputados de baja; con una sola fila, circunscripción de las fichas y votos
   dentro de sus fechas de alta y baja, se atribuye a esa circunscripción
   («bajas», con la fuente). Si no, va a «no_atribuidos» con el motivo.
5. Género, solo de quien lo necesita: «f» si figura en el fichero oficial de
   diputadas de la XV Legislatura y «m» si no; sin ese fichero, nada (texto neutro).
6. Escribe la copia (claves ordenadas, sin fecha de generación: misma entrada,
   mismo fichero) y lista los cruces.
"""
from __future__ import annotations

import html
import json
import pathlib
import re
import sys
import urllib.request

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import congreso_datos as cd  # noqa: E402
import votos_rdl as vr  # noqa: E402

ESTADO = RAIZ / "state" / "congreso.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; TerceraCamara/1.0; +https://terceracamara.es)"}
BASE = "https://www.congreso.es"


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def del_dia(pagina: str, url_json: str) -> tuple[str, str]:
    """(PDF de detalle, expediente) de la votación cuyo JSON es url_json, sacados
    del bloque de esa votación en el listado oficial del día."""
    carpeta = url_json.rsplit("/", 1)[0].replace(BASE, "")          # /webpublica/.../Votacion010
    i = pagina.find(url_json.replace(BASE, ""))
    if i < 0:
        return "", ""
    # El bloque de la votación empieza tras el JSON de la anterior.
    inicio = pagina.rfind(".json", 0, i)
    trozo = pagina[inicio + 1 if inicio >= 0 else 0:i]
    pdf = re.findall(re.escape(carpeta) + r"/[^\"'\s]+\.pdf", trozo)
    expte = re.findall(r"_iniciativas_id=(\d{3}/\d{6})", trozo)
    return (BASE + pdf[-1]) if pdf else "", expte[-1] if expte else ""


def resultado_expediente(pagina: str) -> str:
    """El campo «Resultado tramitación» de la ficha oficial de la iniciativa, tal
    cual (p. ej. «Convalidado»). Vacío si la ficha no lo trae."""
    texto = " ".join(re.sub(r"<[^>]+>", " ", pagina).split())
    m = re.search(r"Resultado tramitación (.+?) Tramitación seguida por la iniciativa", texto)
    return html.unescape(m.group(1)).strip() if m and len(m.group(1)) <= 120 else ""


def diputados_oficiales() -> dict:
    """Del portal de datos abiertos de diputados del Congreso: el fichero de
    diputados de baja (circunscripción, fechas de alta y de baja) y el de
    diputadas (todas las mujeres de cada legislatura). {"bajas": url,
    "diputadas": url, "filas_bajas": [...], "mujeres_xv": set()}."""
    pagina = _get(cd.PAG_DIPUTADOS)
    urls = cd._urls_json(pagina)
    u_bajas, u_mujeres = cd._elegir(urls, "DiputadosDeBaja"), cd._elegir(urls, "Diputadas__")
    out = {"pagina": cd.PAG_DIPUTADOS, "bajas": u_bajas, "diputadas": u_mujeres,
           "filas_bajas": [], "mujeres_xv": set()}
    if u_bajas:
        out["filas_bajas"] = json.loads(_get(u_bajas))
    if u_mujeres:
        out["mujeres_xv"] = {cd.clave_nombre(f"{x.get('APELLIDOS', '')}, {x.get('NOMBRE', '')}")
                             for x in json.loads(_get(u_mujeres)) if x.get("LEGISLATURA") == "Leg. XV"}
    return out


def main() -> int:
    sin_red = "--sin-red" in sys.argv
    estado = json.loads(ESTADO.read_text(encoding="utf-8"))
    nombres = estado.get("det_nombres") or []
    elegidas = vr.seleccionar(estado)
    if len(elegidas) < vr.N_VOTACIONES:
        print(f"ERROR: solo hay {len(elegidas)} votaciones que cumplan el criterio en el estado")
        return 1
    dias: dict = {}
    salida = []
    for url, d in elegidas:
        vot = {
            "fecha": vr.fecha_fuente(d["f"]),
            "fecha_iso": d["f"],
            "sesion": d.get("s"),
            "numero": d.get("n"),
            "titulo": d["t"],
            "texto": d["a"],
            "json": url,
            "pdf": "",
            "dia": vr.DIA_URL.format(fecha=vr.fecha_dia(d["f"])),
            "expediente": "",
            "resultado": "",
            "votos": dict(sorted(vr.votos_de(d, nombres).items())),
        }
        if not sin_red:
            info = (json.loads(_get(url)).get("informacion") or {})
            texto = " ".join((info.get("textoExpediente") or "").split())
            if (info.get("fecha") or "").strip() != vot["fecha"] or texto != vot["texto"]:
                print(f"ERROR: el JSON oficial no coincide con el estado: {url}")
                print(f"  fecha {info.get('fecha')!r} / {vot['fecha']!r}")
                return 1
            if d["f"] not in dias:
                dias[d["f"]] = _get(vot["dia"])
            vot["pdf"], vot["expediente"] = del_dia(dias[d["f"]], url)
            if vot["expediente"]:
                vot["resultado"] = resultado_expediente(
                    _get(vr.EXPTE_URL.format(expte=vot["expediente"])))
        salida.append(vot)
    # Sustitutos: votaciones anteriores a su fecha de alta (la del censo del Congreso).
    censo = estado.get("censo") or {}
    for v in salida:
        v["antes_alta"] = sorted(k for k, c in censo.items()
                                 if k not in v["votos"] and vr.antes_del_alta(v["fecha_iso"], c.get("alta", "")))
    # Bajas: quien votó y ya no está en el censo. Circunscripción y fecha de baja
    # del fichero oficial de diputados de baja; si no está claro, no se atribuye.
    of = {"filas_bajas": [], "mujeres_xv": set(), "bajas": "", "diputadas": "", "pagina": ""}
    if not sin_red:
        of = diputados_oficiales()
    filas = {}
    for x in of["filas_bajas"]:
        filas.setdefault(cd.clave_nombre(x.get("NOMBRE") or ""), []).append(x)
    bajas, no_atribuidos = {}, []
    fuera = sorted({k for v in salida for k in v["votos"] if k not in censo})
    for k in fuera:
        vot_k = [v for v in salida if k in v["votos"]]
        fs = filas.get(k) or []
        motivo = ""
        if not fs:
            motivo = "no aparece en el fichero oficial de diputados de baja"
        elif len(fs) > 1:
            motivo = "aparece más de una vez en el fichero oficial de diputados de baja"
        else:
            x = fs[0]
            circ = (x.get("CIRCUNSCRIPCION") or "").strip()
            baja = (x.get("FECHABAJA") or "").strip()
            alta = (x.get("FECHAALTA") or "").strip()
            fb, fa = vr._fecha_ddmmaaaa(baja), vr._fecha_ddmmaaaa(alta)
            if not circ or not fb or not fa:
                motivo = "el fichero oficial no trae clara la circunscripción o las fechas"
            elif circ not in {c.get("circunscripcion") for c in censo.values()}:
                motivo = f"la circunscripción «{circ}» no casa con ninguna de las fichas"
            elif any(not (fa <= v["fecha_iso"] <= fb) for v in vot_k):
                motivo = "hay votos fuera de sus fechas oficiales de alta y de baja"
            else:
                bajas[k] = {"nombre": x["NOMBRE"].strip(), "natural": cd.nombre_natural(x["NOMBRE"].strip()),
                            "circunscripcion": circ, "alta": alta, "baja": baja, "fuente": of["bajas"]}
        if motivo:
            no_atribuidos.append({"clave": k, "motivo": motivo,
                                  "votaciones": [v["fecha"] for v in vot_k]})
    necesitan = set(bajas) | {k for v in salida for k in v["antes_alta"]}
    generos = {k: ("f" if k in of["mujeres_xv"] else "m") for k in sorted(necesitan)} if of["mujeres_xv"] else {}
    datos = {"criterio": vr.CRITERIO,
             "fuentes_diputados": {k: of[k] for k in ("pagina", "bajas", "diputadas")},
             "bajas": bajas, "no_atribuidos": no_atribuidos, "generos": generos,
             "fuente": "Datos abiertos del Congreso de los Diputados (detalle nominal de cada votación).",
             "votaciones": salida}
    vr.DATOS.write_text(json.dumps(datos, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                        encoding="utf-8")
    print(f"{vr.DATOS.relative_to(RAIZ)}: {len(salida)} votaciones")
    for v in salida:
        print(f"  {v['fecha']:>10}  {v['texto'][:40]}  votos={len(v['votos'])}  "
              f"pdf={'sí' if v['pdf'] else 'no'}  expte={v['expediente'] or '-'}  "
              f"resultado={v['resultado'] or '-'}")
    print("Bajas atribuidas:")
    for k, b in bajas.items():
        print(f"  {k}: {b['circunscripcion']}, baja {b['baja']} ({generos.get(k, '?')})")
    print("No atribuidos:", no_atribuidos or "ninguno")
    print("Aún no eran diputados:")
    for v in salida:
        for k in v["antes_alta"]:
            print(f"  {v['fecha']} {v['texto'][:28]}: {k} ({generos.get(k, '?')}, alta {censo[k].get('alta')})")
    print("Sin dato:")
    for v in salida:
        for k in sorted(set(censo) - set(v["votos"]) - set(v["antes_alta"])):
            print(f"  {v['fecha']} {v['texto'][:28]}: {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
