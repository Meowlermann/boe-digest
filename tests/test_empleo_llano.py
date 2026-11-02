"""Lenguaje llano en /empleo/ (maqueta aprobada 31-10-2026): lugar() sin «de»
inventado, regla de nombres de organismo, plazo en llano (regla estricta y
flag apagada/encendida), «Qué es» por tipo y tarjeta. Sin red."""
import pathlib
import sys
import unittest
from unittest import mock

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))
import empleo as em  # noqa: E402
import empleo_campos as ec  # noqa: E402
from test_empleo import TestPaginas, h_prueba  # noqa: E402

L = "ADMINISTRACIÓN LOCAL"


def t(org):
    return {"dept": L, "titulo": f"Resolución de 20 de octubre de 2026, {org}, referente a la convocatoria."}


class TestLugar(unittest.TestCase):
    CASOS = {  # título real (BOE) -> lugar()
        "del Consorcio Provincial contra Incendios e Salvamento da Coruña (A Coruña)":
            "Consorcio Provincial contra Incendios e Salvamento da Coruña",                 # 22813, 22829
        "del Consorcio para la Gestión de Residuos del Vallés Occidental (Barcelona)":
            "Consorcio para la Gestión de Residuos del Vallés Occidental",                  # 21132
        "de la Mancomunidad Beterri-Buruntza (Gipuzkoa)": "Mancomunidad Beterri-Buruntza",  # 21277
        "de la Mancomunidad del Sur (Madrid)": "Mancomunidad del Sur",                       # 22255
        "de la Mancomunidad Intermunicipal de Servicios Sociales -Missem- (Valencia)":
            "Mancomunidad Intermunicipal de Servicios Sociales -Missem-",                   # 22759
        "de la Diputación Provincial de Palencia": "Diputación Provincial de Palencia",
        "del Ayuntamiento de Tamarite de Litera (Huesca)": "Tamarite de Litera",
        "del Ajuntament de Xàbia/Jávea (Alicante)": "Xàbia/Jávea",
    }

    def test_sin_de_inventado(self):
        for org, esperado in self.CASOS.items():
            with self.subTest(org=org):
                self.assertEqual(ec.lugar(t(org)), esperado)
                self.assertNotRegex(ec.lugar(t(org)), r"\bde (de|del|para|Provincial|Intermunicipal)\b")

    def test_activos_recalcula_localidad(self):
        r = t("del Consorcio Provincial contra Incendios e Salvamento da Coruña (A Coruña)")
        r["campos"] = {"localidad": "Consorcio de Provincial contra Incendios e Salvamento da Coruña"}
        with mock.patch.dict(ec.CAMPOS_ACTIVOS, {"local": frozenset({"localidad"})}):
            self.assertEqual(ec.activos(r)["localidad"],
                             "Consorcio Provincial contra Incendios e Salvamento da Coruña")


class TestOrganismo(unittest.TestCase):
    def test_mayusculas(self):
        for d, e in {
            "MINISTERIO DEL INTERIOR": "Ministerio del Interior",
            "COMUNIDAD DE CASTILLA Y LEÓN": "Comunidad de Castilla y León",
            "MINISTERIO PARA LA TRANSFORMACIÓN DIGITAL Y DE LA FUNCIÓN PÚBLICA":
                "Ministerio para la Transformación Digital y de la Función Pública",
            "MINISTERIO DE DERECHOS SOCIALES, CONSUMO Y AGENDA 2030":
                "Ministerio de Derechos Sociales, Consumo y Agenda 2030",
            "COMISIÓN NACIONAL DE LOS MERCADOS Y LA COMPETENCIA": "Comisión Nacional de los Mercados y la Competencia",
            "CONSEJO GENERAL DEL PODER JUDICIAL": "Consejo General del Poder Judicial",
            "DIRECCIÓN DEL CSIC": "Dirección del CSIC",
            "AGENCIA ESTATAL DE ADMINISTRACIÓN TRIBUTARIA-AEAT": "Agencia Estatal de Administración Tributaria-AEAT",
            "DE LA UNIÓN": "De la Unión",
        }.items():
            with self.subTest(d=d):
                self.assertEqual(em.nombre_dept(d), e)

    def test_en_la_duda_el_original(self):
        for d in ("Ministerio de Sanidad", "MINISTERIO DE SANIDAD [X]", "", "MINISTERIO «X»"):
            self.assertEqual(em.nombre_dept(d), " ".join(d.split()))

    def test_local_y_universidad(self):
        self.assertEqual(em.nombre_organismo(t("del Ayuntamiento de Vigo (Pontevedra)")), "Ayuntamiento de Vigo")
        self.assertEqual(em.nombre_organismo(t("del Concello de Lugo")), "Concello de Lugo")
        self.assertEqual(em.nombre_organismo(t("de l'Ajuntament d'Esplugues")), "Administración Local")
        self.assertEqual(em.nombre_organismo(t("del Ajuntament de Olot (Girona)")), "Ajuntament de Olot")
        self.assertEqual(em.nombre_organismo(t("del Ajuntament de Igualada (Barcelona)")), "Ajuntament de Igualada")
        self.assertEqual(em.nombre_organismo(t("de la Mancomunidad del Sur (Madrid)")), "Mancomunidad del Sur")
        self.assertEqual(em.nombre_organismo({"dept": L, "titulo": "Resolución sin órgano reconocible."}),
                         "Administración Local")
        u = {"dept": "UNIVERSIDADES", "titulo": "Resolución de 1 de octubre de 2026, de la Universidad de "
             "Alcalá y la Consejería de Sanidad de la Comunidad de Madrid, por la que se convoca concurso."}
        self.assertEqual(em.nombre_organismo(u),
                         "Universidad de Alcalá y la Consejería de Sanidad de la Comunidad de Madrid")
        self.assertEqual(em.nombre_organismo({"dept": "UNIVERSIDADES", "titulo":
                         "Resolución de 2 de octubre de 2026, de la Universitat Rovira i Virgili, por la que"}),
                         "Universitat Rovira i Virgili")
        self.assertEqual(em.nombre_organismo({"dept": "UNIVERSIDADES", "titulo": "Otra cosa."}), "Universidades")


class TestPlazoLlano(unittest.TestCase):
    BOE = "«Boletín Oficial del Estado»"

    def test_claros(self):
        f = f"El plazo de presentación de solicitudes será de veinte días hábiles a contar desde el siguiente al de la publicación de esta resolución en el {self.BOE}."
        self.assertEqual(ec.plazo_llano(f), "20 días hábiles desde el día siguiente a su publicación en el BOE")
        f = f"Las solicitudes se presentarán en el plazo de quince días naturales, contados a partir del siguiente al de la publicación en el {self.BOE}."
        self.assertEqual(ec.plazo_llano(f), "15 días naturales desde el día siguiente a su publicación en el BOE")

    def test_dudosos_consulta(self):
        for f in ("", "Contra la presente resolución cabe recurso en el plazo de un mes.",
                  # 21686: la frase guardada se corta justo tras el BOE y oculta el DOGC.
                  f"Las solicitudes deben presentarse en el plazo de quince días naturales contados a partir del día siguiente al de la publicación de las Resoluciones de convocatoria en el {self.BOE} […]",
                  f"El plazo de presentación de solicitudes será de veinte días hábiles a contar desde el siguiente al de la publicación en el «Diario Oficial de Galicia».",
                  "El plazo de presentación de solicitudes será de veinte días hábiles."):
            with self.subTest(f=f[:60]):
                self.assertIsNone(ec.plazo_llano(f))

    def test_flag_encendida_por_defecto(self):
        # Encendida el 01-11-2026 (OK de Xavi); se revierte poniendo False.
        self.assertTrue(ec.MOSTRAR_PLAZO_LLANO)
        r = {"tipo": "convocatoria", "plazo": f"El plazo de presentación de solicitudes será de veinte días hábiles a contar desde el siguiente al de la publicación en el {self.BOE}."}
        self.assertEqual(em.plazo_tarjeta(r), "20 días hábiles desde el día siguiente a su publicación en el BOE")
        self.assertIsNone(em.plazo_tarjeta(r, mostrar=False))
        # Frase truncada tras el BOE (BOE-A-2026-21686): nunca plazo, aun encendida.
        self.assertIsNone(em.plazo_tarjeta({"tipo": "convocatoria", "plazo": "El plazo de presentación de solicitudes será de veinte días hábiles a contar desde el siguiente al de la publicación en el «Boletín Oficial del Estado» […]"}))
        self.assertEqual(em.plazo_tarjeta(r, mostrar=True),
                         "20 días hábiles desde el día siguiente a su publicación en el BOE")
        self.assertIsNone(em.plazo_tarjeta(dict(r, no_oferta="desierta"), mostrar=True))


class TestQueEs(unittest.TestCase):
    def test_por_tipo(self):
        self.assertEqual(em.que_es({"tipo": "admitidos", "titulo": "Resolución por la que se aprueba la lista provisional de admitidos", "epi": "Cuerpo de Gestión"}),
                         "Lista provisional de admitidos y excluidos: Cuerpo de Gestión")
        self.assertEqual(em.que_es({"tipo": "admitidos", "titulo": "Lista definitiva", "epi": "Personal funcionario"}),
                         "Lista definitiva de admitidos y excluidos")
        self.assertEqual(em.que_es({"tipo": "tribunal", "titulo": "X", "epi": "Escala Técnica"}), "Tribunal: Escala Técnica")
        self.assertEqual(em.que_es({"tipo": "resultados", "titulo": "Relación de aprobados de la fase de oposición", "epi": ""}),
                         "Aprobados de la fase de oposición")
        self.assertEqual(em.que_es({"tipo": "resultados", "titulo": "Se publica la valoración", "epi": ""}),
                         "Resultado del proceso")

    def test_provision_uno_y_varios(self):
        r = {"tipo": "provision", "titulo": "Libre designación"}
        self.assertEqual(em.que_es(r, [{"puesto": "Jefe de Área", "nivel": 29}]), "Jefe de Área · nivel 29")
        self.assertEqual(em.que_es(r, [{"puesto": "A"}, {"puesto": "B"}, {"puesto": "C"}]), "3 puestos")
        self.assertEqual(em.que_es(r, []), "Libre designación")

    def test_etiquetas(self):
        self.assertEqual(em.etiqueta_llana({"tipo": "convocatoria", "proc": "Oposición"})[0], "Oposición")
        self.assertEqual(em.etiqueta_llana({"tipo": "convocatoria", "proc": "Concurso-oposición"})[0], "Concurso")
        self.assertEqual(em.etiqueta_llana({"tipo": "convocatoria", "proc": None})[0], "Convocatoria")
        self.assertEqual(em.etiqueta_llana({"tipo": "provision"})[0], "Cambio de puesto")


class TestTarjetaLlana(unittest.TestCase):
    setUp = TestPaginas.setUp
    tearDown = TestPaginas.tearDown
    FRASE = ("El plazo de presentación de solicitudes será de veinte días hábiles a contar desde el siguiente "
             "al de la publicación de esta resolución en el «Boletín Oficial del Estado».")

    def _idx(self):
        r = next(iter(self.estado["registros"].values()))
        r.update({"plazo": self.FRASE, "tipo": "convocatoria", "proc": "Oposición"})
        h, _ = h_prueba(self.carpeta)
        em.generar_paginas(h, self.estado)
        return (self.carpeta / "index.html").read_text(encoding="utf-8")

    def test_apagada_consulta(self):
        with mock.patch.object(ec, "MOSTRAR_PLAZO_LLANO", False):
            idx = self._idx()
        self.assertIn("Consulta el plazo en el BOE", idx)
        self.assertNotIn("Plazo: 20 días", idx)

    def test_encendida_plazo_llano(self):
        with mock.patch.object(ec, "MOSTRAR_PLAZO_LLANO", True):
            idx = self._idx()
        self.assertIn("Plazo: 20 días hábiles desde el día siguiente a su publicación en el BOE", idx)
        for prohibido in ("Cierra", "Fecha de cierre", "Fin de plazo", "Termina el"):
            self.assertNotIn(prohibido, idx)


if __name__ == "__main__":
    unittest.main()
