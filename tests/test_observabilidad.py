"""Pruebas sin red de observabilidad.py (TC-009) y de la incidencia que abre."""
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

RAIZ_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_REPO))

import observabilidad as ob  # noqa: E402

MADRID = ob.MADRID


def web_falsa(ediciones, ultima_feed, boe=200):
    """obtener() falso: sirve las ediciones dadas, un feed y la portada."""
    def obtener(url):
        if "datosabiertos" in url:
            return boe, ""
        if url.endswith("/feed.xml"):
            d = dt.date.fromisoformat(ultima_feed)
            return 200, (f"<rss><channel><item><title>x</title><pubDate>"
                         f"{d:%a, %d %b %Y} 07:00:00 +0000</pubDate></item></channel></rss>")
        if url.endswith("/"):
            return 200, f'<a href="/ediciones/{ultima_feed}.html">hoy</a>'
        for e in ediciones:
            if url.endswith(f"/ediciones/{e}.html"):
                return 200, "<html></html>"
        return 404, ""
    return obtener


def graves(hallazgos):
    return [h for h in hallazgos if h["nivel"] == ob.GRAVE]


class TestProduccion(unittest.TestCase):
    def test_todo_en_orden(self):
        ahora = dt.datetime(2026, 10, 27, 12, 0, tzinfo=MADRID)
        self.assertEqual(graves(ob.comprobar_produccion(ahora, web_falsa(["2026-10-27"], "2026-10-27"))), [])

    def test_fecha_simulada_sin_edicion_es_grave(self):
        # Miércoles 28 a mediodía; la web se quedó en el 27.
        ahora = dt.datetime(2026, 10, 28, 12, 0, tzinfo=MADRID)
        g = graves(ob.comprobar_produccion(ahora, web_falsa(["2026-10-27"], "2026-10-27")))
        self.assertEqual(len(g), 3)
        self.assertIn("2026-10-28", g[0]["detalle"])
        self.assertIn("Qué hacer:", g[0]["detalle"])

    def test_domingo_no_exige_edicion(self):
        ahora = dt.datetime(2026, 10, 25, 12, 0, tzinfo=MADRID)
        h = ob.comprobar_produccion(ahora, web_falsa(["2026-10-24"], "2026-10-24", boe=404))
        self.assertEqual(graves(h), [])

    def test_festivo_sin_boe_segun_api(self):
        ahora = dt.datetime(2026, 12, 25, 12, 0, tzinfo=MADRID)  # viernes
        h = ob.comprobar_produccion(ahora, web_falsa(["2026-12-24"], "2026-12-24", boe=404))
        self.assertEqual(graves(h), [])

    def test_antes_de_la_hora_limite_mira_ayer(self):
        ahora = dt.datetime(2026, 10, 28, 8, 0, tzinfo=MADRID)
        h = ob.comprobar_produccion(ahora, web_falsa(["2026-10-27"], "2026-10-27"))
        self.assertEqual(graves(h), [])

    def test_api_caida_supone_lunes_a_sabado(self):
        ahora = dt.datetime(2026, 10, 28, 12, 0, tzinfo=MADRID)
        h = ob.comprobar_produccion(ahora, web_falsa(["2026-10-28"], "2026-10-28", boe=0))
        self.assertEqual(graves(h), [])
        self.assertTrue(any("no responde" in x["detalle"] for x in h))

    def test_feed_ilegible(self):
        def obtener(url):
            return (200, "") if "datosabiertos" in url else (500, "")
        ahora = dt.datetime(2026, 10, 28, 12, 0, tzinfo=MADRID)
        self.assertEqual(len(graves(ob.comprobar_produccion(ahora, obtener))), 3)


class TestCuentaMensual(unittest.TestCase):
    def test_cuenta(self):
        fechas = ["2026-10-01", "2026-10-02", "2026-10-05"]   # falta el sábado 3
        c = ob.cuenta_mensual(fechas, dt.date(2026, 10, 1), dt.date(2026, 10, 5))
        mes = c["meses"]["2026-10"]
        self.assertEqual(mes["dias_con_boe"], 4)   # 1, 2, 3 y 5 (el 4 es domingo)
        self.assertEqual(mes["sin_edicion"], 1)
        self.assertEqual(mes["fechas"], ["2026-10-03"])

    def test_escribir(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = pathlib.Path(tmp) / "data"
            data.mkdir()
            for f in ("2026-09-30", "2026-10-01"):
                (data / f"{f}.json").write_text("{}")
            destino = pathlib.Path(tmp) / "datos" / "estado-ediciones.json"
            ob.escribir_cuenta(data, destino, dt.date(2026, 10, 2))
            c = json.loads(destino.read_text())
            self.assertEqual(c["esquema"], 1)
            self.assertEqual(c["meses"]["2026-10"]["fechas"], ["2026-10-02"])
            self.assertEqual(c["meses"]["2026-09"]["sin_edicion"], 0)


class TestIncidencia(unittest.TestCase):
    """La fecha simulada provoca la incidencia: se comprueba con un `gh` falso."""

    def _lanzar(self, graves_n):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            registro = tmp / "gh.log"
            gh = tmp / "gh"
            gh.write_text(f'#!/usr/bin/env bash\necho "$@" >> "{registro}"\n')
            gh.chmod(0o755)
            resumen = tmp / "obs.md"
            ahora = dt.datetime(2026, 10, 28, 12, 0, tzinfo=MADRID)
            h = ob.comprobar_produccion(ahora, web_falsa(["2026-10-27"], "2026-10-27"))
            resumen.write_text(ob.markdown(h, ahora))
            env = dict(os.environ, PATH=f"{tmp}:{os.environ['PATH']}", RUNNER_TEMP=str(tmp),
                       GITHUB_SERVER_URL="https://github.com", GITHUB_REPOSITORY="x/y", GITHUB_RUN_ID="1",
                       INCIDENCIA_ETIQUETA="produccion", INCIDENCIA_TITULO="Edición ausente en producción")
            subprocess.run(["bash", str(RAIZ_REPO / "tools/incidencia_salud.sh"), str(graves_n),
                            "2026-10-28", str(resumen)], env=env, check=True, capture_output=True)
            return registro.read_text(), (tmp / "incidencia-salud.md").read_text()

    def test_abre_incidencia(self):
        log, cuerpo = self._lanzar(3)
        self.assertIn("issue create --title Edición ausente en producción --label produccion", log)
        self.assertIn("2026-10-28", cuerpo)
        self.assertIn("no está publicada", cuerpo)

    def test_sin_graves_no_abre(self):
        log, _ = self._lanzar(0)
        self.assertNotIn("issue create", log)


if __name__ == "__main__":
    unittest.main()
