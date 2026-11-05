"""Barra única de /empleo/ (E-2): búsqueda, proceso, provincia, organismo, etiquetas activas."""
import pathlib
import re
import unittest

import empleo as em

JS = (pathlib.Path(em.__file__).parent / "assets" / "empleo.js").read_text(encoding="utf-8")


def reg(i, tipo="convocatoria", titulo="Resolución por la que se convoca proceso selectivo", dept="ADMINISTRACIÓN LOCAL",
        prov=("granada",), fecha="2026-11-03"):
    return {"id": f"BOE-A-2026-{i}", "tipo": tipo, "titulo": titulo, "dept": dept, "prov": list(prov),
            "fecha": fecha, "proc": "", "url": "", "plazo": ""}


class Barra(unittest.TestCase):
    def html(self):
        return em.chips_filtro([reg(1), reg(2, titulo="concurso-oposición libre"), reg(3, tipo="admitidos")],
                               "2026-11-04", [("granada", "Granada", 3)], [("administracion-local", "Administración Local", 3)])

    def test_controles(self):
        h = self.html()
        self.assertIn('<label for="em-q">Buscar en empleo</label>', h)
        self.assertIn('página de provincia', h)
        self.assertIn('/empleo/provincias.html', h)
        self.assertIn('type="search" id="em-q"', h)
        self.assertIn('aria-describedby="em-q-ayuda"', h)
        self.assertIn('<select id="em-prov" aria-describedby="em-prov-ayuda"><option value="">Todas</option><option value="granada">Granada (3)</option>', h)
        self.assertIn('<select id="em-org" aria-describedby="em-org-ayuda">', h)
        self.assertIn('class="em-activos" aria-labelledby="em-act-t"', h)
        self.assertEqual(h.count('role="group"'), 1)
        self.assertEqual(h.count('role="tablist"'), 1)

    def test_sin_opciones_no_hay_select(self):
        self.assertEqual(em._select("em-x", "X", "Todos", []), "")

    def test_plural_grupos(self):
        self.assertEqual(em.PLURAL_GRUPO["concurso"], "concursos")
        self.assertEqual(em.PLURAL_GRUPO["oposicion"], "oposiciones")


class Js(unittest.TestCase):
    def test_busqueda_sin_tildes(self):
        self.assertIn('normalize("NFD").replace(/[\\u0300-\\u036f]/g, "").toLowerCase()', JS)

    def test_parametros(self):
        self.assertIn('K = ["tipo", "dias", "clase", "prov", "org", "q"]', JS)
        self.assertIn("/^#t-(\\w+)$/", JS)

    def test_etiquetas_y_limpiar(self):
        self.assertIn('"Quitar filtro " + x[1]', JS)
        self.assertIn('"Limpiar todo"', JS)

    def test_oculta_enlaces_sin_js(self):
        self.assertIn('D.getElementById("filtros")', JS)

    def test_normaliza_como_python(self):
        # «Maracena» con o sin tilde ni mayúsculas: misma forma que el JS.
        import unicodedata
        f = lambda t: re.sub(r"[\u0300-\u036f]", "", unicodedata.normalize("NFD", t)).lower()
        self.assertIn(f("maracena"), f("Ayuntamiento de MARACENA (Granada)"))
        self.assertEqual(f("Concurso-Oposición"), "concurso-oposicion")


if __name__ == "__main__":
    unittest.main()
