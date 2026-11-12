"""Sitemap por secciones con fecha real (tanda 8, punto 1)."""
import pathlib
import unittest
import xml.etree.ElementTree as ET

import sitemap as sm

S = "https://terceracamara.es/"
NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
HOY = "2026-11-12"


def pagina(cuerpo, fecha_pase=HOY):
    return (f'<html><head><script type="application/ld+json">{{"dateModified":"{fecha_pase}"}}</script>'
            f'<link href="/assets/style.css?v=abcdef1234"></head><body>'
            f'<header class="masthead">{fecha_pase}</header>{cuerpo}'
            f'<footer>pie</footer></body></html>')


class Secciones(unittest.TestCase):
    def test_reparto(self):
        self.assertEqual(sm.seccion(S + "normas/BOE-A-2026-1.html", "2026-10-03", S), "normas-2026-10")
        self.assertEqual(sm.seccion(S + "normas/", HOY, S), "otros")
        self.assertEqual(sm.seccion(S + "ediciones/2026-10.html", "2026-10-28", S), "ediciones")
        self.assertEqual(sm.seccion(S + "diputados/x.html", HOY, S), "diputados")
        self.assertEqual(sm.seccion(S + "personas/x.html", HOY, S), "personas")
        self.assertEqual(sm.seccion(S + "votaciones/x.html", HOY, S), "votaciones")
        self.assertEqual(sm.seccion(S + "tramitacion/x.html", HOY, S), "tramitacion")
        self.assertEqual(sm.seccion(S, HOY, S), "otros")
        self.assertEqual(sm.seccion(S + "aviso-legal.html", HOY, S), "otros")

    def test_indice_y_ficheros(self):
        entradas = [{"url": S, "lastmod": "2026-11-12"},
                    {"url": S + "normas/a.html", "lastmod": "2026-10-03"},
                    {"url": S + "normas/b.html", "lastmod": "2026-11-02"},
                    {"url": S + "normas/b.html", "lastmod": "2026-11-02"},   # duplicada
                    {"url": S + "diputados/x.html", "lastmod": "2026-09-30"}]
        f = sm.generar(entradas, S)
        self.assertEqual(sorted(f), ["sitemap-diputados.xml", "sitemap-normas-2026-10.xml",
                                     "sitemap-normas-2026-11.xml", "sitemap-otros.xml", "sitemap.xml"])
        idx = ET.fromstring(f["sitemap.xml"])
        self.assertEqual(idx.tag, NS + "sitemapindex")
        locs = {s.find(NS + "loc").text: s.find(NS + "lastmod").text for s in idx}
        self.assertEqual(locs[S + "sitemap-diputados.xml"], "2026-09-30")
        self.assertEqual(locs[S + "sitemap-normas-2026-11.xml"], "2026-11-02")
        total = sum(len(ET.fromstring(x)) for k, x in f.items() if k != "sitemap.xml")
        self.assertEqual(total, 4)
        for k, x in f.items():
            if k != "sitemap.xml":
                self.assertEqual(ET.fromstring(x).tag, NS + "urlset")

    def test_parte_si_supera_el_tope(self):
        viejo = sm.MAX_URLS
        sm.MAX_URLS = 2
        try:
            f = sm.generar([{"url": S + f"diputados/{i}.html", "lastmod": HOY} for i in range(5)], S)
        finally:
            sm.MAX_URLS = viejo
        self.assertIn("sitemap-diputados-3.xml", f)
        self.assertNotIn("sitemap-diputados.xml", f)


class FechaReal(unittest.TestCase):
    def test_huella_ignora_lo_del_pase(self):
        a = pagina("<p>12 votaciones</p><span class=\"em-hace\">(hace 2 días)</span>", "2026-11-12")
        b = pagina("<p>12 votaciones</p><span class=\"em-hace\">(hace 3 días)</span>", "2026-11-13")
        self.assertEqual(sm.huella(a), sm.huella(b))
        self.assertNotEqual(sm.huella(a), sm.huella(pagina("<p>13 votaciones</p>")))
        c = pagina("<dd>jueves, 12 de noviembre de 2026</dd>")
        d = pagina("<dd>viernes, 13 de noviembre de 2026</dd>")
        self.assertEqual(sm.huella(c), sm.huella(d))

    def test_primera_vez_toma_la_fecha_de_la_pagina(self):
        html = pagina('<li>Votó <time datetime="2026-09-30">30 sep</time></li><li>01/10/2026</li>'
                      '<li><time datetime="2027-01-01">futuro</time></li>')
        e, est = sm.estabilizar([{"url": S + "diputados/x.html", "lastmod": HOY}], HOY,
                                lambda u: html, {})
        self.assertEqual(e[0]["lastmod"], "2026-10-01")
        self.assertEqual(est[S + "diputados/x.html"]["f"], "2026-10-01")

    def test_fecha_larga_en_espanol(self):
        html = pagina("<p>Publicada el 9 de octubre de 2026; vence el 9 de diciembre de 2026</p>")
        self.assertEqual(sm.fecha_en_pagina(html, HOY), "2026-10-09")

    def test_sin_fechas_en_la_pagina_queda_hoy(self):
        e, _ = sm.estabilizar([{"url": S + "x.html", "lastmod": HOY}], HOY,
                              lambda u: pagina("<p>nada</p>"), {})
        self.assertEqual(e[0]["lastmod"], HOY)

    def test_conserva_la_fecha_si_no_cambia(self):
        html = pagina("<p>igual</p>")
        estado = {S + "x.html": {"h": sm.huella(html), "f": "2026-10-20"}}
        e, est = sm.estabilizar([{"url": S + "x.html", "lastmod": "2026-11-13"}], "2026-11-13",
                                lambda u: html, estado)
        self.assertEqual(e[0]["lastmod"], "2026-10-20")
        self.assertEqual(est[S + "x.html"]["f"], "2026-10-20")

    def test_si_cambia_pasa_a_hoy(self):
        estado = {S + "x.html": {"h": "otra", "f": "2026-10-20"}}
        e, _ = sm.estabilizar([{"url": S + "x.html", "lastmod": "2026-11-13"}], "2026-11-13",
                              lambda u: pagina("<p>nuevo</p>"), estado)
        self.assertEqual(e[0]["lastmod"], "2026-11-13")

    def test_no_toca_fechas_reales(self):
        llamadas = []
        e, est = sm.estabilizar([{"url": S + "normas/a.html", "lastmod": "2026-10-03"}], HOY,
                                lambda u: llamadas.append(u), {})
        self.assertEqual(e[0]["lastmod"], "2026-10-03")
        self.assertEqual(llamadas, [])
        self.assertEqual(est, {})

    def test_edicion_usa_su_fecha_aunque_el_manifiesto_diga_hoy(self):
        """Un cambio de plantilla (pie, navegación) no debe fechar la edición como hoy."""
        entradas = [
            {"id": "2026-09-27", "url": S + "ediciones/2026-09-27.html", "lastmod": "2026-11-12"},
            {"id": "2026-10-28", "url": S + "ediciones/2026-10-28.html", "lastmod": "2026-11-12"},
        ]
        fechas = [e.get("id") or e["lastmod"] for e in entradas]
        self.assertEqual(fechas, ["2026-09-27", "2026-10-28"])
        src = (pathlib.Path(__file__).resolve().parent.parent / "build.py").read_text(encoding="utf-8")
        self.assertIn('{"url": e["url"], "lastmod": e.get("id") or e["lastmod"]}', src)


if __name__ == "__main__":
    unittest.main()
