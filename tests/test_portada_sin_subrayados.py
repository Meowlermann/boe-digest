"""«Portada: sin subrayados»: sin subrayado en reposo, con pistas de enlace
(color, peso, hover y foco), filetes de la línea de elecciones con contraste
y espacio duro antes de las flechas. Sin red."""
import pathlib
import re
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import build  # noqa: E402

CSS = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")


def regla(sel):
    m = re.search(re.escape(sel) + r"\{([^}]*)\}", CSS)
    assert m, sel
    return m.group(1)


def luminancia(hexa):
    c = [int(hexa[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contraste(a, b):
    la, lb = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


class Portada(unittest.TestCase):
    def test_body_marca_la_portada(self):
        self.assertIn('<body class="portada">', (RAIZ / "template.html").read_text(encoding="utf-8"))

    def test_sin_subrayado_en_reposo_y_pistas_de_enlace(self):
        # Ningún subrayado en ningún estado (tampoco hover, foco ni pie).
        todos = regla("body.portada a,body.portada a:hover,body.portada a:focus,body.portada a:focus-visible")
        self.assertIn("text-decoration:none", todos)
        bloque = CSS[CSS.index("«Portada: sin subrayados»"):]
        self.assertNotIn("underline", bloque)
        self.assertIn("background:", regla("body.portada .wrap :is(p,li,dd,span,h2,h3,div.nb-l,footer) > a:hover"))
        foco = regla("\nbody.portada a:focus-visible")
        self.assertIn("outline:2px solid", foco)
        nb = regla("body.portada .nb-l a:not(.srclink)")
        self.assertIn("font-weight:600", nb)
        self.assertIn("color:", nb)
        self.assertIn("color:", regla("body.portada .vtb-d a"))

    def test_filetes_de_la_linea_de_elecciones_entre_3_y_3_5(self):
        self.assertIn("solid var(--filete-29n)", regla(".campana-29n"))
        bgs = re.findall(r"--bg:(#[0-9a-fA-F]{6})", CSS)
        filetes = re.findall(r"--filete-29n:(#[0-9a-fA-F]{6})", CSS)
        self.assertEqual(len(filetes), 3)                     # claro, oscuro (sistema) y oscuro (data-theme)
        self.assertEqual(filetes[1], filetes[2])
        self.assertNotEqual(bgs[0], bgs[1])
        for bg, f in ((bgs[0], filetes[0]), (bgs[1], filetes[1])):
            self.assertTrue(3.0 <= contraste(bg, f) <= 3.5, (bg, f, contraste(bg, f)))

    def test_flechas_con_espacio_duro(self):
        self.assertIn("&nbsp;→</a>", build.linea_campana_portada())
        src = (RAIZ / "build.py").read_text(encoding="utf-8")
        self.assertIn("votaciones&nbsp;→</a></p>'", src)            # «Todas las votaciones», con flecha
        el = (RAIZ / "elecciones.py").read_text(encoding="utf-8")
        self.assertNotIn(" →</a>", el)


if __name__ == "__main__":
    unittest.main()
