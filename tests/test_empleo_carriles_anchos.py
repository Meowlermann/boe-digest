"""Carriles anchos en /empleo/: el carril sale de la columna de lectura y
muestra 2/3/4 tarjetas según el ancho."""
import pathlib, re, unittest
CSS = (pathlib.Path(__file__).resolve().parent.parent / "assets" / "style.css").read_text(encoding="utf-8")

class CarrilesAnchos(unittest.TestCase):
    def test_columnas_por_ancho(self):
        self.assertIn("@media (min-width:1100px){ .tr-ix-em .em-carril{ --em-n:3; } }", CSS)
        self.assertIn("@media (min-width:1400px){ .tr-ix-em .em-carril{ --em-n:4; } }", CSS)
        self.assertIn("grid-auto-columns:calc((100% - var(--em-n) * 10px) / (var(--em-n) + .25))", CSS)

    def test_sale_del_contenedor_sin_desbordar(self):
        self.assertIn("width:min(100vw - 64px, 1440px)", CSS)
        self.assertIn(".tr-ix-em > .tr-ix-lado{ align-self:start; }", CSS)

    def test_movil_hasta_el_borde(self):
        self.assertRegex(CSS, r"max-width:759\.98px\)\{\s*\.tr-ix-em \.em-carril\{ margin-inline:-16px; \}")
        self.assertIn("scroll-padding-inline:16px", CSS)

    def test_se_conserva_snap(self):
        self.assertIn("scroll-snap-type:x mandatory", CSS)

if __name__ == "__main__":
    unittest.main()
