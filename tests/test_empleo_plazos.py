"""TC-013, iteración 1: plazo literal y tipo de proceso de las convocatorias
de empleo público, noindex de /empleo/ y canal en /seguir/. Las frases son
copias literales de disposiciones reales del BOE (20 y 27-10-2026)."""
import pathlib
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import empleo as em  # noqa: E402

LOCAL = ("<p>Resolución de 22 de octubre de 2026, del Ayuntamiento de Aiguamúrcia (Tarragona). "
         "En el «Boletín Oficial de la Provincia de Tarragona», de 9 de octubre de 2026, se han publicado "
         "íntegramente las bases que han de regir la convocatoria para proveer una plaza de Auxiliar "
         "administrativo/a, perteneciente a la escala de Administración General, subescala Auxiliar y clase "
         "Auxiliar, por el sistema de concurso-oposición, en turno libre. El plazo de presentación de "
         "solicitudes será de veinte días hábiles a contar desde el siguiente al de la última publicación en "
         "el «Diari Oficial de la Generalitat de Catalunya» o en el «Boletín Oficial del Estado». Los sucesivos "
         "anuncios se publicarán en la sede electrónica.</p>")

AGE = ("<p>4. Solicitudes 4.1 Las personas interesadas dispondrán de un plazo de presentación de "
       "solicitudes de veinte días hábiles contados a partir del día siguiente al de la fecha de publicación "
       "de esta convocatoria en el «Boletín Oficial del Estado». 5.2 Las personas aspirantes dispondrán de un "
       "plazo de diez días hábiles computados desde el día siguiente a la publicación de la resolución en el "
       "«Boletín Oficial del Estado» para subsanar, en su caso, el defecto que haya motivado la exclusión. "
       "6. Proceso selectivo 6.1 El proceso selectivo se realizará mediante el sistema de oposición, con las "
       "valoraciones que se especifican en el anexo I.</p>")

AECID = ("<p>Los funcionarios interesados dirigirán sus solicitudes, que deberán ajustarse al modelo que "
         "figura en el anexo II, al Sr. Director de la AECID, dentro del plazo de diez días naturales "
         "siguientes al de la publicación de esta convocatoria en el «Boletín Oficial del Estado». Las "
         "solicitudes se presentarán por vía electrónica.</p>")

SUBSANAR = ("<p>Las personas aspirantes dispondrán de un plazo de diez días hábiles para subsanar el "
            "defecto de su solicitud. Contra esta resolución cabe recurso en el plazo de un mes.</p>")


def html(cuerpo):
    return f'<html><body><div id="textoxslt">{cuerpo}</div></body></html>'


class FalsoGet:
    def __init__(self, paginas):
        self.paginas, self.pedidas = paginas, []

    def __call__(self, url):
        self.pedidas.append(url)
        t = self.paginas.get(url.rsplit("=", 1)[1])
        return type("R", (), {"text": t})() if t is not None else None


class TestPlazoLiteral(unittest.TestCase):
    def test_cita_literal_con_otro_boletin(self):
        d = em.detalle(html(LOCAL), {"titulo": "convocatoria para proveer una plaza", "epi": ""})
        self.assertEqual(d["plazo"], "El plazo de presentación de solicitudes será de veinte días hábiles a "
                         "contar desde el siguiente al de la última publicación en el «Diari Oficial de la "
                         "Generalitat de Catalunya» o en el «Boletín Oficial del Estado».")
        self.assertIn(d["plazo"], " ".join(LOCAL.split()))      # literal, no reescrita
        self.assertEqual(d["proc"], "Concurso-oposición")

    def test_quita_epigrafe_y_numeracion_y_no_coge_subsanar(self):
        d = em.detalle(html(AGE), {"titulo": "por la que se convoca proceso selectivo", "epi": ""})
        self.assertTrue(d["plazo"].startswith("Las personas interesadas dispondrán de un plazo"), d)
        self.assertNotIn("subsanar", d["plazo"])
        self.assertNotIn("4.1", d["plazo"])
        self.assertEqual(d["proc"], "Oposición")

    def test_abreviatura_no_corta_la_frase(self):
        d = em.detalle(html(AECID), {"titulo": "provisión por el sistema de libre designación", "epi": ""})
        self.assertIn("plazo de diez días naturales", d["plazo"])
        self.assertEqual(d["proc"], "Libre designación")

    def test_sin_plazo_de_solicitudes_no_hay_cita(self):
        self.assertNotIn("plazo", em.detalle(html(SUBSANAR), {"titulo": "", "epi": ""}))

    def test_nunca_calcula_una_fecha(self):
        for cuerpo in (LOCAL, AGE, AECID):
            p = em.detalle(html(cuerpo), {"titulo": "", "epi": ""})["plazo"]
            self.assertNotRegex(p, r"\d{1,2}/\d{1,2}/\d{4}|\b20\d\d-\d\d-\d\d\b")


class TestProceso(unittest.TestCase):
    def test_etiquetas(self):
        self.assertEqual(em.proceso("convoca la provisión por el sistema de libre designación", ""), "Libre designación")
        self.assertEqual(em.proceso("x", "Procedimientos de libre designación"), "Libre designación")
        self.assertEqual(em.proceso("convoca concurso específico para la provisión de puestos", ""), "Concurso")
        self.assertEqual(em.proceso("para proveer puesto de trabajo por el sistema de concurso.", ""), "Concurso")
        self.assertEqual(em.proceso("proceso selectivo, por concurso-oposición, por el sistema general", ""),
                         "Concurso-oposición")

    def test_varios_sistemas_o_ninguno_sin_etiqueta(self):
        t = ("Tres plazas por el sistema de oposición, en turno libre. Dos plazas por el sistema de "
             "concurso, en turno de movilidad.")
        self.assertEqual(em.proceso("convocatoria para proveer varias plazas", "", t), "")
        self.assertEqual(em.proceso("convocatoria para proveer una plaza", "", "Sin más datos."), "")
        # «salvo oposición expresa» no es un sistema selectivo
        self.assertEqual(em.proceso("x", "", "salvo que conste oposición expresa de la persona interesada"), "")


class TestEnriquecer(unittest.TestCase):
    def regs(self):
        return [
            {"id": "BOE-A-1", "tipo": "convocatoria", "titulo": "referente a la convocatoria para proveer una plaza", "epi": ""},
            {"id": "BOE-A-2", "tipo": "convocatoria", "titulo": "de corrección de errores de la de 16 de octubre", "epi": ""},
            {"id": "BOE-A-3", "tipo": "convocatoria", "titulo": "por la que se modifican Resoluciones", "epi": ""},
            {"id": "BOE-A-4", "tipo": "provision", "titulo": "por la que se declara desierta la convocatoria", "epi": ""},
            {"id": "BOE-A-5", "tipo": "convocatoria", "titulo": "por la que se publica la Resolución", "epi": "Inspección. Cursos"},
            {"id": "BOE-A-6", "tipo": "admitidos", "titulo": "relación de admitidos", "epi": ""},
            {"id": "BOE-A-7", "tipo": "provision", "titulo": "convoca concurso específico", "epi": "Personal funcionario. Concursos"},
        ]

    def test_solo_lee_convocatorias_de_verdad(self):
        get = FalsoGet({"BOE-A-1": html(LOCAL), "BOE-A-7": html(AECID)})
        regs = self.regs()
        cuenta = em.enriquecer(regs, get, log=lambda *a: None)
        self.assertEqual(get.pedidas, ["https://www.boe.es/diario_boe/txt.php?id=BOE-A-1",
                                       "https://www.boe.es/diario_boe/txt.php?id=BOE-A-7"])
        self.assertTrue(all("xml.php" not in u for u in get.pedidas))   # excluido por robots.txt
        self.assertIn("plazo", regs[0])
        self.assertTrue(all("plazo" not in r for r in regs[1:6]))
        self.assertEqual(cuenta["leidas"], 2)

    def test_reutiliza_lo_leido_y_tolera_fallos(self):
        previo = {"BOE-A-1": {"plazo": "cita", "proc": "Oposición", "leido": em.LECTURA}}
        get = FalsoGet({})
        regs = self.regs()
        cuenta = em.enriquecer(regs, get, log=lambda *a: None, previo=previo)
        self.assertEqual(regs[0]["plazo"], "cita")
        self.assertEqual(get.pedidas, ["https://www.boe.es/diario_boe/txt.php?id=BOE-A-7"])
        self.assertEqual((cuenta["reutilizadas"], cuenta["fallos"]), (1, 1))
        self.assertEqual(regs[6].get("proc"), "Concurso")           # del título, sin texto

    def test_sin_red_no_revienta(self):
        def get(url):
            raise RuntimeError("sin red")
        regs = self.regs()
        em.enriquecer(regs, get, log=lambda *a: None)
        self.assertTrue(all("plazo" not in r for r in regs))

    def test_usar_get_para_el_reprocesado(self):
        get = FalsoGet({"BOE-A-1": html(LOCAL)})
        em.usar_get(get)
        try:
            regs = self.regs()[:1]
            em.enriquecer(regs, log=lambda *a: None)
            self.assertIn("plazo", regs[0])
        finally:
            em.usar_get(None)


class TestPublicacion(unittest.TestCase):
    def test_noindex(self):
        self.assertIn("noindex", em.ROBOTS)
        self.assertIn("follow", em.ROBOTS)
        plantilla = (RAIZ / "template_norma.html").read_text(encoding="utf-8")
        self.assertRegex(plantilla, r'<meta name="robots" content="[^"]*">')   # build la sustituye

    def test_seguir_enlaza_el_canal_de_empleo(self):
        import paginas_fijas
        textos = " ".join(v for v in vars(paginas_fijas).values() if isinstance(v, str))
        self.assertIn('href="/empleo/index.xml"', textos)

    def test_reproceso_pasa_el_get(self):
        fuente = (RAIZ / "reproceso.py").read_text(encoding="utf-8")
        self.assertIn("usar_get(get)", fuente)


if __name__ == "__main__":
    unittest.main()



class TestCanalEnSeguir(unittest.TestCase):
    def test_sin_canal_enlaza_la_pagina(self):
        import paginas_fijas as pf
        self.assertIn('href="/empleo/index.xml"', pf.seguir_con_empleo(pf.SEGUIR, True))
        sin = pf.seguir_con_empleo(pf.SEGUIR, False)
        self.assertNotIn("/empleo/index.xml", sin)
        self.assertIn('href="/empleo/"', sin)
