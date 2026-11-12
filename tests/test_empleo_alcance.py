"""Alcance honesto de la búsqueda y contadores de /empleo/ (E-2b ítem 2)."""
import pathlib
import unittest

import empleo as em


class Alcance(unittest.TestCase):
    def test_enlaces_otra_pagina(self):
        self.assertEqual(em.ENLACE_PROVINCIAS, "/empleo/provincias.html")
        self.assertEqual(em.ENLACE_ORGANISMOS, "/empleo/organismos.html")
        self.assertNotIn("#provincias", em.ENLACE_PROVINCIAS)

    def test_ayuda_con_n_de_m(self):
        filas = [{"id": f"BOE-A-2026-{i}", "tipo": "convocatoria", "titulo": "x", "dept": "Ayuntamiento de X",
                  "prov": ["zaragoza"], "fecha": "2026-11-03", "proc": "Oposición", "url": "", "plazo": ""}
                 for i in range(3)]
        h = em.chips_filtro(filas, "2026-11-04",
                            [("zaragoza", "Zaragoza", 3)],
                            [("ayuntamiento-de-x", "Ayuntamiento de X", 3)],
                            (300, 765))
        self.assertIn("las 300 de 765 convocatorias cargadas", h)
        self.assertIn('href="/empleo/provincias.html"', h)
        self.assertIn("Cifras: disposiciones cargadas en esta página.", h)
        self.assertIn("Zaragoza (3)", h)

    def test_desplegable_cuenta_lo_pasado(self):
        # Si el llamador pasa 7 y no 13, el option dice 7.
        h = em.chips_filtro(
            [{"id": "BOE-A-2026-1", "tipo": "convocatoria", "titulo": "x", "dept": "X",
              "prov": ["zaragoza"], "fecha": "2026-11-03", "proc": "", "url": "", "plazo": ""}],
            "2026-11-04", [("zaragoza", "Zaragoza", 7)], [], (1, 10))
        self.assertIn("Zaragoza (7)", h)
        self.assertNotIn("Zaragoza (13)", h)


if __name__ == "__main__":
    unittest.main()
