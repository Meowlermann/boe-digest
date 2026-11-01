"""UX-3: botones de filtro de /empleo/ (tipo y «Últimos 30 días»). Sin JS se
ve el listado completo: los botones salen con hidden y todas las tarjetas
están en el HTML. JS propio y pequeño. Sin red."""
import pathlib
import re
import sys
import tempfile
import unittest

RAIZ_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_REPO))
sys.path.insert(0, str(RAIZ_REPO / "tests"))

import empleo as em  # noqa: E402
from test_empleo import h_prueba  # noqa: E402

JS = RAIZ_REPO / "assets" / "empleo.js"


class TestFiltro(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.carpeta = pathlib.Path(self.tmp.name) / "empleo"
        fechas = ["2026-10-27", "2026-10-20", "2026-09-01", "2026-08-10"]
        regs = {f"BOE-A-2026-{i}": {"fecha": fechas[i % 4], "titulo": f"Convocatoria {i}",
                                     "dept": "MINISTERIO X", "prov": [],
                                     "tipo": "convocatoria" if i < 5 else "admitidos"}
                for i in range(1, 9)}
        self.estado = {"version": 1, "registros": regs, "dias": {}}
        h, _ = h_prueba(self.carpeta)
        h["hoy"] = "2026-10-28"
        em.generar_paginas(h, self.estado)
        self.idx = (self.carpeta / "index.html").read_text(encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_sin_js_listado_completo(self):
        # Las 8 tarjetas están en el HTML (también las de más de 30 días) y el
        # filtro sale oculto: sin JS no hay botones que no hagan nada.
        self.assertEqual(len(re.findall(r'<li class="em-card"', self.idx)), 8)
        self.assertRegex(self.idx, r'<div id="filtro-tipo" class="em-filtro" data-ref="[\d-]+" data-defecto="convocatoria" hidden>')
        self.assertIn(f'<script src="{em.JS_FILTRO}" defer></script>', self.idx)

    def test_botones_de_los_tipos_existentes(self):
        tipos = re.findall(r'data-f="tipo" data-v="(\w*)"', self.idx)
        # Pestañas (lenguaje llano): los mismos valores de ?tipo= que UX-3,
        # Convocatorias primero y seleccionada, y «Todas» al final.
        self.assertEqual(tipos, ["convocatoria", "admitidos", "todas"])
        for t in tipos[:-1]:
            self.assertIn(t, em.ETIQUETA_TIPO)
        self.assertIn(f'data-f="dias" data-v="{em.DIAS_FILTRO}" aria-pressed="false">'
                      f'Últimos {em.DIAS_FILTRO} días</button>', self.idx)
        self.assertEqual(self.idx.count('role="tablist"'), 1)
        self.assertEqual(self.idx.count('role="group"'), 1)
        tabs = re.findall(r'<button[^>]*role="tab"[^>]*>', self.idx)
        self.assertEqual(len(tabs), 3)
        self.assertEqual(sum('aria-selected="true"' in b for b in tabs), 1)
        self.assertIn('id="tab-convocatoria"', tabs[0])
        self.assertIn('aria-controls="p-convocatoria"', tabs[0])
        self.assertIn('tabindex="0"', tabs[0])
        self.assertTrue(all('tabindex="-1"' in b for b in tabs[1:]))
        self.assertIn('id="p-convocatoria"', self.idx)
        for b in re.findall(r"<button[^>]*>", self.idx):
            self.assertIn('type="button"', b)
            if "em-ant" in b or "em-sig" in b:   # ‹ › de los carriles: acciones, sin estado
                continue
            self.assertRegex(b, r'aria-(pressed|selected|expanded)="(true|false)"')

    def test_tarjetas_con_fecha_y_secciones_con_tipo(self):
        for li in re.findall(r'<li class="em-card"[^>]*>', self.idx):
            self.assertRegex(li, r'data-fecha="\d{4}-\d\d-\d\d"')
        self.assertIn('<section class="em-sec" id="p-convocatoria" data-tipo="convocatoria">', self.idx)

    def test_fichas_sin_filtro(self):
        ficha = (self.carpeta / "ministerio-x.html").read_text(encoding="utf-8")
        self.assertNotIn("filtro-tipo", ficha)

    def test_js_pequeno_y_sin_dependencias(self):
        js = JS.read_text(encoding="utf-8")
        self.assertLess(len(js.encode("utf-8")), 5 * 1024)   # 3 KB + carriles (01-11-2026)
        self.assertNotRegex(js, r"\b(import|require|fetch|XMLHttpRequest|eval)\b")
        self.assertIn("replaceState", js)
        self.assertIn('location.hash', js)
        for k in ("ArrowRight", "ArrowLeft", "Home", "End", "tabpanel", "aria-selected", "hashchange"):
            self.assertIn(k, js)


if __name__ == "__main__":
    unittest.main()
