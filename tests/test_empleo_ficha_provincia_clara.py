"""Tanda 2-A: en cada /empleo/provincia-*.html, recuento visible «N convocatorias
publicadas en el BOE en los últimos 90 días» (N = el de la description) y
«Última convocatoria publicada el {fecha}». Sin red."""
import pathlib
import re
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))
import empleo as em  # noqa: E402
from test_empleo import TestPaginas, h_prueba  # noqa: E402


def campos(ruta):
    out = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        k, _, v = linea.partition("=")
        if k.isupper() and k not in out:
            out[k] = v
    return out


class FichaProvincia(TestPaginas):
    def test_recuento_y_fecha_en_todas(self):
        h, _ = h_prueba(self.carpeta)
        em.generar_paginas(h, self.estado)
        fichas = sorted(self.carpeta.glob("provincia-*.html"))
        self.assertTrue(fichas)
        for f in fichas:
            with self.subTest(f.name):
                c = campos(f)
                m = re.match(r"(\d+) (?:oposición u otra convocatoria de plazas publicada|oposiciones y otras convocatorias de plazas publicadas) en el BOE en los últimos 90 días", c["STANDFIRST"])
                self.assertIsNotNone(m, c["STANDFIRST"])
                n = int(m.group(1))
                if n:
                    self.assertTrue(c["META_DESC"].startswith(f"{n} convocatoria"), c["META_DESC"])
                    self.assertRegex(c["EDITION_DATE"], r"^Última convocatoria publicada el \d{4}-\d{2}-\d{2}$")
                else:
                    self.assertEqual(c["EDITION_DATE"], "Sin convocatorias en los últimos 90 días")
                self.assertNotIn("II.B", c["STANDFIRST"] + c["KICKER"] + c["EDITION_DATE"])

    def test_fecha_es_la_mas_reciente(self):
        filas = [{"tipo": "convocatoria", "fecha": "2026-10-01"}, {"tipo": "convocatoria", "fecha": "2026-10-20"},
                 {"tipo": "admitidos", "fecha": "2026-10-30"}]
        self.assertEqual(em.texto_fecha_provincia(filas), "Última convocatoria publicada el 2026-10-20")
        self.assertTrue(em.texto_recuento_provincia(1, "Soria").startswith(
            "1 oposición u otra convocatoria de plazas publicada en el BOE en los últimos 90 días"))


class CoherenciaRecuentoLista(TestPaginas):
    """Lo que dice la entradilla y lo que se lista debajo salen de la misma fuente
    (caso Zamora: 0 oposiciones y, debajo, un traslado) en TODAS las fichas."""
    def test_entradilla_tabla_y_bloques_cuadran(self):
        h, _ = h_prueba(self.carpeta)
        em.generar_paginas(h, self.estado)
        for f in sorted(self.carpeta.glob("provincia-*.html")):
            with self.subTest(f.name):
                c = campos(f)
                cuerpo, ficha = c["CUERPO"], c["FICHA"]
                n = int(re.match(r"\d+", c["STANDFIRST"]).group(0))
                bloques = dict(re.findall(r'<h[23] id="t-(\w+)">[^<]*\((\d+)\)</h[23]>', cuerpo))
                self.assertEqual(int(bloques.get("convocatoria", 0)), n)
                tabla = dict(re.findall(r'<dd><a href="#t-(\w+)">(\d+)</a></dd>', ficha.split("</dd>", 1)[1]))
                self.assertEqual({k: int(v) for k, v in tabla.items()}, {k: int(v) for k, v in bloques.items()})
                self.assertIn(f">{sum(map(int, bloques.values()))}</a></dd>", ficha.split("</dd>", 1)[0] + "</dd>")
                self.assertTrue(c["FICHA"].startswith(f"<dt>{em.TOTAL_PROVINCIA}</dt>"))
                otros = {k: v for k, v in bloques.items() if k != "convocatoria"}
                if not n and otros:
                    for k, v in otros.items():
                        self.assertIn(f"{em.ETIQUETA_PROVINCIA[k]}: {v}", c["STANDFIRST"])
                self.assertIn("La Tercera Cámara →</a>", cuerpo)
                self.assertNotIn("II.B", c.get("FUENTE", ""))


class CSSProvincia(unittest.TestCase):
    def test_sin_subrayado_y_con_foco(self):
        css = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")
        self.assertIn("body:has(.tr-ix-em-prov) .ficha dd a, .tr-ix-em-prov a{text-decoration:none;", css)
        self.assertIn(".tr-ix-em-prov a:focus-visible{outline:2px solid var(--red)", css)
        self.assertIn('<p class="tr-ix-em-prov">', (RAIZ / "empleo.py").read_text(encoding="utf-8"))
        bloque = css.split("/* --- /empleo/")[1].split("/* --- fin /empleo/")[0]
        for linea in bloque.splitlines():
            if "tr-ix-em-prov" in linea:
                self.assertNotIn("underline", linea)
        self.assertIn("min-width:44px;min-height:32px", css)


if __name__ == "__main__":
    unittest.main()
