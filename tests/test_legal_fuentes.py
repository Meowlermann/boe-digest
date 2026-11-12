"""Aviso legal y citas de fuente (tanda legal, noviembre de 2026)."""
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import build
import paginas_fijas as pf

ROOT = pathlib.Path(__file__).resolve().parent.parent
LEMA = "Titulares y entradillas redactados con IA a partir del BOE; el texto oficial está enlazado"


class FuenteConFecha(unittest.TestCase):
    def test_anade_fecha_si_cita_congreso(self):
        f = build._fuente_con_fecha("Fuente: datos abiertos del Congreso de los Diputados.", "02/11/2026")
        self.assertEqual(f, "Fuente: datos abiertos del Congreso de los Diputados. "
                            "Datos del Congreso actualizados el 02/11/2026.")

    def test_no_toca_otras_fuentes_ni_repite(self):
        self.assertEqual(build._fuente_con_fecha("Fuente: Boletín Oficial del Estado.", "02/11/2026"),
                         "Fuente: Boletín Oficial del Estado.")
        ya = "Fuente: Congreso. Datos del Congreso actualizados el 01/11/2026."
        self.assertEqual(build._fuente_con_fecha(ya, "02/11/2026"), ya)

    def test_sin_fecha_no_inventa(self):
        self.assertEqual(build._fuente_con_fecha("Fuente: Congreso.", ""), "Fuente: Congreso.")

    def test_fecha_sale_del_estado(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = pathlib.Path(d) / "congreso.json"
            ruta.write_text(json.dumps({"dias_mirados": ["31/12/2025", "02/11/2026", "30/10/2026"]}))
            with mock.patch.object(build, "ESTADO_CONGRESO", ruta):
                self.assertEqual(build.fecha_datos_congreso(), "02/11/2026")
            with mock.patch.object(build, "ESTADO_CONGRESO", pathlib.Path(d) / "no.json"):
                self.assertEqual(build.fecha_datos_congreso(), "")


class AvisoLegal(unittest.TestCase):
    def test_lema_ia_en_aviso_y_plantillas(self):
        self.assertIn(LEMA, pf.AVISO_LEGAL)
        plantillas = (
            "template_edicion.html",
            "template.html",
            "template_archivo.html",
            "template_norma.html",
        )
        for t in plantillas:
            self.assertIn(LEMA, (ROOT / t).read_text(encoding="utf-8"), t)
        # La frase antigua, que atribuía una revisión humana, no debe quedar
        # en el aviso ni en los pies visibles del sitio.
        textos = [pf.AVISO_LEGAL] + [(ROOT / t).read_text(encoding="utf-8") for t in plantillas]
        for texto in textos:
            self.assertNotIn("revisados por la redacción", texto)
            self.assertNotIn("ayuda de IA", texto)
            self.assertNotIn("Titulares generados con IA", texto)

    def test_cloudflare_sin_cookies(self):
        self.assertIn("Cloudflare Web Analytics", pf.AVISO_LEGAL)
        self.assertIn("no usa cookies", pf.AVISO_LEGAL)

    def test_senado_y_condiciones(self):
        self.assertNotIn("no se recoge", pf.AVISO_LEGAL)
        self.assertIn("senado.es/web/avisojuridico", pf.AVISO_LEGAL)
        self.assertIn("congreso.es/cem/aviso-legal", pf.AVISO_LEGAL)
        self.assertIn("lo patrocina ni lo respalda", pf.AVISO_LEGAL)

    def test_revision_del_aviso(self):
        self.assertEqual(pf.REVISION_AVISO, "2026-11-12")
        self.assertEqual(pf.REVISION, "2026-11-02")
        self.assertEqual(build.fmt_date_es(pf.REVISION_AVISO), "jueves, 12 de noviembre de 2026")

    def test_sin_datos_personales(self):
        self.assertNotIn("@gmail", pf.AVISO_LEGAL)
        self.assertEqual(pf.CONTACTO, "contacto@terceracamara.es")


if __name__ == "__main__":
    unittest.main()
