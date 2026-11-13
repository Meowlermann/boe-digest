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
        self.assertIn("text-decoration:none", h)             # sin subrayado, también aquí
        self.assertIn('content="light dark"', h)
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
        self.assertNotIn("/elecciones/2026/", hoy)           # informe 32: «Hoy» no es su sitio
        parl = re.search(r'id="panel-parlamento".*?</ul>', nav, re.S).group(0)
        self.assertIn("/elecciones/2026/", parl)
        self.assertNotIn('href="/diputados/todos/"', parl)   # ocupa su sitio durante la campaña

    def test_interruptor_campana(self):
        self.assertTrue(build.CAMPANA_29N)
        self.assertIn('href="/elecciones/2026/"', build.linea_campana_portada())
        guardado, guardado_nav = build.CAMPANA_29N, build._NAV_HTML
        try:
            build.CAMPANA_29N, build._NAV_HTML = False, None
            nav = build.render_nav()
            self.assertNotIn("/elecciones/2026/", nav)
            self.assertIn('href="/diputados/todos/"', nav)
            self.assertEqual(build.linea_campana_portada(), "")
        finally:
            build.CAMPANA_29N, build._NAV_HTML = guardado, guardado_nav

    def test_portada_tiene_hueco_para_la_linea(self):
        self.assertIn("__SSR_CAMPANA__", (RAIZ / "template.html").read_text(encoding="utf-8"))
        css = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")
        self.assertIn("text-decoration:none", re.search(r"\.campana-29n a\{[^}]*\}", css).group(0))


class Votaciones(unittest.TestCase):
    def test_bloque_de_votaciones_sin_srclink(self):
        src = (RAIZ / "build.py").read_text(encoding="utf-8")
        self.assertNotIn('<a class="srclink" href="/votaciones/">Todas las', src)
        self.assertIn('<a class="vt-a" href="/votaciones/">Todas las', src)
        css = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")
        self.assertIn("text-decoration:none", re.search(r"\.vt-a\{[^}]*\}", css).group(0))


class Fichas(unittest.TestCase):
    def test_texto_del_enlace_al_hub(self):
        src = (RAIZ / "elecciones.py").read_text(encoding="utf-8")
        self.assertIn("Candidaturas en las 52 circunscripciones →", src)


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
