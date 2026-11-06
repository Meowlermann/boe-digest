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
