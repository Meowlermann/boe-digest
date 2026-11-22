"""Aviso fijo para la noche del 29-N en /elecciones/2026/ y en las 52 páginas por
circunscripción: remite a Infoelectoral y a la aplicación oficial de Interior,
sin cifras propias, sin subrayados ni tarjetas y sin tocar title, description,
canonical, robots ni H1 (prueba de #75). Sin red."""
import pathlib
import re
import sys
import tempfile
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import build  # noqa: E402
import elecciones as el  # noqa: E402


class Aviso(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.escritas = {}

        def suelta(pl, carpeta, nombre, frag):
            cls.escritas[nombre] = frag
        h = {"pagina_suelta": suelta, "plantilla": "<footer>" + el.LEMA_IA + "</footer>",
             "site_url": "https://terceracamara.es/", "carpeta": pathlib.Path(tempfile.gettempdir()),
             "jsonld_script": lambda xs: "", "nombre": build.nombre_circunscripcion, "slug": build._slug_txt}
        el.generar_paginas(h, el.cargar(), [])

    def test_en_el_hub_y_en_las_52(self):
        self.assertEqual(len(self.escritas), 53)
        for nombre, frag in self.escritas.items():
            self.assertEqual(frag["CUERPO"].count(el.AVISO_29N), 1, nombre)
            # Primero del cuerpo: a 375×812 cabe entero en la primera pantalla.
            self.assertTrue(frag["CUERPO"].startswith(el.AVISO_29N), nombre)

    def test_solo_en_el_cuerpo(self):
        for nombre, frag in self.escritas.items():
            for campo in ("TITLE", "META_DESC", "CANONICAL", "HEADLINE", "STANDFIRST", "KICKER", "JSONLD"):
                self.assertNotIn("elec-aviso", str(frag.get(campo, "")), (nombre, campo))
                self.assertNotIn("Infoelectoral", str(frag.get(campo, "")), (nombre, campo))

    def test_enlace_oficial_y_app(self):
        self.assertIn('<a href="https://infoelectoral.interior.gob.es/">Infoelectoral</a>', el.AVISO_29N)
        self.assertIn("la aplicación oficial del Ministerio del Interior “29N Elecciones Generales 2026”", el.AVISO_29N)
        self.assertIn("Aquí no se publica el recuento de la noche.", el.AVISO_29N)
        self.assertIn("Junta Electoral Central en el BOE", el.AVISO_29N)
        self.assertEqual(re.findall(r'href="([^"]+)"', el.AVISO_29N), [el.INFOELECTORAL_URL])

    def test_sin_cifras_propias(self):
        texto = re.sub(r"<[^>]+>", "", el.AVISO_29N)
        texto = texto.replace("29-N", "").replace("“29N Elecciones Generales 2026”", "")
        self.assertIsNone(re.search(r"\d", texto), texto)

    def test_sin_tarjeta_ni_subrayado(self):
        self.assertNotIn("tarjeta", el.AVISO_29N)
        css = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")
        regla = re.search(r"\.elec-aviso\{([^}]*)\}", css).group(1)
        for prop in ("border", "box-shadow", "background", "text-decoration"):
            self.assertNotIn(prop, regla)
        self.assertRegex(css, r"\.elec-aviso a\{[^}]*text-decoration:none")


if __name__ == "__main__":
    unittest.main()
