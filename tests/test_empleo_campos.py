"""Extractor de campos de empleo (empleo_campos). Fixtures: extractos reales
del texto del BOE en tests/datos_empleo/textos/local.json (cada uno cita su
txt.php; las firmas se recortan al cargo, sin nombres de particulares). Sin red."""
import json
import pathlib
import re
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))
import empleo as em  # noqa: E402
import empleo_campos as C  # noqa: E402
from test_empleo import TestPaginas, h_prueba  # noqa: E402

TEXTOS = json.loads((RAIZ / "tests/datos_empleo/textos/local.json").read_text(encoding="utf-8"))


def reg(ident: str) -> dict:
    d = TEXTOS[ident]
    r = {"id": ident, "titulo": d["titulo"], "dept": d["dept"], "tipo": d["tipo"],
         "fecha": "2026-10-20", "prov": "", "epi": ""}
    r.update(C.extraer_campos(r, "\n".join(d["lineas"])))
    return r


def html(ident: str) -> str:
    ps = "".join(f"<p>{x}</p>" for x in TEXTOS[ident]["lineas"])
    return f'<html><body><div id="textoxslt">{ps}</div></body></html>'


class TestNumeros(unittest.TestCase):
    def test_palabras(self):
        self.assertEqual(C.numero("Una"), 1)
        self.assertEqual(C.numero("Setenta y seis"), 76)
        self.assertEqual(C.numero("dos (2)"), 2)
        self.assertEqual(C.numero("14"), 14)

    def test_contradiccion_no_da_cifra(self):
        self.assertIsNone(C.numero("tres (4)"))
        self.assertIsNone(C.numero("varias"))


class TestLocal(unittest.TestCase):
    def test_titular_brigada(self):
        r = reg("BOE-A-2026-20555")
        self.assertEqual(C.titular(r), "2 plazas de Operario/a de brigada municipal de obras · Tamarite de Litera")
        self.assertIn("Turno libre 2", C.chips(r))
        self.assertIn("Bases: Boletín Oficial de la Provincia de Huesca", C.chips(r))

    def test_turnos_mixtos(self):
        c = reg("BOE-A-2026-20418")["campos"]
        self.assertEqual(c["plazas"], 5)
        self.assertEqual(c["turnos"], {"promocion interna": 4, "libre": 1})

    def test_reserva_discapacidad(self):
        self.assertEqual(reg("BOE-A-2026-20638")["campos"]["turnos"], {"libre": 1, "discapacidad": 1})

    def test_numero_en_palabras(self):
        self.assertEqual(reg("BOE-A-2026-20571")["campos"]["plazas"], 76)

    def test_cuerpo_hasta_la_coma(self):
        self.assertEqual(C.titular(reg("BOE-A-2026-21569")), "1 plaza de Psicólogo/a · Cártama")

    def test_lista_acaba_en_texto(self):
        # «Dichas bases fueron rectificadas…» no es una línea de plaza
        self.assertEqual(C.titular(reg("BOE-A-2026-20852")), "1 plaza de Educador/a Social · La Roda")

    def test_puestos_y_diputacion(self):
        r = reg("BOE-A-2026-22112")
        self.assertEqual(r["campos"]["sistema"], "Concurso")
        self.assertTrue(C.titular(r).startswith("3 puestos"))
        self.assertTrue(C.titular(r).endswith("· Diputación Provincial de León"))

    def test_movilidad(self):
        self.assertEqual(reg("BOE-A-2026-21360")["campos"]["turnos"], {"movilidad": 1})

    def test_correccion_solo_etiqueta(self):
        r = reg("BOE-A-2026-21716")
        self.assertEqual(r.get("no_oferta"), "correccion")
        self.assertNotIn("campos", r)
        self.assertEqual(C.etiqueta_no_oferta(r), "Corrección")
        self.assertEqual(C.titular(r), "")
        self.assertEqual(C.chips(r), [])

    def test_sin_nombres_en_campos(self):
        for i in TEXTOS:
            self.assertNotIn("Alcald", json.dumps(reg(i), ensure_ascii=False).split('"titulo"')[0])


class TestInterruptor(unittest.TestCase):
    def test_familias_apagadas(self):
        for fam in ("universidad", "estado", "provision"):
            self.assertEqual(C.CAMPOS_ACTIVOS[fam], frozenset())
        r = {"titulo": "x", "dept": "MINISTERIO DE HACIENDA", "tipo": "convocatoria",
             "campos": {"plazas": 3, "lineas": [{"cuerpo": "X", "clase": "plaza"}], "localidad": "Y"}}
        self.assertEqual(C.titular(r), "")
        self.assertEqual(C.chips(r), [])

    def test_apagar_campo_local(self):
        r = reg("BOE-A-2026-20555")
        viejo = C.CAMPOS_ACTIVOS["local"]
        try:
            C.CAMPOS_ACTIVOS["local"] = viejo - {"plazas"}
            self.assertEqual(C.titular(r), "")   # sin plazas no hay titular: se usa el corto
        finally:
            C.CAMPOS_ACTIVOS["local"] = viejo

    def test_no_oferta_apagada_fuera_de_local(self):
        r = {"titulo": "Corrección de errores de la Resolución…", "dept": "UNIVERSIDADES",
             "tipo": "convocatoria", "no_oferta": "correccion"}
        self.assertEqual(C.etiqueta_no_oferta(r), "")


class TestDetalle(unittest.TestCase):
    def test_detalle_guarda_campos(self):
        d = TEXTOS["BOE-A-2026-20555"]
        out = em.detalle(html("BOE-A-2026-20555"), {"titulo": d["titulo"], "dept": d["dept"], "tipo": "convocatoria"})
        self.assertEqual(out["campos"]["plazas"], 2)
        self.assertIn("veinte días naturales", out["plazo"])

    def test_enriquecer_reutiliza_campos(self):
        previo = {"X": {"leido": 1, "campos": {"plazas": 2}, "plazo": "p"}}
        r = [{"id": "X", "titulo": "convoca", "tipo": "convocatoria", "dept": "ADMINISTRACIÓN LOCAL"}]
        em.enriquecer(r, get=None, log=lambda *_: None, previo=previo)
        self.assertEqual(r[0]["campos"], {"plazas": 2})


class TestTarjeta(unittest.TestCase):
    setUp = TestPaginas.setUp
    tearDown = TestPaginas.tearDown

    def test_tarjeta_con_titular_generado_y_sin_campos_viejos(self):
        r = reg("BOE-A-2026-20555")
        r.update({"fecha": self._fecha(), "prov": "huesca"})
        self.estado["registros"][r["id"]] = r
        h, _ = h_prueba(self.carpeta)
        em.generar_paginas(h, self.estado)
        idx = (self.carpeta / "index.html").read_text(encoding="utf-8")
        self.assertIn("2 plazas de Operario/a de brigada municipal de obras · Tamarite de Litera", idx)
        self.assertIn('class="em-chip"', idx)
        # Los registros sin 'campos' (anteriores al extractor) siguen pintándose
        self.assertGreater(len(re.findall(r'<li class="em-card">', idx)), 1)

    def _fecha(self):
        return max(v["fecha"] for v in self.estado["registros"].values())


if __name__ == "__main__":
    unittest.main()
