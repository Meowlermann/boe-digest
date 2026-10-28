"""UX-1: contadores de /empleo/ enlazados a su sección y tope visible
«N de M». La prueba falla si el contador no coincide con el encabezado sin
ese texto. Sin red."""
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

RAIZ_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_REPO))
sys.path.insert(0, str(RAIZ_REPO / "tools"))
sys.path.insert(0, str(RAIZ_REPO / "tests"))

import empleo as em  # noqa: E402
import verificar as v  # noqa: E402
from test_empleo import h_prueba  # noqa: E402

NOTA = ('<p class="aside-note">Se muestran 2 de 5, las más recientes. El resto, en el '
        '<a href="/empleo/index.xml">canal RSS de empleo</a>.</p>')


def pagina(ficha: str, cuerpo: str) -> str:
    return f"<dl>{ficha}</dl>{cuerpo}"


class TestProblemas(unittest.TestCase):
    def test_coinciden(self):
        html = pagina('<dt>D</dt><dd><a href="#t-a">3</a></dd><dt>A</dt><dd><a href="#t-a">3</a></dd>',
                      '<h2 id="t-a">A (3)</h2>')
        self.assertEqual(v.problemas_contadores(html), [])

    def test_hoy_333_y_300_sin_texto_falla(self):
        html = pagina('<dt>D</dt><dd><a href="#t-a">333</a></dd><dt>A</dt><dd><a href="#t-a">333</a></dd>',
                      '<h2 id="t-a">A (300)</h2>')
        self.assertTrue(any("sin «N de M»" in p for p in v.problemas_contadores(html)))

    def test_recorte_con_n_de_m_y_nota(self):
        html = pagina('<dt>D</dt><dd><a href="#t-a">5</a></dd><dt>A</dt><dd><a href="#t-a">5</a></dd>',
                      '<h2 id="t-a">A (2 de 5)</h2>' + NOTA)
        self.assertEqual(v.problemas_contadores(html), [])

    def test_recorte_sin_nota_falla(self):
        html = pagina('<dt>D</dt><dd><a href="#t-a">5</a></dd><dt>A</dt><dd><a href="#t-a">5</a></dd>',
                      '<h2 id="t-a">A (2 de 5)</h2>')
        self.assertTrue(v.problemas_contadores(html))

    def test_contador_sin_enlace_falla(self):
        html = pagina('<dt>D</dt><dd><a href="#t-a">3</a></dd><dt>A</dt><dd>3</dd>', '<h2 id="t-a">A (3)</h2>')
        self.assertTrue(any("no enlaza" in p for p in v.problemas_contadores(html)))

    def test_ancla_inexistente_falla(self):
        html = pagina('<dt>D</dt><dd><a href="#t-a">3</a></dd><dt>B</dt><dd><a href="#t-b">3</a></dd>',
                      '<h2 id="t-a">A (3)</h2>')
        self.assertTrue(any("no existe" in p for p in v.problemas_contadores(html)))


class TestGenerado(unittest.TestCase):
    """Con las páginas que genera empleo.py y un tope pequeño."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.carpeta = pathlib.Path(self.tmp.name) / "empleo"
        regs = {f"BOE-A-2026-{i}": {"fecha": "2026-10-27", "titulo": f"Convocatoria {i}", "dept": "MINISTERIO X",
                                     "tipo": "convocatoria" if i < 5 else "admitidos", "prov": []}
                for i in range(1, 8)}
        self.estado = {"version": 1, "registros": regs, "dias": {}}

    def tearDown(self):
        self.tmp.cleanup()

    def renderizado(self, nombre="index.html"):
        texto = (self.carpeta / nombre).read_text(encoding="utf-8")
        campos = dict(l.split("=", 1) for l in texto.splitlines() if "=" in l and l.split("=", 1)[0].isupper())
        return pagina(campos["FICHA"], campos["CUERPO"])

    def test_sin_recorte(self):
        h, _ = h_prueba(self.carpeta)
        em.generar_paginas(h, self.estado)
        html = self.renderizado()
        self.assertIn('<dd><a href="#t-convocatoria">4</a></dd>', html)
        self.assertIn('<h2 id="t-convocatoria">Convocatorias de procesos selectivos (4)</h2>', html)
        self.assertEqual(v.problemas_contadores(html), [])

    def test_recorte_dice_n_de_m_y_enlaza(self):
        h, _ = h_prueba(self.carpeta)
        with mock.patch.object(em, "MAX_FILAS", 2):
            em.generar_paginas(h, self.estado)
        html = self.renderizado()
        self.assertIn("(2 de 4)", html)
        self.assertIn('href="/empleo/index.xml"', html)
        self.assertIn('href="/empleo/#organismos"', html)
        self.assertEqual(v.problemas_contadores(html), [])
        self.assertEqual(v.problemas_contadores(self.renderizado("ministerio-x.html")), [])


if __name__ == "__main__":
    unittest.main()
