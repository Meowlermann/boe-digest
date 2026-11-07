"""Tanda 3-B: piloto «lista sin tarjetas» solo en las fichas de LISTA_SIN_TARJETAS.
Filas tipográficas; lo que no consta no se pinta; nunca plazos calculados. Sin red."""
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


class Piloto(TestPaginas):
    def generar(self, activas):
        with mock.patch.object(em, "LISTA_SIN_TARJETAS", frozenset(activas)):
            h, _ = h_prueba(self.carpeta)
            em.generar_paginas(h, self.estado)
        return {f.name[len("provincia-"):-5]: campos(f) for f in self.carpeta.glob("provincia-*.html")}

    def test_solo_la_ficha_piloto(self):
        todas = self.generar(())
        self.assertTrue(todas)
        piloto = sorted(todas)[0]
        con = self.generar({piloto})
        for p, c in con.items():
            with self.subTest(p):
                if p == piloto:
                    self.assertIn('class="tr-ix-em-lista"', c["CUERPO"])
                    self.assertNotIn("em-card", c["CUERPO"])
                else:
                    self.assertEqual(c, todas[p])
                for k in ("TITLE", "META_DESC", "CANONICAL", "STANDFIRST", "FICHA"):
                    self.assertEqual(c.get(k), todas[p].get(k))
        self.assertTrue(em.LISTA_SIN_TARJETAS == frozenset({"zaragoza"}))

    def test_lo_que_no_consta_no_se_pinta(self):
        con = self.generar(set(self.generar(())))
        vistas = 0
        for c in con.values():
            for li in re.findall(r'<li class="em-fila".*?</li>', c["CUERPO"], re.S):
                vistas += 1
                self.assertNotIn(em.SIN_PLAZO, li)
                self.assertNotRegex(li, r"Plazo:</b>\s*<")
                self.assertNotRegex(li, r"hace \d+ d|cierra|abiert[oa]|cerrad[oa]|quedan")
                self.assertEqual(li.count("<a "), 1)
                self.assertRegex(li, r'<a class="em-f-a" href="https://www\.boe\.es/')
        self.assertTrue(vistas)

    def test_turno_solo_si_consta(self):
        """Solo donde el campo literal «turnos» está activo; nunca inferido;
        solo Turno libre / Promoción interna; sin chip ni etiqueta."""
        base = self.generar(set(self.generar(())))
        ids = [m for c in base.values() for m in re.findall(
            r'<li class="em-fila"[^>]*>.*?(BOE-A-\d{4}-\d+)', c["CUERPO"], re.S)]
        self.assertTrue(ids)
        objetivo = ids[0]
        original = em.empleo_campos.activos

        def falso(reg):
            c = dict(original(reg))
            c.pop("turnos", None)
            if reg.get("id") == objetivo:
                c["turnos"] = {"libre": 2, "promocion interna": 1, "discapacidad": 1}
            return c
        with mock.patch.object(em.empleo_campos, "activos", side_effect=falso):
            con = self.generar(set(self.generar(())))
        vistos = 0
        for c in con.values():
            for li in re.findall(r'<li class="em-fila".*?</li>', c["CUERPO"], re.S):
                self.assertNotIn("em-chip", li)
                self.assertNotIn("em-etq", li)
                if objetivo in li:
                    vistos += 1
                    self.assertIn('<span class="em-f-turno">Turno libre 2 · Promoción interna 1</span>', li)
                    self.assertNotIn("discapacidad", li)
                else:
                    self.assertNotIn("em-f-turno", li)
                    self.assertNotIn("Turno libre", li)
        self.assertTrue(vistos)

    def test_css_sin_cajas(self):
        css = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")
        reglas = [l for l in css.splitlines() if l.startswith(".tr-ix-em-lista")]
        self.assertTrue(reglas)
        for l in reglas:
            self.assertNotIn("underline", l)
            self.assertNotIn("gradient", l)
            self.assertNotRegex(l, r"box-shadow:(?!none)")
        self.assertIn(".tr-ix-em-lista .em-f-a{display:block;min-height:44px", css)


if __name__ == "__main__":
    unittest.main()
