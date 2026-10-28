"""UX-2 (4): tarjeta de convocatoria en /empleo/. Titular ≤120 caracteres
sin cortar palabras, título completo en <details>, botones al BOE y al PDF,
«publicada hace N días» determinista y ninguna fecha de cierre. Sin red."""
import pathlib
import re
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))
import empleo as em  # noqa: E402
from test_empleo import TestPaginas, h_prueba  # noqa: E402

LARGO = ("Resolución de 20 de octubre de 2026, de la Subsecretaría, por la que se convoca proceso selectivo "
         "para ingreso, por el sistema general de acceso libre, en el Cuerpo de Gestión de la Administración "
         "Civil del Estado.")


class TestTitular(unittest.TestCase):
    def test_corto_intacto(self):
        self.assertEqual(em.titular_corto({"titulo": "Convoca plazas"}), ("Convoca plazas", False))

    def test_largo_sin_cortar_palabras(self):
        t, rec = em.titular_corto({"titulo": LARGO})
        self.assertTrue(rec)
        self.assertLessEqual(len(t), 120)
        self.assertTrue(t.endswith("…"))
        self.assertTrue(LARGO.startswith(t[:-1]))
        self.assertIn(LARGO[len(t) - 1], " ,")  # el corte cae entre palabras

    def test_cuerpo_si_lo_hubiera(self):
        self.assertEqual(em.titular_corto({"titulo": LARGO, "cuerpo": "Cuerpo de Gestión"}),
                         ("Cuerpo de Gestión", True))


class TestFechas(unittest.TestCase):
    def test_publicada(self):
        self.assertEqual(em.publicada("2026-10-27", "2026-10-27"), "Publicada en el último BOE")
        self.assertEqual(em.publicada("2026-10-26", "2026-10-27"), "Publicada hace 1 día")
        self.assertEqual(em.publicada("2026-10-20", "2026-10-27"), "Publicada hace 7 días")

    def test_referencia_es_el_ultimo_boe(self):
        est = {"registros": {"a": {"fecha": "2026-10-20"}, "b": {"fecha": "2026-10-24"}}}
        self.assertEqual(em.fecha_referencia(est, "2026-12-31"), "2026-10-24")
        self.assertEqual(em.fecha_referencia({"registros": {}}, "2026-12-31"), "2026-12-31")

    def test_pdf_oficial(self):
        self.assertEqual(em.url_pdf({"id": "BOE-A-2026-1", "fecha": "2026-10-27"}),
                         "https://www.boe.es/boe/dias/2026/10/27/pdfs/BOE-A-2026-1.pdf")


class TestTarjetaGenerada(unittest.TestCase):
    setUp = TestPaginas.setUp
    tearDown = TestPaginas.tearDown

    def _indice(self, hoy="2026-12-31"):
        h, _ = h_prueba(self.carpeta, hoy=hoy)   # el reloj no cuenta: manda el último BOE
        em.generar_paginas(h, self.estado)
        return (self.carpeta / "index.html").read_text(encoding="utf-8")

    def test_tarjetas(self):
        idx = self._indice("2026-10-27")
        tarjetas = re.findall(r'<li class="em-card">(.*?)</li>', idx)
        self.assertTrue(tarjetas)
        for t in tarjetas:
            tit = re.search(r'class="em-tit"[^>]*>([^<]*)</a>', t).group(1)
            self.assertLessEqual(len(tit), 120)
            self.assertEqual("<details" in t, tit.endswith("…"))
            self.assertIn(">Ver en el BOE</a>", t)
            self.assertRegex(t, r'href="https://www\.boe\.es/boe/dias/\d{4}/\d\d/\d\d/pdfs/BOE-A-\d{4}-\d+\.pdf"[^>]*>PDF</a>')
            self.assertRegex(t, r"Publicada (en el último BOE|hace \d+ días?)")
        self.assertIn("Publicada en el último BOE", idx)
        self.assertIn("Publicada hace 3 días", idx)        # 24-oct frente al 27-oct

    def test_determinista_y_sin_fecha_de_cierre(self):
        a = self._indice("2026-10-27")
        b = self._indice("2027-01-15")
        cuerpo = lambda x: next(l for l in x.splitlines() if l.startswith("CUERPO="))  # noqa: E731
        self.assertEqual(cuerpo(a), cuerpo(b))
        for prohibido in ("Cierra", "cierra el", "Fecha de cierre", "Fin de plazo", "Termina el"):
            self.assertNotIn(prohibido, a)


if __name__ == "__main__":
    unittest.main()
