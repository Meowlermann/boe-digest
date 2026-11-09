"""Marca por pieza en titulares/entradillas de Gemini (tanda 7b)."""
import pathlib
import tempfile
import unittest
from unittest import mock

import build
import paginas_fijas as pf

ROOT = pathlib.Path(__file__).resolve().parent.parent
MARCA = build.MARCA_IA_TEXTO


class TextoYAviso(unittest.TestCase):
    def test_texto_marca(self):
        self.assertEqual(MARCA, "Titular con IA · Texto oficial en el BOE →")
        self.assertNotIn("subray", MARCA.lower())

    def test_aviso_legal(self):
        self.assertIn("Gemini", pf.AVISO_LEGAL)
        self.assertIn("resumen automático sin IA", pf.AVISO_LEGAL)
        self.assertNotIn("redacción determinista", pf.AVISO_LEGAL)
        self.assertIn("en cada pieza", pf.AVISO_LEGAL)
        self.assertNotIn("al pie de cada edición", pf.AVISO_LEGAL)
        self.assertEqual(pf.CONTACTO, "contacto@terceracamara.es")
        self.assertNotIn("@gmail", pf.AVISO_LEGAL)


class MarcaPorPieza(unittest.TestCase):
    def test_con_ia_lleva_marca_y_enlace_boe(self):
        s = {"redaccion_ia": True, "url": "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-1"}
        html = build.marca_ia_html(s)
        self.assertIn('class="srclink ia-pieza"', html)
        self.assertIn(MARCA, html)
        self.assertIn("https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-1", html)
        self.assertNotIn("Ficha completa", html)  # la ficha va aparte

    def test_sin_ia_no_lleva_marca(self):
        self.assertEqual(build.marca_ia_html({"url": "https://www.boe.es/x"}), "")
        self.assertEqual(build.marca_ia_html({"redaccion_ia": False, "url": "https://x"}), "")
        self.assertEqual(build.marca_ia_html({}), "")

    def test_pie_integra_marca_y_ficha_sin_duplicar(self):
        s = {"redaccion_ia": True, "url": "https://www.boe.es/x", "ref": "BOE-A-2026-1"}
        pie = build.pie_enlaces_boe(s)
        self.assertEqual(pie.count("Ficha completa"), 1)
        self.assertIn("ia-pieza", pie)
        self.assertIn("fichalink", pie)
        # Sin IA: solo ficha
        self.assertEqual(build.pie_enlaces_boe({"ref": "BOE-A-2026-1"}).count("ia-pieza"), 0)
        self.assertIn("Ficha completa", build.pie_enlaces_boe({"ref": "BOE-A-2026-1"}))

    def test_grid_edicion_marca_segun_flag(self):
        day = {"id": "2026-11-09", "boe": {"stories": [
            {"headline": "CON IA", "standfirst": "e", "dept": "X", "ref": "BOE-A-2026-1",
             "url": "https://www.boe.es/x", "cat": "otros", "size": "md", "redaccion_ia": True},
            {"headline": "SIN IA", "standfirst": "e", "dept": "Y", "ref": "BOE-A-2026-2",
             "url": "https://www.boe.es/y", "cat": "otros", "size": "md"},
        ]}}
        html = build.render_boe_grid_ssr(day)
        # Solo la pieza con IA
        self.assertEqual(html.count("ia-pieza"), 1)
        self.assertIn("CON IA", html)
        # La de sin IA no tiene la marca entre su h3 y su foot
        i = html.index("SIN IA")
        trozo = html[i:i + 500]
        self.assertNotIn("ia-pieza", trozo)

    def test_linea_global_retirada(self):
        self.assertEqual(build.etiqueta_ia_html(True), "")
        self.assertEqual(build.etiqueta_ia_html(False), "")


if __name__ == "__main__":
    unittest.main()
