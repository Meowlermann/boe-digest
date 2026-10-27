"""Tabla Markdown con las puntuaciones de Lighthouse CI (TC-008).

Lee lhci-informe/manifest.json (lo escribe `lhci upload --target=filesystem`)
y saca, por URL, la ejecución representativa (mediana). Emite avisos de
GitHub Actions si Rendimiento o Accesibilidad bajan de 90. Sin dependencias.
"""
from __future__ import annotations

import json
import pathlib
import sys

UMBRAL = 90
CATEGORIAS = ("performance", "accessibility", "best-practices", "seo")
NOMBRES = {"performance": "Rend.", "accessibility": "Acces.", "best-practices": "Buenas pr.", "seo": "SEO"}


def resumen(carpeta: pathlib.Path) -> tuple[str, list[str]]:
    manifiesto = carpeta / "manifest.json"
    if not manifiesto.is_file():
        return "Lighthouse: no hay manifest.json (la medición falló).\n", ["Lighthouse: sin resultados"]
    filas = [e for e in json.loads(manifiesto.read_text(encoding="utf-8")) if e.get("isRepresentativeRun")]
    lineas = ["### Lighthouse (mediana de 3 pasadas)", "",
              "| URL | " + " | ".join(NOMBRES[c] for c in CATEGORIAS) + " |",
              "|---|" + "---|" * len(CATEGORIAS)]
    avisos: list[str] = []
    for e in sorted(filas, key=lambda e: e["url"]):
        puntos = {c: round(100 * (e["summary"].get(c) or 0)) for c in CATEGORIAS}
        lineas.append(f"| {e['url']} | " + " | ".join(str(puntos[c]) for c in CATEGORIAS) + " |")
        for c in ("performance", "accessibility"):
            if puntos[c] < UMBRAL:
                avisos.append(f"{NOMBRES[c]} {puntos[c]} < {UMBRAL} en {e['url']}")
    return "\n".join(lineas) + "\n", avisos


def main(argv: list[str]) -> int:
    texto, avisos = resumen(pathlib.Path(argv[1] if len(argv) > 1 else "lhci-informe"))
    print(texto)
    for a in avisos:
        print(f"::warning::{a}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
