"""Prueba de títulos: solo las provincias elegidas cambian; textos sin inventar datos."""
import unittest

import provincias as pv


class PruebaTitulos(unittest.TestCase):
    def test_grupo_de_prueba(self):
        self.assertEqual(pv.PRUEBA_TITULOS, {"murcia", "asturias", "madrid", "ceuta",
                                            "burgos", "cantabria", "melilla"})

    def test_textos_usan_solo_las_cifras_dadas(self):
        t, d, h = pv.textos_prueba("Murcia", 10, 78, 68)
        self.assertEqual(t, "Diputados por Murcia (10), preguntas al Gobierno y BOE")
        self.assertIn("10 diputados", d)
        self.assertIn("78 preguntas", d)
        self.assertIn("68 disposiciones", d)
        self.assertEqual(h, "Murcia: diputados, preguntas y BOE")
        self.assertLessEqual(len(d), 155)

    def test_singular(self):
        t, d, _ = pv.textos_prueba("Ceuta", 1, 1, 1)
        self.assertTrue(t.startswith("Diputado por Ceuta (1)"))
        self.assertIn("1 diputado en", d)
        self.assertIn("1 pregunta al", d)
        self.assertIn("1 disposición", d)


if __name__ == "__main__":
    unittest.main()
