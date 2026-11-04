"""PR UX-2 de /empleo/: «Cargar más» y «Ver en fila» arriba, posición en el
carril, «Qué es» sin encabezado administrativo, sin «N puestos» repetido y
Administración Local desglosada por tipo de entidad."""
import pathlib
import unittest

import empleo as em

RAIZ = pathlib.Path(__file__).resolve().parent.parent
JS = (RAIZ / "assets" / "empleo.js").read_text(encoding="utf-8")
CSS = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")


class QueEsLimpio(unittest.TestCase):
    def test_quita_encabezado(self):
        r = {"titulo": "Resolución de 24 de septiembre de 2026, del Ayuntamiento de Elda "
                       "(Alicante/Alacant), referente a la convocatoria para proveer una plaza."}
        self.assertEqual(em.resumen_limpio(r), "Convocatoria para proveer una plaza.")

    def test_por_la_que_se(self):
        r = {"titulo": "Resolución de 1 de octubre de 2026, de la Universidad de Vigo, "
                       "por la que se convoca concurso de acceso a plazas."}
        self.assertEqual(em.resumen_limpio(r), "Se convoca concurso de acceso a plazas.")

    def test_sin_conector_titular_corto(self):
        r = {"titulo": "Anuncio sin conector reconocible"}
        self.assertEqual(em.resumen_limpio(r), em.titular_corto(r)[0])

    def test_recorta_largo(self):
        r = {"titulo": "Resolución, del Ayuntamiento de X, referente a la " + "palabra " * 60}
        self.assertLessEqual(len(em.resumen_limpio(r)), em.TITULAR_MAX)
        self.assertTrue(em.resumen_limpio(r).endswith("…"))

    def test_que_es_convocatoria_usa_limpio(self):
        r = {"tipo": "convocatoria", "epi": "", "titulo": "Resolución de 2 de octubre de 2026, "
             "del Ayuntamiento de Inca (Illes Balears), referente a la convocatoria para proveer varias plazas."}
        self.assertEqual(em.que_es(r), "Convocatoria para proveer varias plazas.")


class PuestosSinRepetir(unittest.TestCase):
    def test_no_hay_em_npuestos(self):
        src = (RAIZ / "empleo.py").read_text(encoding="utf-8")
        self.assertNotIn('class="ref em-npuestos"', src)


class DesgloseLocal(unittest.TestCase):
    def test_tipos(self):
        L = em.DEPT_LOCAL
        regs = [{"dept": L, "titulo": "del Ayuntamiento de A, x"}, {"dept": L, "titulo": "del Ajuntament de B, x"},
                {"dept": L, "titulo": "de la Diputación Provincial de C, x"},
                {"dept": L, "titulo": "del Cabildo Insular de D, x"},
                {"dept": L, "titulo": "de la Comunidad de Villa y Tierra de E, x"},
                {"dept": "MINISTERIO X", "titulo": "Ayuntamiento"}]
        self.assertEqual(em.desglose_local(regs), [("ayuntamientos", 2), ("cabildos y consejos insulares", 1),
                                                   ("diputaciones", 1), ("otras entidades", 1)])

    def test_vacio(self):
        self.assertEqual(em.desglose_local([]), [])


class CargarMasJS(unittest.TestCase):
    def test_cargar_mas_en_rejilla(self):
        for t in ("Cargar más", "LOTE = 24", "em-oculta"):
            self.assertIn(t, JS)
        self.assertIn(".em-rejilla > li.em-card.em-oculta{ display:none; }", CSS)


if __name__ == "__main__":
    unittest.main()
