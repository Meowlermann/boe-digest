"""Pruebas de tools/verificar.py, sin red.

`python -m unittest tests.test_verificar`. Cada comprobación tiene un caso que
pasa y otro que falla. Los titulares rotos son reales: salieron publicados
antes de que existiera el verificador (las fechas van en los comentarios de
tools/verificar.py).
"""
import json
import re
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

RAIZ_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_REPO / "tools"))

import verificar as v  # noqa: E402

PAGINA = """<!doctype html>
<html lang="es"><head>
<title>{titulo}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{canonical}">
<link rel="alternate" type="application/rss+xml" title="La Tercera Cámara" href="/feed.xml">
<meta property="og:image" content="https://terceracamara.es/assets/og-default.png">
<meta name="twitter:card" content="summary_large_image">
<script type="application/ld+json">{jsonld}</script>
<script>if (typeof x === "undefined" || isNaN(y)) {{}}</script>
</head><body>{cuerpo}<footer>Basado en datos de la <a href="https://www.boe.es">Agencia Estatal Boletín Oficial del Estado</a>. Medio no oficial.</footer></body></html>
"""

BUILD = '''
ROOT = pathlib.Path(__file__).parent
INDEXNOW_KEY = "abc123"
'''

PUBLICABLES = """# lista de prueba
!index.html
sitemap*.xml
feed.xml
rss.xml
index.xml
!normas
mapa
!CNAME
robots.txt
abc123.txt
"""

WEBSITE = '{"@type": "WebSite", "name": "La Tercera Cámara", "url": "https://terceracamara.es/"}'
ARTICULO = ('{"@type": "NewsArticle", "headline": "Ley 1", "datePublished": "2026-10-01T07:40:00+02:00", '
            '"url": "https://terceracamara.es/normas/ley-1.html", '
            '"image": ["https://terceracamara.es/assets/og-default.png"], '
            '"publisher": {"@type": "Organization", "name": "La Tercera Cámara"}}')


def pagina(titulo="Normas — La Tercera Cámara", desc="Descripción.",
           canonical="https://terceracamara.es/normas/", cuerpo="", jsonld='{"@type": "WebPage"}'):
    return PAGINA.format(titulo=titulo, desc=desc, canonical=canonical, cuerpo=cuerpo, jsonld=jsonld)


class Sitio:
    """Un repositorio mínimo en un directorio temporal."""

    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = pathlib.Path(self._tmp.name)
        self.escribir("build.py", BUILD)
        self.lista = self.escribir("tools/publicables.txt", PUBLICABLES)
        self.escribir("CNAME", "terceracamara.es\n")
        rss = ('<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>'
               '<link>https://terceracamara.es/</link><description>D</description>'
               '<item><title>E</title><link>https://terceracamara.es/normas/ley-1.html</link></item>'
               '</channel></rss>')
        for f in ("feed.xml", "rss.xml", "index.xml"):
            self.escribir(f, rss)
        self.escribir("index.html", pagina(canonical="https://terceracamara.es/", jsonld=WEBSITE,
                                           cuerpo='<a href="/normas/">Normas</a>'))
        self.escribir("normas/index.html", pagina(cuerpo='<a href="/mapa/">Mapa</a> '
                                                         '<a href="ley-1.html">Ley</a>'))
        self.escribir("normas/ley-1.html", pagina(canonical="https://terceracamara.es/normas/ley-1.html", jsonld=ARTICULO,
                                                  cuerpo='<a href="../index.html">Portada</a>'))
        self.escribir("mapa/index.html", pagina(canonical="https://terceracamara.es/mapa/",
                                                cuerpo='<a href="https://terceracamara.es/normas/ley-1">x</a>'))

    def escribir(self, rel, texto):
        p = self.raiz / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(texto, encoding="utf-8")
        return p

    def cerrar(self):
        self._tmp.cleanup()


def edicion(boe=(), cortes=()):
    return {"id": "x", "boe": {"stories": list(boe)}, "cortes": {"feed": list(cortes)}}


class TestCarpetas(unittest.TestCase):
    def setUp(self):
        self.s = Sitio()

    def tearDown(self):
        self.s.cerrar()

    def carpetas(self):
        return v.comprobar_carpetas(self.s.raiz, self.s.lista)

    def test_coherentes(self):
        self.assertEqual(self.carpetas(), [])

    def test_carpeta_nueva_sin_registrar(self):
        self.s.escribir("plazos/index.html", pagina())
        h = self.carpetas()
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0]["nivel"], v.GRAVE)
        self.assertEqual(h[0]["fichero"], "tools/publicables.txt")
        self.assertIn("«plazos/»", h[0]["detalle"])
        self.assertIn("Qué hacer:", h[0]["detalle"])

    def test_quitada_de_la_lista(self):
        self.s.escribir("tools/publicables.txt", PUBLICABLES.replace("mapa\n", ""))
        self.assertIn("«mapa/»", self.carpetas()[0]["detalle"])

    def test_ficheros_de_la_raiz(self):
        # robots.txt, la clave de IndexNow y los feeds están en la lista;
        # otro.xml y googleXXX.html no: deben salir los dos.
        for f in ("robots.txt", "abc123.txt", "otro.xml", "google0a1b.html", "requirements.txt",
                  "template.html"):
            self.s.escribir(f, "x")
        self.assertEqual(sorted(h["detalle"].split("«")[1].split("»")[0] for h in self.carpetas()),
                         ["google0a1b.html", "otro.xml"])

    def test_comodines(self):
        self.s.escribir("sitemap.xml", "<x/>")
        self.s.escribir("sitemap-2.xml", "<x/>")
        self.assertEqual(self.carpetas(), [])

    def test_carpetas_no_publicadas_no_cuentan(self):
        for f in ("tests/fixture.html", "docs/x.html", "_site/index.html", "app/x.html"):
            self.s.escribir(f, "<p>x</p>")
        self.assertEqual(self.carpetas(), [])

    def test_sin_lista(self):
        (self.s.raiz / "tools" / "publicables.txt").unlink()
        self.assertIn("No existe", self.carpetas()[0]["detalle"])

    def test_repositorio_real(self):
        # El repositorio tal como está tiene que pasar (es el caso que más ha fallado).
        self.assertEqual(v.comprobar_carpetas(RAIZ_REPO), [])


class TestHtml(unittest.TestCase):
    def setUp(self):
        self.s = Sitio()

    def tearDown(self):
        self.s.cerrar()

    def test_sitio_correcto(self):
        self.assertEqual(v.comprobar_html(self.s.raiz), [])

    def test_marcadores(self):
        for marcador in ("{{HEADLINE}}", "None", "undefined", "NaN", "&lt;EMAIL_DE_CONTACTO&gt;",
                         "__SSR_CORTES_HIDDEN__"):
            with self.subTest(marcador=marcador):
                self.s.escribir("normas/ley-1.html", pagina(
                    canonical="https://terceracamara.es/normas/ley-1.html",
                    cuerpo=f"<p>Publicado el {marcador}</p>"))
                h = v.comprobar_html(self.s.raiz)
                self.assertEqual(len(h), 1, h)
                self.assertIn("Marcador sin sustituir", h[0]["detalle"])

    def test_marcador_en_atributo(self):
        self.s.escribir("normas/ley-1.html", pagina(
            canonical="https://terceracamara.es/normas/ley-1.html", cuerpo='<a title="None" href="#">x</a>'))
        self.assertEqual(len(v.comprobar_html(self.s.raiz)), 1)

    def test_javascript_no_cuenta(self):
        # La plantilla ya lleva «undefined» e «isNaN» en un <script>: no es un fallo.
        self.assertEqual(v.comprobar_html(self.s.raiz), [])

    def test_jsonld_con_nan(self):
        self.s.escribir("normas/ley-1.html", pagina(
            canonical="https://terceracamara.es/normas/ley-1.html", jsonld='{"n": NaN}'))
        h = v.comprobar_html(self.s.raiz)
        self.assertEqual(len(h), 1)
        self.assertIn("JSON-LD", h[0]["detalle"])

    def test_cabecera_incompleta(self):
        self.s.escribir("normas/ley-1.html", pagina(titulo=" ", desc="",
                                                    canonical="https://otro.example/x"))
        detalles = " ".join(x["detalle"] for x in v.comprobar_html(self.s.raiz))
        self.assertIn("<title>", detalles)
        self.assertIn("meta description", detalles)
        self.assertIn("canonical", detalles)

    def test_fragmento_sin_cabecera(self):
        self.s.escribir("datos/banner.html", '<div class="banner"><a href="/normas/">x</a></div>')
        self.assertEqual(v.comprobar_html(self.s.raiz), [])

    def test_enlaces_rotos(self):
        self.s.escribir("normas/index.html", pagina(cuerpo=(
            '<a href="/no-existe/">a</a> <a href="ley-2.html">b</a> '
            '<a href="https://terceracamara.es/normas/ley-9.html?x=1#y">c</a> '
            '<a href="https://www.boe.es/">externo</a> <a href="mailto:datos@terceracamara.es">m</a> '
            '<a href="#arriba">ancla</a>')))
        rotos = sorted(x["detalle"].split("«")[1].split("»")[0] for x in v.comprobar_html(self.s.raiz))
        self.assertEqual(rotos, ["/no-existe/", "/normas/ley-2.html", "/normas/ley-9.html"])

    def test_ruta_interna(self):
        self.assertEqual(v._ruta_interna("../mapa/", "normas/x/ley.html"), "/normas/mapa/")
        self.assertEqual(v._ruta_interna("ley.html", "index.html"), "/ley.html")
        self.assertIsNone(v._ruta_interna("https://www.congreso.es/", "index.html"))
        self.assertEqual(v._ruta_interna("https://terceracamara.es", "index.html"), "/")


class TestSitemap(unittest.TestCase):
    CAB = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'

    def setUp(self):
        self.s = Sitio()

    def tearDown(self):
        self.s.cerrar()

    def sitemap(self, *urls, cierre="</urlset>\n"):
        self.s.escribir("sitemap.xml", self.CAB + "".join(f"<url><loc>{u}</loc></url>\n" for u in urls) + cierre)

    def test_correcto(self):
        self.sitemap("https://terceracamara.es/", "https://terceracamara.es/normas/",
                     "https://terceracamara.es/normas/ley-1.html")
        self.assertEqual(v.comprobar_sitemap(self.s.raiz), [])

    def test_mal_formado(self):
        self.sitemap("https://terceracamara.es/", cierre="</url")
        h = v.comprobar_sitemap(self.s.raiz)
        self.assertEqual(len(h), 1)
        self.assertIn("mal formado", h[0]["detalle"])

    def test_dominio_duplicado_e_inexistente(self):
        self.sitemap("https://terceracamara.es/", "https://terceracamara.es/",
                     "https://boe-digest.github.io/x.html", "https://terceracamara.es/normas/ley-2.html")
        detalles = [x["detalle"] for x in v.comprobar_sitemap(self.s.raiz)]
        self.assertEqual(len(detalles), 3, detalles)
        self.assertTrue(any("duplicada" in d for d in detalles))
        self.assertTrue(any("fuera del dominio" in d for d in detalles))
        self.assertTrue(any("no existe" in d for d in detalles))

    def test_demasiadas_url(self):
        with mock.patch.object(v, "MAX_URLS_SITEMAP", 1):
            self.sitemap("https://terceracamara.es/", "https://terceracamara.es/normas/")
            self.assertIn("máximo", v.comprobar_sitemap(self.s.raiz)[0]["detalle"])

    def test_sin_sitemap(self):
        self.assertEqual(len(v.comprobar_sitemap(self.s.raiz)), 1)


class TestCanonicales(unittest.TestCase):
    CAB = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    URLS = ("https://terceracamara.es/", "https://terceracamara.es/normas/",
            "https://terceracamara.es/normas/ley-1.html", "https://terceracamara.es/mapa/")


    def setUp(self):
        self.s = Sitio()

    def tearDown(self):
        self.s.cerrar()

    def sitemap(self, *urls):
        self.s.escribir("sitemap.xml", self.CAB + "".join(f"<url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n")

    def test_correcto(self):
        self.sitemap(*self.URLS)
        self.assertEqual(v.comprobar_canonicales(self.s.raiz), [])

    def test_sin_sitemap_solo_mira_las_paginas(self):
        self.assertEqual(v.comprobar_canonicales(self.s.raiz), [])

    def test_url_de_pagina(self):
        self.assertEqual(v.url_de_pagina("index.html"), "https://terceracamara.es/")
        self.assertEqual(v.url_de_pagina("normas/index.html"), "https://terceracamara.es/normas/")
        self.assertEqual(v.url_de_pagina("normas/ley-1.html"), "https://terceracamara.es/normas/ley-1.html")

    def test_www_http_e_index(self):
        self.sitemap(*self.URLS)
        for mala in ("https://www.terceracamara.es/mapa/", "http://terceracamara.es/mapa/",
                     "https://terceracamara.es/mapa/index.html", "/mapa/"):
            self.s.escribir("mapa/index.html", pagina(canonical=mala))
            h = v.comprobar_canonicales(self.s.raiz)
            self.assertTrue(any("distinto" in x["detalle"] for x in h), (mala, h))

    def test_dos_o_ningun_canonical(self):
        self.sitemap(*self.URLS)
        doble = pagina(canonical="https://terceracamara.es/mapa/").replace(
            "</head>", '<link rel="canonical" href="https://terceracamara.es/">\n</head>')
        self.s.escribir("mapa/index.html", doble)
        self.assertIn("2 canonicales", v.comprobar_canonicales(self.s.raiz)[0]["detalle"])
        self.s.escribir("mapa/index.html", pagina().replace('<link rel="canonical" href="https://terceracamara.es/normas/">', ""))
        self.assertIn("0 canonicales", v.comprobar_canonicales(self.s.raiz)[0]["detalle"])

    def test_fuera_del_sitemap_y_sitemap_sin_pagina(self):
        self.sitemap(*self.URLS[:3], "https://terceracamara.es/normas/index.html")
        detalles = [x["detalle"] for x in v.comprobar_canonicales(self.s.raiz)]
        self.assertTrue(any("no está en el sitemap" in d for d in detalles), detalles)
        self.assertTrue(any("sin página" in d for d in detalles), detalles)

    def test_fragmento_no_cuenta(self):
        self.sitemap(*self.URLS)
        self.s.escribir("normas/banner.html", "<p>Fragmento</p>")
        self.assertEqual(v.comprobar_canonicales(self.s.raiz), [])

class TestAliasFeed(unittest.TestCase):
    RSS = '<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'

    def setUp(self):
        self.s = Sitio()

    def tearDown(self):
        self.s.cerrar()

    def test_correcto(self):
        self.assertEqual(v.comprobar_alias_feed(self.s.raiz), [])

    def test_alias_ausente_o_distinto(self):
        (self.s.raiz / "rss.xml").unlink()
        self.s.escribir("index.xml", (self.s.raiz / "feed.xml").read_text(encoding="utf-8") + " ")
        detalles = [h["detalle"] for h in v.comprobar_alias_feed(self.s.raiz)]
        self.assertEqual(len(detalles), 2, detalles)

    def test_pagina_sin_enlace_rss(self):
        self.s.escribir("mapa/index.html", re.sub(r'<link rel="alternate"[^>]*>', "",
                                                  pagina(canonical="https://terceracamara.es/mapa/")))
        h = v.comprobar_alias_feed(self.s.raiz)
        self.assertEqual([x["fichero"] for x in h], ["mapa/index.html"])


class TestIndice(unittest.TestCase):
    def setUp(self):
        self.s = Sitio()

    def tearDown(self):
        self.s.cerrar()

    def test_correcto(self):
        self.s.escribir("datos/indice.json", '{"tipos": []}')
        self.s.escribir("datos/indice-norma.json", '{"k": "norma", "items": []}')
        self.assertEqual(v.comprobar_indice(self.s.raiz), [])

    def test_invalido_y_grande(self):
        self.s.escribir("datos/indice.json", '{"tipos": [}')
        self.s.escribir("datos/indice-pregunta-2026-02.json", json.dumps({"x": "a" * 1_000_001}))
        h = v.comprobar_indice(self.s.raiz)
        self.assertEqual(sorted(x["fichero"] for x in h),
                         ["datos/indice-pregunta-2026-02.json", "datos/indice.json"])


class TestTitulares(unittest.TestCase):
    # Titulares rotos que llegaron a publicarse.
    ROTOS = [
        ("SESIÓN DEL ", "preposición"),
        ("SE PUBLICA LA ADENDA DE PRÓRROGA Y MODIFICACIÓN DEL: LA SECRETARÍA DE ESTADO DE "
         "TURISMO, POR LA QUE PUBLICA LA…", "preposición"),
        ("CERTIFICA LA SEGURIDAD DEL PRODUCTO: CENTRO CRIPTOLÓGICO NACIONAL, POR LA QUE SE "
         "CERTIFICA LA…", "preposición"),
        ("REGISTRADO HOY: DSCD-15-PL-204.PDF", "fichero"),
        ("REGISTRADO HOY: BOCG-15-A-113-1.PDF", "fichero"),
        ("VOX LLEVA AL PLENO LA DEFENSA NACIONAL, Y 4 ASUNTOS MÁS", "ASUNTOS MÁS"),
    ]
    BUENOS = [
        "CAMBIAN LOS PRECIOS DEL TABACO EN LOS ESTANCOS",
        "CLIMA DE GALICIA",
        "CERTIFICA LA SEGURIDAD DEL PRODUCTO «PSTGATEWAYS FRAMEWORK VERSION 4.16.8-A»",
        "EL GOBIERNO CONTESTA A ASARTA CUEVAS (Vox) 65 DÍAS DESPUÉS: «Gasto final durante la "
        "presidencia española de la UE»",
        "MATUTE GARCÍA DE JALÓN (EH Bildu) A LA MINISTRA DE TRABAJO Y ECONOMÍA SOCIAL: «¿Propondrán "
        "próximamente la reforma del despido para recuperar indemnizaciones justas y suficientes "
        "para las y los trabajadores?»",
    ]

    def test_rotos(self):
        for titular, motivo in self.ROTOS:
            with self.subTest(titular=titular):
                problemas = v.problemas_titular(titular)
                self.assertTrue(any(n == v.GRAVE and motivo in m for n, m in problemas), problemas)

    def test_buenos(self):
        for titular in self.BUENOS:
            with self.subTest(titular=titular):
                self.assertEqual(v.problemas_titular(titular, titular.upper()), [])

    def test_palabra_cortada(self):
        # Real (2026-09-24): la fuente decía «Economía Aplicada».
        titular = "EL PACTO DE TOLEDO ESCUCHA A FUNDACIÓN DE ESTUDIOS DE ECONOM"
        fuente = "COMPARECENCIA DE LA FUNDACIÓN DE ESTUDIOS DE ECONOMÍA APLICADA (FEDEA)"
        self.assertIn((v.GRAVE, "palabra cortada al final («ECONOM»)"), v.problemas_titular(titular, fuente))
        completo = "EL PACTO DE TOLEDO ESCUCHA A FUNDACIÓN DE ESTUDIOS DE ECONOMÍA APLICADA"
        self.assertEqual(v.problemas_titular(completo, fuente), [])

    def test_longitud(self):
        self.assertEqual(v.problemas_titular("A" * 300)[0][0], v.AVISO)
        self.assertEqual(v.problemas_titular("")[0][0], v.GRAVE)

    def test_edicion(self):
        s = Sitio()
        try:
            s.escribir("data/2026-09-18.json", json.dumps(edicion(
                boe=[{"headline": "CAMBIAN LOS PRECIOS DEL TABACO EN LOS ESTANCOS", "ref": "BOE-A-2026-1"}],
                cortes=[{"headline": "REGISTRADO HOY: DSCD-15-PL-204.PDF", "source": {"url": "u"}}])))
            h = v.comprobar_titulares(s.raiz, "2026-09-18")
            self.assertEqual(len(h), 1)
            self.assertIn("[cortes]", h[0]["detalle"])
            self.assertEqual(v.comprobar_titulares(s.raiz, "2026-09-19")[0]["nivel"], v.AVISO)
        finally:
            s.cerrar()


class TestDuplicados(unittest.TestCase):
    def setUp(self):
        self.s = Sitio()

    def tearDown(self):
        self.s.cerrar()

    def dia(self, fecha, **kw):
        self.s.escribir(f"data/{fecha}.json", json.dumps(edicion(**kw)))

    def test_sin_repetidos(self):
        self.dia("2026-09-25", boe=[{"ref": "BOE-A-1", "headline": "UNO"}])
        self.dia("2026-09-26", boe=[{"ref": "BOE-A-2", "headline": "DOS"}])
        self.assertEqual(v.comprobar_duplicados(self.s.raiz, "2026-09-26"), [])

    def test_identificador_repetido(self):
        # Real: el domingo 27 de septiembre repitió las piezas de Cortes del sábado.
        doc = "https://www.congreso.es/public_oficiales/L15/CONG/DS/PL/DSCD-15-PL-206.PDF"
        self.dia("2026-09-26", cortes=[{"headline": "GRUPO MIXTO LLEVA AL PLENO…", "source": {"url": doc}}])
        self.dia("2026-09-27", cortes=[{"headline": "OTRO", "source": {"url": doc}}])
        h = v.comprobar_duplicados(self.s.raiz, "2026-09-27")
        self.assertEqual([x["nivel"] for x in h], [v.GRAVE])
        self.assertIn("2026-09-26", h[0]["detalle"])

    def test_fuera_de_la_ventana(self):
        self.dia("2026-09-18", boe=[{"ref": "BOE-A-1", "headline": "UNO"}])
        self.dia("2026-09-26", boe=[{"ref": "BOE-A-1", "headline": "UNO"}])
        self.assertEqual(v.comprobar_duplicados(self.s.raiz, "2026-09-26"), [])

    def test_titular_repetido_es_aviso(self):
        t = "CAMBIAN LOS PRECIOS DEL TABACO EN LOS ESTANCOS"
        self.dia("2026-10-01", boe=[{"ref": "BOE-A-2026-20000", "headline": t}])
        self.dia("2026-10-03", boe=[{"ref": "BOE-A-2026-20529", "headline": t}])
        self.assertEqual([x["nivel"] for x in v.comprobar_duplicados(self.s.raiz, "2026-10-03")], [v.AVISO])

    def test_recuento_propio_no_es_duplicado(self):
        url = "https://terceracamara.es/preguntas/#pendientes"
        self.dia("2026-10-03", cortes=[{"headline": "22 PREGUNTAS…", "source": {"url": url}}])
        self.dia("2026-10-04", cortes=[{"headline": "27 PREGUNTAS…", "source": {"url": url}}])
        self.assertEqual(v.comprobar_duplicados(self.s.raiz, "2026-10-04"), [])


class TestTamanos(unittest.TestCase):
    MIB = 1024 ** 2

    def setUp(self):
        self.s = Sitio()

    def tearDown(self):
        self.s.cerrar()

    def tamanos(self, main=0, datos=0):
        return v.comprobar_tamanos(self.s.raiz, main, datos)

    def test_sin_hallazgos(self):
        self.s.escribir("state/congreso.json", "{}")
        self.assertEqual(self.tamanos(61 * self.MIB, 5 * self.MIB), [])

    def test_main(self):
        self.assertEqual(self.tamanos(main=600 * self.MIB)[0]["nivel"], v.AVISO)
        h = self.tamanos(main=1100 * self.MIB)
        self.assertEqual((h[0]["nivel"], h[0]["fichero"]), (v.GRAVE, ".git"))

    def test_rama_datos(self):
        self.assertEqual(self.tamanos(datos=250 * self.MIB)[0]["nivel"], v.AVISO)
        h = self.tamanos(datos=600 * self.MIB)
        self.assertEqual((h[0]["nivel"], h[0]["fichero"]), (v.GRAVE, "datos"))
        self.assertIn("compacta", h[0]["detalle"])

    def test_clon_superficial_usa_la_api(self):
        with mock.patch.object(v, "tamano_ref", return_value=None), \
                mock.patch.dict(os.environ, {"REPO_TAMANO_KB": str(950 * 1024)}):
            h = v.comprobar_tamanos(self.s.raiz, None, 0)
        self.assertEqual([x["nivel"] for x in h], [v.GRAVE])
        self.assertIn("API", h[0]["detalle"])

    def test_tamano_ref_en_un_repositorio_real(self):
        import subprocess
        r = self.s.raiz
        def git(*a):
            subprocess.run(["git", *a], cwd=r, check=True, capture_output=True)
        git("init", "-q"); git("-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q",
                              "--allow-empty", "-m", "x")
        git("-c", "user.email=a@b", "-c", "user.name=a", "add", "-A")
        git("-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "-m", "y")
        self.assertGreater(v.tamano_ref(r, "HEAD"), 0)
        self.assertIsNone(v.tamano_ref(r, "origin/datos"))

    def test_state(self):
        self.s.escribir("state/x.json", "{}")
        with mock.patch.object(v, "STATE_AVISO_BYTES", 1), mock.patch.object(v, "STATE_GRAVE_BYTES", 100):
            self.assertEqual([x["nivel"] for x in self.tamanos()], [v.AVISO])
        with mock.patch.object(v, "STATE_AVISO_BYTES", 1), mock.patch.object(v, "STATE_GRAVE_BYTES", 2):
            self.assertEqual([x["nivel"] for x in self.tamanos()], [v.GRAVE])

    def test_numero_de_ficheros_publicados(self):
        # Cuenta lo de la lista (index.html, feed.xml y sus 2 alias, normas/ ×2, mapa/, CNAME),
        # no state/ ni tests/.
        self.s.escribir("state/a.json", "{}")
        self.s.escribir("tests/b.py", "")
        with mock.patch.object(v, "LISTA_PUBLICABLES", self.s.lista), \
                mock.patch.object(v, "FICHEROS_AVISO", 8), mock.patch.object(v, "FICHEROS_GRAVE", 9):
            h = self.tamanos()
        self.assertEqual([x["nivel"] for x in h], [v.AVISO])
        self.assertIn("8 ficheros publicados", h[0]["detalle"])


class TestCompartir(unittest.TestCase):
    """(j) og:image, twitter:card y el JSON-LD que toca a cada tipo de página."""

    TARJETA = ('<meta property="og:image" content="https://terceracamara.es/assets/og-default.png">'
               '<meta name="twitter:card" content="summary_large_image">')

    def pagina(self, ld, tarjeta=True):
        return ("<!doctype html><html><head>" + (self.TARJETA if tarjeta else "")
                + '<script type="application/ld+json">' + json.dumps(ld) + "</script></head></html>")

    def comprobar(self, rel, texto):
        with tempfile.TemporaryDirectory() as d:
            raiz = pathlib.Path(d)
            f = raiz / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(texto, encoding="utf-8")
            return v.comprobar_compartir(raiz, [f])

    ARTICULO = {"@context": "https://schema.org", "@graph": [{
        "@type": "NewsArticle", "headline": "Edición", "datePublished": "2026-10-26T07:40:00+01:00",
        "url": "https://terceracamara.es/ediciones/2026-10-26.html",
        "image": ["https://terceracamara.es/assets/og-default.png"],
        "publisher": {"@type": "Organization", "name": "La Tercera Cámara"}}]}

    def test_paginas_correctas_pasan(self):
        self.assertEqual(self.comprobar("ediciones/2026-10-26.html", self.pagina(self.ARTICULO)), [])
        self.assertEqual(self.comprobar("index.html", self.pagina(
            {"@type": "WebSite", "name": "La Tercera Cámara", "url": "https://terceracamara.es/"})), [])
        self.assertEqual(self.comprobar("diputados/ana-perez.html", self.pagina(
            {"@type": "ProfilePage", "mainEntity": {"@type": "Person", "name": "Ana Pérez"}})), [])
        # Los índices no son fichas: no se les exige Person.
        self.assertEqual(self.comprobar("diputados/provincia-soria.html", self.pagina({})), [])

    def test_falta_tarjeta(self):
        h = self.comprobar("temas/index.html", self.pagina({}, tarjeta=False))
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0]["nivel"], v.GRAVE)
        self.assertIn("og:image", h[0]["detalle"])
        self.assertIn("twitter:card", h[0]["detalle"])

    def test_tarjeta_pequena_no_vale(self):
        texto = self.pagina({}).replace("summary_large_image", "summary")
        self.assertIn("twitter:card", self.comprobar("mapa/index.html", texto)[0]["detalle"])

    def test_falta_jsonld_de_su_tipo(self):
        self.assertIn("NewsArticle", self.comprobar(
            "ediciones/2026-10-26.html", self.pagina({"@type": "WebSite"}))[0]["detalle"])
        self.assertIn("WebSite", self.comprobar("index.html", self.pagina({}))[0]["detalle"])
        self.assertIn("Person", self.comprobar("personas/ana-perez.html", self.pagina({}))[0]["detalle"])

    def test_articulo_sin_imagen(self):
        ld = json.loads(json.dumps(self.ARTICULO))
        del ld["@graph"][0]["image"]
        h = self.comprobar("ediciones/2026-10-26.html", self.pagina(ld))
        self.assertIn("image", h[0]["detalle"])

    def test_fecha_sin_hora_o_zona_falla(self):
        for malo in ("2026-10-26", "2026-10-26T07:40:00"):
            ld = json.loads(json.dumps(self.ARTICULO))
            ld["@graph"][0]["dateModified"] = malo
            h = self.comprobar("ediciones/2026-10-26.html", self.pagina(ld))
            self.assertEqual(len(h), 1)
            self.assertIn("dateModified", h[0]["detalle"])

    def test_fecha_ld_offset_verano_invierno(self):
        import build
        self.assertEqual(build.fecha_ld("2026-10-24"), "2026-10-24T07:40:00+02:00")
        self.assertEqual(build.fecha_ld("2026-10-26"), "2026-10-26T07:40:00+01:00")
        self.assertEqual(build.fecha_ld("2026-10-26T21:40:00+01:00"), "2026-10-26T21:40:00+01:00")

    def test_fragmento_no_se_exige(self):
        self.assertEqual(self.comprobar("datos/votaciones-banner.html", "<div>x</div>"), [])


class TestEjecucion(unittest.TestCase):
    def setUp(self):
        self.s = Sitio()
        self.s.escribir("sitemap.xml", TestSitemap.CAB + "".join(
            f"<url><loc>{u}</loc></url>" for u in TestCanonicales.URLS) + "</urlset>")
        self.s.escribir("datos/indice.json", "{}")
        self.s.escribir("data/2026-10-04.json", json.dumps(edicion(
            boe=[{"ref": "BOE-A-1", "headline": "CAMBIAN LOS PRECIOS DEL TABACO EN LOS ESTANCOS"}])))
        # La comprobación (i) de la salud diaria tiene sus propias pruebas
        # (test_semana.py); aquí se aísla para contar solo los graves de cada caso.
        self.sin_semana = mock.patch.object(v, "comprobar_semana", return_value=[])
        self.sin_semana.start()
        # Igual con (n) migas, probada en test_migas.py.
        self.sin_migas = mock.patch.object(v, "comprobar_migas", return_value=[])
        self.sin_migas.start()
        # Y con (p) correcciones, probada en test_correcciones.py.
        self.sin_corr = mock.patch.object(v, "comprobar_correcciones", return_value=[])
        self.sin_corr.start()
        # Y con (o) enlazado, probada en test_enlazado.py.
        self.sin_enlazado = mock.patch.object(v, "comprobar_enlazado", return_value=[])
        self.sin_enlazado.start()

    def tearDown(self):
        self.sin_semana.stop()
        self.sin_migas.stop()
        self.sin_corr.stop()
        self.sin_enlazado.stop()
        self.s.cerrar()

    def test_ci_verde(self):
        salida = self.s.raiz / "informe.json"
        with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": "", "GITHUB_OUTPUT": ""}), \
                mock.patch("sys.stdout"):
            codigo = v.main(["--modo", "ci", "--raiz", str(self.s.raiz), "--salida", str(salida)])
        self.assertEqual(codigo, 0)
        informe = json.loads(salida.read_text(encoding="utf-8"))
        self.assertEqual((informe["graves"], informe["fecha"]), (0, "2026-10-04"))

    def test_forzar_grave(self):
        resumen = self.s.raiz / "resumen.md"
        salidas = self.s.raiz / "salidas.txt"
        entorno = {"SALUD_FORZAR_GRAVE": "1", "GITHUB_STEP_SUMMARY": str(resumen),
                   "GITHUB_OUTPUT": str(salidas)}
        with mock.patch.dict(os.environ, entorno), mock.patch("sys.stdout"):
            ci = v.main(["--modo", "ci", "--raiz", str(self.s.raiz)])
            diario = v.main(["--modo", "diario", "--raiz", str(self.s.raiz), "--fecha", "2026-10-04"])
        self.assertEqual((ci, diario), (1, 0))        # el diario informa, no bloquea
        salud = json.loads((self.s.raiz / "debug" / "salud.json").read_text(encoding="utf-8"))
        self.assertEqual(salud["graves"], 1)
        self.assertEqual(salud["hallazgos"][0]["comprobacion"], "forzado")
        self.assertIn("graves=1", salidas.read_text(encoding="utf-8"))
        self.assertIn("forzado", resumen.read_text(encoding="utf-8"))

    def test_datos_no_bloquean_el_ci(self):
        # Un titular roto en la última edición: aviso en el CI, grave en la salud diaria.
        self.s.escribir("data/2026-10-04.json", json.dumps(edicion(
            boe=[{"ref": "BOE-A-1", "headline": "REGISTRADO HOY: DSCD-15-PL-204.PDF"}])))
        ci = v.ejecutar(self.s.raiz, "ci")
        diario = v.ejecutar(self.s.raiz, "diario")
        self.assertEqual((ci["graves"], diario["graves"]), (0, 1))
        self.assertIn("no bloquea el CI", ci["hallazgos"][0]["detalle"])
        self.assertEqual(ci["hallazgos"][0]["nivel"], v.AVISO)

    def test_una_comprobacion_que_revienta_es_grave(self):
        with mock.patch.object(v, "comprobar_indice", side_effect=RuntimeError("roto")):
            informe = v.ejecutar(self.s.raiz, "ci")
        self.assertEqual(informe["graves"], 1)
        self.assertEqual(informe["hallazgos"][0]["comprobacion"], "indice")

    def test_forma_de_los_hallazgos(self):
        with mock.patch.dict(os.environ, {"SALUD_FORZAR_GRAVE": "1"}):
            informe = v.ejecutar(self.s.raiz, "diario", "2026-10-04")
        for h in informe["hallazgos"]:
            self.assertEqual(set(h), {"nivel", "comprobacion", "detalle", "fichero"})
            if h["nivel"] == v.GRAVE:
                self.assertIn("Qué hacer:", h["detalle"])


if __name__ == "__main__":
    unittest.main()


class TestBoletin(unittest.TestCase):
    """TC-024: ninguna página promete un boletín; solo RSS."""

    def _pagina(self, cuerpo, meta=""):
        return (f'<!doctype html><html><head><title>t</title>{meta}</head>'
                f'<body><main>{cuerpo}</main></body></html>')

    def test_promesas_fallan(self):
        for frase in ("Estamos preparando un boletín semanal propio.",
                      "No hay boletín por correo, publicidad ni cuentas.",
                      "Apúntate a nuestro boletín."):
            with self.subTest(frase=frase):
                self.assertTrue(v.problemas_boletin(self._pagina(f"<p>{frase}</p>")))

    def test_meta_description_cuenta(self):
        meta = '<meta name="description" content="Recibe el boletín cada lunes">'
        self.assertTrue(v.problemas_boletin(self._pagina("<p>hola</p>", meta)))

    def test_permitidos_pasan(self):
        for frase in ("Basado en datos de la Agencia Estatal Boletín Oficial del Estado.",
                      "Publicado en el Boletín de las Cortes Generales.",
                      "Por ahora no hay boletín por correo.",
                      "No cubre los boletines oficiales provinciales."):
            with self.subTest(frase=frase):
                self.assertEqual(v.problemas_boletin(self._pagina(f"<p>{frase}</p>")), [])

    def test_texto_de_la_fuente_no_cuenta(self):
        cuerpo = ('<div class="articlebody"><p>según el boletín municipal</p></div>'
                  '<blockquote>el boletín</blockquote><p>dijo «nuestro boletín»</p>')
        self.assertEqual(v.problemas_boletin(self._pagina(cuerpo)), [])

    def test_comprobar_boletin_en_disco(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = pathlib.Path(d)
            (raiz / "mal.html").write_text(self._pagina("<p>Suscríbete al boletín</p>"), encoding="utf-8")
            (raiz / "bien.html").write_text(self._pagina("<p>Boletín Oficial del Estado</p>"), encoding="utf-8")
            h = v.comprobar_boletin(raiz, [raiz / "mal.html", raiz / "bien.html"])
            self.assertEqual(len(h), 1)
            self.assertEqual(h[0]["gravedad"] if "gravedad" in h[0] else v.GRAVE, v.GRAVE)

    def test_paginas_fijas_sin_promesas(self):
        sys.path.insert(0, str(RAIZ_REPO))
        import paginas_fijas
        for nombre in dir(paginas_fijas):
            valor = getattr(paginas_fijas, nombre)
            if isinstance(valor, str) and "<" in valor:
                with self.subTest(constante=nombre):
                    self.assertEqual(v.problemas_boletin(valor), [])
