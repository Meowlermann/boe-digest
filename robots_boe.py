"""Respeto al robots.txt del BOE (TC-023).

Antes de cada petición a www.boe.es, build.get() pregunta a permitido(). Las
reglas salen del robots.txt vivo (se descarga una vez por ejecución) y, si no
se puede descargar, del extracto commiteado en tools/robots_boe.txt.

urllib.robotparser no sirve: no entiende los comodines «*» ni el ancla «$»
que usa el BOE (p. ej. «Disallow: /*BOE-A-2026-4920$»). Aquí se aplica la
semántica de RFC 9309: gana la regla más larga que encaja y, a igual
longitud, Allow.

Para actualizar el extracto (cuando el BOE cambie su robots.txt):
    python robots_boe.py --actualizar
Guarda solo las reglas del grupo «User-agent: *» que afectan a las rutas que
lee el recolector (RUTAS_LEIDAS) y, para las que llevan año, las de
AÑO_MINIMO en adelante: el archivo empieza en 2026. Todo con requests, sin
dependencias nuevas.
"""

from __future__ import annotations

import pathlib
import re
import sys
from urllib.parse import urlsplit

URL_ROBOTS = "https://www.boe.es/robots.txt"
EXTRACTO = pathlib.Path(__file__).resolve().parent / "tools" / "robots_boe.txt"
# Prefijos de las rutas que lee el recolector (y las que dejó de leer, para que
# la comprobación del CI pueda demostrar que están excluidas).
RUTAS_LEIDAS = ("/datosabiertos/", "/diario_boe/txt.php", "/diario_boe/xml.php", "/boe/dias/")
AÑO_MINIMO = 2025

_reglas: list[tuple[bool, str, re.Pattern]] | None = None
origen = ""


def parsear(texto: str) -> list[tuple[bool, str, re.Pattern]]:
    """Reglas (permite, patrón, regex) de los grupos que aplican a «*»."""
    reglas, en_grupo, agentes_previos = [], False, False
    for linea in texto.splitlines():
        linea = linea.split("#", 1)[0].strip()
        if ":" not in linea:
            continue
        campo, valor = (x.strip() for x in linea.split(":", 1))
        campo = campo.lower()
        if campo == "user-agent":
            if not agentes_previos:
                en_grupo = False
            agentes_previos = True
            en_grupo = en_grupo or valor == "*"
            continue
        agentes_previos = False
        if campo in ("allow", "disallow") and en_grupo and valor:
            rx = re.escape(valor).replace(r"\*", ".*")
            if rx.endswith(r"\$"):
                rx = rx[:-2] + "$"
            reglas.append((campo == "allow", valor, re.compile(rx)))
    return reglas


def permitido_con(url: str, reglas) -> bool:
    partes = urlsplit(url)
    ruta = (partes.path or "/") + (f"?{partes.query}" if partes.query else "")
    mejor, permite = -1, True
    for allow, patron, rx in reglas:
        if rx.match(ruta):
            largo = len(patron)
            if largo > mejor or (largo == mejor and allow):
                mejor, permite = largo, allow
    return permite


def cargar(texto: str | None = None, desde: str = "") -> None:
    global _reglas, origen
    if texto is None:
        texto, desde = EXTRACTO.read_text(encoding="utf-8"), "extracto commiteado"
    _reglas, origen = parsear(texto), desde


def permitido(url: str) -> bool:
    if _reglas is None:
        cargar()
    return permitido_con(url, _reglas)


def reducir(texto: str) -> str:
    """Extracto: cabecera + reglas de «*» sobre RUTAS_LEIDAS o con comodín inicial,
    descartando las de años anteriores a AÑO_MINIMO."""
    salida = ["# Extracto del robots.txt de https://www.boe.es (grupo User-agent: *).",
              "# Generado por «python robots_boe.py --actualizar»; no editar a mano.",
              f"# Rutas: {', '.join(RUTAS_LEIDAS)} y reglas «/*…»; años >= {AÑO_MINIMO}.",
              "User-agent: *"]
    for allow, patron, _ in parsear(texto):
        if not (patron.startswith(RUTAS_LEIDAS) or patron.startswith("/*")):
            continue
        años = [int(a) for a in re.findall(r"(?<!\d)(19\d\d|20\d\d)(?!\d)", patron)]
        if años and max(años) < AÑO_MINIMO:
            continue
        salida.append(f"{'Allow' if allow else 'Disallow'}: {patron}")
    return "\n".join(salida) + "\n"


if __name__ == "__main__":
    if "--actualizar" in sys.argv:
        import requests
        r = requests.get(URL_ROBOTS, timeout=30)
        r.raise_for_status()
        EXTRACTO.write_text(reducir(r.text), encoding="utf-8")
        print(f"{EXTRACTO}: {len(EXTRACTO.read_text(encoding='utf-8').splitlines())} líneas")
    else:
        for u in sys.argv[1:]:
            print(("permitido " if permitido(u) else "EXCLUIDO  ") + u)
