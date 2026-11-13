"""«Elecciones: enlaces al hub»: /elecciones/ redirige a /elecciones/2026/,
enlace en el menú y en /diputados/, y «Todo sobre X…» sin subrayado. Sin red."""
import pathlib
import re
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))
import build  # noqa: E402
import elecciones as el  # noqa: E402
import verificar as v  # noqa: E402


class Redireccion(unittest.TestCase):
    def test_meta_refresh_canonical_noindex(self):
        h = el.redireccion_html("https://terceracamara.es/")
        self.assertIn('<meta http-equiv="refresh" content="0; url=/elecciones/2026/">', h)
        self.assertIn('<link rel="canonical" href="https://terceracamara.es/elecciones/2026/">', h)
        self.assertIn('content="noindex, follow"', h)
        self.assertIn('href="/elecciones/2026/"', h)          # enlace por si no hay refresh
        self.assertIsNone(v.RE_DOCUMENTO.search(h[:500]))     # no es página completa
        self.assertIn("/elecciones/", v.HUERFANAS_JUSTIFICADAS)   # nadie la enlaza a propósito


class Menu(unittest.TestCase):
    def test_hub_en_el_menu_sin_pasar_del_maximo(self):
        nav = build.render_nav()
        self.assertEqual(nav.count('href="/elecciones/2026/"'), 1)
        for clave in ("hoy", "parlamento", "mas"):
            panel = re.search(rf'id="panel-{clave}".*?</ul>', nav, re.S).group(0)
            self.assertLessEqual(panel.count("<li>"), build.MENU_MAX_ENLACES, clave)
        hoy = re.search(r'id="panel-hoy".*?</ul>', nav, re.S).group(0)
        self.assertIn("/elecciones/2026/", hoy)


class Diputados(unittest.TestCase):
    def test_enlace_desde_el_buscador_de_diputados(self):
        fichas = [{"natural": "Ana Uno", "nombre": "Uno, Ana", "slug": "ana-uno", "circunscripcion": "Soria"}]
        html = build.buscador_diputados(fichas, {"Soria": fichas})
        self.assertIn('href="../elecciones/2026/"', html)

    def test_codigo_enlaza_el_hub_y_todo_sobre_sin_srclink(self):
        src = (RAIZ / "build.py").read_text(encoding="utf-8")
        self.assertIn('<a href="../elecciones/2026/">Elecciones 29-N: candidaturas por provincia →</a>', src)
        self.assertNotIn('<a class="srclink" href="../provincias/{esc_attr(ps)}.html">', src)
        css = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")
        regla = re.search(r"\.destacado-a\{[^}]*\}", css).group(0)
        self.assertIn("text-decoration:none", regla)


if __name__ == "__main__":
    unittest.main()
