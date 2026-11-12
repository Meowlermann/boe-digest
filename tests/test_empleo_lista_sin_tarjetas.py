"""Tanda 3-B / 4: TODAS las fichas /empleo/provincia-*.html en filas tipográficas
(sin tarjetas); /empleo/ también, igual que ellas. Las fichas por organismo
siguen con tarjetas.
Lo que no consta no se pinta; nunca plazos ni estados calculados. Sin red."""
import pathlib
import re
import sys
import unittest
from unittest import mock

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))
import empleo as em  # noqa: E402
from test_empleo import TestPaginas, h_prueba  # noqa: E402
from test_empleo_ficha_provincia_clara import campos  # noqa: E402

FILA = r'<li class="em-fila[^"]*".*?</li>'


class Filas(TestPaginas):
    def generar(self):
        h, _ = h_prueba(self.carpeta)
        em.generar_paginas(h, self.estado)
        prov = {f.name[len("provincia-"):-5]: campos(f) for f in self.carpeta.glob("provincia-*.html")}
        otras = {f.name: campos(f) for f in self.carpeta.glob("*.html") if not f.name.startswith("provincia-")}
        return prov, otras

    def test_todas_las_provincias_sin_tarjetas(self):
        prov, otras = self.generar()
        self.assertTrue(prov)
        self.assertFalse(hasattr(em, "LISTA_SIN_TARJETAS"))
        for p, c in prov.items():
            with self.subTest(p):
                self.assertIn('class="tr-ix-em-filas"', c["CUERPO"])
                self.assertNotIn("em-card", c["CUERPO"])
                self.assertNotIn('class="aside-note">«Turno libre»', c["CUERPO"])
        # /empleo/ (índice) también en filas; las tarjetas quedan en organismos.
        self.assertIn('class="tr-ix-em-filas"', otras["index.html"]["CUERPO"])
        self.assertNotIn("em-card", otras["index.html"]["CUERPO"])
        self.assertTrue(any(
            n not in {"index.html", "provincias.html", "organismos.html"} and "em-card" in c.get("CUERPO", "")
            for n, c in otras.items()))

    def test_lo_que_no_consta_no_se_pinta(self):
        prov, _ = self.generar()
        vistas = 0
        for c in prov.values():
            for li in re.findall(FILA, c["CUERPO"], re.S):
                vistas += 1
                self.assertNotRegex(li, r"Plazo:</b>\s*<")
                self.assertNotRegex(li, r"cierra|abiert[oa] hasta|cerrad[oa]|quedan")
                self.assertEqual(li.count("<a "), 1)
                self.assertNotIn("em-chip", li)
                self.assertNotIn("em-etq", li)
        self.assertTrue(vistas)

    def test_procedimiento_literal(self):
        prov, _ = self.generar()
        regs = {r["id"]: r for r in self.todos}
        for c in prov.values():
            for li in re.findall(FILA, c["CUERPO"], re.S):
                r = regs.get(re.search(r"BOE-A-\d{4}-\d+", li).group(0))
                if not r:
                    continue
                proc = r.get("proc") if r["tipo"] == "convocatoria" else None
                if proc in em.PROC_LISTA:
                    self.assertIn(f'<span class="em-f-tipo">{proc}</span>', li)
                else:
                    self.assertNotIn("em-f-tipo", li)

    def test_turno_y_nota_junto_a_la_primera_fila(self):
        prov, _ = self.generar()
        ids = [m for c in prov.values() for m in re.findall(
            r'<li class="em-fila[^"]*"[^>]*>.*?(BOE-A-\d{4}-\d+)', c["CUERPO"], re.S)]
        objetivo = set(ids[:2])
        original = em.empleo_campos.activos

        def falso(reg):
            c = dict(original(reg))
            c.pop("turnos", None)
            if reg.get("id") in objetivo:
                c["turnos"] = {"libre": 2, "promocion interna": 1, "discapacidad": 1}
            return c
        with mock.patch.object(em.empleo_campos, "activos", side_effect=falso):
            prov, _ = self.generar()
        for c in prov.values():
            filas = re.findall(FILA, c["CUERPO"], re.S)
            con = [li for li in filas if "em-f-turno" in li]
            for li in filas:
                if any(i in li for i in objetivo):
                    self.assertIn('<span class="em-f-nw">Turno libre</span> · '
                                  '<span class="em-f-nw">Promoción interna</span>', li)
                    self.assertNotIn("discapacidad", li)
                else:
                    self.assertNotIn("em-f-turno", li)
            if con:
                # La nota va en la primera fila con turno (tras el enlace), una sola vez.
                self.assertIn(f'</a><span class="em-f-nota">{em.NOTA_TURNOS["Turno libre"]}</span>', con[0])
                self.assertEqual(c["CUERPO"].count(em.NOTA_TURNOS["Turno libre"]), 1)
            else:
                self.assertNotIn("em-f-nota", c["CUERPO"])

    def test_plazo_literal_o_aviso_como_la_tarjeta(self):
        prov, _ = self.generar()
        regs = {r["id"]: r for r in self.todos}
        con_aviso = 0
        for c in prov.values():
            for li in re.findall(FILA, c["CUERPO"], re.S):
                r = regs.get(re.search(r"BOE-A-\d{4}-\d+", li).group(0))
                if not r:
                    continue
                abierta = r["tipo"] in em.ORDEN_ABIERTOS and not em.empleo_campos.etiqueta_no_oferta(r)
                literal = em.plazo_tarjeta(r)
                if abierta and literal:
                    self.assertIn("<b>Plazo:</b>", li)
                    self.assertNotIn(em.SIN_PLAZO, li)
                elif abierta:
                    con_aviso += 1
                    self.assertIn(f'<span class="em-f-plazo em-f-sin">{em.SIN_PLAZO}</span>', li)
                    self.assertNotIn("<b>Plazo:</b>", li)
                else:
                    self.assertNotIn("em-f-plazo", li)
                if abierta:
                    self.assertRegex(li, r'<a class="em-f-a" href="https://www\.boe\.es/')
        self.assertTrue(con_aviso)

    def test_texto_turnos(self):
        pl = {"lineas": [{"n": 1, "clase": "plaza"}, {"n": 2, "clase": "plaza"}]}
        self.assertEqual(em.texto_turnos({"libre": 1}, pl), "Turno libre: 1 plaza")
        self.assertEqual(em.texto_turnos({"libre": 2, "promocion interna": 1}, pl),
                         "Turno libre: 2 plazas · Promoción interna: 1 plaza")
        self.assertEqual(em.texto_turnos({"libre": 2}, {"lineas": [{"n": 2, "clase": "puesto"}]}), "Turno libre")
        self.assertEqual(em.texto_turnos({"libre": 2}, {}), "Turno libre")

    def test_antiguedad_como_la_tarjeta(self):
        prov, _ = self.generar()
        n = 0
        for c in prov.values():
            for li in re.findall(FILA, c["CUERPO"], re.S):
                n += 1
                self.assertRegex(li, r'<span class="em-hace">\([^<)]+\)</span>')
        self.assertTrue(n)

    def test_indice_general_en_filas(self):
        """ /empleo/ reutiliza la lista compacta: sin tarjetas, con plazo literal,
        diario o aviso, enlace al BOE y los data-* que necesitan los filtros. """
        _, otras = self.generar()
        cuerpo = otras["index.html"]["CUERPO"]
        self.assertNotIn("em-card", cuerpo)
        self.assertIn('class="tr-ix-em-filas"', cuerpo)
        filas = re.findall(FILA, cuerpo, re.S)
        self.assertTrue(filas)
        self.assertTrue(any("<b>Plazo:</b>" in li or "em-f-sin" in li for li in filas))
        self.assertTrue(all("Ver en el BOE" in li for li in filas))
        self.assertTrue(all('data-o="' in li and 'data-p="' in li for li in filas))
        self.assertTrue(all("em-c-" in li[:120] for li in filas))

    def test_noindex_sin_oposiciones(self):

        """Las fichas con 0 oposiciones (p. ej. Zamora) siguen en noindex."""
        h, _ = h_prueba(self.carpeta)
        salidas = em.generar_paginas(h, self.estado)
        prov = {s["url"].rsplit("provincia-", 1)[1][:-5]: s for s in salidas if "/provincia-" in s["url"]}
        self.assertTrue(prov)
        for p, s in prov.items():
            c = campos(self.carpeta / f"provincia-{p}.html")
            self.assertEqual(s["indexable"], not c["STANDFIRST"].startswith("0 "), p)

    def test_css_sin_cajas(self):
        css = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")
        reglas = [l for l in css.splitlines() if l.startswith(".tr-ix-em-filas")]
        self.assertTrue(reglas)
        for l in reglas:
            self.assertNotIn("underline", l)
            self.assertNotIn("gradient", l)
            self.assertNotRegex(l, r"box-shadow:(?!none)")
        self.assertIn(".tr-ix-em-filas .em-f-a{display:block;min-height:44px", css)
        self.assertIn(".tr-ix-em-filas .em-f-nw{white-space:nowrap}", css)


if __name__ == "__main__":
    unittest.main()
