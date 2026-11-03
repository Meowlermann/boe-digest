"""/empleo/: mismo lenguaje que /tramitacion/ y /seguimiento/, sin subrayados,
acotado, y sin perder los carriles (PR #66)."""
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CSS = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")
INI, FIN = "/* --- /empleo/ (reutiliza", "/* --- fin /empleo/"


def bloque() -> str:
    return CSS[CSS.index(INI):CSS.index(FIN)]


class EmpleoIndice(unittest.TestCase):
    def test_sin_subrayado(self):
        self.assertNotIn("underline", bloque())

    def test_reutiliza_tr_ix(self):
        self.assertIn("body:has(.tr-ix) a{text-decoration:none}", CSS)
        self.assertIn("body:has(.tr-ix) a:focus-visible{outline:3px", CSS)
        self.assertIn("body:has(.tr-ix) .miga a{border-bottom:0", CSS)
        self.assertIn("box-shadow:inset 0 -2px 0 var(--red)", bloque())

    def test_rss_y_pie_acotados(self):
        self.assertIn("body:has(.tr-ix-em) .seguir-rss a{border-bottom:0", bloque())
        self.assertIn("body:has(.tr-ix-em) footer a", bloque())

    def test_selectores_acotados(self):
        cuerpo = re.sub(r"/\*.*?\*/", "", bloque(), flags=re.S)
        for sel in re.findall(r"([^{}@]+)\{[^{}]*\}", cuerpo):
            for s in sel.split(","):
                s = s.strip()
                if s:
                    self.assertTrue(s.startswith((".tr-ix", "body:has(.tr-ix")), s)

    def test_empleo_usa_clases_y_conserva_carriles(self):
        src = (RAIZ / "empleo.py").read_text(encoding="utf-8")
        for c in ("tr-ix tr-ix-em", "tr-ix-resumen", "tr-ix-cifras", "tr-ix-lado", "tr-ix-em-dos",
                  'id="organismos"', 'id="provincias"',
                  # Carriles de PR #66 y filtros: intactos.
                  "em-carril", "em-pista", "em-ant", "em-sig", "em-vertodos", "em-carril-nav",
                  "em-tab", "em-dias", 'id="filtros"', "em-sel-{clase}"):
            self.assertIn(c, src, c)
        js = (RAIZ / "assets" / "empleo.js").read_text(encoding="utf-8")
        for c in ("hashchange", "em-pista-todo", "em-vertodos", "tipo="):
            self.assertIn(c, js, c)


if __name__ == "__main__":
    unittest.main()
