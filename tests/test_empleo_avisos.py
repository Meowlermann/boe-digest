"""UX-3: bloque «Recibe avisos» de /empleo/ y enlace desde /seguir/. Solo
canales Atom que existen; nada de correo. Sin red."""
import pathlib
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

RAIZ_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_REPO))
sys.path.insert(0, str(RAIZ_REPO / "tests"))

import empleo as em  # noqa: E402
import paginas_fijas as pf  # noqa: E402
from test_empleo import h_prueba  # noqa: E402

ATOM = "{http://www.w3.org/2005/Atom}"


class TestAvisos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.carpeta = pathlib.Path(self.tmp.name) / "empleo"
        regs = {f"BOE-A-2026-{i}": {"fecha": "2026-10-27", "titulo": f"Convocatoria {i} en Soria",
                                     "dept": "MINISTERIO X" if i % 2 else "UNIVERSIDAD Y",
                                     "prov": ["soria"], "tipo": "convocatoria"} for i in range(1, 5)}
        self.estado = {"version": 1, "registros": regs, "dias": {}}
        self.h, _ = h_prueba(self.carpeta)
        self.h["hoy"] = "2026-10-28"
        self.h.setdefault("ref_provincias", [])
        if not any(p["slug"] == "soria" for p in self.h["ref_provincias"]):
            self.h["ref_provincias"] = list(self.h["ref_provincias"]) + [{"slug": "soria", "nombre": "Soria"}]

    def tearDown(self):
        self.tmp.cleanup()

    def test_bloque_enlaza_canales_que_existen(self):
        em.canales(self.h, self.estado)
        em.generar_paginas(self.h, self.estado)
        idx = (self.carpeta / "index.html").read_text(encoding="utf-8")
        self.assertIn('<section id="avisos"', idx)
        self.assertIn('<h2 id="avisos-t">Recibe avisos</h2>', idx)
        bloque = idx[idx.index('<section id="avisos"'):]
        bloque = bloque[:bloque.index("</section>")]
        xmls = re.findall(r'href="([^"]+\.xml)"', bloque)
        self.assertIn(em.RSS_EMPLEO, xmls)
        self.assertIn("provincia-soria.xml", xmls)
        self.assertIn("ministerio-x.xml", xmls)
        for x in xmls:
            ruta = self.carpeta / pathlib.Path(x).name
            self.assertTrue(ruta.exists(), x)
            raiz = ET.fromstring(ruta.read_text(encoding="utf-8"))
            self.assertEqual(raiz.tag, f"{ATOM}feed")
            for campo in ("id", "title", "updated"):
                self.assertIsNotNone(raiz.find(f"{ATOM}{campo}"), (x, campo))
            self.assertTrue(raiz.findall(f"{ATOM}entry"), x)
        # Solo RSS: ni correo ni formularios.
        self.assertNotRegex(bloque.lower(), r"mailto:|<form|<input|boletín|newsletter|@")

    def test_sin_datos_no_hay_bloque(self):
        em.generar_paginas(self.h, {"version": 1, "registros": {}, "dias": {}})
        self.assertNotIn('id="avisos"', (self.carpeta / "index.html").read_text(encoding="utf-8"))

    def test_seguir_enlaza_avisos(self):
        self.assertIn('<a href="/empleo/#avisos">', pf.seguir_con_empleo(pf.SEGUIR, True))
        sin = pf.seguir_con_empleo(pf.SEGUIR, False)
        self.assertNotIn("/empleo/#avisos", sin)
        self.assertNotIn("/empleo/index.xml", sin)


if __name__ == "__main__":
    unittest.main()
