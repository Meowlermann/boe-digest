"""Rejilla por clase en /empleo/ (variante A, 04-11-2026): sustituye a los
carriles. Un bloque por etiqueta con su rejilla; sin JS se ve todo; el JS
pagina de 24 en 24 con «Cargar más». Sin carril ni scroll lateral. Sin red."""
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


class TestRejilla(unittest.TestCase):
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

    def test_todas_las_tarjetas_en_rejilla(self):
        self.assertEqual(len(re.findall(r'<li class="em-card"', self.idx)), 9)
        self.assertGreaterEqual(self.idx.count('<ul class="ix-lista em-rejilla">'), 2)

    def test_sin_carriles(self):
        for k in ("em-carril", "em-pista", "em-ant", "em-sig", "em-vertodos", "fila deslizable"):
            self.assertNotIn(k, self.idx, k)

    def test_orden_de_encabezados_sin_saltos(self):
        niveles = [int(n) for n in re.findall(r"<h([1-6])[ >]", self.idx)]
        for a, b in zip(niveles, niveles[1:]):
            self.assertLessEqual(b, a + 1, niveles)
        self.assertFalse(re.search(r'class="em-bloque-t" id="t-', self.idx))

    def test_fichas_sin_rejilla_por_clase(self):
        ficha = (self.carpeta / "ministerio-x.html").read_text(encoding="utf-8")
        self.assertNotIn("em-bloque", ficha)

    def test_js_paginado_sin_carriles(self):
        js = JS.read_text(encoding="utf-8")
        for k in ("URLSearchParams(location.hash", "hashchange", "em-bloque", "LOTE = 24",
                  "Cargar más", "em-oculta"):
            self.assertIn(k, js, k)
        for k in ("em-carril", "scrollBy", "scrollLeft", "Ver en fila", "em-pos", "em-enfila"):
            self.assertNotIn(k, js, k)

    def test_css_rejilla_sin_scroll_lateral(self):
        css = (RAIZ_REPO / "assets" / "style.css").read_text(encoding="utf-8")
        self.assertIn(".ix-lista.em-rejilla{ grid-template-columns:1fr; gap:14px; }", css)
        self.assertIn("repeat(auto-fill,minmax(280px,1fr))", css)
        self.assertIn("body:has(.tr-ix-em) .wrap,body:has(.tr-ix-em) .norma{max-width:1280px}", css)
        for k in (".em-pista", ".em-carril", "scroll-snap-type:x", ".em-pos", ".em-enfila"):
            self.assertNotIn(k, css, k)


if __name__ == "__main__":
    unittest.main()
