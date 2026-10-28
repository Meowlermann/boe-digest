"""UX-1: Empleo en la barra principal y en la barra inferior móvil de todas
las páginas, comprobado por verificar.py (q) menu. Sin red."""
import pathlib
import sys
import tempfile
import unittest

RAIZ_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_REPO))
sys.path.insert(0, str(RAIZ_REPO / "tools"))

import build  # noqa: E402
import verificar as v  # noqa: E402


def pagina(nav: str) -> str:
    return f"<!doctype html><html lang=\"es\"><body>{nav}<main>x</main></body></html>"


class TestMenu(unittest.TestCase):
    def test_render_nav_lleva_empleo_en_las_dos_barras(self):
        nav = build.render_nav()
        self.assertEqual(v.problemas_menu(pagina(nav)), [])
        tab = v.RE_TABBAR.search(nav).group(1)
        self.assertEqual(tab.count("<a "), 6)
        self.assertEqual(len(set(__import__("re").findall(r'href="([^"]+)"', tab))), 6)

    def test_plantillas_llevan_la_navegacion(self):
        for nombre in ("template.html", "template_edicion.html", "template_norma.html",
                       "template_archivo.html"):
            self.assertIn("__SSR_NAV__", (RAIZ_REPO / nombre).read_text(encoding="utf-8"), nombre)

    def test_falta_en_la_barra_movil(self):
        nav = build.render_nav().replace('<a href="/empleo/" data-pilar="empleo">', '<a href="/x/">', 1)
        self.assertTrue(any("barra inferior" in p for p in v.problemas_menu(pagina(nav))))

    def test_falta_en_la_barra_principal(self):
        nav = build.render_nav().replace('class="pilar-b" href="/empleo/"', 'class="pilar-b" href="/x/"', 1)
        self.assertTrue(any("barra principal" in p for p in v.problemas_menu(pagina(nav))))

    def test_sin_navegacion_es_grave(self):
        self.assertEqual(len(v.problemas_menu(pagina(""))), 2)

    def test_fragmento_no_cuenta(self):
        self.assertEqual(v.problemas_menu("<div>fragmento</div>"), [])

    def test_comprobar_menu_en_disco(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = pathlib.Path(d)
            (raiz / "a.html").write_text(pagina(build.render_nav()), encoding="utf-8")
            (raiz / "b.html").write_text(pagina(""), encoding="utf-8")
            hs = v.comprobar_menu(raiz, [raiz / "a.html", raiz / "b.html"])
            self.assertEqual({h["fichero"] for h in hs}, {"b.html"})
            self.assertTrue(all(h["nivel"] == v.GRAVE for h in hs))


if __name__ == "__main__":
    unittest.main()
