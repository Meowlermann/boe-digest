"""Migas visibles y JSON-LD BreadcrumbList (TC-005), sin red."""
import json
import pathlib
import sys
import tempfile
import unittest

RAIZ_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_REPO))
sys.path.insert(0, str(RAIZ_REPO / "tools"))

import build  # noqa: E402
import verificar as v  # noqa: E402

CANON = "https://terceracamara.es/personas/ana-perez.html"
MIGA = ('<a href="../">Portada</a> › <a href="../nombramientos/">Nombramientos</a> › '
        '<a href="./">Personas</a> › <span aria-current="page">Ana P&eacute;rez</span>')


def pagina(miga=MIGA, jsonld=None, canon=CANON):
    ld = jsonld if jsonld is not None else build.jsonld_script([build.jsonld_migas(miga, canon)])
    return (f'<html><head><link rel="canonical" href="{canon}">{ld}</head><body>'
            f'<nav class="miga" aria-label="Ruta">{miga}</nav></body></html>')


class TestJsonldMigas(unittest.TestCase):
    def test_deriva_de_la_miga(self):
        ld = build.jsonld_migas(MIGA, CANON)
        el = ld["itemListElement"]
        self.assertEqual([e["name"] for e in el], ["Portada", "Nombramientos", "Personas", "Ana Pérez"])
        self.assertEqual([e["item"] for e in el], ["https://terceracamara.es/",
                                                    "https://terceracamara.es/nombramientos/",
                                                    "https://terceracamara.es/personas/", CANON])
        self.assertEqual([e["position"] for e in el], [1, 2, 3, 4])

    def test_miga_vacia(self):
        self.assertIsNone(build.jsonld_migas("", CANON))

    def test_replace_placeholders_anade_breadcrumb(self):
        html = build._replace_placeholders("__SSR_JSONLD__|__SSR_MIGA__",
                                           {"JSONLD": "", "MIGA": MIGA, "CANONICAL": CANON})
        self.assertIn('"@type":"BreadcrumbList"', html)

    def test_no_duplica_un_breadcrumb_propio(self):
        propio = '<script type="application/ld+json">{"@type":"BreadcrumbList"}</script>'
        html = build._replace_placeholders("__SSR_JSONLD__", {"JSONLD": propio, "MIGA": MIGA,
                                                              "CANONICAL": CANON})
        self.assertEqual(html.count("BreadcrumbList"), 1)


class TestComprobacionMigas(unittest.TestCase):
    def test_bien(self):
        self.assertEqual(v.problemas_migas(pagina(), True), [])

    def test_falta_jsonld(self):
        self.assertIn("falta el JSON-LD BreadcrumbList", v.problemas_migas(pagina(jsonld=""), True))

    def test_falta_miga_en_ficha(self):
        texto = '<html><head></head><body></body></html>'
        self.assertTrue(v.problemas_migas(texto, True))
        self.assertEqual(v.problemas_migas(texto, False), [])

    def test_pasos_distintos(self):
        corto = build.jsonld_script([build.jsonld_migas('<a href="../">Portada</a> › '
                                                        '<span aria-current="page">X</span>', CANON)])
        self.assertTrue(any("pasos" in p for p in v.problemas_migas(pagina(jsonld=corto), True)))

    def test_ultimo_no_canonico(self):
        otro = build.jsonld_script([build.jsonld_migas(MIGA, "https://terceracamara.es/personas/otra.html")])
        self.assertTrue(any("canónica" in p for p in v.problemas_migas(pagina(jsonld=otro), True)))

    def test_en_disco(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = pathlib.Path(tmp)
            (raiz / "personas").mkdir()
            (raiz / "personas" / "bien.html").write_text(pagina())
            (raiz / "personas" / "mal.html").write_text(pagina(jsonld=""))
            h = v.comprobar_migas(raiz, [raiz / "personas" / "bien.html", raiz / "personas" / "mal.html"])
            self.assertEqual([x["fichero"] for x in h], ["personas/mal.html"])
            self.assertEqual(h[0]["nivel"], v.GRAVE)


if __name__ == "__main__":
    unittest.main()
