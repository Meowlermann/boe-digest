"""Tanda E5: imagen para redes por circunscripción del 29-N. Cada una de las 52
páginas /elecciones/2026/<slug>.html (y su ficha /diputados/provincia-<slug>.html)
lleva su og:image y su twitter:image, y el PNG existe. Sin red y sin Pillow."""
import json
import pathlib
import struct
import sys
import tempfile
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import build  # noqa: E402
import elecciones as el  # noqa: E402

CARPETA = RAIZ / el.OG_CARPETA
SITE = "https://terceracamara.es/"


def tam_png(ruta: pathlib.Path) -> tuple[int, int]:
    b = ruta.read_bytes()[:24]
    assert b[:8] == b"\x89PNG\r\n\x1a\n", ruta
    return struct.unpack(">II", b[16:24])


class Imagenes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.datos = el.cargar()
        cls.textos = el.textos_og(cls.datos, build.nombre_circunscripcion, build._slug_txt)

    def test_una_por_circunscripcion_y_existe(self):
        self.assertEqual(len(self.textos), 52)
        for slug in self.textos:
            png = CARPETA / f"{slug}.png"
            self.assertTrue(png.is_file(), png)
            self.assertEqual(tam_png(png), (1200, 630), slug)

    def test_ninguna_sobra(self):
        sobran = {p.stem for p in CARPETA.glob("*.png")} - set(self.textos)
        self.assertEqual(sobran, set())

    def test_indice_al_dia_con_los_datos(self):
        # Si cambia curated/elecciones_2026.json, hay que volver a ejecutar
        # python tools/generar_og.py --elecciones (las imágenes se commitean).
        indice = json.loads((CARPETA / "indice.json").read_text(encoding="utf-8"))
        self.assertEqual(indice, self.textos)

    def test_texto_tal_cual_de_los_datos(self):
        t = {x["nombre"]: x for x in self.textos.values()}
        self.assertEqual(t["Madrid"]["cifras"], "38 escaños · 14 candidaturas al Congreso")
        self.assertEqual(t["Soria"]["cifras"], "2 escaños · 11 candidaturas al Congreso")
        self.assertEqual(t["Melilla"]["cifras"], "1 escaño · 5 candidaturas al Congreso")   # singular
        for x in self.textos.values():
            self.assertEqual(x["antetitulo"], "Elecciones generales 29-N")
            self.assertEqual(x["fecha"], self.datos["fecha_literal"])

    def test_imagenes_distintas(self):
        hashes = {(CARPETA / f"{s}.png").read_bytes() for s in self.textos}
        self.assertEqual(len(hashes), 52)


class Paginas(unittest.TestCase):
    def setUp(self):
        self.pl = ((RAIZ / "template_norma.html").read_text(encoding="utf-8")
                   .replace('href="../', 'href="../../').replace('src="../', 'src="../../'))

    def test_cada_pagina_lleva_su_imagen(self):
        plantillas = {}

        def suelta(pl, carpeta, nombre, frag):
            plantillas[nombre] = pl
        h = {"pagina_suelta": suelta, "plantilla": self.pl, "site_url": SITE,
             "carpeta": pathlib.Path(tempfile.gettempdir()), "jsonld_script": lambda xs: "",
             "nombre": build.nombre_circunscripcion, "slug": build._slug_txt}
        el.generar_paginas(h, el.cargar(), [])
        provincias = {k: v for k, v in plantillas.items() if k != "index.html"}
        self.assertEqual(len(provincias), 52)
        for nombre, pl in provincias.items():
            slug = nombre[:-5]
            url = f"{SITE}{el.OG_CARPETA}/{slug}.png"
            self.assertIn(f'<meta property="og:image" content="{url}">', pl, slug)
            self.assertIn(f'<meta name="twitter:image" content="{url}">', pl, slug)
            self.assertNotIn("og-default.png", pl, slug)
            self.assertIn("Elecciones generales 29-N en ", pl, slug)        # og:image:alt propio
            self.assertTrue((RAIZ / el.OG_CARPETA / f"{slug}.png").is_file(), slug)
        # El hub conserva la imagen genérica.
        self.assertIn("og-default.png", plantillas["index.html"])

    def test_solo_cambia_la_imagen(self):
        # Prueba #75: title, description, canonical, robots y H1 no se tocan.
        nueva = el.og_plantilla(self.pl, SITE, "soria", "Elecciones generales 29-N en Soria: x.")
        quitar = lambda s: [ln for ln in s.splitlines() if "og:image" not in ln and "twitter:image" not in ln]  # noqa: E731
        self.assertEqual(quitar(nueva), quitar(self.pl))
        self.assertNotEqual(nueva, self.pl)

    def test_sin_png_no_cambia(self):
        self.assertEqual(el.og_plantilla(self.pl, SITE, "no-existe", "x"), self.pl)

    def test_fichas_de_diputados(self):
        src = (RAIZ / "build.py").read_text(encoding="utf-8")
        self.assertIn("el.og_plantilla(plantilla_p, SITE_URL, ps, og[\"alt\"])", src)
        og = build._og_elecciones()
        self.assertEqual(len(og), 52)
        # Las URL de las fichas usan el mismo slug que los PNG.
        for slug in og:
            self.assertTrue((CARPETA / f"{slug}.png").is_file(), slug)


if __name__ == "__main__":
    unittest.main()
