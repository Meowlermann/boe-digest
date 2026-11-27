"""E6: /404.html propia (paginas_fijas.generar_404). Sin red."""
import pathlib
import re
import sys
import tempfile
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))
import build  # noqa: E402
import paginas_fijas as pf  # noqa: E402
import montar_sitio  # noqa: E402

CSS = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")


def _h(raiz):
    return {"esc_html": build.esc_html, "esc_attr": build.esc_attr, "pagina_suelta": build._pagina_suelta,
            "plantilla": build.TEMPLATE_NORMA.read_text(encoding="utf-8"), "raiz": raiz,
            "fmt_date_es": build.fmt_date_es, "jsonld_script": build.jsonld_script, "site_url": build.SITE_URL}


class Pagina404(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = pathlib.Path(tempfile.mkdtemp())
        cls.ret = pf.generar_404(_h(cls.dir))
        cls.html = (cls.dir / "404.html").read_text(encoding="utf-8")

    def test_existe_en_la_raiz_y_se_publica(self):
        self.assertTrue((self.dir / "404.html").is_file())
        self.assertIn(("404.html", True), montar_sitio.leer_publicables())   # obligatoria

    def test_noindex_y_canonical_propio(self):
        self.assertEqual(re.findall(r'<meta name="robots" content="([^"]*)">', self.html), ["noindex"])
        self.assertEqual(re.findall(r'<link rel="canonical" href="([^"]*)">', self.html),
                         ["https://terceracamara.es/404.html"])
        self.assertRegex(self.html, r'"@type":\s*"BreadcrumbList"')

    def test_cabecera_pie_y_texto(self):
        self.assertIn('class="miga"', self.html)
        self.assertIn('<h1 class="display">Página no encontrada</h1>', self.html)
        self.assertIn("Esta dirección no existe en La Tercera Cámara.", self.html)
        self.assertIn("/assets/style.css", self.html)
        self.assertIn("<footer", self.html)
        self.assertIn('action="/buscar/"', self.html)                      # buscador que ya existe

    def test_rutas_absolutas(self):
        for attr, url in re.findall(r'\b(href|src|action)="([^"]*)"', self.html):
            self.assertTrue(re.match(r"(/|https?://|data:|mailto:|#)", url), f"{attr}={url}")
            self.assertFalse(url.startswith(".."), url)

    def test_enlaces_internos_validos(self):
        publicables = [p for p, _ in montar_sitio.leer_publicables()]
        internos = {u for u in re.findall(r'href="(/[^"#?]*)', self.html) if not u.startswith("//")}
        for u, _n, _d in pf.SECCIONES_404:
            self.assertIn(u, internos)
        for u in internos:
            primero = u.strip("/").split("/")[0]
            if primero:
                self.assertTrue(montar_sitio.cubre(publicables, primero), u)
        for u in ("/", "/normas/", "/diputados/", "/elecciones/2026/", "/empleo/", "/buscar/"):
            self.assertIn(u, internos)

    def test_fuera_de_los_sitemaps(self):
        self.assertIsNone(self.ret)                                          # no devuelve URL
        urls = pf.generar_paginas(_h(pathlib.Path(tempfile.mkdtemp())))
        self.assertFalse([e for e in urls if e["url"].endswith("/404.html")])
        for f in RAIZ.glob("sitemap*.xml"):                                  # tras un render
            self.assertNotIn("terceracamara.es/404.html<", f.read_text(encoding="utf-8"), f.name)

    def test_no_cambia_la_plantilla_de_las_demas(self):
        pl = build.TEMPLATE_NORMA.read_text(encoding="utf-8")
        pf.plantilla_404(pl)
        self.assertIn('<meta name="robots" content="index, follow', build.TEMPLATE_NORMA.read_text(encoding="utf-8"))
        self.assertIn('<meta name="robots" content="index, follow', pl)


class Estilo404(unittest.TestCase):
    def _reglas(self):
        css = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
        return [(s.strip(), c.replace(" ", "").replace("\n", "")) for s, c in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
                if "e404" in s]

    def test_sin_subrayado_en_ningun_estado(self):
        reglas = self._reglas()
        self.assertTrue(reglas)
        for sel, c in reglas:
            self.assertNotIn("underline", c, sel)
            m = re.search(r"text-decoration:([^;]+)", c)
            if m:
                self.assertEqual(m.group(1), "none", sel)
        enlaces = [s for s, c in reglas if ".e404-secciones a:hover" in s]
        self.assertTrue(enlaces)
        for e in (":visited", ":hover", ":focus", ":focus-visible", ":active"):
            self.assertIn(f".e404-secciones a{e}", enlaces[0])

    def test_ruta_sin_subrayado(self):
        reglas = [(s, c) for s, c in self._reglas() if ".miga a:hover" in s]
        self.assertTrue(reglas)
        self.assertIn("border-bottom:0", reglas[0][1])
        self.assertIn("text-decoration:none", reglas[0][1])

    def test_sin_tarjetas(self):
        for sel, c in self._reglas():
            if sel in (".e404-buscar", ".e404-secciones", ".e404-secciones li"):
                self.assertNotIn("border", c, sel)
                self.assertNotIn("background", c, sel)
                self.assertNotIn("box-shadow", c, sel)
