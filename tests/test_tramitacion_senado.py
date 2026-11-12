"""Limpieza del residuo del Senado en /tramitacion/: páginas de estado vacías,
artículo en autores institucionales y nota de las proposiciones caducadas."""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import tramitacion as tr  # noqa: E402


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _attr(s):
    return _esc(s).replace('"', "&quot;")


def _hooks(carpeta):
    def pagina_suelta(_plantilla, carpeta, nombre, ctx):
        (carpeta / nombre).write_text(
            f"<title>{ctx['TITLE']}</title>\n"
            f'<meta name="description" content="{ctx["META_DESC"]}">\n'
            f'<link rel="canonical" href="{ctx["CANONICAL"]}">\n'
            f'<h1>{ctx["HEADLINE"]}</h1>\n'
            f'<p class="entradilla">{ctx["STANDFIRST"]}</p>\n'
            f'{ctx["FICHA"]}\n{ctx["CUERPO"]}\n',
            encoding="utf-8",
        )

    return {
        "esc_html": _esc,
        "esc_attr": _attr,
        "fmt_date_es": lambda d: d or "",
        "jsonld_script": lambda _d: "",
        "pagina_suelta": pagina_suelta,
        "plantilla": "",
        "site_url": "https://ejemplo.test/",
        "carpeta": carpeta,
        "log": lambda *_a, **_k: None,
        "detalle": [],
        "pagina_votacion": None,
        "normas_por_ley": {},
    }


def _ini(exp, est, autor, tipo="Proposición de ley del Senado", titulo=None):
    return exp, {
        "t": titulo or f"Proposición de prueba {exp}",
        "est": est,
        "tipo": tipo,
        "a": autor,
        "fp": "2024-01-15",
        "sit": "Caducado" if est == "caducada" else "Aprobado",
        "hitos": [{"f": "2026-10-06", "h": "Caducado" if est == "caducada" else "Aprobado"}],
    }


class ArticuloAutor(unittest.TestCase):
    def test_institucionales(self):
        casos = {
            "Senado": "el Senado",
            "Gobierno": "el Gobierno",
            "Grupo Parlamentario Socialista": "el Grupo Parlamentario Socialista",
            "Grupo Parlamentario Mixto Grupo Parlamentario Plurinacional SUMAR":
                "el Grupo Parlamentario Mixto Grupo Parlamentario Plurinacional SUMAR",
            "Comisión de Derechos Sociales y Consumo":
                "la Comisión de Derechos Sociales y Consumo",
            "Comunidad Autónoma de Andalucía-Parlamento":
                "la Comunidad Autónoma de Andalucía-Parlamento",
            "Comunidad de Madrid - Asamblea": "la Comunidad de Madrid - Asamblea",
            "Comunidad Autónoma de Castilla-La Mancha - Cortes":
                "la Comunidad Autónoma de Castilla-La Mancha - Cortes",
        }
        for crudo, esperado in casos.items():
            with self.subTest(crudo=crudo):
                self.assertEqual(tr.autor_en_frase(crudo), esperado)

    def test_personas_sin_articulo(self):
        persona = "González López, Nahuel (GSUMAR) y 45 Diputados"
        self.assertEqual(tr.autor_en_frase(persona), persona)
        lista = "Álvaro Vidal, Francesc-Marc (GR) Vallugera Balañà, Pilar (GR)"
        self.assertEqual(tr.autor_en_frase(lista), lista)

    def test_frase_del_senado(self):
        self.assertEqual(
            f"Lo que ha presentado {tr.autor_en_frase('Senado')}",
            "Lo que ha presentado el Senado",
        )


class NotaCaducadas(unittest.TestCase):
    def test_cifra_dinamica_y_sin_constante_47(self):
        self.assertIn("3 proposiciones caducaron", tr.texto_nota_caducadas_senado(3))
        self.assertIn("6 de octubre de 2026", tr.texto_nota_caducadas_senado(3))
        self.assertTrue(tr.texto_nota_caducadas_senado(1).startswith("Esta proposición caducó al disolverse"))
        self.assertEqual(tr.texto_nota_caducadas_senado(0), "")
        src = pathlib.Path(tr.__file__).read_text(encoding="utf-8")
        self.assertNotIn("47", src)


class PaginasEstadoVacias(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.carpeta = pathlib.Path(self.tmp.name)
        # Residuo de un render anterior: debe desaparecer.
        (self.carpeta / "estado-senado.html").write_text("vacia previa", encoding="utf-8")
        (self.carpeta / "estado-pleno.html").write_text("vacia previa", encoding="utf-8")
        ini = dict((
            _ini("124-000001", "caducada", "Senado"),
            _ini("124-000002", "caducada", "Senado", titulo="Otra proposición del Senado"),
            _ini("121-000010", "aprobada", "Gobierno",
                 tipo="Proyecto de ley", titulo="Proyecto de ley de prueba"),
        ))
        self.h = _hooks(self.carpeta)
        self.h["estado"] = {"ini": ini, "leyes": [], "actualizado": "2026-11-12"}
        self.salidas = tr.generar_paginas(self.h)

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_genera_estados_vacios_ni_los_deja_en_disco(self):
        nombres = {u["url"].rsplit("/", 1)[-1] or "index.html" for u in self.salidas}
        for vacia in ("estado-senado.html", "estado-pleno.html",
                      "estado-presentada.html", "estado-toma-en-consideracion.html",
                      "estado-plazo-de-enmiendas.html", "estado-ponencia-comision.html"):
            self.assertNotIn(vacia, nombres)
            self.assertFalse((self.carpeta / vacia).exists(), vacia)
        self.assertTrue((self.carpeta / "estado-caducada.html").exists())
        self.assertTrue((self.carpeta / "estado-aprobada.html").exists())

    def test_indice_no_enlaza_estados_vacios(self):
        html = (self.carpeta / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('href="estado-senado.html"', html)
        self.assertNotIn('href="estado-pleno.html"', html)
        self.assertIn('href="estado-caducada.html"', html)
        self.assertIn('class="tr-ix-vacio"', html)
        # La cifra 0 sigue visible, sin enlace.
        self.assertIn("Senado", html)

    def test_autor_senado_nota_y_articulo(self):
        html = (self.carpeta / "autor-senado.html").read_text(encoding="utf-8")
        self.assertIn("Lo que ha presentado el Senado", html)
        self.assertNotIn("Lo que ha presentado Senado y", html)
        self.assertIn("Estas 2 proposiciones caducaron al disolverse las Cortes "
                      "el 6 de octubre de 2026.", html)
        # Title y description no se tocan (siguen el patrón anterior).
        self.assertIn("<title>Iniciativas de Senado: en qué punto están | La Tercera Cámara</title>", html)
        self.assertIn('content="Las 2 iniciativas legislativas presentadas por Senado', html)

    def test_autor_gobierno_con_articulo(self):
        html = (self.carpeta / "autor-gobierno.html").read_text(encoding="utf-8")
        self.assertIn("Lo que ha presentado el Gobierno", html)

    def test_sitemap_sin_estados_vacios(self):
        urls = [u["url"] for u in self.salidas]
        self.assertTrue(any(u.endswith("tramitacion/estado-caducada.html") for u in urls))
        self.assertFalse(any("estado-senado.html" in u for u in urls))
        self.assertFalse(any("estado-pleno.html" in u for u in urls))


if __name__ == "__main__":
    unittest.main()
