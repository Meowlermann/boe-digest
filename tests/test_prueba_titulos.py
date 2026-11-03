"""Prueba de títulos en /diputados/provincia-X.html (tanda SEO 1b): solo las
provincias elegidas cambian; textos sin inventar datos; /provincias/ vuelve al
texto original."""
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import build  # noqa: E402
import provincias as pv  # noqa: E402

CONTROL = {"barcelona", "alicante-alacant", "navarra", "salamanca", "valladolid", "soria", "coruna-a"}


class PruebaTitulos(unittest.TestCase):
    def test_grupo_de_prueba_y_control(self):
        self.assertEqual(build.PRUEBA_TITULOS_DIP, {"murcia", "asturias", "madrid", "ceuta",
                                                    "burgos", "cantabria", "melilla"})
        self.assertFalse(build.PRUEBA_TITULOS_DIP & CONTROL)

    def test_textos_usan_solo_las_cifras_dadas(self):
        t, d, h = build.textos_prueba_dip("Murcia", [(5, "PP"), (3, "PSOE"), (2, "Vox")])
        self.assertEqual(t, "Diputados por Murcia (10): quiénes son y cómo votan | La Tercera Cámara")
        self.assertEqual(d, "Murcia tiene 10 diputados en el Congreso: PP 5, PSOE 3 y Vox 2. "
                            "Ficha de cada uno, con intervenciones y votos en el Pleno.")
        self.assertEqual(h, "Diputados por Murcia: quiénes son y cómo votan")
        self.assertLessEqual(len(d), 155)

    def test_singular(self):
        t, d, h = build.textos_prueba_dip("Ceuta", [(1, "PP")])
        self.assertTrue(t.startswith("Diputado por Ceuta (1): quién es y cómo vota"))
        self.assertIn("1 diputado en el Congreso: PP 1.", d)
        self.assertNotIn("diputados", d + t + h)

    def test_descripcion_larga_sin_reparto(self):
        rep = [(i, f"Grupo{i}") for i in range(9, 0, -1)]
        _, d, _ = build.textos_prueba_dip("Madrid", rep)
        self.assertLessEqual(len(d), 155)

    def test_provincias_vuelve_al_original(self):
        self.assertFalse(hasattr(pv, "PRUEBA_TITULOS"))
        src = (RAIZ / "provincias.py").read_text(encoding="utf-8")
        self.assertIn('"HEADLINE": esc(nombre)', src)
        self.assertIn("en las Cortes y en el BOE: diputados, preguntas y votaciones", src)


if __name__ == "__main__":
    unittest.main()
