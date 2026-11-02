"""Versión de assets: ?v=<hash del contenido> en el HTML publicado."""
import hashlib
import pathlib
import sys
import tempfile
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))
import build  # noqa: E402
import verificar  # noqa: E402


class VersionAssets(unittest.TestCase):
    def test_hash_determinista_y_del_contenido(self):
        h1 = build.huellas_assets()
        h2 = build.huellas_assets()
        self.assertEqual(h1, h2)
        esperado = hashlib.sha256((RAIZ / "assets" / "style.css").read_bytes()).hexdigest()[:10]
        self.assertEqual(h1["style.css"], esperado)

    def test_versionar_idempotente_y_actualiza(self):
        html = '<link href="../assets/style.css"><script src="/assets/nav.js" defer></script>'
        h = {"style.css": "aaaa", "nav.js": "bbbb"}
        v = build.versionar_html(html, h)
        self.assertIn('../assets/style.css?v=aaaa"', v)
        self.assertIn('/assets/nav.js?v=bbbb"', v)
        self.assertEqual(build.versionar_html(v, h), v)
        self.assertIn("style.css?v=cccc", build.versionar_html(v, {"style.css": "cccc"}))
        self.assertEqual(build._sin_version(v), html)
        # Lo que no es un asset propio no se toca.
        otro = '<a href="https://x.es/assets/style.css">x</a><img src="../assets/og-default.png">'
        self.assertNotIn("?v=", build.versionar_html(otro, {"og-default.png": "x"}))

    def test_sitio_entero_y_verificador(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = pathlib.Path(d)
            (raiz / "assets").mkdir()
            (raiz / "assets" / "style.css").write_text("body{}", encoding="utf-8")
            (raiz / "ediciones").mkdir()
            pag = raiz / "ediciones" / "2026-01-01.html"
            pag.write_text('<link rel="stylesheet" href="../assets/style.css">', encoding="utf-8")
            (raiz / "index.html").write_text('<link href="assets/style.css?v=0000000000">', encoding="utf-8")
            paginas = [pag, raiz / "index.html"]
            self.assertTrue(verificar.comprobar_assets(raiz, paginas))
            self.assertEqual(build.versionar_assets(raiz), 2)
            self.assertEqual(build.versionar_assets(raiz), 0)
            self.assertEqual(verificar.comprobar_assets(raiz, paginas), [])
            h = hashlib.sha256(b"body{}").hexdigest()[:10]
            self.assertIn(f"style.css?v={h}", pag.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
