"""Pruebas de los canales Atom por entidad (feeds.py), de su anuncio en las
páginas (build._anunciar_feed), de la baliza de analítica y de la comprobación
(h) de tools/verificar.py. Sin red.
"""
import pathlib
import sys
import tempfile
import unittest

RAIZ_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_REPO))
sys.path.insert(0, str(RAIZ_REPO / "tools"))

import feeds as fd  # noqa: E402
import verificar as v  # noqa: E402


def _canal(n=3, **kw):
    ents = [fd.entrada(f"x:{i}", f"Título {i}", f"2026-09-{10 + i:02d}",
                       f"https://terceracamara.es/x/{i}.html", "resumen") for i in range(n)]
    return fd.atom(kw.get("titulo", "Canal & prueba"), "Sub", "https://terceracamara.es/x.xml",
                   "https://terceracamara.es/x.html", fd.ordenar(ents))


class Generacion(unittest.TestCase):
    def test_atom_valido(self):
        texto = _canal()
        self.assertEqual(v.problemas_canal(texto), [])
        self.assertIn("&amp; prueba", texto)
        # La entrada más reciente primero y su fecha es la del canal.
        self.assertLess(texto.index("Título 2"), texto.index("Título 0"))
        self.assertIn("<updated>2026-09-12T00:00:00Z</updated>\n  <author>", texto)

    def test_tope_y_duplicados(self):
        ents = [fd.entrada(f"x:{i % 60}", "T", "2026-01-01", "https://e/") for i in range(120)]
        out = fd.ordenar(ents)
        self.assertEqual(len(out), fd.MAX_ENTRADAS)
        self.assertEqual(len({e["id"] for e in out}), fd.MAX_ENTRADAS)

    def test_estable(self):
        """Mismos datos, mismo texto: un canal sin novedades no cambia."""
        self.assertEqual(_canal(), _canal())

    def test_vacio_no_se_escribe(self):
        self.assertEqual(fd.atom("t", "s", "u", "p", []), "")

    def test_entrada_incompleta(self):
        self.assertIsNone(fd.entrada("x", "t", "17/09/2026", "https://e/"))
        self.assertIsNone(fd.entrada("x", "", "2026-09-17", "https://e/"))
        self.assertEqual(fd.ddmmaaaa_a_iso("17/09/2026"), "2026-09-17")

    def test_departamento(self):
        casos = {
            "Vicepresidenta Primera del Gobierno y Ministra de Hacienda": "Hacienda",
            "Ministro del Hacienda": "Hacienda",
            "Vicepresidenta cuarta y ministra de Hacienda y Función Pública": "Hacienda",
            "Ministro de Interior": "Interior",
            "Ministro del Interior": "Interior",
            "Presidente del Gobierno": "Presidencia del Gobierno",
            "Ministra de Educación, Formación Profesional y Deportes":
                "Educación, Formación Profesional y Deporte",
            "Secretario de Estado": "",
        }
        for cargo, esperado in casos.items():
            self.assertEqual(fd.departamento(cargo), esperado, cargo)
        self.assertEqual(fd.etiqueta_departamento("Ministro del Interior"), "Ministerio del Interior")

    def test_ministerios(self):
        orales = {"180/1": {"cargo": "Ministro del Hacienda", "s": "2026-01-01"},
                  "180/2": {"cargo": "Vicepresidenta Primera del Gobierno y Ministra de Hacienda",
                            "s": "2026-02-01"},
                  "180/3": {"cargo": "Vicepresidenta Primera del Gobierno y Ministra de Hacienda",
                            "s": "2026-03-01"}}
        m = fd.ministerios(orales)
        self.assertEqual(list(m), ["hacienda"])
        self.assertEqual(m["hacienda"]["nombre"], "Ministerio de Hacienda")
        self.assertEqual([e for e, _r in m["hacienda"]["regs"]], ["180/3", "180/2", "180/1"])


class Anuncio(unittest.TestCase):
    def setUp(self):
        import build
        self.build = build

    def tearDown(self):
        self.build.FEEDS_PAGINA.clear()

    def test_pagina_con_canal(self):
        html = '<html><head></head><body><p class="entradilla">x</p><dl class="ficha"></dl></body></html>'
        self.build.FEEDS_PAGINA[("diputados", "ana.html")] = ("ana.xml", "Ana")
        out = self.build._anunciar_feed(html, pathlib.Path("/r/diputados"), "ana.html")
        self.assertIn('<link rel="alternate" type="application/atom+xml" title="Ana" href="ana.xml">', out)
        self.assertIn("Seguir con RSS", out)
        self.assertEqual(self.build._anunciar_feed(html, pathlib.Path("/r/diputados"), "otro.html"), html)

    def test_baliza(self):
        self.assertEqual(self.build.baliza_analitica(""), "")
        self.assertEqual(self.build.baliza_analitica("no válido!"), "")
        b = self.build.baliza_analitica("0123456789abcdef0123456789abcdef")
        self.assertIn("static.cloudflareinsights.com/beacon.min.js", b)
        self.assertIn('data-cf-beacon=\'{"token": "0123456789abcdef0123456789abcdef"}\'', b)
        self.assertIn('type="module"', b)
        # El token del sitio está puesto y tiene forma válida.
        self.assertTrue(self.build.baliza_analitica())

    def test_plantillas_sin_goatcounter(self):
        for p in RAIZ_REPO.glob("template*.html"):
            t = p.read_text(encoding="utf-8")
            self.assertIn("__SSR_ANALITICA__", t, p.name)
            self.assertNotIn("goatcounter", t, p.name)
            self.assertIn("/privacidad.html", t, p.name)
            self.assertIn("/aviso-legal.html", t, p.name)


class Verificador(unittest.TestCase):
    def test_mal_formado(self):
        self.assertTrue(v.problemas_canal("<feed><entry>")[0].startswith("XML mal formado"))

    def test_campos_y_duplicados(self):
        texto = _canal().replace("<id>tag:terceracamara.es,2026:x:1</id>",
                                 "<id>tag:terceracamara.es,2026:x:2</id>")
        self.assertTrue(any("duplicadas" in p for p in v.problemas_canal(texto)))
        sin_titulo = _canal().replace("<title>Título 1</title>", "<title></title>")
        self.assertTrue(any("<title>" in p for p in v.problemas_canal(sin_titulo)))
        mala_fecha = _canal().replace("2026-09-11T00:00:00Z", "11/09/2026")
        self.assertTrue(any("RFC 3339" in p for p in v.problemas_canal(mala_fecha)))

    def test_demasiadas(self):
        ents = "".join(f"<entry><id>{i}</id><title>t</title><updated>2026-01-01T00:00:00Z</updated>"
                       f'<link href="https://e/"/></entry>' for i in range(51))
        texto = (f'<feed xmlns="{fd.ATOM_NS}"><id>u</id><title>t</title><updated>2026-01-01T00:00:00Z'
                 f'</updated><link rel="self" href="u"/><author><name>a</name></author>{ents}</feed>')
        self.assertTrue(any("máximo" in p for p in v.problemas_canal(texto)))

    def test_rss2(self):
        bueno = ('<rss version="2.0"><channel><title>t</title><link>https://e/</link>'
                 '<description>d</description><item><title>a</title><link>https://e/a</link>'
                 '<guid>https://e/a</guid><pubDate>Thu, 08 Oct 2026 07:00:00 +0000</pubDate>'
                 '</item></channel></rss>')
        self.assertEqual(v.problemas_canal(bueno), [])
        self.assertTrue(v.problemas_canal(bueno.replace("Thu, 08 Oct 2026 07:00:00 +0000", "ayer")))

    def test_comprobar_feeds(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = pathlib.Path(d)
            (raiz / "diputados").mkdir()
            (raiz / "diputados" / "ana.html").write_text("<html></html>")
            (raiz / "diputados" / "ana.xml").write_text(_canal(), encoding="utf-8")
            (raiz / "sitemap.xml").write_text("<urlset/>")
            self.assertEqual(v.comprobar_feeds(raiz), [])
            (raiz / "diputados" / "luis.xml").write_text("<feed>", encoding="utf-8")
            h = v.comprobar_feeds(raiz)
            self.assertEqual([x["fichero"] for x in h], ["diputados/luis.xml"])
            self.assertEqual(h[0]["nivel"], v.GRAVE)

    def test_titular_pendiente_es_aviso(self):
        pagina = ('<!doctype html><html><head><title>t</title><meta name="description" content="d">'
                  '<link rel="canonical" href="https://terceracamara.es/aviso-legal.html"></head>'
                  '<body>Titular: &lt;TITULAR_PENDIENTE&gt;</body></html>')
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "aviso-legal.html"
            p.write_text(pagina, encoding="utf-8")
            h = v.comprobar_html(pathlib.Path(d), [p])
        self.assertEqual([x["nivel"] for x in h], [v.AVISO])
        self.assertIn("LSSI", h[0]["detalle"])


if __name__ == "__main__":
    unittest.main()
