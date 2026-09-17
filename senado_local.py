#!/usr/bin/env python3
"""
Recolector del Senado para ejecutar EN TU ORDENADOR.

Por qué existe: el Senado sirve su web detrás de Akamai y bloquea en el edge las
peticiones que llegan desde rangos de centro de datos, así que GitHub Actions
recibe siempre un 403. Desde una conexión doméstica normal sí responde.

Este script descarga el boletín del Senado del día, lo convierte en artículos y
escribe (o completa) curated/AAAA-MM-DD.json con la clave "feed_append", que el
pipeline añade a lo que ya haya recolectado del Congreso, sin pisarlo.

No es un runner de GitHub Actions a propósito: un runner self-hosted en un
repositorio público permitiría a cualquiera ejecutar código en tu máquina a
través de un pull request. Esto es un script tuyo, que corre cuando tú decides.

Uso:
    python senado_local.py                 # boletín de hoy -> curated/
    python senado_local.py --date 2026-09-18
    python senado_local.py --push          # además, commit y push

Para dejarlo automático en tu equipo:
    macOS   -> launchd, o  crontab -e:  10 8 * * 1-5  cd /ruta/boe-digest && /usr/bin/python3 senado_local.py --push
    Windows -> Programador de tareas, acción: python senado_local.py --push
    Linux   -> crontab -e, misma línea que macOS
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys

import build   # reutilizamos el motor del pipeline

ROOT = pathlib.Path(__file__).parent
CURATED = ROOT / "curated"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="fecha AAAA-MM-DD (por defecto, hoy)")
    ap.add_argument("--push", action="store_true", help="hacer commit y push al terminar")
    args = ap.parse_args()

    fecha = dt.date.fromisoformat(args.date) if args.date else dt.date.today()

    print(f"Buscando el boletín del Senado para {fecha.isoformat()}…")
    docs = build.fetch_senado()
    if not docs:
        print("\nNo se ha podido descargar ningún boletín del Senado.")
        print("Si esto ocurre desde tu propia conexión, revisa que www.senado.es")
        print("responda en el navegador: puede que hayan cambiado la numeración.")
        return 1

    cortes = build.redactar_cortes(docs, None)
    articulos = cortes.get("feed", [])
    if not articulos:
        print("Se descargó el boletín pero no se generó ningún artículo.")
        return 1

    CURATED.mkdir(exist_ok=True)
    destino = CURATED / f"{fecha.isoformat()}.json"

    actual: dict = {}
    if destino.exists():
        try:
            actual = json.loads(destino.read_text(encoding="utf-8"))
        except Exception as exc:                              # noqa: BLE001
            print(f"Aviso: {destino.name} no se pudo leer ({exc}); se reescribe.")
            actual = {}

    actual.setdefault("cortes", {})
    previos = actual["cortes"].get("feed_append", [])
    titulares = {a.get("headline") for a in previos}
    nuevos = [a for a in articulos if a.get("headline") not in titulares]
    actual["cortes"]["feed_append"] = previos + nuevos

    destino.write_text(json.dumps(actual, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nEscrito {destino.relative_to(ROOT)} con {len(nuevos)} artículo(s) del Senado:")
    for a in nuevos:
        print(f"  - {a['headline'][:80]}")

    if args.push:
        try:
            subprocess.run(["git", "add", str(destino)], cwd=ROOT, check=True)
            subprocess.run(["git", "commit", "-m",
                            f"Senado: boletín del {fecha.isoformat()}"], cwd=ROOT, check=True)
            subprocess.run(["git", "push"], cwd=ROOT, check=True)
            print("\nSubido. La próxima ejecución del workflow lo incorporará al sitio.")
        except subprocess.CalledProcessError as exc:
            print(f"\nNo se pudo hacer push ({exc}). El fichero está escrito; súbelo a mano.")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
