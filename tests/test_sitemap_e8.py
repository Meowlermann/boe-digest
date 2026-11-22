"""Tanda E8: sitemap prioritario y sitemap de noticias de 48 horas (Google News).
Sin red: las páginas son HTML de prueba con su JSON-LD."""
import datetime as dt
import json
import pathlib
import sys
import unittest
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import sitemap as sm  # noqa: E402

S = "https://terceracamara.es/"
NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
NN = "{http://www.google.com/schemas/sitemap-news/0.9}"
MADRID = ZoneInfo("Europe/Madrid")
AHORA = dt.datetime(2026, 11, 22, 15, 30, tzinfo=MADRID)


def pagina(url, titular, publicada, extra=()):
    graf = [{"@type": "NewsArticle", "url": url, "headline": titular, "datePublished": publicada}]
    graf += list(extra)
    return f'<html><head><script type="application/ld+json">{json.dumps(graf)}</script></head></html>'


class Prioritario(unittest.TestCase):
    def test_que_entra(self):
        for ruta in ("", "empleo/", "diputados/", "elecciones/2026/", "elecciones/2026/soria.html",
                     "diputados/provincia-s-c-tenerife.html"):
            self.assertEqual(sm.seccion(S + ruta, "2026-11-16", S), "prioritario", ruta)
        for ruta, sec in (("diputados/ana.html", "diputados"), ("diputados/grupo-vox.html", "diputados"),
                          ("provincias/soria.html", "otros"), ("empleo/provincia-soria.html", "otros"),
                          ("elecciones/", "otros"), ("normas/", "otros")):
            self.assertEqual(sm.seccion(S + ruta, "2026-11-16", S), sec, ruta)

    def test_lastmod_real_y_cada_url_una_vez(self):
        e = [{"url": S, "lastmod": "2026-11-21"},
             {"url": S + "elecciones/2026/soria.html", "lastmod": "2026-11-07"},
             {"url": S + "diputados/provincia-soria.html", "lastmod": "2026-10-30"},
             {"url": S + "diputados/ana.html", "lastmod": "2026-10-01"}]
        f = sm.generar(e, S)
        pr = ET.fromstring(f["sitemap-prioritario.xml"])
        fechas = {u.find(NS + "loc").text: u.find(NS + "lastmod").text for u in pr.iter(NS + "url")}
        self.assertEqual(fechas, {S: "2026-11-21", S + "elecciones/2026/soria.html": "2026-11-07",
                                  S + "diputados/provincia-soria.html": "2026-10-30"})
        self.assertNotIn(S + "diputados/provincia-soria.html", f["sitemap-diputados.xml"])
        self.assertNotIn("sitemap-otros.xml", f)        # la portada ya no está ahí
        ix = ET.fromstring(f["sitemap.xml"])
        locs = {s.find(NS + "loc").text: s.find(NS + "lastmod").text for s in ix.iter(NS + "sitemap")}
        self.assertEqual(locs[S + "sitemap-prioritario.xml"], "2026-11-21")


class Noticias(unittest.TestCase):
    def setUp(self):
        self.paginas = {
            S + "ediciones/2026-11-21.html": pagina(S + "ediciones/2026-11-21.html",
                                                    "Edición del sábado, 21 de noviembre de 2026",
                                                    "2026-11-21T07:40:00+01:00",
                                                    extra=[{"@type": "NewsArticle", "url": S + "normas/BOE-A-2026-9.html",
                                                            "headline": "otra", "datePublished": "2026-11-22T07:40:00+01:00"}]),
            S + "ediciones/2026-11-20.html": pagina(S + "ediciones/2026-11-20.html", "Edición del viernes",
                                                    "2026-11-20T07:40:00+01:00"),
            S + "normas/BOE-A-2026-1.html": pagina(S + "normas/BOE-A-2026-1.html", "Ley de A & B <prueba>",
                                                   "2026-11-21T07:40:00+01:00"),
            S + "normas/BOE-A-2026-2.html": pagina(S + "normas/BOE-A-2026-2.html", "Futura",
                                                   "2026-11-23T07:40:00+01:00"),
            S + "normas/BOE-A-2026-3.html": pagina(S + "normas/BOE-A-2026-3.html", "Sin zona",
                                                   "2026-11-22T07:40:00"),
            S + "normas/BOE-A-2026-4.html": "<html>sin JSON-LD</html>",
        }

    def leer(self, url):
        return self.paginas.get(url)

    def test_solo_48_horas_con_fecha_real(self):
        n = sm.noticias(list(self.paginas), AHORA, self.leer)
        # Misma hora: desempata la URL, de mayor a menor (orden estable).
        self.assertEqual([x["url"] for x in n], [S + "normas/BOE-A-2026-1.html", S + "ediciones/2026-11-21.html"])
        self.assertEqual({x["fecha"] for x in n}, {"2026-11-21T07:40:00+01:00"})
        # La edición del 20 a las 07:40 queda a más de 48 horas; la futura, la
        # que no tiene zona y la que no tiene NewsArticle no entran.
        urls = {x["url"] for x in n}
        for fuera in ("ediciones/2026-11-20.html", "normas/BOE-A-2026-2.html", "normas/BOE-A-2026-3.html",
                      "normas/BOE-A-2026-4.html"):
            self.assertNotIn(S + fuera, urls)

    def test_limite_exacto(self):
        n = sm.noticias([S + "ediciones/2026-11-20.html"],
                        dt.datetime(2026, 11, 22, 7, 40, tzinfo=MADRID), self.leer)
        self.assertEqual(len(n), 1)                      # justo 48 horas: entra
        n = sm.noticias([S + "ediciones/2026-11-20.html"],
                        dt.datetime(2026, 11, 22, 7, 41, tzinfo=MADRID), self.leer)
        self.assertEqual(n, [])

    def test_xml_google_news_y_enlazado_desde_el_indice(self):
        n = sm.noticias(list(self.paginas), AHORA, self.leer)
        e = [{"url": u, "lastmod": "2026-11-21"} for u in self.paginas] + [{"url": S, "lastmod": "2026-11-21"}]
        f = sm.generar(e, S, n)
        x = ET.fromstring(f["sitemap-noticias.xml"])            # bien formado (y escapado)
        urls = list(x.iter(NS + "url"))
        self.assertEqual(len(urls), 2)
        for u in urls:
            nw = u.find(NN + "news")
            self.assertEqual(nw.find(NN + "publication").find(NN + "name").text, "La Tercera Cámara")
            self.assertEqual(nw.find(NN + "publication").find(NN + "language").text, "es")
            self.assertEqual(nw.find(NN + "publication_date").text, "2026-11-21T07:40:00+01:00")
            self.assertTrue(nw.find(NN + "title").text)
        self.assertIn("Ley de A &amp; B &lt;prueba&gt;", f["sitemap-noticias.xml"])
        ix = ET.fromstring(f["sitemap.xml"])
        locs = {s.find(NS + "loc").text: s.find(NS + "lastmod") for s in ix.iter(NS + "sitemap")}
        self.assertEqual(locs[S + "sitemap-noticias.xml"].text, "2026-11-21")
        # Cada URL en un solo sitemap: las noticias salen de su sección.
        todas = []
        for nombre, xml in f.items():
            r = ET.fromstring(xml)
            if r.tag == NS + "urlset":
                todas += [l.text for l in r.iter(NS + "loc")]
        self.assertEqual(len(todas), len(set(todas)))
        self.assertNotIn(S + "normas/BOE-A-2026-1.html", f.get("sitemap-normas-2026-11.xml", ""))
        self.assertIn(S + "ediciones/2026-11-20.html", f["sitemap-ediciones.xml"])   # fuera de 48 h: en su sección

    def test_sin_noticias_fichero_vacio_valido(self):
        f = sm.generar([{"url": S, "lastmod": "2026-11-21"}], S, [])
        x = ET.fromstring(f["sitemap-noticias.xml"])
        self.assertEqual(list(x.iter(NS + "url")), [])
        ix = ET.fromstring(f["sitemap.xml"])
        s = [s for s in ix.iter(NS + "sitemap") if s.find(NS + "loc").text.endswith("noticias.xml")][0]
        self.assertIsNone(s.find(NS + "lastmod"))             # sin fecha inventada

    def test_sin_parametro_no_hay_sitemap_de_noticias(self):
        self.assertNotIn("sitemap-noticias.xml", sm.generar([{"url": S, "lastmod": "2026-11-21"}], S))


class Robots(unittest.TestCase):
    def test_robots_declara_solo_el_indice(self):
        r = (RAIZ / "robots.txt").read_text(encoding="utf-8")
        self.assertIn("Sitemap: https://terceracamara.es/sitemap.xml", r)


if __name__ == "__main__":
    unittest.main()
