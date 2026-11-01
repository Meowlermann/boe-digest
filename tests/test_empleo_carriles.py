"""Carriles por clase en /empleo/ (maqueta 2, 01-11-2026): una fila
deslizable por etiqueta (Oposición, Concurso…), con ‹ › y «Ver todos». Todo el
contenido está en el HTML sin JS; los controles salen con hidden. Sin red."""
import pathlib
import re
import sys
import tempfile
import unittest

RAIZ_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_REPO))
sys.path.insert(0, str(RAIZ_REPO / "tests"))

import empleo as em  # noqa: E402
from test_empleo import h_prueba  # noqa: E402

JS = RAIZ_REPO / "assets" / "empleo.js"
TITULOS = ["Resolución por la que se convoca proceso selectivo para ingreso, por el sistema de "
           "acceso libre, en el Cuerpo X", "Resolución por la que se convoca concurso de "
           "traslados para la provisión de puestos de trabajo", "Convocatoria 3", "Convocatoria 4"]


class TestCarriles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.carpeta = pathlib.Path(self.tmp.name) / "empleo"
        regs = {f"BOE-A-2026-{i}": {"fecha": "2026-10-27", "titulo": TITULOS[i % 4],
                                     "dept": "MINISTERIO X", "prov": [],
                                     "tipo": "convocatoria" if i < 7 else "admitidos"}
                for i in range(1, 10)}
        h, _ = h_prueba(self.carpeta)
        h["hoy"] = "2026-10-28"
        em.generar_paginas(h, {"version": 1, "registros": regs, "dias": {}})
        self.idx = (self.carpeta / "index.html").read_text(encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_todas_las_tarjetas_en_carriles(self):
        self.assertEqual(len(re.findall(r'<li class="em-card"', self.idx)), 9)
        pistas = re.findall(r'<ul class="ix-lista em-pista" tabindex="0" aria-label="[^"]+: fila deslizable">', self.idx)
        self.assertGreaterEqual(len(pistas), 2)

    def test_orden_de_encabezados_sin_saltos(self):
        niveles = [int(n) for n in re.findall(r"<h([1-6])[ >]", self.idx)]
        for a, b in zip(niveles, niveles[1:]):
            self.assertLessEqual(b, a + 1, niveles)
        # Los ids de carril no usan el prefijo t- (lo reservan los contadores).
        self.assertFalse(re.search(r'class="em-carril-t" id="t-', self.idx))

    def test_controles_ocultos_sin_js_y_nombre_accesible(self):
        for nav in re.findall(r'<span class="em-carril-nav"[^>]*>', self.idx):
            self.assertIn("hidden", nav)
        for b in re.findall(r'<button[^>]*em-vertodos[^>]*>([^<]*)</button>', self.idx):
            self.assertRegex(b, r"^Ver todos \(\d+\)$")
        self.assertNotRegex(self.idx, r'<button[^>]*(em-ant|em-sig|em-vertodos)[^>]*aria-label')
        for b in re.findall(r'<button[^>]*em-vertodos[^>]*>', self.idx):
            self.assertIn('aria-expanded="false"', b)
            self.assertIn("hidden", b)

    def test_fichas_sin_carriles(self):
        ficha = (self.carpeta / "ministerio-x.html").read_text(encoding="utf-8")
        self.assertNotIn("em-carril", ficha)

    def test_js_hash_y_carriles(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn("URLSearchParams(location.hash", js)
        for k in ("em-carril", "scrollBy", "aria-expanded", "Ver en fila"):
            self.assertIn(k, js)


if __name__ == "__main__":
    unittest.main()
