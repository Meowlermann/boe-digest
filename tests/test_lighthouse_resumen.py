import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import lighthouse_resumen as lr  # noqa: E402


class TestResumen(unittest.TestCase):
    def test_tabla_y_avisos(self):
        with tempfile.TemporaryDirectory() as d:
            m = [
                {"url": "https://x/", "isRepresentativeRun": True,
                 "summary": {"performance": 0.95, "accessibility": 0.85, "best-practices": 1, "seo": 1}},
                {"url": "https://x/", "isRepresentativeRun": False,
                 "summary": {"performance": 0.1, "accessibility": 0.1, "best-practices": 0, "seo": 0}},
            ]
            (pathlib.Path(d) / "manifest.json").write_text(json.dumps(m))
            texto, avisos = lr.resumen(pathlib.Path(d))
        self.assertIn("| https://x/ | 95 | 85 | 100 | 100 |", texto)
        self.assertEqual(avisos, ["Acces. 85 < 90 en https://x/"])

    def test_sin_manifiesto(self):
        with tempfile.TemporaryDirectory() as d:
            texto, avisos = lr.resumen(pathlib.Path(d))
        self.assertIn("falló", texto)
        self.assertTrue(avisos)


if __name__ == "__main__":
    unittest.main()
