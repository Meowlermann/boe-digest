"""Puestos de provisión (concursos y libre designación) desde las tablas del
anexo del txt.php del BOE: resultas, correcciones, varios puestos, localidad
sucia, documento que falla la comprobación y flag CAMPOS_ACTIVOS. Sin red."""
import pathlib
import re
import sys
import unittest
from unittest import mock

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))
import empleo as em  # noqa: E402
import empleo_campos as ec  # noqa: E402
from test_empleo import TestPaginas, h_prueba  # noqa: E402

CAB = ("<tr><td><p>N.º orden</p></td><td><p>Código puesto</p></td><td><p>Denominación del puesto</p></td>"
       "<td><p>Nivel</p></td><td><p>Localidad</p></td></tr>")


def fila(n, cod, puesto, nivel, loc):
    return (f"<tr><td><p>{n}</p></td><td><p>{cod}</p></td><td><p>{puesto}</p></td>"
            f"<td><p>{nivel}</p></td><td>{''.join(f'<p>{x}</p>' for x in loc.split('|'))}</td></tr>")


def doc(*anexos):
    cuerpo = "".join(f'<h5 class="anexo">{t}</h5><table>{CAB}{"".join(fs)}</table>' for t, fs in anexos)
    return f'<div id="textoxslt"><p>Se convoca concurso.</p>{cuerpo}</div>'


VARIOS = doc(("ANEXO I", [
    fila(1, "1234567", "Jefe / Jefa de Sección", 26, "MADRID - MADRID"),
    fila(2, "1234568", "Jefe / Jefa de Negociado", 18, "- MADRID - |- MADRID"),
    fila(3, "1234569", "Técnico / Técnica Superior", 24, "VALENCIA - VALENCIA"),
    fila(4, "1234570", "Analista de Sistemas", 22, "BERLIN"),
]))
REG = {"tipo": "provision", "dept": "MINISTERIO DE HACIENDA", "titulo": "Resolución por la que se convoca concurso"}


class TestExtraccion(unittest.TestCase):
    def test_varios_puestos(self):
        c = ec.campos_provision("", VARIOS)
        ps = c["puestos"]
        self.assertEqual(len(ps), 4)
        self.assertEqual(ps[0], {"puesto": "Jefe/Jefa de Sección", "nivel": 26, "localidad": "Madrid"})
        self.assertEqual(ps[2]["nivel"], 24)

    def test_localidad_sucia_se_limpia_u_oculta(self):
        ps = ec.campos_provision("", VARIOS)["puestos"]
        self.assertEqual(ps[1]["localidad"], "Madrid")      # «- MADRID - - MADRID»
        self.assertNotIn("localidad", ps[3])                 # extranjero: se oculta, no se inventa
        self.assertEqual(ec.limpia_localidad("MADRID/ - MADRD"), "")  # errata: oculta

    def test_resultas_excluidas(self):
        h = doc(("ANEXO I", [fila(1, "1", "Jefe de Servicio", 28, "MADRID - MADRID")]),
                ("ANEXO II (Resultas)", [fila(2, "2", "Jefe de Sección", 26, "MADRID - MADRID")]))
        c = ec.campos_provision("", h)
        self.assertEqual([p["puesto"] for p in c["puestos"]], ["Jefe de Servicio"])
        self.assertEqual(c.get("resultas"), 1)

    def test_fila_incomprensible_anula_el_documento(self):
        # El código suelto en la columna de puesto (caso 22241) no debe salir como puesto.
        h = doc(("ANEXO I", [fila(1, "1", "Jefe de Servicio", 28, "MADRID - MADRID"),
                             fila(2, "2", "2958401", 26, "MADRID - MADRID")]))
        self.assertEqual(ec.campos_provision("", h), {})

    def test_sin_html_o_sin_tabla(self):
        self.assertEqual(ec.campos_provision("texto", ""), {})
        self.assertEqual(ec.campos_provision("", '<div id="textoxslt"><p>Prosa</p></div>'), {})

    def test_correccion_no_es_oferta(self):
        r = ec.extraer_campos({**REG, "titulo": "Resolución por la que se corrigen errores en la de 1 de octubre"},
                              "Advertidos errores", VARIOS)
        self.assertIn("no_oferta", r)
        self.assertNotIn("campos", r)


class TestFlag(unittest.TestCase):
    def reg(self):
        return {**REG, **ec.extraer_campos(REG, "", VARIOS)}

    def test_activos_solo_validados(self):
        self.assertEqual(ec.CAMPOS_ACTIVOS["provision"], frozenset({"puesto", "nivel", "localidad"}))
        self.assertEqual(ec.CAMPOS_ACTIVOS["estado"], frozenset())
        self.assertEqual(ec.CAMPOS_ACTIVOS["universidad"], frozenset())

    def test_apagado(self):
        with mock.patch.dict(ec.CAMPOS_ACTIVOS, {"provision": frozenset()}):
            self.assertEqual(ec.puestos_activos(self.reg()), [])

    def test_estado_previo_sin_campos(self):
        # Un registro leído con LECTURA anterior (sin 'campos') se pinta como antes.
        with mock.patch.dict(ec.CAMPOS_ACTIVOS, {"provision": frozenset({"puesto", "nivel", "localidad"})}):
            self.assertEqual(ec.puestos_activos(dict(REG)), [])

    def test_encendido(self):
        with mock.patch.dict(ec.CAMPOS_ACTIVOS, {"provision": frozenset({"puesto", "nivel"})}):
            ps = ec.puestos_activos(self.reg())
        self.assertEqual(len(ps), 4)
        self.assertEqual(ps[0], {"puesto": "Jefe/Jefa de Sección", "nivel": 26})


    def test_detalle_pasa_el_html(self):
        d = em.detalle(VARIOS, REG)
        self.assertEqual(len(d["campos"]["puestos"]), 4)
        self.assertEqual(em.LECTURA, 4)


ENCENDIDO = {"provision": frozenset({"puesto", "nivel", "localidad"})}


class TestTarjeta(unittest.TestCase):
    setUp = TestPaginas.setUp
    tearDown = TestPaginas.tearDown

    def _indice(self, campos):
        r = next(iter(self.estado["registros"].values()))
        r.update({"tipo": "provision", "dept": "MINISTERIO DE HACIENDA", "campos": campos})
        h, _ = h_prueba(self.carpeta)
        em.generar_paginas(h, self.estado)
        return (self.carpeta / "index.html").read_text(encoding="utf-8")

    def test_apagado_igual_que_hoy(self):
        with mock.patch.dict(ec.CAMPOS_ACTIVOS, {"provision": frozenset()}):
            idx = self._indice(ec.campos_provision("", VARIOS))
        self.assertNotIn("em-puestos", idx)

    def test_varios_puestos_tres_y_ver_todos(self):
        with mock.patch.dict(ec.CAMPOS_ACTIVOS, ENCENDIDO):
            idx = self._indice(ec.campos_provision("", VARIOS))
        self.assertIn("4 puestos", idx)
        self.assertIn("Jefe/Jefa de Sección · Nivel 26 · Madrid", re.sub(r"<[^>]+>", "", idx))
        self.assertIn('<span class="em-tag em-tag-nivel">Nivel 26</span>', idx)
        self.assertIn("Ver todos los puestos (4)", idx)
        self.assertIn("Analista de Sistemas · Nivel 22\n", re.sub(r"<[^>]+>", "", idx.replace("</li>", "\n")))   # sin localidad dudosa

    def test_un_puesto(self):
        with mock.patch.dict(ec.CAMPOS_ACTIVOS, ENCENDIDO):
            idx = self._indice({"puestos": [{"puesto": "Jefe de Área", "nivel": 29}], "n_puestos": 1})
        self.assertIn('<dd class="em-que">Jefe de Área · nivel 29</dd>', idx)
        self.assertNotIn("em-tag-loc", idx)
        self.assertNotIn("Ver todos los puestos", idx)
        self.assertNotIn("1 puestos", idx)


if __name__ == "__main__":
    unittest.main()


TEXTOS = RAIZ / "tests" / "datos_empleo" / "textos"


class TestNombreSobreCodigo(unittest.TestCase):
    """BOE-A-2026-22467: el nombre va en la fila de unidad y la del puesto solo
    dice «Código de puesto: NNN». Nunca debe mostrarse el código como nombre."""

    def test_22467_real(self):
        h = (TEXTOS / "22467.html").read_text(encoding="utf-8")
        c = ec.campos_provision("", h)
        self.assertEqual(c["puestos"], [{"puesto": "Vocal Asesor/Vocal Asesora", "nivel": 30, "localidad": "Madrid"}])

    def test_codigo_solo_se_descarta(self):
        for nombre in ("Código de puesto: 882380", "4711234", "A1-27"):
            h = doc(("ANEXO", [fila(1, "1234567", nombre, 26, "MADRID")]))
            self.assertFalse((ec.campos_provision("", h) or {}).get("puestos"), nombre)

    def test_es_codigo(self):
        self.assertTrue(ec._es_codigo("Código de puesto: 5087694"))
        self.assertTrue(ec._es_codigo("5087694"))
        self.assertFalse(ec._es_codigo("Jefe / Jefa de Sección"))

    def test_nombre_en_dos_lineas(self):
        h = doc(("ANEXO", [fila(1, "1234567", "Jefe / Jefa de Sección</p><p>de Atención al Ciudadano", 24, "MADRID")]))
        ps = (ec.campos_provision("", h) or {}).get("puestos") or []
        for p in ps:
            self.assertFalse(ec._es_codigo(p["puesto"]))
