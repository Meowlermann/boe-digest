"""Etiqueta visible en páginas con titulares/entradillas de Gemini (tanda 7)."""
import pathlib
import tempfile
import unittest
from unittest import mock

import build
import paginas_fijas as pf

ROOT = pathlib.Path(__file__).resolve().parent.parent
ETIQUETA = build.ETIQUETA_IA_TEXTO
PLANTILLAS = ("template.html", "template_edicion.html", "template_norma.html",
              "template_archivo.html")


class TextoYPlantillas(unittest.TestCase):
    def test_texto_cubre_titular_y_entradilla(self):
        # Gemini escribe ambos (redaccion.py); el propuesto solo decía titulares.
        self.assertIn("Titulares y entradillas", ETIQUETA)
        self.assertIn("BOE", ETIQUETA)
        self.assertIn("enlazado", ETIQUETA)
        self.assertNotIn("subray", ETIQUETA.lower())

    def test_html_solo_si_hay_ia(self):
        self.assertIn('class="ia-etiqueta"', build.etiqueta_ia_html(True))
        self.assertIn(ETIQUETA, build.etiqueta_ia_html(True))
        self.assertEqual(build.etiqueta_ia_html(False), "")

    def test_plantillas_tienen_marcador(self):
        for t in PLANTILLAS:
            self.assertIn("__SSR_IA_ETIQUETA__", (ROOT / t).read_text(encoding="utf-8"), t)

    def test_aviso_explica_gemini(self):
        self.assertIn("Gemini", pf.AVISO_LEGAL)
        self.assertIn("titular", pf.AVISO_LEGAL.lower())
        self.assertIn("entradilla", pf.AVISO_LEGAL.lower())
        self.assertIn(pf.CONTACTO, pf.AVISO_LEGAL)
        self.assertNotIn("@gmail", pf.AVISO_LEGAL)


class PaginasConIA(unittest.TestCase):
    """Falla si una página generada con titulares de IA no lleva la etiqueta."""

    def test_dia_con_ia(self):
        self.assertFalse(build.dia_con_ia({"boe": {"stories": [{"headline": "X"}]}}))
        self.assertTrue(build.dia_con_ia(
            {"boe": {"stories": [{"headline": "X", "redaccion_ia": True}]}}))

    def test_edicion_con_ia_lleva_etiqueta(self):
        plantilla = (ROOT / "template_edicion.html").read_text(encoding="utf-8")
        # Frag mínimo: el resto de marcadores se borran en _replace_placeholders.
        frag = {
            "TITLE": "t", "META_DESC": "d", "CANONICAL": "https://terceracamara.es/x",
            "JSONLD": "", "EDITION_DATE": "X", "LABEL_LARGO": "x",
            "BOE_STATS": "", "BOE_GRID": "<h3>TITULAR IA</h3>", "BOE_NOTE": "",
            "NOMBRAMIENTOS": "", "ARCHIVO_AVISO": "", "CORTES_HIDDEN": "hidden",
            "COVERAGE_HIDDEN": "hidden", "COVERAGE_NOTE": "", "CHAMBER_CARDS": "",
            "SCOREBOARD_HIDDEN": "hidden", "SCOREBOARD": "", "CORTES_FEED": "",
            "PREV_LINK": "", "NEXT_LINK": "",
            "IA_ETIQUETA": build.etiqueta_ia_html(True),
        }
        with mock.patch.object(build, "render_nav", return_value=""), \
             mock.patch.object(build, "baliza_analitica", return_value=""):
            html = build._replace_placeholders(plantilla, frag)
        self.assertIn('class="ia-etiqueta"', html)
        self.assertIn(ETIQUETA, html)
        self.assertNotIn("__SSR_IA_ETIQUETA__", html)

    def test_edicion_sin_ia_no_lleva_etiqueta(self):
        plantilla = (ROOT / "template_edicion.html").read_text(encoding="utf-8")
        frag = {
            "TITLE": "t", "META_DESC": "d", "CANONICAL": "https://terceracamara.es/x",
            "JSONLD": "", "EDITION_DATE": "X", "LABEL_LARGO": "x",
            "BOE_STATS": "", "BOE_GRID": "", "BOE_NOTE": "", "NOMBRAMIENTOS": "",
            "ARCHIVO_AVISO": "", "CORTES_HIDDEN": "hidden", "COVERAGE_HIDDEN": "hidden",
            "COVERAGE_NOTE": "", "CHAMBER_CARDS": "", "SCOREBOARD_HIDDEN": "hidden",
            "SCOREBOARD": "", "CORTES_FEED": "", "PREV_LINK": "", "NEXT_LINK": "",
            "IA_ETIQUETA": build.etiqueta_ia_html(False),
        }
        with mock.patch.object(build, "render_nav", return_value=""), \
             mock.patch.object(build, "baliza_analitica", return_value=""):
            html = build._replace_placeholders(plantilla, frag)
        self.assertNotIn('class="ia-etiqueta"', html)
        self.assertNotIn("__SSR_IA_ETIQUETA__", html)

    def test_render_pone_etiqueta_segun_flag(self):
        """El camino real de edición rellena IA_ETIQUETA según redaccion_ia."""
        vistos = []

        def fake_replace(plantilla, frag):
            vistos.append(frag.get("IA_ETIQUETA", "FALTA"))
            return "<html></html>"

        dia_ia = {
            "id": "2026-11-07",
            "boe": {"stories": [{"headline": "H", "redaccion_ia": True, "ref": "BOE-A-2026-1",
                                 "url": "https://www.boe.es/x", "cat": "otros"}]},
            "cortes": {"feed": []},
        }
        dia_no = {
            "id": "2026-11-06",
            "boe": {"stories": [{"headline": "H", "ref": "BOE-A-2026-2",
                                 "url": "https://www.boe.es/y", "cat": "otros"}]},
            "cortes": {"feed": []},
        }
        with tempfile.TemporaryDirectory() as d:
            base = pathlib.Path(d)
            (base / "data").mkdir()
            (base / "state").mkdir()
            for x in (dia_ia, dia_no):
                (base / "data" / f"{x['id']}.json").write_text("{}", encoding="utf-8")
            parches = [
                mock.patch.object(build, "EDICIONES_DIR", base / "ediciones"),
                mock.patch.object(build, "DATA_DIR", base / "data"),
                mock.patch.object(build, "ESTADO", base / "state"),
                mock.patch.object(build, "MANIFIESTO", base / "state" / "ediciones.json"),
                mock.patch.object(build, "HUELLAS", base / "state" / "ediciones_huellas.json"),
                mock.patch.object(build, "render_ssr_fragments",
                                  lambda day: {"BOE_STATS": "", "BOE_GRID": "", "BOE_NOTE": "",
                                               "NOMBRAMIENTOS": "", "CHAMBER_CARDS": "",
                                               "SCOREBOARD": "", "CORTES_FEED": "",
                                               "COVERAGE_NOTE": "", "EDITION_DATE": "X"}),
                mock.patch.object(build, "jsonld_for_day", lambda day, url: ""),
                mock.patch.object(build, "_replace_placeholders", fake_replace),
                mock.patch("sys.stdout"),
            ]
            for p in parches:
                p.start()
            try:
                build.renderizar_ediciones([dia_ia, dia_no])
            finally:
                for p in parches:
                    p.stop()
        self.assertEqual(len(vistos), 2)
        self.assertEqual(vistos[0], "")      # 2026-11-06 sin IA (orden por id)
        self.assertIn(ETIQUETA, vistos[1])   # 2026-11-07 con IA


if __name__ == "__main__":
    unittest.main()
