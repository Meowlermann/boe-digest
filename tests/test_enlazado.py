"""Enlazado interno (TC-006): huérfanas y fichas con pocos enlaces, sin red."""
import pathlib
import sys
import tempfile
import unittest

RAIZ_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_REPO / "tools"))

import verificar as v  # noqa: E402


def html(*hrefs):
    enlaces = "".join(f'<a href="{h}">x</a>' for h in hrefs)
    return f"<!doctype html><html><body>{enlaces}</body></html>"


class TestEnlazado(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def escribir(self, rel, texto):
        f = self.raiz / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(texto, encoding="utf-8")
        return f

    def paginas(self):
        return sorted(self.raiz.rglob("*.html"))

    def sitio_bueno(self):
        self.escribir("index.html", html("/diputados/", "/diputados/a.html"))
        self.escribir("diputados/index.html", html("/", "a.html", "b.html"))
        self.escribir("diputados/a.html", html("../", "./", "b.html"))
        self.escribir("diputados/b.html", html("../", "./", "a.html"))

    def test_sitio_sin_huerfanas(self):
        self.sitio_bueno()
        self.assertEqual(v.comprobar_enlazado(self.raiz, self.paginas()), [])

    def test_huerfana(self):
        self.sitio_bueno()
        self.escribir("diputados/c.html", html("../", "./", "a.html"))
        h = v.comprobar_enlazado(self.raiz, self.paginas())
        self.assertEqual(len(h), 1)
        self.assertIn("huérfana", h[0]["detalle"])
        self.assertIn("/diputados/c.html", h[0]["detalle"])
        self.assertEqual(h[0]["nivel"], v.GRAVE)

    def test_autoenlace_no_cuenta(self):
        self.sitio_bueno()
        self.escribir("diputados/c.html", html("c.html", "#arriba", "../", "./", "a.html"))
        self.assertTrue(any("/diputados/c.html" in x["detalle"]
                            for x in v.comprobar_enlazado(self.raiz, self.paginas())))

    def test_enlace_en_script_no_cuenta(self):
        self.sitio_bueno()
        self.escribir("diputados/c.html", html("../", "./", "a.html"))
        self.escribir("diputados/b.html", '<script>var x=\'<a href="c.html">\';</script>'
                      + html("../", "./", "a.html"))
        self.assertTrue(any("huérfana" in x["detalle"] for x in v.comprobar_enlazado(self.raiz, self.paginas())))

    def test_huerfana_justificada(self):
        self.sitio_bueno()
        self.escribir("datos/votaciones-banner.html", "<div>fragmento</div>")
        self.assertEqual(v.comprobar_enlazado(self.raiz, self.paginas()), [])

    def test_ficha_con_pocos_enlaces(self):
        self.sitio_bueno()
        self.escribir("diputados/b.html", html("../", "a.html"))
        h = v.comprobar_enlazado(self.raiz, self.paginas())
        self.assertEqual(len(h), 1)
        self.assertIn("2 enlaces internos", h[0]["detalle"])

    def test_indice_no_es_ficha(self):
        self.sitio_bueno()
        self.escribir("diputados/index.html", html("a.html", "b.html"))
        self.assertEqual(v.comprobar_enlazado(self.raiz, self.paginas()), [])

    def test_url_publica(self):
        self.assertEqual(v.url_publica("index.html"), "/")
        self.assertEqual(v.url_publica("diputados/index.html"), "/diputados/")
        self.assertEqual(v.url_publica("diputados/a.html"), "/diputados/a.html")


if __name__ == "__main__":
    unittest.main()
