"""Nombres populares y títulos cortos.

Los textos oficiales no usan los nombres con los que se conocen las cosas:
nadie en el BOE escribe «Verifactu» ni «ley mordaza», y quien busca eso en el
sitio no encontraba nada. curated/nombres_populares.json, editado a mano, dice
qué nombre popular corresponde a qué palabras oficiales; el buscador lo añade
al texto buscable de las entradas que las contienen. No se muestra en ninguna
página, solo sirve para encontrar.

También da títulos cortos para las iniciativas cuyo título oficial es una
frase de sesenta palabras. Si no hay uno escrito a mano, tramitacion.py recorta
el oficial con reglas fijas (titulo_corto). Todo determinista: sin modelos.
"""

from __future__ import annotations

import json
import pathlib
import re
import unicodedata

FICHERO = pathlib.Path(__file__).parent / "curated" / "nombres_populares.json"
_CACHE: dict = {}
_VACIAS = {"de", "del", "la", "las", "el", "los", "y", "e", "o", "u", "a", "en", "por",
           "para", "con", "que", "se", "sus", "su", "al"}


def _tokens(texto: str) -> set[str]:
    base = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return {t for t in re.findall(r"[a-z0-9/]+", base) if t not in _VACIAS}


def cargar() -> dict:
    if not _CACHE:
        try:
            datos = json.loads(FICHERO.read_text(encoding="utf-8"))
        except Exception:                                     # noqa: BLE001
            datos = {}
        reglas = []
        for a in datos.get("alias") or []:
            frases = [_tokens(f) for f in a.get("si_contiene") or []]
            reglas.append((" ".join([a["nombre"], *a.get("variantes", [])]), [f for f in frases if f]))
        _CACHE.update({"reglas": reglas, "cortos": datos.get("cortos") or {}})
    return _CACHE


def alias_para(texto: str) -> list[str]:
    """Nombres populares que corresponden a un texto: los de las reglas en las
    que alguna frase aparece entera (todas sus palabras, en cualquier orden)."""
    tok = _tokens(texto)
    return [nombres for nombres, frases in cargar()["reglas"]
            if any(f <= tok for f in frases)]


def corto(clave: str) -> str | None:
    """Título corto escrito a mano para una iniciativa (clave: expediente)."""
    return cargar()["cortos"].get(clave)
