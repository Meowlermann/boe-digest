"""TC-023: recolector del BOE por la API de datos abiertos y respeto al
robots.txt. Sin red: el robots.txt es el extracto commiteado
(tools/robots_boe.txt) y la API se simula.

`python -m unittest tests.test_robots_boe`.
"""
import datetime as dt
import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import build  # noqa: E402
import robots_boe  # noqa: E402

REGLAS = robots_boe.parsear(robots_boe.EXTRACTO.read_text(encoding="utf-8"))


def permitido(url):
    return robots_boe.permitido_con(url, REGLAS)


class TestMatcher(unittest.TestCase):
    def test_comodines_y_ancla(self):
        r = robots_boe.parsear("User-agent: *\nDisallow: /*X-1$\nDisallow: /a/\nAllow: /a/b\n")
        self.assertFalse(robots_boe.permitido_con("https://h/p?id=X-1", r))
        self.assertTrue(robots_boe.permitido_con("https://h/p?id=X-12", r))
        self.assertFalse(robots_boe.permitido_con("https://h/a/c", r))
        self.assertTrue(robots_boe.permitido_con("https://h/a/b", r))   # la más larga gana

    def test_empate_gana_allow(self):
        r = robots_boe.parsear("User-agent: *\nDisallow: /x\nAllow: /x\n")
        self.assertTrue(robots_boe.permitido_con("https://h/x", r))

    def test_otros_agentes_no_aplican(self):
        r = robots_boe.parsear("User-agent: otro\nDisallow: /\n\nUser-agent: *\nDisallow: /y\n")
        self.assertTrue(robots_boe.permitido_con("https://h/z", r))
        self.assertFalse(robots_boe.permitido_con("https://h/y", r))


class TestRutasDelRecolector(unittest.TestCase):
    """Comprobación del CI: lo que pide el recolector está permitido por el
    extracto; lo que dejó de pedir (y otros ejemplos) está excluido."""

    def test_api_del_sumario_permitida(self):
        d = dt.date(2026, 1, 1)
        while d <= dt.date(2026, 12, 31):
            url = build.API_SUMARIO_BOE.format(aaaammdd=d.strftime("%Y%m%d"))
            self.assertTrue(permitido(url), url)
            d += dt.timedelta(days=1)

    def test_texto_de_disposicion_normal_permitido(self):
        for ident in ("BOE-A-2026-4781", "BOE-A-2026-22000", "BOE-A-2025-100"):
            self.assertTrue(permitido(build.BOE_TXT.format(ident=ident)), ident)

    def test_exclusiones_conocidas(self):
        for url in ("https://www.boe.es/boe/dias/2026/03/02/",
                    "https://www.boe.es/boe/dias/2026/03/02/index.php",
                    "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-4920",
                    "https://www.boe.es/diario_boe/xml.php?id=BOE-A-2026-4781",
                    "https://www.boe.es/boe/dias/2026/02/28/pdfs/BOE-A-2026-4920.pdf"):
            self.assertFalse(permitido(url), url)

    def test_extracto_al_dia(self):
        """El extracto es lo que reducir() saca de sí mismo (no se editó a mano)."""
        texto = robots_boe.EXTRACTO.read_text(encoding="utf-8")
        self.assertEqual(robots_boe.reducir(texto), texto)

    def test_get_no_pide_lo_excluido(self):
        robots_boe.cargar()
        with mock.patch.object(build, "sesion_para") as sesion, mock.patch("sys.stdout"):
            r = build.get("https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-4920")
        self.assertIsNone(r)
        sesion.assert_not_called()
        self.assertEqual(build.DIAG["peticiones"][-1]["status"], "robots.txt")


def sumario(*diarios):
    return {"data": {"sumario": {"diario": list(diarios)}}}


ITEM = {"identificador": "BOE-A-2026-4781",
        "titulo": "Orden APA/150/2026, de 24 de febrero, por la que se regula el Comité de Caza.",
        "url_pdf": {"texto": "https://www.boe.es/boe/dias/2026/03/02/pdfs/BOE-A-2026-4781.pdf"}}
ANUNCIO = {"identificador": "BOE-B-2026-1", "titulo": "Anuncio de licitación de un contrato de obras cualquiera."}


class Resp:
    def __init__(self, datos):
        self._d = datos

    def json(self):
        return self._d


class TestFetchBoe(unittest.TestCase):
    def setUp(self):
        build.DIAG.pop("boe_error", None)

    def test_parseo_incluido_el_objeto_texto(self):
        datos = sumario({"numero": "54", "seccion": [{"nombre": "I. Disposiciones generales", "departamento": [
            {"nombre": "MINISTERIO DE AGRICULTURA", "texto": {"epigrafe": [{"nombre": "Organización", "item": ITEM}]}},
            {"nombre": "OTRO", "item": [ANUNCIO, dict(ITEM)]}]}]})
        entradas, numeros = build.entradas_sumario_api(datos["data"]["sumario"])
        self.assertEqual(numeros, ["54"])
        self.assertEqual(len(entradas), 1)                     # anuncio fuera, duplicado fuera
        e = entradas[0]
        self.assertEqual((e["ident"], e["epigrafe"], e["dept"]),
                         ("BOE-A-2026-4781", "Organización", "MINISTERIO DE AGRICULTURA"))
        self.assertTrue(e["url"].endswith("BOE-A-2026-4781.pdf"))

    def test_404_retrocede_un_dia(self):
        datos = sumario({"numero": "54", "seccion": {"nombre": "I", "departamento": {"nombre": "M", "item": ITEM}}})
        pedidas = []

        def falso_get(url, **kw):
            pedidas.append(url)
            if url.endswith("20260302"):
                build.DIAG["peticiones"].append({"url": url, "status": 404})
                return None
            return Resp(datos)
        with mock.patch.object(build, "get", falso_get), mock.patch("sys.stdout"):
            r = build.fetch_boe(dt.date(2026, 3, 2))
        self.assertEqual(r["fecha_boe"], dt.date(2026, 3, 1))
        self.assertEqual(len(pedidas), 2)
        self.assertNotIn("boe_error", build.DIAG)

    def test_fallo_de_la_api_es_claro_y_no_retrocede(self):
        pedidas = []

        def falso_get(url, **kw):
            pedidas.append(url)
            build.DIAG["peticiones"].append({"url": url, "status": 503})
            return None
        with mock.patch.object(build, "get", falso_get), mock.patch("sys.stdout") as out:
            r = build.fetch_boe(dt.date(2026, 3, 2))
        self.assertIsNone(r)
        self.assertEqual(len(pedidas), 1)
        self.assertIn("503", build.DIAG["boe_error"])
        self.assertIn("BOE: ERROR", "".join(str(c) for c in out.mock_calls))

    def test_json_ilegible(self):
        class Mala:
            def json(self):
                raise ValueError("no es JSON")
        with mock.patch.object(build, "get", lambda url, **kw: Mala()), mock.patch("sys.stdout"):
            self.assertIsNone(build.fetch_boe(dt.date(2026, 3, 2)))
        self.assertIn("JSON", build.DIAG["boe_error"])


if __name__ == "__main__":
    unittest.main()
