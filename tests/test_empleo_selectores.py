"""UX-2 (3): selectores de provincia y organismo arriba en /empleo/.
Son <details> con enlaces (funcionan sin JS) y van antes del listado. Sin red."""
import pathlib
import re
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))
import empleo as em  # noqa: E402
from test_empleo import TestPaginas, h_prueba  # noqa: E402


class TestSelectores(unittest.TestCase):
    setUp = TestPaginas.setUp
    tearDown = TestPaginas.tearDown

    def _cuerpo(self):
        h, _ = h_prueba(self.carpeta)
        em.generar_paginas(h, self.estado)
        return next(l for l in (self.carpeta / "index.html").read_text(encoding="utf-8").splitlines()
                    if l.startswith("CUERPO="))

    def test_antes_del_listado_y_sin_js(self):
        c = self._cuerpo()
        self.assertIn('<nav id="filtros"', c)
        self.assertLess(c.index('id="filtros"'), c.index('<h2 id="t-'))
        nav = c[c.index('<nav id="filtros"'):c.index("</nav>")]
        self.assertEqual(nav.count("<details"), 2)
        self.assertNotIn("<script", nav)
        self.assertNotIn("<select", nav)      # sin JS: enlaces, no un <select> que necesite onchange

    def test_enlazan_a_todas_las_paginas_existentes(self):
        c = self._cuerpo()
        nav = c[c.index('<nav id="filtros"'):c.index("</nav>")]
        enlaces = set(re.findall(r'href="([^"]+\.html)"', nav))
        paginas = {p.name for p in self.carpeta.glob("*.html")} - {"index.html"}
        self.assertEqual(enlaces, paginas)
        prov = {e for e in enlaces if e.startswith("provincia-")}
        self.assertTrue(prov)
        self.assertTrue(enlaces - prov)
        self.assertIn('class="em-sel em-sel-prov"', nav)
        self.assertIn('class="em-sel em-sel-org"', nav)

    def test_sin_datos_sin_selectores(self):
        self.assertEqual(em.selectores([], []), "")


class TestCSS(unittest.TestCase):
    def test_panel_ancho_no_desborda_en_la_franja_intermedia(self):
        css = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")
        self.assertIn(".em-filtros", css)
        self.assertRegex(css, r"@media \(min-width:721px\) and \(max-width:1240px\)\{[^}]*\.nav-pilares\{ position:relative; \}")


if __name__ == "__main__":
    unittest.main()
