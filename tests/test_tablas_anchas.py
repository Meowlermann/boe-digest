"""Las tablas anchas van dentro de un contenedor con scroll horizontal: un
overflow-x puesto en la propia <table> no evita que la página se ensanche en móvil."""
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


class TablasAnchas(unittest.TestCase):
    def test_tablas_de_provincias_en_contenedor(self):
        src = (RAIZ / "provincias.py").read_text(encoding="utf-8")
        tablas = [m.start() for m in re.finditer(r"<table class=", src)]
        self.assertTrue(tablas)
        for i in tablas:
            antes = src[max(0, i - 40):i]
            self.assertIn('<div class="tabla-ancha">', antes, src[i:i + 60])

    def test_rk_tabla_es_contenedor_en_rankings(self):
        src = (RAIZ / "rankings.py").read_text(encoding="utf-8")
        self.assertNotIn('<table class="rk-tabla"', src)

    def test_css_contenedor(self):
        css = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.tabla-ancha\{[^}]*overflow-x:auto")


if __name__ == "__main__":
    unittest.main()
