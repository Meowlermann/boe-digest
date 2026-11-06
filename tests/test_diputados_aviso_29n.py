"""Tanda 1-B: aviso de legislatura disuelta y frase de grupo en /diputados/. Sin red."""
import pathlib
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import build  # noqa: E402


class Aviso(unittest.TestCase):
    def test_fuente_oficial_y_fecha(self):
        a = build.AVISO_LEGISLATURA
        self.assertIn("https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-20742", a)
        self.assertIn("Real Decreto 806/2026", a)
        self.assertIn("29 de noviembre de 2026", a)
        self.assertIn("XV Legislatura", a)
        self.assertIn('role="note"', a)

    def test_frase_grupo_con_reparto(self):
        gente = [{"circunscripcion": "Madrid"}, {"circunscripcion": "Madrid"},
                 {"circunscripcion": "Ávila"}]
        h = build.frase_grupo("Grupo Parlamentario X", gente)
        self.assertIn("tenía <b>3</b> diputados", h)
        self.assertIn("Por circunscripción: Madrid 2 · Ávila 1.", h)
        self.assertIn("1 diputado en", build.frase_grupo("G", [{"circunscripcion": ""}]).replace("<b>", "").replace("</b>", ""))

    def test_css_sin_subrayado(self):
        css = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")
        bloque = css[css.index(".aviso-leg{"):css.index(".destacado{")]
        self.assertNotIn("underline", bloque)


if __name__ == "__main__":
    unittest.main()


class Ajustes(unittest.TestCase):
    def test_aviso_antes_de_la_tabla(self):
        pl = build.plantilla_con_aviso('<p class="entradilla">x</p>\n<dl class="ficha">y</dl>')
        self.assertLess(pl.index("aviso-leg"), pl.index('<dl class="ficha">'))
        self.assertGreater(pl.index("aviso-leg"), pl.index("entradilla"))
        self.assertIn("23 de diciembre", build.AVISO_LEGISLATURA)

    def test_nombre_oficial_una_vez(self):
        g = [{"circunscripcion": "Madrid"}]
        self.assertIn("El Grupo PSOE (Grupo Parlamentario Socialista) tenía",
                      build.frase_grupo("Grupo PSOE", g, "Grupo Parlamentario Socialista"))
        self.assertIn("El Grupo Mixto tenía", build.frase_grupo("Grupo Mixto", g, "Grupo Parlamentario Mixto"))
        self.assertIn("El Grupo Vox tenía", build.frase_grupo("Grupo Vox", g, "Grupo Parlamentario VOX"))

    def test_un_nombre_por_grupo(self):
        self.assertEqual(build.nombre_grupo("Grupo Parlamentario Socialista"), "Grupo PSOE")
        self.assertEqual(build.nombre_grupo("Grupo Parlamentario Mixto"), "Grupo Mixto")

    def test_entradillas_atadas_a_la_xv(self):
        src = (RAIZ / "build.py").read_text(encoding="utf-8")
        # La entradilla ya no usa el presente; la description de main sí (desacoplada).
        self.assertEqual(src.count("diputados que representan a {prov} en el Congreso"), 1)
        self.assertIn("meta_desc=desc_p or (", src)
        self.assertIn('f"Ficha de cada uno de los {len(gente)} diputados del {largo}: sus "', src)
        self.assertIn("en la {LEGISLATURA_DISUELTA}, con su actividad y sus votos.", src)
