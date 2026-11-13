"""Genera curated/elecciones_2026.json desde el BOE (tanda E2).

Lee tres documentos del BOE (txt.php, permitido por su robots.txt) y aplica
el parser determinista de elecciones.py:

  BOE-A-2026-20742  Real Decreto 806/2026 (fecha y escaños por circunscripción)
  BOE-A-2026-23103  candidaturas proclamadas
  BOE-A-2026-23383  corrección de errores de las candidaturas

Uso:
  python tools/elecciones_2026.py               # descarga del BOE
  python tools/elecciones_2026.py --dir CARPETA # usa CARPETA/<id>.html ya bajados

Es una copia fija: las candidaturas ya están proclamadas y no cambian salvo
otra corrección en el BOE. Si sale una, se añade su id aquí y en elecciones.py
y se vuelve a generar. El render no usa la red: lee el JSON.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import elecciones as el  # noqa: E402


def leer(ident: str, carpeta: pathlib.Path | None) -> str:
    if carpeta:
        return (carpeta / f"{ident}.html").read_text(encoding="utf-8")
    import build
    r = build.get(el.url_boe(ident))
    if r is None or r.status_code != 200:
        raise SystemExit(f"No se pudo descargar {ident} del BOE; no se genera nada.")
    time.sleep(1)
    r.encoding = "utf-8"
    return r.text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=pathlib.Path)
    args = ap.parse_args()
    html = {i: leer(i, args.dir) for i in (el.ID_RD, el.ID_CANDIDATURAS, el.ID_CORRECCION)}
    datos = el.construir(html[el.ID_RD], html[el.ID_CANDIDATURAS], html[el.ID_CORRECCION])
    texto = json.dumps(datos, ensure_ascii=False, separators=(",", ":"))
    el.DATOS.write_text(texto + "\n", encoding="utf-8")
    circs = datos["circunscripciones"]
    print(f"{el.DATOS.relative_to(RAIZ)}: {len(circs)} circunscripciones, "
          f"{sum(c['escanos'] for c in circs)} escaños, "
          f"{sum(len(c['candidaturas']) for c in circs)} candidaturas al Congreso "
          f"({sum(1 for c in circs for k in c['candidaturas'] if not k['proclamada'])} no proclamadas), "
          f"{len(texto) // 1024} KB")
    for c in datos["correcciones_congreso"]:
        print(f"  corrección {c['junta']}: {c['estado']}")
    for a in el.anomalias(datos):
        print(f"  AVISO {a}")


if __name__ == "__main__":
    main()
