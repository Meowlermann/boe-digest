"""Tanda 3-A: buscador arriba de /diputados/ (provincia + nombre), accesible y
con alternativa sin JS. Sin red."""
import pathlib
import re
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import build  # noqa: E402

FICHAS = [{"natural": "Ana Pérez", "slug": "ana-perez", "circunscripcion": "Murcia"},
          {"natural": "Álvaro Ruiz", "slug": "alvaro-ruiz", "circunscripcion": "Ávila"}]
POR_PROV = {"Murcia": [FICHAS[0]], "Ávila": [FICHAS[1]]}


class Buscador(unittest.TestCase):
    def setUp(self):
        self.h = build.buscador_diputados(FICHAS, POR_PROV)

    def test_formularios_con_label(self):
        self.assertIn('<label for="dip-prov">', self.h)
        self.assertIn('<select id="dip-prov"', self.h)
        self.assertIn('<label for="dip-nom">', self.h)
        self.assertIn('list="dip-nombres"', self.h)
        self.assertEqual(self.h.count('<button type="submit">Ir</button>'), 2)

    def test_destinos_reales(self):
        self.assertIn('<option value="provincia-murcia.html">Murcia</option>', self.h)
        self.assertIn('data-s="ana-perez"', self.h)
        self.assertEqual(len(re.findall(r'<option value="provincia-', self.h)), 2)
        self.assertEqual(self.h.count("data-s="), 2)

    def test_sin_js_y_legislatura(self):
        self.assertIn('href="#circunscripciones"', self.h)
        self.assertIn("XV Legislatura (disuelta)", self.h)
        self.assertIn('href="https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-20742"', self.h)
        self.assertTrue((RAIZ / "assets" / "dip-busca.js").exists())

    def test_solo_en_el_indice_y_antes_del_aviso(self):
        src = (RAIZ / "build.py").read_text(encoding="utf-8")
        self.assertEqual(src.count("buscador_diputados(fichas, por_prov)"), 1)
        self.assertIn("plantilla.replace(AVISO_LEGISLATURA, buscador_diputados(fichas, por_prov)\n"
                      "                                         + AVISO_LEGISLATURA, 1)", src)
        self.assertIn('_pagina_suelta(plantilla_indice, DIPUTADOS_DIR, "index.html"', src)

    def test_css_sin_subrayado_y_tactil(self):
        css = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")
        bloque = css.split("/* --- /diputados/ buscador")[1].split("/* --- fin /diputados/ buscador")[0]
        self.assertNotIn("underline", bloque)
        self.assertNotIn("gradient", bloque)
        self.assertNotIn("box-shadow", bloque)
        self.assertIn("min-height:44px", bloque)
        self.assertIn(":focus-visible", bloque)


if __name__ == "__main__":
    unittest.main()
