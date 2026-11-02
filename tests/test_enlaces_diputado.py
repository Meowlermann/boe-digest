"""Las fichas de diputado enlazan a la votación limpia con #d=slug, no ?d=."""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


class EnlacesDiputado(unittest.TestCase):
    def test_build_no_genera_query_d(self):
        src = (ROOT / "build.py").read_text(encoding="utf-8")
        self.assertNotIn('"?d="', src)
        self.assertIn('"#d=" + f["slug"]', src)

    def test_js_lee_fragmento_y_query_antigua(self):
        js = (ROOT / "assets" / "votaciones.js").read_text(encoding="utf-8")
        self.assertIn("location.hash", js)
        self.assertIn('searchParams.get("d")', js)   # compatibilidad con ?d=
        self.assertIn('searchParams.delete("d")', js)  # y lo pasa a fragmento
        self.assertNotIn('searchParams.set("d"', js)


if __name__ == "__main__":
    unittest.main()
