"""Listado completo de diputados en el HTML de /diputados/, sin JS. Sin red."""
import pathlib
import re
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import build  # noqa: E402

FICHAS = [
    {"natural": "Álvaro Ruiz", "slug": "alvaro-ruiz", "sigla": "PP",
     "circunscripcion": "Ávila", "partido": "PP"},
    {"natural": "Ana Pérez", "slug": "ana-perez", "sigla": "PSOE",
     "circunscripcion": "Murcia", "partido": "PSOE"},
    {"natural": "Beatriz Sol", "slug": "beatriz-sol", "sigla": "Sumar",
     "circunscripcion": "Madrid", "partido": "Sumar"},
]


class Listado(unittest.TestCase):
    def setUp(self):
        self.h = build.lista_completa_diputados(FICHAS)

    def test_enlace_a_cada_ficha(self):
        for f in FICHAS:
            self.assertIn(f'href="{f["slug"]}.html"', self.h)
            self.assertIn(f["natural"], self.h)
        self.assertEqual(self.h.count("<li>"), len(FICHAS))
        self.assertIn('id="todos"', self.h)
        self.assertIn("Los 3 diputados", self.h)
        self.assertNotIn("<script", self.h)

    def test_orden_alfabetico(self):
        pos = [self.h.index(f'href="{f["slug"]}.html"') for f in FICHAS]
        # Álvaro (sin tilde: alvaro), Ana, Beatriz.
        self.assertEqual(pos, sorted(pos))

    def test_grupo_y_circunscripcion(self):
        self.assertIn("PP · Ávila", self.h)
        self.assertIn("PSOE · Murcia", self.h)

    def test_vacio(self):
        self.assertEqual(build.lista_completa_diputados([]), "")

    def test_en_el_indice_y_en_el_buscador(self):
        src = (RAIZ / "build.py").read_text(encoding="utf-8")
        self.assertEqual(src.count("lista_completa_diputados(fichas)"), 1)
        self.assertIn('href="#todos"', src)
        self.assertIn("Los {len(fichas)} diputados, uno a uno", src)
        # Title, description y canonical del índice no se tocan (prueba #75).
        self.assertIn(
            '"TITLE": "Así vota y así trabaja cada diputado | La Tercera Cámara"', src)
        self.assertIn(
            '"META_DESC": esc_attr("Los 350 diputados del Congreso, uno a uno: intervenciones, "',
            src)
        self.assertIn('"CANONICAL": url,', src)

    def test_css_sin_subrayado_ni_tarjetas(self):
        css = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")
        bloque = css.split("/* --- /diputados/ listado completo")[1].split(
            "/* --- fin /diputados/ listado completo")[0]
        self.assertNotIn("underline", bloque)
        self.assertNotIn("gradient", bloque)
        self.assertNotIn("box-shadow", bloque)
        self.assertNotIn("border-radius", bloque)
        self.assertIn("text-decoration:none", bloque)
        self.assertIn(":focus-visible", bloque)
        self.assertIn("column-count:2", bloque)


if __name__ == "__main__":
    unittest.main()
