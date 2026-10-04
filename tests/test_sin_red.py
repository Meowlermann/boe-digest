"""Pruebas del modo --sin-red de build.py y del Senado fuera de la automatización.

`python -m unittest tests.test_sin_red`. Sin red, claro: lo que se prueba es
justo que no salga ninguna petición.
"""
import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

import build  # noqa: E402


class TestSinRed(unittest.TestCase):
    def setUp(self):
        self._request = requests.sessions.Session.request
        self._sin_red = build.SIN_RED

    def tearDown(self):
        requests.sessions.Session.request = self._request
        build.SIN_RED = self._sin_red

    def test_get_y_post_lanzan_sinred(self):
        with mock.patch("sys.stdout"):
            build.activar_sin_red()
        with self.assertRaises(build.SinRed):
            build.get("https://www.boe.es/datosabiertos/api/boe/sumario/20261002")
        with self.assertRaises(build.SinRed):
            build.post("https://www.congreso.es/es/busqueda-de-iniciativas", {"a": 1})

    def test_requests_directo_tambien(self):
        # redaccion.py y la capa LLM usan requests.post sin pasar por build.get.
        with mock.patch("sys.stdout"):
            build.activar_sin_red()
        with self.assertRaises(build.SinRed):
            requests.post("https://generativelanguage.googleapis.com/", json={})

    def test_sin_render_no_se_admite(self):
        with mock.patch.object(sys, "argv", ["build.py", "--sin-red"]):
            with self.assertRaises(SystemExit):
                build.main()

    def test_sin_activar_no_corta(self):
        build.SIN_RED = False
        build._comprobar_red("https://www.boe.es/")       # no lanza


class TestSenado(unittest.TestCase):
    def test_desactivado(self):
        self.assertFalse(build.SENADO_ACTIVO)

    def test_construir_dia_no_llama_al_senado(self):
        with mock.patch.object(build, "fetch_senado") as senado, \
                mock.patch.object(build, "fetch_boe", return_value=None), \
                mock.patch.object(build, "capturar_nombramientos", return_value=[]), \
                mock.patch.object(build, "capturar_provincias"), \
                mock.patch.object(build, "cortes_congreso", return_value={"feed": []}), \
                mock.patch("sys.stdout"):
            build.construir_dia(build.dt.date(2026, 10, 4))
        senado.assert_not_called()

    def test_nota_de_cobertura(self):
        pieza = {"chamber": "congreso", "headline": "X", "source": {"url": "u"}}
        cortes = build.redactar_cortes({"feed": [pieza]}, [], None)
        self.assertEqual(cortes["coverage"]["nota"], build.NOTA_SENADO_INACTIVO)
        self.assertEqual(build.NOTA_SENADO_INACTIVO,
                         "El Senado no ofrece por ahora acceso automatizado a sus datos, "
                         "así que esta sección cubre solo el Congreso.")
        vacio = build.redactar_cortes({"feed": []}, [], None)
        self.assertTrue(vacio["coverage"]["nota"].startswith(build.NOTA_SENADO_INACTIVO))
        self.assertNotIn("Senado", vacio["constructionNote"])


if __name__ == "__main__":
    unittest.main()
