"""/seguimiento/: mismo lenguaje que /tramitacion/, sin subrayados y acotado."""
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CSS = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")
INI, FIN = "/* --- /seguimiento/ (reutiliza", "/* --- fin /seguimiento/"


def bloque() -> str:
    return CSS[CSS.index(INI):CSS.index(FIN)]


class SeguimientoIndice(unittest.TestCase):
    def test_sin_subrayado(self):
        self.assertNotIn("underline", bloque())

    def test_reutiliza_tr_ix(self):
        # Las reglas generales (sin subrayado, migas, foco) vienen de .tr-ix.
        self.assertIn("body:has(.tr-ix) a{text-decoration:none}", CSS)
        self.assertIn("body:has(.tr-ix) a:focus-visible{outline:3px", CSS)
        self.assertIn("body:has(.tr-ix) .miga a{border-bottom:0", CSS)

    def test_pie_acotado(self):
        self.assertIn("body:has(.tr-ix-seg) footer a", bloque())

    def test_selectores_acotados(self):
        cuerpo = re.sub(r"/\*.*?\*/", "", bloque(), flags=re.S)
        for sel in re.findall(r"([^{}@]+)\{[^{}]*\}", cuerpo):
            for s in sel.split(","):
                s = s.strip()
                if s:
                    self.assertTrue(s.startswith((".tr-ix", "body:has(.tr-ix")), s)

    def test_build_usa_clases(self):
        src = (RAIZ / "build.py").read_text(encoding="utf-8")
        i = src.index("def renderizar_seguimiento")
        trozo = src[i:src.index("\ndef ", i + 10)]
        for c in ("tr-ix tr-ix-seg", "tr-ix-movs", "tr-ix-tarjetas", "tr-ix-lado", "/provincias/"):
            self.assertIn(c, trozo)


if __name__ == "__main__":
    unittest.main()
