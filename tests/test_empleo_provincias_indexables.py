"""Tanda 1-A: /empleo/provincia-*.html con convocatorias son indexables y van al
sitemap; el resto de /empleo/ sigue en noindex. Sin red."""
import pathlib
import re
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))
import empleo as em  # noqa: E402
from test_empleo import TestPaginas, h_prueba  # noqa: E402

NOINDEX = '<meta name="robots" content="noindex, follow">'


class Indexables(TestPaginas):
    def _generar(self):
        h, _ = h_prueba(self.carpeta)
        h["plantilla"] = NOINDEX
        base = h["pagina_suelta"]

        def con_plantilla(pl, carpeta, nombre, frag):
            base(pl, carpeta, nombre, frag)
            ruta = carpeta / nombre
            ruta.write_text(pl + "\n" + ruta.read_text(encoding="utf-8"), encoding="utf-8")
        h["pagina_suelta"] = con_plantilla
        return em.generar_paginas(h, self.estado)

    def test_solo_provincias_con_convocatorias(self):
        salidas = self._generar()
        for s in salidas:
            nombre = s["url"].rsplit("/", 1)[-1] or "index.html"
            html = (self.carpeta / nombre).read_text(encoding="utf-8")
            if s["indexable"]:
                self.assertTrue(nombre.startswith("provincia-"), nombre)
                self.assertIn('content="index, follow"', html)
                self.assertNotIn("noindex", html)
            else:
                self.assertIn("noindex", html)
        self.assertTrue(any(s["indexable"] for s in salidas))

    def test_title_sin_cifra_y_cifra_en_description(self):
        for s in self._generar():
            if s["indexable"]:
                nombre = s["url"].rsplit("/", 1)[-1]
                html = (self.carpeta / nombre).read_text(encoding="utf-8")
                self.assertRegex(html, r"TITLE=Oposiciones y empleo público en [^|:\d]+ \| La Tercera Cámara")
                self.assertRegex(html, r"META_DESC=\d+ convocatorias? publicadas? en el BOE en los últimos 90 días")
                self.assertIsNotNone(re.search(r"\d{4}-\d{2}-\d{2}", s["lastmod"]))

    def test_portada_sigue_noindex(self):
        self.assertEqual(em.ROBOTS, "noindex, follow")
        self.assertEqual(em.ROBOTS_PROVINCIA, "index, follow")


if __name__ == "__main__":
    unittest.main()
