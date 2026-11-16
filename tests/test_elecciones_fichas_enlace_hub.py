"""Tras poner al día #112 con main: las 52 fichas de provincia siguen diciendo
«Candidaturas en las 52 circunscripciones →» (enlace al hub de #110). Sin red.
El espacio antes de → puede ser duro (&nbsp;): se normaliza."""
import pathlib
import re
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import build  # noqa: E402
import elecciones as el  # noqa: E402

TEXTO = "Candidaturas en las 52 circunscripciones →"


def normaliza(h: str) -> str:
    return h.replace("&nbsp;", " ").replace("\u00a0", " ")


class EnlaceAlHubEnLas52(unittest.TestCase):
    def test_bloque_de_cada_circunscripcion(self):
        datos = el.cargar()
        if not datos:
            self.skipTest("sin curated/elecciones_2026.json")
        self.assertEqual(len(datos["circunscripciones"]), 52)
        for c in datos["circunscripciones"]:
            cc = el.circ_congreso(c["circunscripcion"])
            h = normaliza(el.bloque_ficha(datos, c["circunscripcion"], [], cc, "x", []))
            self.assertIn(TEXTO, h, cc)
            self.assertRegex(h, r'<a [^>]*href="/elecciones/2026/"[^>]*>Candidaturas en las 52 circunscripciones →</a>')

    def test_fichas_pintadas(self):
        fichas = sorted((RAIZ / "diputados").glob("provincia-*.html"))
        if not fichas:
            self.skipTest("fichas de provincia sin pintar (build.py --render)")
        self.assertEqual(len(fichas), 52)
        for f in fichas:
            self.assertIn(TEXTO, normaliza(f.read_text(encoding="utf-8")), f.name)


if __name__ == "__main__":
    unittest.main()
