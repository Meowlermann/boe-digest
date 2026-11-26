#!/usr/bin/env python3
"""Genera curated/resultados_29n.json desde la proclamación de la JEC en el BOE.

Uso, en local y a mano (no lo llama ningún cron):

    python3 tools/generar_resultados_29n.py --id BOE-A-AAAA-NNNNN            # solo informa
    python3 tools/generar_resultados_29n.py --id BOE-A-AAAA-NNNNN --escribir # y escribe

Comprueba que el documento es la resolución de la Junta Electoral Central con
el resumen de resultados de las elecciones convocadas por el Real Decreto
806/2026; si no, para. Lee los cuadros de votos del XML y la relación de
diputados electos del PDF (pdftotext, de poppler). Las circunscripciones que no
cuadran quedan fuera y se listan; nada se completa a mano ni desde otra web.
Sin dependencias nuevas: urllib y pdftotext.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import urllib.request

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import resultados_29n as rs  # noqa: E402

UA = {"User-Agent": "TerceraCamara/1.0 (+https://terceracamara.es; contacto@terceracamara.es)"}
CONVOCATORIA = "Real Decreto 806/2026"


def _get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()


def comprobar_documento(xml: str) -> tuple[str, str]:
    """(título, literal «BOE núm. N, de dd/mm/aaaa»), o ValueError si no es la
    resolución que buscamos."""
    m = re.search(r"<titulo>(.*?)</titulo>", xml, re.S)
    titulo = rs._limpio(m.group(1)) if m else ""
    if not ("Junta Electoral Central" in titulo and "resumen de los resultados" in titulo
            and CONVOCATORIA in titulo):
        raise ValueError(f"no es la proclamación de la JEC de las elecciones del {CONVOCATORIA}: «{titulo}»")
    num = re.search(r"<diario_numero>(\d+)</diario_numero>", xml)
    fec = re.search(r"<fecha_publicacion>(\d{8})</fecha_publicacion>", xml)
    if not (num and fec):
        raise ValueError("faltan número o fecha del diario en el XML")
    f = fec.group(1)
    return titulo, f"BOE núm. {num.group(1)}, de {f[6:8]}/{f[4:6]}/{f[:4]}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True, help="identificador BOE-A-… de la resolución de la JEC")
    ap.add_argument("--escribir", action="store_true")
    a = ap.parse_args()
    if not re.fullmatch(r"BOE-A-\d{4}-\d+", a.id):
        print("identificador no válido", file=sys.stderr)
        return 2
    xml = _get(f"https://www.boe.es/diario_boe/xml.php?id={a.id}").decode("utf-8")
    titulo, literal = comprobar_documento(xml)
    pdf_rel = re.search(r"<url_pdf>(.*?)</url_pdf>", xml)
    if not pdf_rel:
        print("el XML no enlaza el PDF", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        pdf = pathlib.Path(tmp) / "jec.pdf"
        pdf.write_bytes(_get("https://www.boe.es" + pdf_rel.group(1).strip()))
        txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], check=True,
                             capture_output=True, text=True).stdout
    import elecciones as el
    circs = [c["circunscripcion"] for c in el.cargar()["circunscripciones"]]
    datos = rs.construir(xml, txt, {"id": a.id, "titulo": titulo, "literal": literal}, circs)
    print(f"{len(datos['circunscripciones'])} circunscripciones listas; {len(datos['excluidas'])} fuera")
    for c, motivo in datos["excluidas"].items():
        print(f"  fuera: {c}: {motivo}")
    for av in datos["avisos"]:
        print(f"  aviso: {av}")
    err = rs.validar(datos)
    if err:
        print("no válido:", *err, sep="\n  ", file=sys.stderr)
        return 1
    if a.escribir:
        datos.pop("avisos", None)
        rs.DATOS.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"escrito {rs.DATOS.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
