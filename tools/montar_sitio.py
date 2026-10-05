#!/usr/bin/env python3
"""
Monta _site/ con SOLO lo publicable, para subirlo como artefacto de GitHub Pages.

La lista sale de tools/publicables.txt (el único sitio donde se declara qué se
publica). Este script la usa publicar.yml; tools/verificar.py lee la misma
lista con leer_publicables().

Antes de dar el sitio por bueno comprueba:
  - que están todas las entradas obligatorias (marcadas con «!»);
  - que CNAME sigue siendo terceracamara.es (si no, Pages perdería el dominio);
  - que el total no pasa del límite de GitHub Pages (1 GB).
Si algo falla, sale con código 1 y publicar.yml no despliega.

Uso:
    python tools/montar_sitio.py [--raiz .] [--destino _site]
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import pathlib
import shutil
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
LISTA = pathlib.Path(__file__).resolve().parent / "publicables.txt"

DOMINIO = "terceracamara.es"
# Límite de tamaño del sitio publicado en GitHub Pages; el aviso deja margen.
LIMITE_PAGES_BYTES = 1024 ** 3
AVISO_PAGES_BYTES = 800 * 1024 ** 2


def leer_publicables(lista: pathlib.Path | None = None) -> list[tuple[str, bool]]:
    """[(patrón, obligatorio)] de tools/publicables.txt."""
    salida = []
    for linea in (lista or LISTA).read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        obligatorio = linea.startswith("!")
        salida.append((linea.lstrip("!").strip().rstrip("/"), obligatorio))
    return salida


def resolver(raiz: pathlib.Path, patron: str) -> list[pathlib.Path]:
    """Rutas de primer nivel (o con subcarpeta explícita) que casan con el patrón."""
    if any(c in patron for c in "*?["):
        padre = raiz / os.path.dirname(patron)
        if not padre.is_dir():
            return []
        return sorted(p for p in padre.iterdir()
                      if fnmatch.fnmatch(p.name, os.path.basename(patron)))
    p = raiz / patron
    return [p] if p.exists() else []


def cubre(patrones: list[str], nombre: str) -> bool:
    """¿Alguna entrada de la lista publica la ruta de primer nivel `nombre`?"""
    return any(fnmatch.fnmatch(nombre, p.split("/")[0]) for p in patrones)


def tamano(ruta: pathlib.Path) -> tuple[int, int]:
    """(ficheros, bytes) de un fichero o carpeta."""
    if ruta.is_file():
        return 1, ruta.stat().st_size
    n = b = 0
    for actual, _dirs, ficheros in os.walk(ruta):
        for f in ficheros:
            n += 1
            b += os.path.getsize(os.path.join(actual, f))
    return n, b


def montar(raiz: pathlib.Path, destino: pathlib.Path) -> tuple[list[str], dict]:
    """Copia lo publicable a `destino`. Devuelve (problemas, resumen)."""
    problemas: list[str] = []
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True)
    copiadas = 0
    for patron, obligatorio in leer_publicables():
        rutas = resolver(raiz, patron)
        if not rutas:
            if obligatorio:
                problemas.append(f"Falta «{patron}», que es obligatorio.")
            continue
        for r in rutas:
            rel = r.relative_to(raiz)
            (destino / rel).parent.mkdir(parents=True, exist_ok=True)
            if r.is_dir():
                shutil.copytree(r, destino / rel, dirs_exist_ok=True)
            else:
                shutil.copy2(r, destino / rel)
            copiadas += 1
    cname = destino / "CNAME"
    if cname.exists() and cname.read_text(encoding="utf-8").strip() != DOMINIO:
        problemas.append(f"CNAME dice «{cname.read_text(encoding='utf-8').strip()}» y no {DOMINIO}.")
    n, b = tamano(destino)
    if b >= LIMITE_PAGES_BYTES:
        problemas.append(f"_site ocupa {b / 1024 ** 2:.0f} MiB: pasa del límite de Pages (1 GB).")
    raiz_sitio = sorted(p.name + ("/" if p.is_dir() else "") for p in destino.iterdir())
    resumen = {"entradas": copiadas, "ficheros": n, "bytes": b,
               "aviso": b >= AVISO_PAGES_BYTES, "raiz": raiz_sitio}
    return problemas, resumen


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Monta _site/ con lo publicable.")
    ap.add_argument("--raiz", default=str(RAIZ))
    ap.add_argument("--destino", default=str(RAIZ / "_site"))
    args = ap.parse_args(argv)
    problemas, r = montar(pathlib.Path(args.raiz).resolve(), pathlib.Path(args.destino).resolve())
    texto = (f"### Sitio montado\n\n{r['entradas']} entradas, {r['ficheros']} ficheros, "
             f"**{r['bytes'] / 1024 ** 2:.1f} MiB** (límite de Pages: 1 GB).\n")
    texto += "\nRaíz de `_site`: " + ", ".join(f"`{x}`" for x in r["raiz"]) + "\n"
    if r["aviso"]:
        texto += "\n⚠️ Pasa de 800 MiB: aplica las salidas de ARQUITECTURA.md §7.\n"
    for p in problemas:
        texto += f"\n- ❌ {p}"
    print(texto)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(texto + "\n")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
