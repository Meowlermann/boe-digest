"""Pulido de /empleo/: el chip de días dice que filtra dentro de la ventana
(«Solo los últimos 30 días» frente a «Últimos 90 días» del resumen) y
«Cargar más» se lee bien cuando quedan menos de un lote."""
import pathlib
import unittest

import empleo as em

JS = (pathlib.Path(__file__).resolve().parent.parent / "assets" / "empleo.js").read_text(encoding="utf-8")


class ChipDias(unittest.TestCase):
    def test_filtro_dentro_de_la_ventana(self):
        self.assertLess(em.DIAS_FILTRO, em.DIAS_PORTADA)
        src = (pathlib.Path(em.__file__)).read_text(encoding="utf-8")
        self.assertIn("Solo los últimos {DIAS_FILTRO} días", src)
        self.assertNotIn('aria-pressed="false">Últimos {DIAS_FILTRO} días', src)


class CargarMas(unittest.TestCase):
    def test_textos(self):
        self.assertIn('q > LOTE ? "Cargar más (" + LOTE + " de " + q + " restantes)"', JS)
        self.assertIn('"Cargar las " + q + " restantes"', JS)
        self.assertIn('"Cargar la última"', JS)


if __name__ == "__main__":
    unittest.main()
