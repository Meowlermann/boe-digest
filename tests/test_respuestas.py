"""Pruebas de respuestas.py sin red.

Se ejecutan con `python -m unittest tests.test_respuestas`. El HTML de prueba
reproduce la estructura real del texto íntegro del Diario de Sesiones
(DSCD-15-PL-207, sesión del 23 de septiembre de 2026): sumario con los
rótulos en minúsculas, rótulos del cuerpo en mayúsculas, párrafos separados
por <br><br>, marcas «Página N», acotaciones y el artículo en mayúsculas
(«LA señora …») que aparece en algunas sesiones. Los PDF de contestación
escrita siguen el formato de /l15p/e12/e_0124421_n_000.pdf (184/41381).
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import respuestas as rp  # noqa: E402

DIARIO = """<p>SUMARIO</p><br><br>
- De la diputada doña Concepción Gamarra Ruiz-Clavijo, del Grupo Parlamentario Popular en el
Congreso, que formula a la señora ministra de Defensa: ¿Cree que puede estar orgullosa de su
trabajo, ministra? (Número de expediente 180/001178) ... <a href='#(Página32)'>(Página32)</a><br><br>
- De la diputada doña Sofía Acedo Reyes, del Grupo Parlamentario Popular en el Congreso, que
formula a la señora ministra de Defensa: ¿De verdad merece la pena, señora Robles? (Número de
expediente 180/001179) ... <br><br>
- DE LA DIPUTADA DOÑA CONCEPCIÓN GAMARRA RUIZ-CLAVIJO, DEL GRUPO PARLAMENTARIO POPULAR EN EL
CONGRESO, QUE FORMULA A LA SEÑORA MINISTRA DE DEFENSA: ¿CREE QUE PUEDE ESTAR ORGULLOSA DE SU
TRABAJO, MINISTRA? (Número de expediente 180/001178). <br><br>
La señora PRESIDENTA: Las siguientes preguntas van dirigidas a la señora ministra de Defensa.
Tiene la palabra la señora Gamarra. <br><br>
LA señora GAMARRA RUIZ-CLAVIJO: Gracias, presidenta. <br><br>
Bienvenida, señora Robles. Hoy es su segunda asistencia al Pleno de control en todo un año.
(Aplausos). <br><br>
La señora PRESIDENTA: Muchas gracias, señora Gamarra. <br><br>
Señora ministra. <br><br>
La señora MINISTRA DE DEFENSA (Robles Fernández): Gracias, señora presidenta. <br><br>
Mire, yo tengo un respeto ilimitado por el Congreso (Rumores.-Protestas). Y siento mucho
estar aquí solo hoy. <br><br>
Página 33<br><br>
Y sí, me siento orgullosa del trabajo de las Fuerzas Armadas. <br><br>
La señora PRESIDENTA: Muchas gracias, señora ministra. <br><br>
Señora Gamarra. <br><br>
La señora GAMARRA RUIZ-CLAVIJO: Señora ministra, dejemos trabajar a la justicia (Un señor
diputado: ¡Muy bien!). ¿Ese es su Gobierno? (Aplausos). <br><br>
La señora PRESIDENTA: Señora ministra. <br><br>
EL señor VICEPRESIDENTE PRIMERO DEL GOBIERNO Y MINISTRO DE ECONOMÍA (Cuerpo Caballero): No
es mi turno, pero lo anoto. <br><br>
La señora MINISTRA DE DEFENSA (Robles Fernández): Muchas gracias. Lo que usted llama
hipocresía se llama respeto a las instituciones. <br><br>
- DE LA DIPUTADA DOÑA SOFÍA ACEDO REYES, DEL GRUPO PARLAMENTARIO POPULAR EN EL CONGRESO, QUE
FORMULA A LA SEÑORA MINISTRA DE DEFENSA: ¿DE VERDAD MERECE LA PENA, SEÑORA ROBLES? (Número de
expediente 180/001179). <br><br>
La señora PRESIDENTA: Pregunta de la señora Acedo. <br><br>
La señora ACEDO REYES: Gracias. ¿Merece la pena? <br><br>
"""

PDF_ESCRITA = """SECRETARIA DE ESTADO DE
RELACIONES CON LAS CORTES   Y
ASUNTOS CONSTITUCIONALES
RESPUESTA DEL GOBIERNO
(184) PREGUNTA ESCRITA CONGRESO
184/41381   21/05/2026   115570
AUTOR/A: CONDE LÓPEZ, Francisco José (GP); LLAMAZARES DOMINGO, Esther
(GP)
RESPUESTA:
Se informa, en relación con la pregunta planteada,   de   que el Ministerio de
Defensa no tiene conocimiento de demoras en ninguno de los expedientes.
Se adjunta tabla de los principales contratos con la empresa.
Madrid, 27 de agosto de 2026
"""


class Orales(unittest.TestCase):
    def setUp(self):
        self.pars = rp.parrafos(DIARIO)

    def test_sin_marcas_de_pagina(self):
        self.assertNotIn("Página 33", self.pars)

    def test_ignora_el_sumario_y_corta_en_el_rotulo_siguiente(self):
        ts = rp.turnos(self.pars, "180/001178/0000")
        rotulos = [r for r, _t in ts]
        self.assertEqual(rotulos[0], "PRESIDENTA")
        self.assertNotIn("ACEDO REYES", rotulos)
        self.assertIn("GAMARRA RUIZ-CLAVIJO", rotulos)      # «LA señora» en mayúsculas

    def test_parrafos_sin_rotulo_siguen_el_turno(self):
        ts = dict((r, t) for r, t in rp.turnos(self.pars, "180/001178")[:6])
        self.assertIn("orgullosa del trabajo de las Fuerzas Armadas",
                      ts["MINISTRA DE DEFENSA (Robles Fernández)"])

    def test_quien_es_gobierno(self):
        self.assertTrue(rp.es_gobierno("MINISTRA DE DEFENSA (Robles Fernández)"))
        self.assertTrue(rp.es_gobierno("PRESIDENTE DEL GOBIERNO (Sánchez Pérez-Castejón)"))
        self.assertFalse(rp.es_gobierno("PRESIDENTA"))
        self.assertFalse(rp.es_gobierno("VICEPRESIDENTA (Gil Lázaro)"))
        self.assertTrue(rp.es_presidencia("VICEPRESIDENTA (Gil Lázaro)"))
        self.assertFalse(rp.es_gobierno("GAMARRA RUIZ-CLAVIJO"))

    def test_intercambio(self):
        d = rp.intercambio(rp.turnos(self.pars, "180/001178"))
        self.assertEqual(d["quien"], "Robles Fernández")
        # Sin saludo ni acotaciones, y el punto de la frase se conserva.
        self.assertTrue(d["c1"].startswith("Mire, yo tengo un respeto ilimitado por el Congreso."))
        self.assertNotIn("Rumores", d["c1"])
        self.assertTrue(d["r"].startswith("Señora ministra, dejemos trabajar a la justicia."))
        self.assertNotIn("Muy bien", d["r"])
        self.assertTrue(d["c2"].startswith("Lo que usted llama hipocresía"))

    def test_pregunta_sin_contestacion(self):
        self.assertEqual(rp.intercambio(rp.turnos(self.pars, "180/001179")), {})

    def test_expediente_sin_rotulo(self):
        self.assertEqual(rp.turnos(self.pars, "180/009999"), [])


class Citas(unittest.TestCase):
    def test_frases_enteras_y_marca_de_continuacion(self):
        t = "Gracias, señora presidenta. Primera frase corta. " + "Segunda frase muy larga " * 30 + "."
        c = rp.cita(t, 100)
        self.assertEqual(c, "Primera frase corta. […]")

    def test_primera_frase_demasiado_larga(self):
        c = rp.cita("palabra " * 100, 60)
        self.assertTrue(c.endswith("…"))
        self.assertLessEqual(len(c), 61)

    def test_cita_completa_sin_marca(self):
        self.assertEqual(rp.cita("Muchas gracias. Nada más."), "Nada más.")


class Escritas(unittest.TestCase):
    def test_extraer(self):
        d = rp.extraer_escrita(PDF_ESCRITA)
        self.assertTrue(d["cita"].startswith("Se informa, en relación con la pregunta planteada, de que"))
        self.assertNotIn("Madrid", d["cita"])
        self.assertGreater(d["pal"], 20)

    def test_pdf_sin_formato(self):
        self.assertIsNone(rp.extraer_escrita("imagen escaneada"))
        self.assertIsNone(rp.extraer_escrita(""))

    def test_palabras_partidas(self):
        voc = {"colectivos", "la", "discapacidad", "en", "entorno", "torno", "principios",
               "principio", "demás", "más", "de"}
        casos = [
            ("a cole ctivos vulnerables", "a colectivos vulnerables"),
            ("que l a aplicación", "que la aplicación"),
            ("e n la página", "en la página"),
            ("Di scapacidad (CDPD)", "Discapacidad (CDPD)"),
            ("desde principio s de 2025", "desde principios de 2025"),
            ("Plan 2022 -2030", "Plan 2022-2030"),
            # Dos palabras que juntas también existen: no se tocan.
            ("en torno a", "en torno a"),
            ("de más", "de más"),
            # Sin la palabra entera en el vocabulario, tampoco.
            ("un trozo raro", "un trozo raro"),
        ]
        for entrada, esperado in casos:
            self.assertEqual(rp.reparar_partidas(entrada, voc), esperado, entrada)

    def test_enlace_contestacion(self):
        html = ('<ul class="documentos">\r\n\t<li>\r\n\t\t<a href="/l15p/e12/e_0124421_n_000.pdf" '
                'target="_blank">Contestación</a>\r\n</li></ul>')
        self.assertEqual(rp.enlace_contestacion(html),
                         "https://www.congreso.es/l15p/e12/e_0124421_n_000.pdf")
        solo_pregunta = '<a href="/l15p/e12/e_0121690_n_000.pdf" target="_blank">Pregunta</a>'
        self.assertIsNone(rp.enlace_contestacion(solo_pregunta))


if __name__ == "__main__":
    unittest.main()
