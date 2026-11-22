"""PR «Parlamento: fuera el Senado, panel de decretos-ley»."""
import json
import pathlib
import re
import unittest

import build
import decretos_ley as dl

RAIZ = pathlib.Path(__file__).resolve().parent.parent


class SinSenado(unittest.TestCase):
    def test_tagline_sin_senado(self):
        t = (RAIZ / "template.html").read_text(encoding="utf-8")
        self.assertNotIn("Senado", t)
        self.assertIn("El BOE y el Congreso bajo control ciudadano", t)

    def test_sin_ficha_del_senado(self):
        dia = {"id": "2026-10-05", "cortes": {
            "congreso": {"presidenta": "P", "legislatura": "L", "sede": "S"},
            "senado": {"presidente": "Pedro Rollán", "legislatura": "L", "sede": "S"}}}
        h = build.render_chamber_cards_ssr(dia)
        self.assertNotIn("SENADO", h)
        self.assertNotIn("Rollán", h)
        self.assertIn("CONGRESO DE LOS DIPUTADOS", h)

    def test_nota_de_cobertura_sin_senado(self):
        oculto, h = build.render_coverage_note_ssr({"cortes": {"coverage": {"nota": build.NOTA_SENADO_INACTIVO}}})
        self.assertTrue(oculto)
        self.assertEqual(h, "")
        oculto, h = build.render_coverage_note_ssr(
            {"cortes": {"coverage": {"nota": build.NOTA_SENADO_INACTIVO + " Sin sesión nueva."}}})
        self.assertFalse(oculto)
        self.assertNotIn("Senado", h)
        self.assertIn("Sin sesión nueva.", h)


class Disolucion(unittest.TestCase):
    def test_desde_el_boe_del_rd_no_hay_ficha_de_legislatura(self):
        pub = json.loads((RAIZ / "curated" / "elecciones_2026.json").read_text(encoding="utf-8"))
        fecha = pub["publicaciones"]["BOE-A-2026-20742"]["fecha"]
        h = build.render_chamber_cards_ssr({"id": fecha, "cortes": {
            "congreso": {"presidenta": "P", "legislatura": "XV Legislatura (2023– )", "sede": "S"}}})
        self.assertNotIn("chamber-card", h)
        self.assertNotIn("(2023– )", h)
        self.assertIn("Real Decreto 806/2026, de 5 de octubre", h)
        self.assertIn("BOE núm. 248, de 6 de octubre de 2026", h)
        self.assertIn("txt.php?id=BOE-A-2026-20742", h)
        self.assertIn("Diputación Permanente", h)
        self.assertIn("artículo 78 de la Constitución", h)
        self.assertNotRegex(h, r"\bplazo\b|\bd[ií]as\b")


class PanelDecretos(unittest.TestCase):
    datos = {"decretos": [
        {"numero": "Real Decreto-ley 14/2026", "titulo": "Real Decreto-ley 14/2026, de x.", "boe": "BOE núm. 1, de 01/01/2026",
         "id_boe": "BOE-A-2026-1", "expediente": "130/000045", "estado_campo": "Resultado tramitación",
         "estado": "Convalidado y tramitado como proyecto de ley", "organo": "Pleno"},
        {"numero": "Real Decreto-ley 33/2026", "titulo": "Real Decreto-ley 33/2026, de y.", "boe": "BOE núm. 2, de 02/01/2026",
         "id_boe": "", "expediente": "", "estado_campo": "", "estado": "", "organo": ""},
    ]}
    votos = {"votaciones": [{"texto": "Real Decreto-ley 14/2026, de x.", "json": "https://oficial/v.json"}]}

    def panel(self, votacion=lambda u: "/votaciones/p.html"):
        return dl.panel_html(self.datos, self.votos, votacion,
                             lambda i: f"/normas/{i}.html" if i else "")

    def test_estado_tal_cual_y_enlaces(self):
        h = self.panel()
        self.assertIn("Resultado tramitación: Convalidado y tramitado como proyecto de ley", h)
        self.assertIn('href="/votaciones/p.html">Votación', h)
        self.assertIn("_iniciativas_id=130/000045", h)
        self.assertIn('href="/normas/BOE-A-2026-1.html"', h)
        self.assertIn('href="/diputados/#circunscripciones"', h)

    def test_sin_ficha_no_hay_estado(self):
        h = self.panel()
        fila = re.search(r'<li class="dl-fila"><p class="dl-meta"><b class="dl-num">Real Decreto-ley 33/2026.*?</li>', h).group(0)
        self.assertIn("Sin ficha de expediente en el Congreso", fila)
        self.assertNotIn("dl-estado", fila)
        self.assertNotRegex(fila, r"(?i)convalidad|derogad|pendiente")
        self.assertNotIn("Votación", fila)

    def test_orden_y_sin_tarjetas(self):
        h = self.panel()
        self.assertLess(h.index("Real Decreto-ley 33/2026</b>"), h.index("Real Decreto-ley 14/2026</b>"))
        self.assertNotIn("card", h)

    def test_resto_plegado(self):
        muchos = {"decretos": [dict(self.datos["decretos"][1], numero=f"Real Decreto-ley {n}/2026")
                               for n in range(14, 14 + dl.VISIBLES + 3)]}
        h = dl.panel_html(muchos, {}, lambda u: "", lambda i: "")
        self.assertIn("<summary>Los 3 anteriores</summary>", h)
        self.assertEqual(h.count('class="dl-fila"'), dl.VISIBLES + 3)

    def test_sin_datos_no_hay_panel(self):
        self.assertEqual(dl.panel_html(None, None, str, str), "")

    def test_copia_fija(self):
        d = dl.cargar()
        self.assertIsNotNone(d)
        nums = [r["numero"] for r in d["decretos"]]
        self.assertEqual(nums[0], "Real Decreto-ley 14/2026")
        self.assertEqual(len(nums), len(set(nums)))
        validos = {"Resultado tramitación", "Situación actual", ""}
        for r in d["decretos"]:
            self.assertIn(r["estado_campo"], validos)
            if not r["expediente"]:
                self.assertEqual(r["estado"], "", r["numero"])
            self.assertRegex(r["boe"], r"^BOE núm\. \d+, de \d{2}/\d{2}/\d{4}$")
        # Muestra contrastada con la ficha oficial (130/000057).
        rdl24 = next(r for r in d["decretos"] if r["numero"] == "Real Decreto-ley 24/2026")
        self.assertEqual((rdl24["estado"], rdl24["organo"]), ("Convalidado", "Diputación Permanente"))

    def test_estados_de_votos_rdl_coinciden(self):
        import votos_rdl as vr
        d = {r["numero"]: r for r in dl.cargar()["decretos"]}
        for v in vr.cargar()["votaciones"]:
            num = dl.RE_NUM.match(v["texto"]).group(0)
            self.assertEqual(d[num]["expediente"], v["expediente"])
            if v.get("resultado"):
                self.assertEqual(d[num]["estado"], v["resultado"])


if __name__ == "__main__":
    unittest.main()
