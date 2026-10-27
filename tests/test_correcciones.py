"""Página /correcciones/ y aviso en la pieza corregida (TC-017), sin red."""
import json
import pathlib
import sys
import tempfile
import unittest

RAIZ_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_REPO))
sys.path.insert(0, str(RAIZ_REPO / "tools"))

import build  # noqa: E402
import registro_correcciones as rc  # noqa: E402
import verificar as v  # noqa: E402

ENTRADA = {"id": "2026-10-20-cuantia", "fecha": "2026-10-21", "url": "/ediciones/2026-10-20.html",
           "pieza": "Subvenciones a la vivienda", "dice": "12 millones", "debe_decir": "1,2 millones",
           "motivo": "Error de transcripción de la cuantía."}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = pathlib.Path(self.tmp.name)
        self.registro = self.raiz / "editorial" / "correcciones.json"
        self.registro.parent.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def guardar(self, entradas):
        self.registro.write_text(json.dumps({"correcciones": entradas}), encoding="utf-8")


class TestRegistro(Base):
    def test_registro_del_repo_es_valido(self):
        rc.cargar()     # el real: si está mal formado, el CI falla aquí

    def test_vacio(self):
        self.guardar([])
        self.assertEqual(rc.cargar(self.registro), [])

    def test_campo_que_falta(self):
        self.guardar([{**ENTRADA, "motivo": ""}])
        with self.assertRaises(ValueError):
            rc.cargar(self.registro)

    def test_id_repetido(self):
        self.guardar([ENTRADA, dict(ENTRADA)])
        with self.assertRaises(ValueError):
            rc.cargar(self.registro)

    def test_orden(self):
        otra = {**ENTRADA, "id": "otra", "fecha": "2026-10-25"}
        self.guardar([ENTRADA, otra])
        self.assertEqual([e["id"] for e in rc.cargar(self.registro)], ["otra", ENTRADA["id"]])


class TestMarcado(unittest.TestCase):
    def test_aviso_bajo_el_titular(self):
        html = '<header>x</header><h1 class="display" style="a">Edición</h1><p>cuerpo</p>'
        out = rc.marcar(html, [ENTRADA], build.esc_html, build.fmt_date_es)
        self.assertIn('href="/correcciones/#c-2026-10-20-cuantia"', out)
        self.assertLess(out.index("</h1>"), out.index('class="correccion"'))
        self.assertEqual(rc.marcar(out, [ENTRADA], build.esc_html, build.fmt_date_es), out)

    def test_replace_placeholders_marca_la_pagina(self):
        build._CORRECCIONES = rc.por_pagina([ENTRADA])
        try:
            html = build._replace_placeholders('<h1 class="display">__SSR_HEADLINE__</h1>',
                                               {"CANONICAL": "https://terceracamara.es/ediciones/2026-10-20.html",
                                                "HEADLINE": "Edición"})
            self.assertIn("/correcciones/#c-2026-10-20-cuantia", html)
            otra = build._replace_placeholders('<h1 class="display">x</h1>',
                                               {"CANONICAL": "https://terceracamara.es/ediciones/2026-10-21.html"})
            self.assertNotIn("correccion", otra)
        finally:
            build._CORRECCIONES = None

    def test_pagina_sin_correcciones(self):
        c = rc.cuerpo([], build.esc_html, build.fmt_date_es)
        self.assertIn("Por ahora no hay correcciones publicadas", c)
        self.assertIn("contacto@terceracamara.es", c)
        self.assertNotIn("gmail", c.lower())

    def test_pagina_con_correccion(self):
        c = rc.cuerpo([ENTRADA], build.esc_html, build.fmt_date_es)
        self.assertIn('id="c-2026-10-20-cuantia"', c)
        self.assertIn('href="/ediciones/2026-10-20.html"', c)


class TestVerificar(Base):
    def escribir(self, rel, texto):
        f = self.raiz / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(texto, encoding="utf-8")

    def test_ok(self):
        self.guardar([ENTRADA])
        self.escribir("correcciones/index.html", '<section id="c-2026-10-20-cuantia"></section>')
        self.escribir("ediciones/2026-10-20.html", '<a href="/correcciones/#c-2026-10-20-cuantia">x</a>')
        self.assertEqual(v.comprobar_correcciones(self.raiz, self.registro), [])

    def test_pieza_sin_enlace(self):
        self.guardar([ENTRADA])
        self.escribir("correcciones/index.html", '<section id="c-2026-10-20-cuantia"></section>')
        self.escribir("ediciones/2026-10-20.html", "<p>sin aviso</p>")
        h = v.comprobar_correcciones(self.raiz, self.registro)
        self.assertEqual(len(h), 1)
        self.assertIn("no enlaza a su corrección", h[0]["detalle"])

    def test_pagina_inexistente_y_entrada_ausente(self):
        self.guardar([ENTRADA])
        self.escribir("correcciones/index.html", "<p></p>")
        self.assertEqual(len(v.comprobar_correcciones(self.raiz, self.registro)), 2)

    def test_falta_la_pagina_de_correcciones(self):
        self.guardar([])
        self.assertEqual(len(v.comprobar_correcciones(self.raiz, self.registro)), 1)


if __name__ == "__main__":
    unittest.main()
