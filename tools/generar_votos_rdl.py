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
3. Escribe la copia (claves ordenadas, sin fecha de generación: misma entrada,
   mismo fichero) y lista los cruces dudosos: nombres del listado sin ficha en
   el censo actual y diputados del censo sin voto en alguna votación.
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
    datos = {"criterio": vr.CRITERIO,
             "fuente": "Datos abiertos del Congreso de los Diputados (detalle nominal de cada votación).",
             "votaciones": salida}
    vr.DATOS.write_text(json.dumps(datos, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                        encoding="utf-8")
    print(f"{vr.DATOS.relative_to(RAIZ)}: {len(salida)} votaciones")
    for v in salida:
        print(f"  {v['fecha']:>10}  {v['texto'][:40]}  votos={len(v['votos'])}  "
              f"pdf={'sí' if v['pdf'] else 'no'}  expte={v['expediente'] or '-'}  "
              f"resultado={v['resultado'] or '-'}")
    # Cruces dudosos
    censo = estado.get("censo") or {}
    print("Cruces dudosos:")
    for v in salida:
        fuera = sorted(k for k in v["votos"] if k not in censo)
        faltan = sorted(k for k in censo if k not in v["votos"])
        if fuera or faltan:
            print(f"  {v['fecha']} {v['texto'][:28]}")
            for k in fuera:
                print(f"    vota sin ficha en el censo actual (no se atribuye): {k} [{v['votos'][k]}]")
            for k in faltan:
                c = censo[k]
                print(f"    sin dato: {k} ({c.get('circunscripcion')}, alta {c.get('alta')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
