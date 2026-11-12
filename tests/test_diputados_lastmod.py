"""Lastmod del sitemap de diputados: última actividad, nunca la del barrido."""
import pathlib
import unittest

import build

HOY = "2026-11-12"
FUENTE = "Fuente: datos abiertos del Congreso. Datos del Congreso actualizados el 12/11/2026."


def ficha(**kwargs):
    base = {
        "clave": "perez garcia ana",
        "alta": "08/08/2023",
        "ultimos_votos": [],
        "ultimas_intervenciones": [],
    }
    base.update(kwargs)
    return base


class FechaIsoFlex(unittest.TestCase):
    def test_formatos(self):
        self.assertEqual(build.fecha_iso_flex("2026-09-30"), "2026-09-30")
        self.assertEqual(build.fecha_iso_flex("30/9/2026"), "2026-09-30")
        self.assertEqual(build.fecha_iso_flex("08/08/2023"), "2023-08-08")
        self.assertEqual(build.fecha_iso_flex("16/10/2026"), "2026-10-16")
        self.assertEqual(build.fecha_iso_flex(""), "")
        self.assertEqual(build.fecha_iso_flex("no es una fecha"), "")
        self.assertEqual(build.fecha_iso_flex("32/13/2026"), "")


class LastmodDiputado(unittest.TestCase):
    def test_ultima_votacion(self):
        f = ficha(ultimos_votos=[
            {"fecha": "2026-09-30"},
            {"fecha": "15/9/2026"},
        ], ultimas_intervenciones=[{"fecha": "10/09/2026"}])
        self.assertEqual(build.lastmod_diputado(f), "2026-09-30")

    def test_ultima_intervencion_mas_reciente(self):
        f = ficha(ultimos_votos=[{"fecha": "2026-09-30"}],
                  ultimas_intervenciones=[{"fecha": "16/10/2026"}])
        self.assertEqual(build.lastmod_diputado(f), "2026-10-16")

    def test_ultima_pregunta_mas_reciente(self):
        f = ficha(ultimos_votos=[{"fecha": "2026-09-30"}])
        preguntas = {"perez garcia ana": {"ultimas": [
            ("184/000001", {"pr": "2026-09-18", "p": "2026-10-20"}),
        ]}}
        self.assertEqual(build.lastmod_diputado(f, preguntas), "2026-10-20")

    def test_pregunta_solo_pr(self):
        f = ficha()
        preguntas = {"perez garcia ana": {"ultimas": [
            ("184/000002", {"pr": "2026-08-01"}),
        ]}}
        self.assertEqual(build.lastmod_diputado(f, preguntas), "2026-08-01")

    def test_sin_actividad_usa_alta(self):
        f = ficha(alta="17/09/2024")
        self.assertEqual(build.lastmod_diputado(f), "2024-09-17")
        self.assertEqual(build.lastmod_diputado(f, {}), "2024-09-17")

    def test_sin_actividad_ni_alta_no_inventa_hoy(self):
        f = ficha(alta="")
        self.assertEqual(build.lastmod_diputado(f), "")
        self.assertNotEqual(build.lastmod_diputado(f), HOY)

    def test_ignora_la_fecha_del_barrido(self):
        f = ficha(alta="08/08/2023", fuente=FUENTE, actualizado=HOY)
        self.assertEqual(build.lastmod_diputado(f), "2023-08-08")
        self.assertNotEqual(build.lastmod_diputado(f), HOY)

    def test_listado_es_el_maximo_de_sus_fichas(self):
        a = ficha(clave="a", alta="08/08/2023",
                  ultimos_votos=[{"fecha": "2026-09-30"}])
        b = ficha(clave="b", alta="08/08/2023",
                  ultimas_intervenciones=[{"fecha": "16/10/2026"}])
        c = ficha(clave="c", alta="01/02/2025")  # sin actividad
        self.assertEqual(build.lastmod_listado_diputados([a, b, c]), "2026-10-16")
        self.assertEqual(build.lastmod_listado_diputados([c]), "2025-02-01")
        self.assertEqual(build.lastmod_listado_diputados([]), "")


class ContratoFuente(unittest.TestCase):
    def test_renderizar_usa_la_actividad_y_no_cambia_lo_visible(self):
        src = pathlib.Path(build.__file__).read_text(encoding="utf-8")
        self.assertIn('salidas.append({"url": url, "lastmod": lastmod_diputado(f, resumen_preguntas)})', src)
        self.assertIn("lastmod=lastmod_listado_diputados(gente, resumen_preguntas)", src)
        self.assertIn("lastmod_lista = lastmod_listado_diputados(fichas, resumen_preguntas)", src)
        self.assertIn('salidas.append({"url": url, "lastmod": lastmod_lista})', src)
        self.assertIn('salidas.append({"url": url_todos, "lastmod": lastmod_lista})', src)
        # La línea de barrido sigue en la fuente visible; no se usa como lastmod.
        self.assertIn("Datos del Congreso actualizados el", src)
        self.assertIn("fecha_datos_congreso()", src)


if __name__ == "__main__":
    unittest.main()
