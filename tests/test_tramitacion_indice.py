"""/tramitacion/: el CSS del índice no subraya y el índice usa su diseño propio."""
import pathlib
import re
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def bloque_css() -> str:
    css = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")
    a = css.index("/* --- /tramitacion/ (índice")
    b = css.index("/* --- fin /tramitacion/", a)
    return css[a:b]


class IndiceTramitacion(unittest.TestCase):
    def test_sin_subrayado(self):
        css = re.sub(r"/\*.*?\*/", "", bloque_css(), flags=re.S)
        self.assertNotIn("underline", css)
        self.assertIn("body:has(.tr-ix) .miga a{border-bottom:0;text-decoration:none", css)
        self.assertIn("body:has(.tr-ix) a{text-decoration:none}", css)

    def test_foco_visible(self):
        self.assertIn("a:focus-visible{outline:3px solid", bloque_css())

    def test_selectores_acotados(self):
        css = re.sub(r"/\*.*?\*/", "", bloque_css(), flags=re.S)
        css = re.sub(r"@media[^{]*\{", "", css)
        for sel in re.findall(r"([^{}]+)\{", css):
            for parte in sel.split(","):
                parte = parte.strip()
                if parte:
                    self.assertTrue(parte.startswith((".tr-ix", "body:has(.tr-ix)")), parte)

    def test_indice_usa_el_diseno(self):
        src = (RAIZ / "tramitacion.py").read_text(encoding="utf-8")
        for c in ('class="tr-ix"', "tr-ix-estados", "tr-ix-movs", "tr-ix-tabla", "tr-ix-lado"):
            self.assertIn(c, src)


if __name__ == "__main__":
    unittest.main()
