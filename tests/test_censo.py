"""El censo de diputados y el hemiciclo tras una disolución de las Cortes, sin red.

`python -m unittest tests.test_censo`. Desde el 7-10-2026 (Cortes disueltas
por el Real Decreto 806/2026) DiputadosActivos solo trae a la Diputación
Permanente: ese censo parcial no puede sustituir al de la legislatura.
"""
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import congreso_datos as cd  # noqa: E402


def censo(n, prefijo="d"):
    return {f"{prefijo} {i}": {"nombre": f"{prefijo} {i}"} for i in range(n)}


class TestElegirCenso(unittest.TestCase):
    def test_completo_sustituye(self):
        nuevo = censo(350, "nuevo")
        self.assertIs(cd.elegir_censo(nuevo, censo(350)), nuevo)

    def test_parcial_no_sustituye_al_completo(self):
        previo = censo(350)
        avisos = []
        self.assertIs(cd.elegir_censo(censo(137, "dp"), previo, avisos.append), previo)
        self.assertIn("137", avisos[0])

    def test_estado_ya_parcial_usa_el_respaldo(self):
        with tempfile.TemporaryDirectory() as tmp:
            respaldo = pathlib.Path(tmp) / "censo.json"
            respaldo.write_text(json.dumps({"censo": censo(350, "xv")}), encoding="utf-8")
            with mock.patch.object(cd, "CENSO_RESPALDO", respaldo):
                elegido = cd.elegir_censo(censo(137, "dp"), censo(137, "dp"))
        self.assertEqual(len(elegido), 350)
        self.assertIn("xv 0", elegido)

    def test_sin_respaldo_se_queda_lo_que_hay(self):
        with mock.patch.object(cd, "CENSO_RESPALDO", pathlib.Path("/no/existe.json")):
            self.assertEqual(len(cd.elegir_censo(censo(137), {})), 137)

    def test_respaldo_real(self):
        datos = json.loads(cd.CENSO_RESPALDO.read_text(encoding="utf-8"))
        self.assertEqual(len(datos["censo"]), 350)
        self.assertGreaterEqual(len(datos["censo"]), cd.CENSO_MINIMO)


if __name__ == "__main__":
    unittest.main()


class TestHemicicloDiputacionPermanente(unittest.TestCase):
    def test_resalta_solo_la_permanente(self):
        orden = [{"clave": "a", "slug": "a", "natural": "A", "grupo": ""},
                 {"clave": "b", "slug": "b", "natural": "B", "grupo": ""}]
        svg = cd.hemiciclo_svg(orden, resaltar={"a"})
        self.assertEqual(svg.count("fuera-dp"), 1)
        self.assertIn('class="escano fuera-dp" data-d="b"', svg)
        self.assertNotIn("fuera-dp", cd.hemiciclo_svg(orden))

    def test_estado(self):
        self.assertIsNone(cd.diputacion_permanente({}))
        self.assertEqual(cd.diputacion_permanente({"diputacion_permanente": {"miembros": ["a"]}}), {"a"})
