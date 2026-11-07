import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import empleo, empleo_campos as ec

TX = Path(__file__).parent / "datos_empleo" / "textos"
DOGC = "Diari Oficial de la Generalitat de Catalunya"
PL = f"El plazo de presentación de solicitudes será de veinte días naturales a contar desde el siguiente al de la publicación en el «{DOGC}»."


class TestDiario(unittest.TestCase):
    def test_la_garriga(self):
        r = {"id": "BOE-A-2026-23211", "titulo": "Resolución de 30 de octubre de 2026, del Ayuntamiento de La Garriga (Barcelona), referente a la convocatoria para proveer varias plazas.",
             "epi": "Personal funcionario y laboral", "dept": "ADMINISTRACIÓN LOCAL", "tipo": "convocatoria"}
        d = empleo.detalle((TX / "BOE-A-2026-23211.html").read_text(), r)
        self.assertEqual(d["diario"], {"bol": DOGC, "num": "9784", "fecha": "30 de octubre de 2026"})
        self.assertEqual(ec.texto_diario(d["diario"]),
                         f"Publicado en el «{DOGC}» número 9784, de 30 de octubre de 2026")

    def test_variantes_literales(self):
        for t, num, f in ((f"En el «{DOGC}» (DOGC) número 9763, de fecha 2 de octubre de 2026, se han publicado", "9763", "2 de octubre de 2026"),
                          (f"en el «{DOGC}» núm. 9754, de 18 de septiembre de 2026.", "9754", "18 de septiembre de 2026")):
            self.assertEqual(ec.diario_literal(t, DOGC), {"bol": DOGC, "num": num, "fecha": f})

    def test_dudosos(self):
        dos = f"«{DOGC}» número 1, de 2 de octubre de 2026 y «{DOGC}» número 2, de 3 de octubre de 2026"
        for t in ("", dos, f"«{DOGC}», de 6 de octubre de 2026",                  # sin número
                  "«Boletín Oficial de la Provincia de Lleida» número 192, de 8 de octubre de 2026"):  # otro boletín
            self.assertIsNone(ec.diario_literal(t, DOGC))
        self.assertEqual(ec.texto_diario({}), "")
        self.assertEqual(ec.boletin_del_plazo("en el plazo de veinte días desde su publicación en el «Boletín Oficial del Estado»."), "")
        self.assertEqual(ec.boletin_del_plazo(PL), DOGC)

    def test_relectura_solo_si_falta(self):
        base = {"leido": empleo.LECTURA, "plazo": PL}
        self.assertFalse(empleo.al_dia(base))
        self.assertTrue(empleo.al_dia({**base, "diario": {}}))
        self.assertTrue(empleo.al_dia({"leido": empleo.LECTURA, "plazo": "x"}))

    def test_html_solo_con_plazo_del_mismo_boletin(self):
        r = {"diario": {"bol": DOGC, "num": "9784", "fecha": "30 de octubre de 2026"}}
        self.assertIn("9784", empleo.diario_html(r, f"20 días desde el «{DOGC}»", "span", "x"))
        self.assertEqual(empleo.diario_html(r, None, "span", "x"), "")
        self.assertEqual(empleo.diario_html(r, "20 días desde su publicación en el BOE", "span", "x"), "")

    def test_excluida_ciutadilla(self):
        r = {"id": "BOE-A-2026-22137", "diario": {"bol": DOGC, "num": "9974", "fecha": "16 de octubre de 2026"}}
        self.assertEqual(empleo.diario_html(r, f"20 días hábiles desde el «{DOGC}»", "span", "x"), "")
        motivo, fuente = ec.DIARIO_EXCLUIDO["BOE-A-2026-22137"]
        self.assertIn("9774", motivo); self.assertIn("CIDO", fuente)

    def test_ayuda_solo_en_fila(self):
        r = {"id": "BOE-A-2026-23211", "diario": {"bol": DOGC, "num": "9784", "fecha": "30 de octubre de 2026"}}
        pl = f"20 días desde el «{DOGC}»"
        self.assertIn(empleo.AYUDA_DIARIO, empleo.diario_html(r, pl, "span", "em-f-diario"))
        self.assertNotIn(empleo.AYUDA_DIARIO, empleo.diario_html(r, pl, "p", "em-c-diario"))
        self.assertNotIn("href", empleo.diario_html(r, pl, "span", "em-f-diario"))

    def test_etiqueta_proceso_literal(self):
        self.assertEqual(empleo.etiqueta_llana({"tipo": "convocatoria", "proc": "Concurso-oposición"}),
                         ("Concurso y concurso-oposición", "concurso"))
        self.assertEqual(empleo.etiqueta_llana({"tipo": "convocatoria", "proc": "Oposición"}), ("Oposición", "oposicion"))


if __name__ == "__main__":
    unittest.main()
