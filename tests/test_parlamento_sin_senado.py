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

    def test_plantillas_sin_caracteres_de_control(self):
        # El pie llevaba un \x01 (un «\1» de una sustitución) que se veía como un cuadro.
        for f in sorted(RAIZ.glob("template*.html")):
            t = f.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", t), f.name)

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
         "estado": "Convalidado y tramitado como proyecto de ley", "organo": "Pleno", "resolucion": {}},
        {"numero": "Real Decreto-ley 30/2026", "titulo": "Real Decreto-ley 30/2026, de z.", "boe": "BOE núm. 3, de 03/01/2026",
         "id_boe": "BOE-A-2026-3", "expediente": "130/000061", "estado_campo": "Situación actual",
         "estado": "Concluido - (Convalidado)", "organo": "Diputación Permanente", "resolucion": {}},
        {"numero": "Real Decreto-ley 33/2026", "titulo": "Real Decreto-ley 33/2026, de y.", "boe": "BOE núm. 2, de 02/01/2026",
         "id_boe": "BOE-A-2026-2", "expediente": "", "estado_campo": "", "estado": "", "organo": "",
         "resolucion": {"id": "BOE-A-2026-24294", "boe": "BOE núm. 289, de 20/11/2026",
                        "acuerdo": "la Diputación Permanente del Congreso de los Diputados, en su sesión del día de hoy, acordó convalidar",
                        "objeto": "el Real Decreto-ley 33/2026"}},
        {"numero": "Real Decreto-ley 37/2026", "titulo": "Real Decreto-ley 37/2026, de w.", "boe": "BOE núm. 4, de 04/01/2026",
         "id_boe": "", "expediente": "", "estado_campo": "", "estado": "", "organo": "", "resolucion": {}},
    ]}
    votos = {"votaciones": [{"texto": "Real Decreto-ley 14/2026, de x.", "json": "https://oficial/v.json"}]}

    def panel(self, votacion=lambda u: "/votaciones/p.html"):
        return dl.panel_html(self.datos, self.votos, votacion,
                             lambda i: f"/normas/{i}.html" if i else "")

    def fila(self, h, num):
        return re.search(r'<li class="dl-fila"><p class="dl-meta"><b class="dl-num">Real Decreto-ley '
                         + re.escape(num) + r'</b>.*?</li>', h).group(0)

    def test_etiqueta_y_literal_del_expediente(self):
        f = self.fila(self.panel(), "14/2026")
        self.assertIn('<a class="dl-estado" href="/votaciones/p.html">'
                      'Convalidado por el Pleno y tramitado como proyecto de ley</a>', f)
        self.assertIn("«Resultado tramitación: Convalidado y tramitado como proyecto de ley» · Pleno", f)
        self.assertIn('<a href="/normas/BOE-A-2026-1.html">Real Decreto-ley 14/2026, de x.</a>', f)
        f = self.fila(self.panel(), "30/2026")
        self.assertIn(">Convalidado por la Diputación Permanente</a>", f)
        self.assertIn("_iniciativas_id=130/000061", f)          # sin votación: al expediente
        self.assertIn("«Situación actual: Concluido - (Convalidado)»", f)

    def test_sin_expediente_sale_de_la_resolucion_del_boe(self):
        f = self.fila(self.panel(), "33/2026")
        self.assertIn('href="https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-24294">'
                      'Convalidado por la Diputación Permanente</a>', f)
        self.assertIn("BOE-A-2026-24294, BOE núm. 289, de 20/11/2026", f)
        self.assertIn("acordó convalidar el Real Decreto-ley 33/2026", f)

    def test_sin_ninguna_fuente(self):
        f = self.fila(self.panel(), "37/2026")
        self.assertIn('<span class="dl-estado dl-sin">Aún sin votación publicada</span>', f)
        self.assertNotRegex(f, r"(?i)convalidad|derogad")
        self.assertNotIn("<a ", f)

    def test_quien_voto_que_una_sola_vez_y_entradilla(self):
        h = self.panel()
        self.assertEqual(h.count("/diputados/#circunscripciones"), 1)
        nota = re.search(r'<p class="dl-nota">(.*?)</p>', h).group(1)
        self.assertTrue(nota.startswith("Qué ha pasado con cada decreto-ley que el Gobierno aprueba "
                                        "sin pasar antes por las Cortes"))
        self.assertLess(nota.index("sin pasar antes"), nota.index("Desde el 14/2026"))

    def test_un_enlace_de_estado_y_uno_de_titulo_por_fila(self):
        for num in ("14/2026", "30/2026", "33/2026"):
            self.assertEqual(self.fila(self.panel(), num).count("<a "), 2, num)

    def test_literal_desconocido_se_muestra_tal_cual(self):
        r = dict(self.datos["decretos"][0], estado="Retirado", organo="Pleno")
        self.assertEqual(dl.etiqueta(r), ("Retirado", "expediente"))
        self.assertEqual(dl.sin_correspondencia({"decretos": [r]}), ["Real Decreto-ley 14/2026: Retirado (Pleno)"])

    def test_orden_y_sin_tarjetas(self):
        h = self.panel()
        self.assertLess(h.index("Real Decreto-ley 37/2026</b>"), h.index("Real Decreto-ley 14/2026</b>"))
        self.assertNotIn("card", h)
        self.assertNotRegex(h, r"\bplazo|\bquedan? \d+ d[ií]as")

    def test_resto_plegado(self):
        muchos = {"decretos": [dict(self.datos["decretos"][3], numero=f"Real Decreto-ley {n}/2026")
                               for n in range(14, 14 + dl.VISIBLES + 3)]}
        h = dl.panel_html(muchos, {}, lambda u: "", lambda i: "")
        self.assertIn("<summary>Los 3 anteriores</summary>", h)
        self.assertEqual(h.count('class="dl-fila"'), dl.VISIBLES + 3)

    def test_sin_datos_no_hay_panel(self):
        self.assertEqual(dl.panel_html(None, None, str, str), "")

    def test_completar_con_ediciones(self):
        sin = {"decretos": [dict(self.datos["decretos"][3])]}
        dias = [{"boe": {"numero": "289", "fechaISO": "2026-11-20", "stories": [{
            "ref": "BOE-A-2026-99999",
            "titulo_oficial": "Resolución de 18 de noviembre de 2026, del Congreso de los Diputados, por la que se "
                              "ordena la publicación del Acuerdo de derogación del Real Decreto-ley 37/2026, de w.",
            "materia": "PARTE DISPOSITIVA:\nDe conformidad con lo dispuesto en el artículo 86.2 de la Constitución, la "
                       "Diputación Permanente del Congreso de los Diputados, en su sesión del día de hoy, acordó "
                       "derogar el Real Decreto-ley 37/2026, de w."}]}}]
        out = dl.completar_con_ediciones(sin, dias)
        r = out["decretos"][0]
        self.assertEqual(dl.etiqueta(r), ("Derogado por la Diputación Permanente", "resolucion"))
        self.assertEqual(r["resolucion"]["boe"], "BOE núm. 289, de 20/11/2026")
        # Si todos tienen estado (de la ficha o de la resolución), no se toca nada.
        con = {"decretos": self.datos["decretos"][:3]}
        self.assertIs(dl.completar_con_ediciones(con, dias), con)

    def test_copia_fija(self):
        d = dl.cargar()
        self.assertIsNotNone(d)
        nums = [r["numero"] for r in d["decretos"]]
        self.assertEqual(nums[0], "Real Decreto-ley 14/2026")
        self.assertEqual(len(nums), len(set(nums)))
        for r in d["decretos"]:
            self.assertIn(r["estado_campo"], {"Resultado tramitación", "Situación actual", ""})
            if not r["expediente"]:
                self.assertEqual(r["estado"], "", r["numero"])
            self.assertRegex(r["boe"], r"^BOE núm\. \d+, de \d{2}/\d{2}/\d{4}$")
            res = r.get("resolucion") or {}
            if res:
                self.assertRegex(res["id"], r"^BOE-A-\d{4}-\d+$")
                self.assertEqual(res["objeto"], "el " + r["numero"])
        rdl24 = next(r for r in d["decretos"] if r["numero"] == "Real Decreto-ley 24/2026")
        self.assertEqual((rdl24["estado"], rdl24["organo"]), ("Convalidado", "Diputación Permanente"))
        # Informe 45: RDL 33 a 36, convalidados por la Diputación Permanente (BOE núm. 289).
        for n, ident in zip(range(33, 37), range(24294, 24298)):
            r = next(x for x in d["decretos"] if x["numero"] == f"Real Decreto-ley {n}/2026")
            # Primero sale de la resolución; cuando el Congreso publica la ficha, de la ficha.
            self.assertEqual(dl.etiqueta(r)[0], "Convalidado por la Diputación Permanente")
            self.assertEqual(r["resolucion"]["id"], f"BOE-A-2026-{ident}")

    def test_toda_la_copia_tiene_correspondencia(self):
        # Si falla: hay un texto oficial nuevo. Se muestra literal; añadirlo a la
        # correspondencia de decretos_ley.py si su sentido es inequívoco.
        self.assertEqual(dl.sin_correspondencia(dl.cargar()), [])

    def test_expediente_y_resolucion_coinciden(self):
        for r in dl.cargar()["decretos"]:
            res = r.get("resolucion") or {}
            if r["estado"] and res.get("acuerdo"):
                conv = "Convalidado" in r["estado"]
                self.assertEqual(conv, res["acuerdo"].endswith("convalidar"), r["numero"])

    def test_ficha_de_la_norma_solo_si_esta_en_el_sitio(self):
        dia = {"boe": {"stories": [{"ref": "BOE-A-2026-23602", "titulo_oficial": "x"}]}}
        h = build.render_decretos_ley_ssr([dia])
        self.assertIn('href="/normas/BOE-A-2026-23602.html"', h)
        self.assertNotIn('href="/normas/BOE-A-2026-20266.html"', h)
        self.assertIn('href="https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-20266"', h)

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
