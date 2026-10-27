"""TC-021: atribución del BOE en todas las plantillas, sin red.

`python -m unittest tests.test_atribucion`. Condiciones de reutilización de la
AEBOE: https://www.boe.es/informacion/aviso_legal/index.php (condición cuarta).
"""
import pathlib
import sys
import unittest

RAIZ_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_REPO / "tools"))

import verificar as v  # noqa: E402


class Atribucion(unittest.TestCase):
    def test_todas_las_plantillas(self):
        plantillas = sorted(RAIZ_REPO.glob("template*.html"))
        self.assertTrue(plantillas)
        for p in plantillas:
            with self.subTest(plantilla=p.name):
                self.assertEqual(v.problemas_atribucion(p.read_text(encoding="utf-8")), [])

    def test_detecta_faltas(self):
        bueno = ('<footer>Basado en datos de la <a href="https://www.boe.es" rel="noopener">'
                 'Agencia Estatal Boletín Oficial del Estado</a>. Medio no oficial.</footer>')
        self.assertEqual(v.problemas_atribucion(bueno), [])
        literal = bueno.replace("Basado en datos de la", "Fuente de los datos:")
        self.assertEqual(v.problemas_atribucion(literal), [])
        self.assertEqual(len(v.problemas_atribucion("<footer>Fuentes: boe.es</footer>")), 2)
        sin_enlace = bueno.replace("https://www.boe.es", "https://example.org")
        self.assertEqual(len(v.problemas_atribucion(sin_enlace)), 1)
        marco = bueno + '<iframe src="https://www.boe.es/diario_boe/"></iframe>'
        self.assertEqual(len(v.problemas_atribucion(marco)), 1)


if __name__ == "__main__":
    unittest.main()
