"""Pruebas de tools/verificar.py, sin red.

`python -m unittest tests.test_verificar`. Cada comprobación tiene un caso que
pasa y otro que falla. Los titulares rotos son reales: salieron publicados
antes de que existiera el verificador (las fechas van en los comentarios de
tools/verificar.py).
"""
import json
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
<script type="application/ld+json">{jsonld}</script>
<script>if (typeof x === "undefined" || isNaN(y)) {{}}</script>
</head><body>{cuerpo}</body></html>
"""

BUILD = '''
ROOT = pathlib.Path(__file__).parent
INDEXNOW_KEY = "abc123"
'''

PUBLICABLES = """# lista de prueba
!index.html
sitemap*.xml
!normas
mapa
!CNAME
robots.txt
abc123.txt
"""


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
        self.escribir("index.html", pagina(canonical="https://terceracamara.es/",
                                           cuerpo='<a href="/normas/">Normas</a>'))
        self.escribir("normas/index.html", pagina(cuerpo='<a href="/mapa/">Mapa</a> '
                                                         '<a href="ley-1.html">Ley</a>'))
        self.escribir("normas/ley-1.html", pagina(canonical="https://terceracamara.es/normas/ley-1.html",
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
        # robots.txt y la clave de IndexNow están en la lista; feed.xml y
        # googleXXX.html no: deben salir los dos.
        for f in ("robots.txt", "abc123.txt", "feed.xml", "google0a1b.html", "requirements.txt",
                  "template.html"):
            self.s.escribir(f, "x")
        self.assertEqual(sorted(h["detalle"].split("«")[1].split("»")[0] for h in self.carpetas()),
                         ["feed.xml", "google0a1b.html"])

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
        # Cuenta lo de la lista (index.html, normas/ ×2, mapa/, CNAME), no state/ ni tests/.
        self.s.escribir("state/a.json", "{}")
        self.s.escribir("tests/b.py", "")
        with mock.patch.object(v, "LISTA_PUBLICABLES", self.s.lista), \
                mock.patch.object(v, "FICHEROS_AVISO", 5), mock.patch.object(v, "FICHEROS_GRAVE", 6):
            h = self.tamanos()
        self.assertEqual([x["nivel"] for x in h], [v.AVISO])
        self.assertIn("5 ficheros publicados", h[0]["detalle"])


class TestEjecucion(unittest.TestCase):
    def setUp(self):
        self.s = Sitio()
        self.s.escribir("sitemap.xml", TestSitemap.CAB + "<url><loc>https://terceracamara.es/</loc></url></urlset>")
        self.s.escribir("datos/indice.json", "{}")
        self.s.escribir("data/2026-10-04.json", json.dumps(edicion(
            boe=[{"ref": "BOE-A-1", "headline": "CAMBIAN LOS PRECIOS DEL TABACO EN LOS ESTANCOS"}])))
        # La comprobación (i) de la salud diaria tiene sus propias pruebas
        # (test_semana.py); aquí se aísla para contar solo los graves de cada caso.
        self.sin_semana = mock.patch.object(v, "comprobar_semana", return_value=[])
        self.sin_semana.start()

    def tearDown(self):
        self.sin_semana.stop()
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
