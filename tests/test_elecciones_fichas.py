"""Tanda E3: reparto por formación y preguntas frecuentes de las fichas de provincia."""
import pathlib
import re
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import elecciones as el  # noqa: E402

GRUPO = {"GP": "Grupo PP", "GS": "Grupo Sumar", "GM": "Grupo Mixto", "GV": "Grupo Vox"}.get


def dip(nombre, partido, grupo):
    return {"natural": nombre, "partido": partido, "grupo": grupo, "slug": nombre.lower()}


GENTE = [dip("A", "PP", "GP"), dip("B", "SUMAR", "GS"), dip("C", "SUMAR", "GM"),
         dip("D", "PP", "GP"), dip("E", "VOX", "GV"), dip("F", "BNG", "GM")]

DATOS = {
    "fecha_literal": "domingo 29 de noviembre de 2026",
    "fuentes": {"rd_anterior": "BOE-A-2023-12663"},
    "circunscripciones": [
        {"circunscripcion": "Madrid", "escanos": 7, "escanos_anterior": 6, "candidaturas": [
            {"orden": 1, "nombre": "PARTIDO POPULAR", "sigla": "PP", "proclamada": True, "titulares": ["X"]},
            {"orden": 2, "nombre": "ESCAÑOS EN BLANCO", "sigla": "EB", "proclamada": False, "titulares": []},
            {"orden": 3, "nombre": "VOX", "sigla": "VOX", "proclamada": True, "titulares": ["Y"]}]},
        {"circunscripcion": "Ceuta", "escanos": 1, "escanos_anterior": 1, "candidaturas": [
            {"orden": 1, "nombre": "VOX", "sigla": "VOX", "proclamada": True, "titulares": ["Z"]}]},
    ],
}


class Reparto(unittest.TestCase):
    def test_orden_y_grupos(self):
        filas = el.reparto_xv(GENTE, GRUPO)
        self.assertEqual([(p, n) for p, n, _ in filas], [("PP", 2), ("SUMAR", 2), ("BNG", 1), ("VOX", 1)])
        self.assertEqual(dict((p, g) for p, _n, g in filas)["SUMAR"], [("Grupo Mixto", 1), ("Grupo Sumar", 1)])
        self.assertEqual(sum(n for _p, n, _g in filas), len(GENTE))

    def test_html(self):
        h = el.reparto_html(GENTE, "Madrid", GRUPO)
        self.assertIn("Reparto de escaños en la legislatura disuelta", h)
        self.assertIn("Los 6 escaños de Madrid", h)
        self.assertIn("<td>Grupo Mixto: 1; Grupo Sumar: 1</td>", h)
        self.assertIn("<td>Grupo PP</td>", h)               # un solo grupo: sin número
        self.assertNotIn("tarjeta", h)
        self.assertIn("El escaño de Ceuta en la XV Legislatura", el.reparto_html(GENTE[:1], "Ceuta", GRUPO))
        self.assertNotIn("Los 1 ", el.reparto_html(GENTE[:1], "Ceuta", GRUPO))
        self.assertEqual(el.reparto_html([], "Soria", GRUPO), "")


class Faq(unittest.TestCase):
    def setUp(self):
        sal = [{"ficha": {"natural": "A"}}]
        self.p = el.faq_provincia(DATOS, "Madrid", "Madrid", "madrid", GENTE, sal, GRUPO)

    def test_preguntas(self):
        qs = [q for q, _ in self.p]
        self.assertEqual(len(qs), 5)
        self.assertEqual(qs[0], "¿Cuántos diputados elige Madrid en las elecciones del domingo 29 de noviembre de 2026?")
        r = dict(self.p)
        self.assertIn("7 diputados, según el", r[qs[0]])
        self.assertIn("En las elecciones de 2023 fueron 6", r[qs[0]])
        self.assertIn("2 candidaturas proclamadas, según el BOE: PARTIDO POPULAR, VOX.", r[qs[1]])
        self.assertIn("1 candidatura no proclamada", r[qs[1]])
        self.assertEqual(r[qs[2]], "Por formación: PP, 2; SUMAR, 2; BNG, 1; VOX, 1.")
        self.assertIn("1 figura con su nombre completo, letra por letra, en las listas al Congreso por Madrid: A.", r[qs[3]])
        self.assertIn('href="/elecciones/2026/madrid.html"', r[qs[4]])

    def test_sin_cambio_ni_salientes(self):
        r = dict(el.faq_provincia(DATOS, "Ceuta", "Ceuta", "ceuta", GENTE[:1], [], GRUPO))
        q0 = "¿Cuántos diputados elige Ceuta en las elecciones del domingo 29 de noviembre de 2026?"
        self.assertIn("1 diputado, según", r[q0])
        self.assertNotIn("2023", r[q0])
        self.assertIn("Ninguno figura", r["¿Qué diputados de la legislatura disuelta se presentan de nuevo por Ceuta?"])
        self.assertIn("1 candidatura proclamada", r["¿Cuántas candidaturas se presentan al Congreso por Ceuta?"])

    def test_sin_fechas_calculadas(self):
        texto = " ".join(q + r for q, r in self.p)
        self.assertNotRegex(texto, r"\b(días?|quedan|faltan|mañana|hoy)\b")

    def test_html(self):
        h = el.faq_html(self.p)
        self.assertEqual(h.count("<h3>"), 5)
        self.assertIn("sin IA", h)
        self.assertEqual(el.faq_html([]), "")


class Integracion(unittest.TestCase):
    def test_build_usa_reparto_y_faq_sin_tocar_metas(self):
        src = (RAIZ / "build.py").read_text(encoding="utf-8")
        self.assertIn('bloque_elecciones.get(prov, "") + _reparto_provincia(gente, prov)', src)
        self.assertIn("FAQ_ELECCIONES.get(prov, \"\")", src)
        # title, description y H1 de la prueba #75 no cambian
        self.assertIn('textos_prueba_dip(prov, reparto)', src)
        self.assertTrue(re.search(r'meta_desc=desc_p or \(f"Los \{len\(gente\)\} diputados que representan', src))


if __name__ == "__main__":
    unittest.main()
