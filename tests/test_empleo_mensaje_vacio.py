"""Mensaje visible de sin resultados en /empleo/ (E-2b ítem 1)."""
import pathlib
import re
import unittest

CSS = (pathlib.Path(__file__).resolve().parents[1] / "assets" / "style.css").read_text(encoding="utf-8")
JS = (pathlib.Path(__file__).resolve().parents[1] / "assets" / "empleo.js").read_text(encoding="utf-8")
PY = (pathlib.Path(__file__).resolve().parents[1] / "empleo.py").read_text(encoding="utf-8")


class MensajeVacio(unittest.TestCase):
    def test_em_fn_visible(self):
        bloque = re.search(r"\.tr-ix-em \.em-fn\{[^}]+\}", CSS).group(0)
        self.assertIn("position:static", bloque)
        self.assertNotIn("width:1px", bloque)

    def test_placeholder_ink_soft(self):
        self.assertIn(".tr-ix-em .em-busca input::placeholder{color:var(--ink-soft);opacity:1}", CSS)

    def test_js_sigue_avisando(self):
        self.assertIn("Ninguna coincide: quita algún filtro.", JS)
        self.assertIn('role="status"', PY)


if __name__ == "__main__":
    unittest.main()
