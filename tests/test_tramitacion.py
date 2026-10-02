"""Pruebas de tramitacion.contenido() y tramitacion.situacion(), sin red.

`python -m unittest tests.test_tramitacion`. El texto reproduce la estructura
del BOCG-15-B-335-1 (122/000283): cabeceras de página, «cve:», números romanos
de sección, la frase de estructura de la exposición de motivos y artículos
con un título que se modifica entre comillas.
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import tramitacion as tr  # noqa: E402

BOLETIN = """BOLETÍN OFICIAL
DE LAS CORTES GENERALES
CONGRESO DE LOS DIPUTADOS
XV LEGISLATURA
Serie B:
PROPOSICIONES DE LEY 29 de mayo de 2026 Núm. 335-1 Pág. 1 cve: BOCG-15-B-335-1
PROPOSICIÓN DE LEY 122/000283 Proposición de Ley de creación del Impuesto.
Exposición de motivos
I
En las sociedades contemporáneas, la herencia ha adquirido un papel central como
mecanismo de transmi-
sión intergeneracional de la riqueza.
V
La presente norma consta de 36 artículos, dos disposiciones adicionales y cuatro
disposiciones finales, mediante las cuales se configura un nuevo tributo estatal.
Artículo 1. Impuesto de las Grandes Herencias y Donaciones.
Se crea el impuesto.
BOLETÍN OFICIAL DE LAS CORTES GENERALES CONGRESO DE LOS DIPUTADOS Serie B Núm. 335-1 29 de mayo de 2026 Pág. 5
Artículo 2. Naturaleza y objeto del Impuesto.
Se modifica así: «Artículo 91. Tipos impositivos reducidos.»
Disposición final cuarta. Entrada en vigor.
"""


class Contenido(unittest.TestCase):
    def test_frase_de_estructura_y_titulos(self):
        c = tr.contenido(BOLETIN)
        self.assertTrue(c["em"].startswith("La presente norma consta de 36 artículos"))
        self.assertEqual(c["art"], ["Artículo 1. Impuesto de las Grandes Herencias y Donaciones.",
                                    "Artículo 2. Naturaleza y objeto del Impuesto.",
                                    "Disposición final cuarta. Entrada en vigor."])
        self.assertNotIn("BOLETÍN", " ".join(c["art"]))

    def test_objeto_antes_que_estructura(self):
        texto = BOLETIN.replace("En las sociedades contemporáneas,",
                                "Esta ley tiene por objeto gravar las grandes herencias. En las sociedades,")
        self.assertTrue(tr.contenido(texto)["em"].startswith("Esta ley tiene por objeto gravar"))

    def test_sin_exposicion(self):
        self.assertEqual(tr.contenido("Acuerdo de la Mesa sin más texto."), {})


class Situacion(unittest.TestCase):
    HOY = "2026-10-02"

    def test_pendiente_de_pleno(self):
        v = {"est": "toma-en-consideracion", "tipo": "Proposición de ley de Grupos Parlamentarios del Congreso",
             "pasos": [["Gobierno · Contestación", "2026-05-29", "2026-09-04"],
                       ["Pleno · Toma en consideración", "2026-09-04", ""]]}
        s = tr.situacion(v, self.HOY)
        self.assertEqual(s["titulo"], "Pendiente de debate en el Pleno")
        self.assertEqual(s["dias"], 28)

    def test_congelador(self):
        v = {"est": "plazo-de-enmiendas", "amp": 102, "tipo": "Proposición de ley del Senado",
             "pasos": [["Comisión de Hacienda y Función Pública · Enmiendas", "2023-12-11", ""]]}
        self.assertTrue(tr.congelada(v, self.HOY))
        self.assertIn("congelador", tr.situacion(v, self.HOY)["titulo"])

    def test_plazo_normal_no_es_congelador(self):
        v = {"est": "plazo-de-enmiendas", "amp": 3, "fe": "2026-10-10",
             "pasos": [["Comisión de Justicia · Enmiendas", "2026-09-01", ""]]}
        self.assertFalse(tr.congelada(v, self.HOY))
        self.assertEqual(tr.situacion(v, self.HOY)["titulo"], "En plazo de enmiendas")

    def test_cerradas_sin_caja(self):
        self.assertIsNone(tr.situacion({"est": "aprobada"}, self.HOY))


if __name__ == "__main__":
    unittest.main()
