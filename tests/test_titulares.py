"""Pruebas de build.desambiguar_titulares(), sin red.

`python -m unittest tests.test_titulares`. El caso es real: el 5 de octubre de
2026 salieron dos resoluciones de la Comisión Mixta para las Relaciones con el
Tribunal de Cuentas con el mismo titular, y el desempate las dejó otra vez
iguales y cortadas («… PARA LAS: APROBADA POR LA COMISIÓN MIXTA PARA LAS
RELACIONES CON EL…»).
"""
import pathlib
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))

import build  # noqa: E402
import verificar  # noqa: E402

T1 = ("Resolución de 28 de abril de 2026, aprobada por la Comisión Mixta para las Relaciones con el "
      "Tribunal de Cuentas, en relación con el Informe de fiscalización de la Cuenta General de la "
      "Comunidad Autónoma de Extremadura, ejercicio 2023.")
T2 = ("Resolución de 9 de junio de 2026, aprobada por la Comisión Mixta para las Relaciones con el "
      "Tribunal de Cuentas, en relación con el Informe de fiscalización de la atención al ciudadano "
      "en el ámbito de las entidades que integran el Sistema de la Seguridad Social, ejercicio 2023.")


class TestDesambiguar(unittest.TestCase):
    def test_caso_real(self):
        piezas = [{"headline": "RESOLUCIÓN, APROBADA POR LA COMISIÓN MIXTA PARA LAS", "titulo_oficial": t}
                  for t in (T1, T2)]
        build.desambiguar_titulares(piezas)
        h1, h2 = (p["headline"] for p in piezas)
        self.assertNotEqual(h1, h2)
        self.assertIn("EXTREMADURA", h1)
        self.assertIn("ATENCIÓN AL CIUDADANO", h2)
        for h in (h1, h2):
            self.assertNotIn("…", h)
            self.assertEqual(build.titular_valido(h), "")
            self.assertEqual(verificar.problemas_titular(h), [], h)

    def test_distintos_no_se_tocan(self):
        piezas = [{"headline": "CAMBIAN LOS PRECIOS DEL TABACO", "titulo_oficial": T1},
                  {"headline": "SE CONVOCAN BECAS DE INVESTIGACIÓN", "titulo_oficial": T2}]
        build.desambiguar_titulares(piezas)
        self.assertEqual(piezas[0]["headline"], "CAMBIAN LOS PRECIOS DEL TABACO")

    def test_lo_que_distingue(self):
        self.assertEqual(build.lo_que_distingue(["la ley de aguas", "la ley de costas"]),
                         ["aguas", "costas"])
        self.assertEqual(build.lo_que_distingue(["igual", "igual"]), ["", ""])
        self.assertEqual(build.lo_que_distingue(["algo", ""]), ["", ""])


if __name__ == "__main__":
    unittest.main()
