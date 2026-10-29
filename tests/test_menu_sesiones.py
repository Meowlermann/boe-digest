"""El enlace a /sesiones/ del menú, /seguimiento/ y el mapa se decide con el
estado (state/respuestas/), no con sesiones/index.html: en un checkout limpio
el menú se pintaba antes que /sesiones/ y lo omitía. Sin red."""
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

RAIZ_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_REPO))

import build  # noqa: E402
import respuestas as rp  # noqa: E402


class TestMenuSesiones(unittest.TestCase):
    def _estado(self, d: dict):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = pathlib.Path(tmp.name)
        (p / "respuestas").mkdir()
        if d is not None:
            (p / "respuestas" / "2026.json").write_text(json.dumps(d), encoding="utf-8")
        vacia = p / "sesiones"                      # sin index.html: checkout limpio
        for x in (mock.patch.object(rp, "DIR", p / "respuestas"), mock.patch.dict(rp._CACHE, clear=True),
                  mock.patch.object(build, "SESIONES_DIR", vacia), mock.patch.object(build, "_NAV_HTML", None)):
            x.start()
            self.addCleanup(x.stop)

    def test_checkout_limpio_con_sesiones_en_el_estado(self):
        self._estado({"sesiones": {"2026-10-21": {}}, "orales": {"680/1": {"s": "2026-10-21"}}})
        self.assertFalse((build.SESIONES_DIR / "index.html").exists())
        self.assertTrue(build.sesiones_publicadas())
        self.assertIn('href="/sesiones/"', build.render_nav())

    def test_sesion_sin_preguntas_no_cuenta(self):
        self._estado({"sesiones": {"2026-10-21": {}}, "orales": {}})
        self.assertFalse(build.sesiones_publicadas())

    def test_sin_estado(self):
        self._estado(None)
        self.assertFalse(build.sesiones_publicadas())
        self.assertNotIn('href="/sesiones/"', build.render_nav())


if __name__ == "__main__":
    unittest.main()
