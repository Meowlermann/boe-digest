"""Pruebas de la detección de cambios de las ediciones sin HTML en el disco.

`python -m unittest tests.test_sitio_completo`. Desde que la web se publica
como artefacto, cada pase empieza sin ediciones/*.html: «¿ha cambiado esta
edición?» se responde con la huella guardada en state/ediciones_huellas.json.
"""
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import build  # noqa: E402


class TestHuellas(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = pathlib.Path(self._tmp.name)
        self.parches = [
            mock.patch.object(build, "EDICIONES_DIR", base / "ediciones"),
            mock.patch.object(build, "DATA_DIR", base / "data"),
            mock.patch.object(build, "ESTADO", base / "state"),
            mock.patch.object(build, "MANIFIESTO", base / "state" / "ediciones.json"),
            mock.patch.object(build, "HUELLAS", base / "state" / "ediciones_huellas.json"),
            mock.patch.object(build, "render_ssr_fragments", lambda day: {"X": day.get("x", "")}),
            mock.patch.object(build, "build_title", lambda day, edicion=True: "t"),
            mock.patch.object(build, "build_meta_description", lambda day: "d"),
            mock.patch.object(build, "jsonld_for_day", lambda day, url: ""),
            mock.patch.object(build, "_replace_placeholders", lambda plantilla, frag: repr(sorted(frag.items()))),
            mock.patch("sys.stdout"),
        ]
        for p in self.parches:
            p.start()
        (base / "data").mkdir()
        self.base = base

    def tearDown(self):
        for p in self.parches:
            p.stop()
        self._tmp.cleanup()

    def pase(self, dias):
        for d in dias:
            (self.base / "data" / f"{d['id']}.json").write_text("{}", encoding="utf-8")
        # Cada pase empieza sin HTML, como en publicar.yml.
        for f in (self.base / "ediciones").glob("*.html") if (self.base / "ediciones").exists() else []:
            f.unlink()
        build.renderizar_ediciones(dias)
        return build.DIAG["urls_cambiadas"]

    def test_sin_cambios_no_se_anuncia_nada(self):
        dias = [{"id": "2026-10-05", "x": "a"}, {"id": "2026-10-06", "x": "b"}]
        self.assertEqual(len(self.pase(dias)), 2)          # nuevas: se anuncian
        self.assertEqual(self.pase(dias), [])              # igual y sin disco: nada
        dias[0]["x"] = "corregida"
        self.assertEqual(self.pase(dias), ["https://terceracamara.es/ediciones/2026-10-05.html"])
        huellas = json.loads((self.base / "state" / "ediciones_huellas.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(huellas), ["2026-10-05", "2026-10-06"])

    def test_primer_pase_sin_huellas_no_inunda(self):
        # Ediciones ya publicadas (en el manifiesto) sin huella ni HTML: no se
        # dan por cambiadas de golpe.
        (self.base / "state").mkdir()
        (self.base / "state" / "ediciones.json").write_text(
            json.dumps({"2026-10-05": "2026-10-05"}), encoding="utf-8")
        self.assertEqual(self.pase([{"id": "2026-10-05", "x": "a"}]), [])


if __name__ == "__main__":
    unittest.main()
