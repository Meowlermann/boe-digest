"""Tanda E4: ItemList de diputados en las fichas de provincia y Event en el
hub y en las páginas por circunscripción. Se valida el JSON-LD tal como sale
de jsonld_script (json.loads + campos obligatorios). Sin red."""
import json
import pathlib
import re
import sys
import tempfile
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import build  # noqa: E402
import elecciones as el  # noqa: E402

RE_LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
SITE = "https://terceracamara.es/"


def grafo(script: str) -> list:
    m = RE_LD.fullmatch(script)
    assert m, script[:80]
    d = json.loads(m.group(1))
    assert d["@context"] == "https://schema.org"
    return d["@graph"]


def validar_evento(test, e, url):
    test.assertEqual(e["@type"], "Event")
    for k in ("name", "description", "startDate", "eventStatus", "eventAttendanceMode", "location", "url"):
        test.assertTrue(e.get(k), k)
    test.assertRegex(e["startDate"], r"^\d{4}-\d{2}-\d{2}$")
    test.assertEqual(e["url"], url)
    test.assertEqual(e["location"]["@type"], "Place")
    test.assertEqual(e["location"]["address"]["addressCountry"], "ES")
    test.assertTrue(e["eventStatus"].startswith("https://schema.org/"))
    test.assertEqual(e["subjectOf"]["url"], el.url_boe(el.ID_RD))


class Fecha(unittest.TestCase):
    def test_transcribe_sin_calcular(self):
        self.assertEqual(el.fecha_iso_literal("domingo 29 de noviembre de 2026"), "2026-11-29")
        self.assertEqual(el.fecha_iso_literal("domingo 3 de marzo de 2030"), "2030-03-03")
        for malo in ("", "el 29-N", "domingo 29 de brumario de 2026"):
            with self.assertRaises(ValueError):
                el.fecha_iso_literal(malo)


class Evento(unittest.TestCase):
    def setUp(self):
        self.datos = el.cargar()
        self.assertIsNotNone(self.datos, "falta curated/elecciones_2026.json")

    def test_hub_y_provincia(self):
        url = SITE + el.HUB
        g = grafo(build.jsonld_script([el.evento(self.datos, url)]))
        validar_evento(self, g[0], url)
        self.assertEqual(g[0]["startDate"], "2026-11-29")       # la del RD 806/2026
        self.assertEqual(g[0]["location"]["name"], "España")
        u = url + "soria.html"
        g = grafo(build.jsonld_script([el.evento(self.datos, u, "Soria")]))
        validar_evento(self, g[0], u)
        self.assertEqual(g[0]["location"]["address"]["addressRegion"], "Soria")

    def test_paginas_generadas_llevan_event_valido(self):
        escritas = {}
        h = {"pagina_suelta": lambda pl, carpeta, nombre, frag: escritas.__setitem__(nombre, frag),
             "plantilla": "", "site_url": SITE, "carpeta": pathlib.Path(tempfile.gettempdir()),
             "jsonld_script": build.jsonld_script, "nombre": build.nombre_circunscripcion,
             "slug": build._slug_txt}
        el.generar_paginas(h, self.datos, [])
        self.assertEqual(len(escritas), 53)
        for nombre, frag in escritas.items():
            g = grafo(frag["JSONLD"])
            tipos = [o["@type"] for o in g]
            self.assertEqual(tipos.count("Event"), 1, nombre)
            self.assertIn("BreadcrumbList", tipos, nombre)
            validar_evento(self, next(o for o in g if o["@type"] == "Event"), frag["CANONICAL"])


class ListaDiputados(unittest.TestCase):
    def test_item_list(self):
        gente = [{"natural": "Ana Uno", "slug": "ana-uno"}, {"natural": "Bea Dos", "slug": "bea-dos"}]
        g = grafo(build.jsonld_script([el.lista_diputados("Soria", gente, SITE)]))
        il = g[0]
        self.assertEqual(il["@type"], "ItemList")
        self.assertEqual(il["numberOfItems"], 2)
        self.assertEqual([x["position"] for x in il["itemListElement"]], [1, 2])
        self.assertEqual(il["itemListElement"][1],
                         {"@type": "ListItem", "position": 2, "name": "Bea Dos",
                          "url": SITE + "diputados/bea-dos.html"})

    def test_build_lo_pone_solo_en_las_fichas_de_provincia(self):
        src = (RAIZ / "build.py").read_text(encoding="utf-8")
        self.assertEqual(src.count("jsonld_extra=_lista_diputados_jsonld(prov, gente)"), 1)
        self.assertIn('"inLanguage": "es-ES", "dateModified": hoy}] + list(jsonld_extra or [])', src)


if __name__ == "__main__":
    unittest.main()
