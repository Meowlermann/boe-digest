"""Marca por pieza en titulares/entradillas de Gemini (tanda 7b)."""
import pathlib
import tempfile
import unittest
from unittest import mock

import build
import paginas_fijas as pf

ROOT = pathlib.Path(__file__).resolve().parent.parent
MARCA = build.MARCA_IA_TEXTO


class TextoYAviso(unittest.TestCase):
    def test_texto_marca(self):
        self.assertEqual(MARCA, "Titular con IA · Texto oficial en el BOE →")
        self.assertNotIn("subray", MARCA.lower())

    def test_aviso_legal(self):
        self.assertIn("Gemini", pf.AVISO_LEGAL)
        self.assertIn("resumen automático sin IA", pf.AVISO_LEGAL)
        self.assertNotIn("redacción determinista", pf.AVISO_LEGAL)
        self.assertIn("en cada pieza", pf.AVISO_LEGAL)
        self.assertNotIn("al pie de cada edición", pf.AVISO_LEGAL)
        self.assertNotIn("revisados por la redacción", pf.AVISO_LEGAL)
        self.assertNotIn("ayuda de IA", pf.AVISO_LEGAL)
        self.assertIn("Titulares y entradillas redactados con IA a partir del BOE", pf.AVISO_LEGAL)
        self.assertEqual(pf.CONTACTO, "contacto@terceracamara.es")
        self.assertNotIn("@gmail", pf.AVISO_LEGAL)
        self.assertIn("sección Parlamento", pf.AVISO_LEGAL)
        self.assertIn("preguntas, votaciones, diputados", pf.AVISO_LEGAL)
        self.assertIn("Cortes", pf.AVISO_LEGAL)
        self.assertIn("sí pueden llevar titular de IA y lo marcan", pf.AVISO_LEGAL)
        self.assertNotIn("Los titulares de las Cortes (preguntas, votaciones)", pf.AVISO_LEGAL)


class MarcaPorPieza(unittest.TestCase):
    def test_con_ia_lleva_marca_y_enlace_boe(self):
        s = {"redaccion_ia": True, "url": "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-1"}
        html = build.marca_ia_html(s)
        self.assertIn('class="srclink ia-pieza"', html)
        self.assertIn(MARCA, html)
        self.assertIn("https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-1", html)
        self.assertNotIn("Ficha completa", html)  # la ficha va aparte

    def test_sin_ia_no_lleva_marca(self):
        self.assertEqual(build.marca_ia_html({"url": "https://www.boe.es/x"}), "")
        self.assertEqual(build.marca_ia_html({"redaccion_ia": False, "url": "https://x"}), "")
        self.assertEqual(build.marca_ia_html({}), "")

    def test_pie_integra_marca_y_ficha_sin_duplicar(self):
        s = {"redaccion_ia": True, "url": "https://www.boe.es/x", "ref": "BOE-A-2026-1"}
        pie = build.pie_enlaces_boe(s)
        self.assertEqual(pie.count("Ficha completa"), 1)
        self.assertIn("ia-pieza", pie)
        self.assertIn("fichalink", pie)
        # Sin IA: solo ficha
        self.assertEqual(build.pie_enlaces_boe({"ref": "BOE-A-2026-1"}).count("ia-pieza"), 0)
        self.assertIn("Ficha completa", build.pie_enlaces_boe({"ref": "BOE-A-2026-1"}))

    def test_grid_edicion_marca_segun_flag(self):
        day = {"id": "2026-11-09", "boe": {"stories": [
            {"headline": "CON IA", "standfirst": "e", "dept": "X", "ref": "BOE-A-2026-1",
             "url": "https://www.boe.es/x", "cat": "otros", "size": "md", "redaccion_ia": True},
            {"headline": "SIN IA", "standfirst": "e", "dept": "Y", "ref": "BOE-A-2026-2",
             "url": "https://www.boe.es/y", "cat": "otros", "size": "md"},
        ]}}
        html = build.render_boe_grid_ssr(day)
        # Solo la pieza con IA
        self.assertEqual(html.count("ia-pieza"), 1)
        self.assertIn("CON IA", html)
        # La de sin IA no tiene la marca entre su h3 y su foot
        i = html.index("SIN IA")
        trozo = html[i:i + 500]
        self.assertNotIn("ia-pieza", trozo)

    def test_linea_global_retirada(self):
        self.assertEqual(build.etiqueta_ia_html(True), "")
        self.assertEqual(build.etiqueta_ia_html(False), "")


if __name__ == "__main__":
    unittest.main()


class ListasConMarca(unittest.TestCase):
    """Índice de normas, archivo y buscador: marca solo si redaccion_ia."""

    def test_marca_enlaza_txt_php_del_ref(self):
        s = {"redaccion_ia": True, "ref": "BOE-A-2026-23384",
             "url": "https://www.boe.es/boe/dias/2026/11/09/pdfs/BOE-A-2026-23384.pdf"}
        html = build.marca_ia_html(s)
        self.assertIn("https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-23384", html)
        self.assertNotIn("/pdfs/", html)
        self.assertIn(MARCA, html)

    def test_marca_corta_sin_enlace(self):
        self.assertEqual(build.MARCA_IA_CORTA, "Titular con IA")
        html = build.marca_ia_corta_html({"redaccion_ia": True})
        self.assertEqual(html, '<span class="ia-pieza">Titular con IA</span>')
        self.assertNotIn("href=", html)
        self.assertEqual(build.marca_ia_corta_html({"redaccion_ia": False}), "")
        self.assertEqual(build.marca_ia_corta_html(con_ia=False), "")
        self.assertIn("Titular con IA", build.marca_ia_corta_html(con_ia=True))

    def test_archivo_marca_solo_si_lead_con_ia(self):
        import indices as ix  # noqa: F401
        dia_ia = {"id": "2026-11-09", "boe": {"stories": [
            {"headline": "TITULAR GEMINI DEL DÍA", "size": "lead", "redaccion_ia": True,
             "ref": "BOE-A-2026-1", "url": "https://www.boe.es/x", "cat": "otros"}]}}
        dia_no = {"id": "2026-11-08", "boe": {"stories": [
            {"headline": "TITULAR DETERMINISTA", "size": "lead",
             "ref": "BOE-A-2026-2", "url": "https://www.boe.es/y", "cat": "otros"}]}}
        entradas = [{"id": "2026-11-09", "url": "https://x/ediciones/2026-11-09.html"},
                    {"id": "2026-11-08", "url": "https://x/ediciones/2026-11-08.html"}]
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            ed = root / "ediciones"
            ed.mkdir()
            plant = (ROOT / "template_archivo.html").read_text(encoding="utf-8")
            with mock.patch.object(build, "EDICIONES_DIR", ed), \
                 mock.patch.object(build, "TEMPLATE_ARCHIVO", ROOT / "template_archivo.html"), \
                 mock.patch.object(build, "escribir_si_cambia",
                                   lambda path, texto: path.write_text(texto, encoding="utf-8")):
                build.renderizar_archivo(entradas, [dia_ia, dia_no])
            html = (ed / "index.html").read_text(encoding="utf-8")
        self.assertIn("TITULAR GEMINI DEL DÍA", html)
        self.assertIn("TITULAR DETERMINISTA", html)
        # La nota de lista mezclada cita la marca; la marca corta solo va junto al día con IA.
        self.assertIn(build.ARCHIVO_NOTA_TITULARES_MEZCLA, html)
        self.assertNotIn("sin IA", html)
        self.assertEqual(html.count("Titular con IA"), 2)
        self.assertNotIn("Texto oficial en el BOE", html)  # corta, sin enlace BOE
        i_ia = html.index("TITULAR GEMINI DEL DÍA")
        i_no = html.index("TITULAR DETERMINISTA")
        self.assertIn("ia-pieza", html[i_ia:i_ia + 200])
        self.assertNotIn("ia-pieza", html[i_no:i_no + 200])

    def test_indice_normas_despues_con_marca(self):
        import indices as ix
        x = {"headline": "CON IA", "ref": "BOE-A-2026-1", "dept": "Hacienda",
             "cat": "otros", "redaccion_ia": True,
             "url": "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-1"}
        despues = build.marca_ia_wrap(x)
        html = ix.fila("BOE-A-2026-1.html", x["headline"],
                       [ix.etiqueta("Otros", "ix-cat")],
                       tipo="otros", color="otros", clase="ix-norma",
                       despues=despues)
        self.assertIn("ia-pieza", html)
        self.assertIn("txt.php?id=BOE-A-2026-1", html)
        self.assertIn("CON IA", html)

    def test_nota_archivo_segun_haya_filas_con_ia(self):
        self.assertEqual(
            build.ARCHIVO_NOTA_TITULARES,
            "Títulos del resumen automático, sin IA; "
            "el titular de cada pieza puede variar dentro de la edición",
        )
        dia_no = {"id": "2026-11-07", "boe": {"stories": [
            {"headline": "CAMBIAN LOS PRECIOS DEL TABACO EN LOS ESTANCOS", "size": "lead",
             "ref": "BOE-A-2026-23341"}]}}
        html = build.nota_archivo_titulares_html(["2026-11-07"], {"2026-11-07": dia_no})
        self.assertIn("archivo-nota-ia", html)
        self.assertIn(build.ARCHIVO_NOTA_TITULARES, html)

        dia_ia = {"id": "2026-11-09", "boe": {"stories": [
            {"headline": "TITULAR GEMINI", "size": "lead", "redaccion_ia": True,
             "ref": "BOE-A-2026-1"}]}}
        # Página mezclada: línea cierta, nunca «sin IA».
        mezcla = build.nota_archivo_titulares_html(
            ["2026-11-09", "2026-11-07"], {"2026-11-09": dia_ia, "2026-11-07": dia_no})
        self.assertIn(build.ARCHIVO_NOTA_TITULARES_MEZCLA, mezcla)
        self.assertIn("«Titular con IA»", mezcla)
        self.assertNotIn("sin IA", mezcla)

        # Todas las filas con IA: texto equivalente, tampoco «sin IA».
        todo = build.nota_archivo_titulares_html(["2026-11-09"], {"2026-11-09": dia_ia})
        self.assertIn(build.ARCHIVO_NOTA_TITULARES_TODO_IA, todo)
        self.assertNotIn("sin IA", todo)
        self.assertNotIn(build.ARCHIVO_NOTA_TITULARES, todo)
        self.assertNotIn(build.ARCHIVO_NOTA_TITULARES, mezcla)

    def test_archivo_render_incluye_nota_cuando_sin_ia(self):
        dia_no = {"id": "2026-11-07", "boe": {"stories": [
            {"headline": "CAMBIAN LOS PRECIOS DEL TABACO EN LOS ESTANCOS", "size": "lead",
             "ref": "BOE-A-2026-23341", "url": "https://www.boe.es/x", "cat": "otros"}]}}
        entradas = [{"id": "2026-11-07", "url": "https://x/ediciones/2026-11-07.html"}]
        with tempfile.TemporaryDirectory() as tmp:
            ed = pathlib.Path(tmp) / "ediciones"
            ed.mkdir()
            with mock.patch.object(build, "EDICIONES_DIR", ed), \
                 mock.patch.object(build, "TEMPLATE_ARCHIVO", ROOT / "template_archivo.html"), \
                 mock.patch.object(build, "escribir_si_cambia",
                                   lambda path, texto: path.write_text(texto, encoding="utf-8")):
                build.renderizar_archivo(entradas, [dia_no])
            html = (ed / "index.html").read_text(encoding="utf-8")
        self.assertIn(build.ARCHIVO_NOTA_TITULARES, html)
        self.assertIn("archivo-nota-ia", html)
        self.assertNotIn(">Titular con IA<", html)

    def test_archivo_render_mezcla_linea_y_marca(self):
        dia_ia = {"id": "2026-10-15", "boe": {"stories": [
            {"headline": "TITULAR GEMINI DEL DÍA", "size": "lead", "redaccion_ia": True,
             "ref": "BOE-A-2026-1", "url": "https://www.boe.es/x", "cat": "otros"}]}}
        dia_no = {"id": "2026-10-14", "boe": {"stories": [
            {"headline": "TITULAR DETERMINISTA", "size": "lead",
             "ref": "BOE-A-2026-2", "url": "https://www.boe.es/y", "cat": "otros"}]}}
        entradas = [{"id": "2026-10-15", "url": "https://x/ediciones/2026-10-15.html"},
                    {"id": "2026-10-14", "url": "https://x/ediciones/2026-10-14.html"}]
        with tempfile.TemporaryDirectory() as tmp:
            ed = pathlib.Path(tmp) / "ediciones"
            ed.mkdir()
            with mock.patch.object(build, "EDICIONES_DIR", ed), \
                 mock.patch.object(build, "TEMPLATE_ARCHIVO", ROOT / "template_archivo.html"), \
                 mock.patch.object(build, "escribir_si_cambia",
                                   lambda path, texto: path.write_text(texto, encoding="utf-8")):
                build.renderizar_archivo(entradas, [dia_ia, dia_no])
            indice = (ed / "index.html").read_text(encoding="utf-8")
            octubre = (ed / "2026-10.html").read_text(encoding="utf-8")
        for html, nombre in ((indice, "índice"), (octubre, "octubre")):
            self.assertIn(build.ARCHIVO_NOTA_TITULARES_MEZCLA, html, nombre)
            self.assertNotIn("sin IA", html, nombre)
            self.assertEqual(html.count("Titular con IA"), 2, nombre)  # nota + marca de la fila
            self.assertIn("TITULAR GEMINI DEL DÍA", html)
            self.assertIn("TITULAR DETERMINISTA", html)
            # El pie habla de cada edición, no de la lista: no se contradicen.
            self.assertIn("En cada edición, titulares y entradillas redactados con IA", html)

    def test_buscar_marca_completa_con_txt_php(self):
        html = build.marca_ia_html({"redaccion_ia": True, "ref": "BOE-A-2026-23384"})
        self.assertEqual(html.count(build.MARCA_IA_TEXTO), 1)
        self.assertIn("https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-23384", html)
        src = (ROOT / "app" / "buscar.jsx").read_text(encoding="utf-8")
        self.assertIn("Titular con IA · Texto oficial en el BOE →", src)
        self.assertIn("txt.php?id=", src)
        self.assertIn("item.r", src)


if __name__ == "__main__":
    unittest.main()
