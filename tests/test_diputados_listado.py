"""Listado completo de diputados en el HTML de /diputados/, sin JS. Sin red."""
import pathlib
import re
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import build  # noqa: E402

FICHAS = [
    {"nombre": "Ruiz, Álvaro", "natural": "Álvaro Ruiz", "slug": "alvaro-ruiz",
     "sigla": "PP", "circunscripcion": "Ávila", "partido": "PP"},
    {"nombre": "Pérez, Ana", "natural": "Ana Pérez", "slug": "ana-perez",
     "sigla": "PSOE", "circunscripcion": "Palmas (Las)", "partido": "PSOE"},
    {"nombre": "Álvarez de Toledo Peralta-Ramos, Cayetana",
     "natural": "Cayetana Álvarez de Toledo Peralta-Ramos",
     "slug": "cayetana-alvarez-de-toledo-peralta-ramos",
     "sigla": "PP", "circunscripcion": "Madrid", "partido": "PP"},
    {"nombre": "Sol, Beatriz", "natural": "Beatriz Sol", "slug": "beatriz-sol",
     "sigla": "Sumar", "circunscripcion": "Coruña (A)", "partido": "Sumar"},
]


class Circunscripcion(unittest.TestCase):
    def test_nombres_habituales(self):
        casos = {
            "Palmas (Las)": "Las Palmas",
            "S/C Tenerife": "Santa Cruz de Tenerife",
            "Balears (Illes)": "Illes Balears",
            "Coruña (A)": "A Coruña",
            "Rioja (La)": "La Rioja",
            "Madrid": "Madrid",
            "Valencia/València": "Valencia/València",
            "Alicante/Alacant": "Alicante/Alacant",
            "Araba/Álava": "Araba/Álava",
            "": "",
        }
        for crudo, habitual in casos.items():
            self.assertEqual(build.nombre_circunscripcion(crudo), habitual, crudo)

    def test_no_cambia_el_slug(self):
        self.assertEqual(build._slug_txt("Palmas (Las)"), "palmas-las")
        self.assertEqual(build._slug_txt("S/C Tenerife"), "s-c-tenerife")
        self.assertEqual(build._slug_txt("Coruña (A)"), "coruna-a")


class Listado(unittest.TestCase):
    def setUp(self):
        self.h = build.lista_completa_diputados(FICHAS)

    def test_enlace_a_cada_ficha(self):
        for f in FICHAS:
            self.assertIn(f'href="{f["slug"]}.html"', self.h)
            self.assertIn(f["nombre"], self.h)
        self.assertEqual(self.h.count("<li>"), len(FICHAS))
        self.assertIn('id="todos"', self.h)
        self.assertIn("Los 4 diputados", self.h)
        self.assertNotIn("<script", self.h)
        self.assertNotIn("<details", self.h)

    def test_orden_por_apellido_y_formato(self):
        # Álvarez…, Pérez, Ruiz, Sol — no por el nombre de pila.
        orden = re.findall(r'href="([^"]+)\.html"', self.h)
        self.assertEqual(orden, [
            "cayetana-alvarez-de-toledo-peralta-ramos",
            "ana-perez",
            "alvaro-ruiz",
            "beatriz-sol",
        ])
        self.assertIn("Álvarez de Toledo Peralta-Ramos, Cayetana", self.h)
        self.assertIn("Pérez, Ana", self.h)
        self.assertIn("orden alfabético de apellido", self.h)
        # El nombre de pila delante ya no es el título de la fila.
        self.assertNotIn(">Ana Pérez<", self.h)
        self.assertNotIn(">Álvaro Ruiz<", self.h)

    def test_grupo_y_circunscripcion_habitual(self):
        self.assertIn("PSOE · Las Palmas", self.h)
        self.assertIn("Sumar · A Coruña", self.h)
        self.assertNotIn("Palmas (Las)", self.h)
        self.assertNotIn("Coruña (A)", self.h)

    def test_indice_az_y_volver(self):
        self.assertIn('class="dip-az"', self.h)
        self.assertIn('href="#letra-a"', self.h)
        self.assertIn('href="#letra-p"', self.h)
        self.assertIn('id="letra-a"', self.h)
        self.assertIn('id="letra-p"', self.h)
        # Solo letras con diputados: A, P, R, S. No B, C…
        self.assertNotIn('href="#letra-b"', self.h)
        self.assertNotIn('href="#letra-z"', self.h)
        self.assertGreaterEqual(self.h.count("Volver arriba"), 4)
        self.assertIn('href="#todos"', self.h)
        self.assertNotIn("<details", self.h)

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

    def test_css_compacto_sin_subrayado_ni_tarjetas(self):
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
        self.assertIn("min-width:760px", bloque)
        self.assertNotIn("<details", bloque)


if __name__ == "__main__":
    unittest.main()
