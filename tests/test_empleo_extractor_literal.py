"""Tanda 5: el extractor recoge plazo, turno y procedimiento LITERALES del BOE.
Nunca calcula fechas ni estados; si la frase es dudosa, nada (y la fila dice
SIN_PLAZO). Textos reales recortados a #textoxslt en tests/datos_empleo/textos/.
Sin red."""
import pathlib
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import empleo as em  # noqa: E402
import empleo_campos as ec  # noqa: E402

TEXTOS = RAIZ / "tests" / "datos_empleo" / "textos"
LOCAL = {"dept": "ADMINISTRACIÓN LOCAL", "tipo": "convocatoria", "epi": "Personal funcionario y laboral",
         "titulo": "Resolución de 30 de octubre de 2026, del Ayuntamiento de La Garriga (Barcelona), "
                   "referente a la convocatoria para proveer varias plazas."}
UNIZAR_PI = {"dept": "UNIVERSIDADES", "tipo": "convocatoria",
             "epi": "Personal técnico, de gestión y de administración y servicios",
             "titulo": "Resolución de 19 de octubre de 2026, de la Universidad de Zaragoza, por la que se publica "
                       "la convocatoria del proceso selectivo para ingreso, por el sistema de promoción interna, en "
                       "la Escala de Técnicos Superiores de Laboratorio y Talleres."}
UNIZAR_AL = dict(UNIZAR_PI, titulo="Resolución de 9 de octubre de 2026, de la Universidad de Zaragoza, por la que "
                 "se publica la convocatoria de proceso selectivo para ingreso, por el sistema general de acceso "
                 "libre, en la Escala de Técnicos Superiores de Laboratorio y Talleres.")


def leer(ident, reg):
    return em.detalle((TEXTOS / f"{ident}.html").read_text(encoding="utf-8"), dict(reg))


class Extractor(unittest.TestCase):
    def test_la_garriga_plazo_desde_otro_boletin(self):
        d = leer("BOE-A-2026-23211", LOCAL)
        self.assertEqual(ec.plazo_llano(d["plazo"]),
                         "20 días naturales desde el día siguiente al de la publicación en el "
                         "«Diari Oficial de la Generalitat de Catalunya»")
        self.assertEqual(d["proc"], "Concurso-oposición")

    def test_unizar_promocion_interna(self):
        self.assertTrue(em.es_convocatoria(UNIZAR_PI))      # antes «se publica» la descartaba
        d = leer("BOE-A-2026-22390", UNIZAR_PI)
        self.assertEqual(ec.plazo_llano(d["plazo"]), "20 días naturales desde el día siguiente a su publicación en el BOE")
        self.assertEqual(d["proc"], "Concurso-oposición")
        self.assertEqual(d["turno"], "promocion interna")

    def test_unizar_acceso_libre(self):
        self.assertTrue(em.es_convocatoria(UNIZAR_AL))
        d = leer("BOE-A-2026-21595", UNIZAR_AL)
        self.assertEqual(ec.plazo_llano(d["plazo"]), "20 días naturales desde el día siguiente a su publicación en el BOE")
        self.assertEqual(d["proc"], "Concurso-oposición")
        self.assertEqual(d["turno"], "libre")

    def test_dudoso_sigue_sin_plazo(self):
        # «última publicación en el DOGC o en el BOE»: depende de cuál sea la
        # última; no se publica nada.
        d = leer("BOE-A-2026-22493", LOCAL)
        self.assertIsNone(ec.plazo_llano(d["plazo"]))
        for f in ("El plazo de presentación de solicitudes será de veinte días hábiles a contar desde el "
                  "siguiente al de la publicación en el «Diari Oficial de la Generalitat de Catalunya» o en el "
                  "«Boletín Oficial del Estado».",
                  "[…] plazo de diez días hábiles a partir del día siguiente al de la publicación de la "
                  "convocatoria en el «Boletín Oficial de la Junta de Andalucía» […]",
                  "El plazo de presentación de solicitudes será de veinte o treinta días naturales a contar desde "
                  "el siguiente al de la publicación en el «Diari Oficial de la Generalitat de Catalunya».",
                  "El plazo de presentación de solicitudes será de veinte días naturales a contar desde el "
                  "siguiente al de la última publicación en el «Boletín Oficial de la Provincia de Girona»."):
            self.assertIsNone(ec.plazo_llano(f), f)

    def test_nunca_fechas_ni_estados(self):
        for ident, reg in (("BOE-A-2026-23211", LOCAL), ("BOE-A-2026-22390", UNIZAR_PI),
                           ("BOE-A-2026-21595", UNIZAR_AL)):
            t = ec.plazo_llano(leer(ident, reg)["plazo"])
            self.assertNotRegex(t, r"\d{1,2} de (?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
                                   r"septiembre|octubre|noviembre|diciembre)|\d{4}|abiert|cerrad|quedan|cierra")

    def test_turno_literal_unico(self):
        self.assertEqual(em.turno_literal("para el ingreso, por el turno de promoción interna, en la Escala"), "promocion interna")
        self.assertEqual(em.turno_literal("una plaza por el turno de acceso libre en la Escala"), "libre")
        self.assertEqual(em.turno_literal("por el turno de acceso libre y por el turno de promoción interna"), "")
        self.assertEqual(em.turno_literal("por el turno libre, con reserva para personas con discapacidad"), "")
        self.assertEqual(em.turno_literal("sin turno"), "")

    def test_turno_literal_en_la_fila_sin_numero(self):
        self.assertEqual(em.texto_turnos({"promocion interna": None}, {}), "Promoción interna")

    def test_copiar_guarda_el_turno(self):
        r = {}
        em._copiar({"leido": em.LECTURA, "turno": "libre", "plazo": "x"}, r)
        self.assertEqual(r.get("turno"), "libre")


if __name__ == "__main__":
    unittest.main()
