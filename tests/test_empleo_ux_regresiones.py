"""/empleo/: arreglos de la auditoría UX del 03-11-2026 (regresiones de #74,
botón al pie, filtro de días y <details> con icono propio). Sin subrayados."""
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CSS = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")
SRC = (RAIZ / "empleo.py").read_text(encoding="utf-8")
BLOQUE = CSS[CSS.index("/* --- /empleo/ (reutiliza"):CSS.index("/* --- fin /empleo/")]


class RegresionesEmpleo(unittest.TestCase):
    def test_enlaces_texto_corrido_por_peso_y_color(self):
        self.assertNotIn("underline", BLOQUE)
        self.assertRegex(BLOQUE, r"\.tr-ix-em \.aside-note a[^{]*\{color:var\(--red-ink\);font-weight:700")

    def test_total_de_la_caja_sin_enlace(self):
        self.assertNotRegex(SRC, r'tr-ix-leyes"><span>[^\n]*<a href=')
        self.assertIn("<b>{len(recientes)}</b>", SRC)

    def test_estado_visualmente_oculto_pero_leido(self):
        self.assertIn('role="status" aria-live="polite"', SRC)
        self.assertRegex(BLOQUE, r"\.tr-ix-em \.em-fn\{position:absolute;width:1px")

    def test_en_cifras_compacto_bajo_980(self):
        self.assertIn("@media (max-width:979.98px)", BLOQUE)
        self.assertIn(".tr-ix-em > .tr-ix-lado{order:-1", BLOQUE)
        self.assertEqual(SRC.count("tr-ix-em-rep"), 4)

    def test_listas_apiladas(self):
        self.assertIn(".tr-ix-em .tr-ix-em-dos{grid-template-columns:1fr !important}", BLOQUE)
        self.assertIn("column-count:2", BLOQUE)

    def test_boton_al_pie(self):
        self.assertIn(".tr-ix-em .em-card .em-boe{margin-top:auto}", BLOQUE)

    def test_filtro_dias_no_parece_pestana(self):
        self.assertRegex(BLOQUE, r"\.tr-ix-em \.em-dias\{border-radius:8px;border-style:dashed")

    def test_details_sin_marcador_nativo(self):
        self.assertIn(".tr-ix-em summary{list-style:none", BLOQUE)
        self.assertIn(".tr-ix-em summary::-webkit-details-marker{display:none}", BLOQUE)
        self.assertIn(".tr-ix-em details[open] > summary::after", BLOQUE)
        # El icono no es un carácter: lo dibujan los bordes (nada que leer).
        m = re.search(r"\.tr-ix-em summary::after\{content:\"\"", BLOQUE)
        self.assertIsNotNone(m)


if __name__ == "__main__":
    unittest.main()
