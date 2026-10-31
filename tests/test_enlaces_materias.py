"""Enlaces contextuales a las páginas de materia: fila «Materias» en la ficha
de cada norma y línea «Por materias» en el pie de la portada. Sin red."""
import pathlib
import re
import sys
import unittest

RAIZ_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_REPO))

import build  # noqa: E402


class TestEnlacesMaterias(unittest.TestCase):
    def test_ficha_enlaza_sus_materias_sin_repetir(self):
        s = {"headline": "Orden", "titulo_oficial": "Orden por la que se convocan subvenciones para la contratación laboral y ayudas al empleo"}
        h = build.materias_enlaces(s)
        self.assertTrue(h.startswith("<dt>Materias</dt>"))
        hrefs = re.findall(r'href="([^"]+)"', h)
        self.assertIn("../temas/subvenciones.html", hrefs)
        self.assertEqual(len(hrefs), len(set(hrefs)))
        for x in hrefs:
            self.assertRegex(x, r"^\.\./temas/[a-z-]+\.html$")

    def test_ficha_vacia_sin_materia(self):
        self.assertEqual(build.materias_enlaces({"headline": "", "titulo_oficial": ""}), "")

    def test_pie_las_17_una_vez(self):
        h = build.pie_materias()
        hrefs = re.findall(r'href="([^"]+)"', h)
        self.assertEqual(len(hrefs), len(build.MATERIAS))
        self.assertEqual(len(hrefs), len(set(hrefs)))
        self.assertNotIn('href="temas/"', h)   # el índice ya está en el pie
        self.assertIn('aria-label="Materias"', h)

    def test_plantilla_lleva_el_hueco(self):
        self.assertIn("__SSR_PIE_MATERIAS__", (RAIZ_REPO / "template.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
