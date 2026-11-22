"""«¿Quién votó qué en tu provincia?» (votos_rdl.py y curated/votos_rdl.json).

Criterio mecánico, voto tal cual, «sin dato» explicado y no como voto, enlaces
a la fuente oficial, sin porcentajes, sin tarjetas ni subrayados. Sin red."""
import json
import pathlib
import re
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import votos_rdl as vr  # noqa: E402

URL = "https://www.congreso.es/webpublica/opendata/votaciones/Leg15/Sesion{s:03d}/{f}/Votacion{n:03d}/VOT_{f}1.json"


def _det(f, s, n, a, t=vr.TITULO, v="SN-AX"):
    return URL.format(s=s, f=f.replace("-", ""), n=n), {"f": f, "s": s, "n": n, "t": t, "a": a, "v": v}


class Criterio(unittest.TestCase):
    def estado(self):
        det = dict([
            _det(f"2026-0{1 + i // 3}-1{i % 3}", 100 + i, 1, f"Real Decreto-ley {i}/2026, de prueba.")
            for i in range(12)])
        det.update([
            _det("2026-09-30", 300, 1, "Tramitación como Proyecto de Ley por el procedimiento de urgencia del Real Decreto-ley 11/2026."),
            _det("2026-09-30", 300, 2, "Moción.", t="Mociones consecuencia de interpelaciones urgentes."),
        ])
        u, d = _det("2026-09-30", 300, 3, "Real Decreto-ley 99/2019, de otra legislatura.")
        det[u.replace("/Leg15/", "/Leg14/")] = d
        return {"detalle": det, "det_nombres": ["a", "b", "c", "d", "e"]}

    def test_diez_mas_recientes_sin_tramitacion(self):
        sel = vr.seleccionar(self.estado())
        self.assertEqual(len(sel), 10)
        textos = [d["a"] for _u, d in sel]
        self.assertEqual(textos[0], "Real Decreto-ley 11/2026, de prueba.")
        self.assertEqual(textos[-1], "Real Decreto-ley 2/2026, de prueba.")
        self.assertFalse(any(t.startswith("Tramitación") for t in textos))
        self.assertTrue(all("/Leg15/" in u for u, _d in sel))
        fechas = [(d["f"], d["s"], d["n"]) for _u, d in sel]
        self.assertEqual(fechas, sorted(fechas, reverse=True))

    def test_quien_no_figura_no_tiene_voto(self):
        _u, d = _det("2026-01-10", 1, 1, "x", v="SN-AX")
        self.assertEqual(vr.votos_de(d, ["a", "b", "c", "d", "e"]),
                         {"a": "S", "b": "N", "d": "A", "e": "X"})

    def test_fechas_tal_cual_formato_fuente(self):
        self.assertEqual(vr.fecha_fuente("2026-09-03"), "3/9/2026")
        self.assertEqual(vr.fecha_dia("2026-09-03"), "03/09/2026")


GENTE = [
    {"clave": "uno", "natural": "Ana Uno", "nombre": "Uno, Ana", "slug": "ana-uno", "alta": "08/08/2023"},
    {"clave": "dos", "natural": "Bea Dos", "nombre": "Dos, Bea", "slug": "bea-dos", "alta": "08/08/2023"},
    {"clave": "tres", "natural": "Carla Tres", "nombre": "Tres, Carla", "slug": "carla-tres", "alta": "15/09/2026"},
]
VOT = {"fecha": "23/9/2026", "fecha_iso": "2026-09-23", "titulo": vr.TITULO,
       "texto": "Real Decreto-ley 23/2026, de 8 de septiembre, por el que se adoptan medidas <urgentes>.",
       "json": "https://www.congreso.es/webpublica/opendata/votaciones/Leg15/Sesion200/x.json",
       "pdf": "https://www.congreso.es/webpublica/opendata/votaciones/Leg15/Sesion200/x.pdf",
       "dia": vr.DIA_URL.format(fecha="23/09/2026"), "expediente": "130/000054",
       "resultado": "Derogado", "votos": {"uno": "S", "dos": "X", "otro": "N"}}


class Bloque(unittest.TestCase):
    def h(self, **cambios):
        return vr.bloque_html({"votaciones": [{**VOT, **cambios}]}, GENTE, "Madrid")

    def test_estructura_y_nota(self):
        h = self.h()
        self.assertIn('<h2 id="prov-votos">¿Quién votó qué en Madrid?</h2>', h)
        self.assertIn(vr.NOTA, h)
        self.assertEqual(h.count('class="pv-vot"'), 1)
        self.assertIn('<span class="pv-fecha">23/9/2026</span>', h)
        # Texto oficial tal cual (escapado), con el número del RDL en negrita.
        self.assertIn("<b>Real Decreto-ley 23/2026</b>, de 8 de septiembre, por el que se adoptan "
                      "medidas &lt;urgentes&gt;.", h)

    def test_votos_y_sin_dato(self):
        h = self.h()
        self.assertIn('<span class="pv-v">Sí:</span> <a href="ana-uno.html">Ana Uno</a>', h)
        self.assertIn('<span class="pv-v">No vota:</span> <a href="bea-dos.html">Bea Dos</a>', h)
        self.assertIn('<li class="pv-sin"><span class="pv-v">Sin dato</span> (no aparece en el listado '
                      'oficial de esta votación): <a href="carla-tres.html">Carla Tres</a> '
                      '(alta en el Congreso: 15/09/2026)</li>', h)
        # Quien no es de la provincia (o no tiene ficha) no sale.
        self.assertNotIn("otro", h)
        self.assertNotIn("No:", h)
        self.assertNotIn("no figura", h.lower())
        self.assertNotIn("no era diputad", h.lower())
        self.assertNotIn("%", h)

    def test_enlaces_oficiales(self):
        h = self.h()
        for clave in ("json", "pdf"):
            self.assertIn(f'href="{VOT[clave]}"', h)
        self.assertIn(">votaciones del día</a>", h)
        self.assertIn("_iniciativas_id=130/000054", h)
        for href in re.findall(r'href="([^"]+)"', h):
            self.assertTrue(href.startswith("https://www.congreso.es/") or href.endswith(".html"), href)

    def test_orden_alfabetico_sin_tildes_al_final(self):
        gente = GENTE + [{"clave": "cuatro", "natural": "Eva Álvarez", "nombre": "Álvarez, Eva",
                          "slug": "eva-alvarez"}]
        h = vr.bloque_html({"votaciones": [{**VOT, "votos": {"uno": "S", "cuatro": "S"}}]}, gente, "X")
        self.assertLess(h.index("Eva Álvarez"), h.index("Ana Uno"))

    def test_resultado_solo_si_viene(self):
        self.assertIn("Resultado, según el expediente del Congreso: Derogado.", self.h())
        sin = self.h(resultado="", pdf="", expediente="")
        self.assertNotIn("Resultado", sin)
        self.assertNotIn("Convalidad", sin)
        self.assertNotIn("Derogad", sin)
        self.assertNotIn("PDF", sin)
        self.assertNotIn("expediente", sin)

    def test_sin_copia_no_hay_bloque(self):
        self.assertEqual(vr.bloque_html(None, GENTE, "Madrid"), "")
        self.assertEqual(vr.bloque_html({"votaciones": []}, GENTE, "Madrid"), "")

    def test_css_sin_tarjetas_ni_subrayados(self):
        css = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")
        self.assertIn(".prov-votos a{color:var(--red-ink,var(--red));text-decoration:none", css)
        reglas = re.findall(r"\.(?:prov-votos|pv-[a-z]+)[^{]*\{([^}]*)\}", css)
        self.assertTrue(reglas)
        for r in reglas:
            for prohibido in ("background", "box-shadow", "border-radius", "underline"):
                self.assertNotIn(prohibido, r)


class CopiaFija(unittest.TestCase):
    def setUp(self):
        self.datos = vr.cargar()
        if not self.datos:
            self.skipTest("sin curated/votos_rdl.json")

    def test_criterio(self):
        vs = self.datos["votaciones"]
        self.assertEqual(len(vs), vr.N_VOTACIONES)
        self.assertEqual(self.datos["criterio"], vr.CRITERIO)
        for v in vs:
            self.assertEqual(v["titulo"], vr.TITULO)
            self.assertRegex(v["texto"], r"^Real Decreto-ley \d+/\d{4}, ")
            self.assertTrue(v["json"].startswith(
                "https://www.congreso.es/webpublica/opendata/votaciones/Leg15/"), v["json"])
            self.assertEqual(v["fecha"], vr.fecha_fuente(v["fecha_iso"]))
            self.assertTrue(set(v["votos"].values()) <= set("SNAX"))
            self.assertEqual(list(v["votos"]), sorted(v["votos"]))
            if v["pdf"]:
                self.assertTrue(v["pdf"].startswith(v["json"].rsplit("/", 1)[0] + "/"), v["pdf"])
                self.assertTrue(v["pdf"].endswith(".pdf"))
            if v["expediente"]:
                self.assertRegex(v["expediente"], r"^130/\d{6}$")
        orden = [(v["fecha_iso"], v["sesion"], v["numero"]) for v in vs]
        self.assertEqual(orden, sorted(orden, reverse=True))

    def test_coincide_con_el_estado(self):
        """Lo que sigue en el estado tiene que casar con la copia; las votaciones
        nuevas no cuentan (la copia solo cambia cuando se regenera)."""
        ruta = RAIZ / "state" / "congreso.json"
        if not ruta.exists():
            self.skipTest("sin state/congreso.json")
        estado = json.loads(ruta.read_text(encoding="utf-8"))
        nombres = estado.get("det_nombres") or []
        for v in self.datos["votaciones"]:
            d = (estado.get("detalle") or {}).get(v["json"])
            if not d:
                continue
            self.assertEqual(d["a"], v["texto"])
            self.assertEqual(d["f"], v["fecha_iso"])
            self.assertEqual(vr.votos_de(d, nombres), v["votos"])


class Pintadas(unittest.TestCase):
    def test_fichas_de_provincia(self):
        fichas = sorted((RAIZ / "diputados").glob("provincia-*.html"))
        if not fichas or not vr.cargar():
            self.skipTest("fichas de provincia sin pintar (build.py --render)")
        self.assertEqual(len(fichas), 52)
        for f in fichas:
            h = f.read_text(encoding="utf-8")
            self.assertEqual(h.count('<section class="prov-votos"'), 1, f.name)
            self.assertEqual(h.count('class="pv-vot"'), vr.N_VOTACIONES, f.name)
            i = h.index('<section class="prov-votos"')
            self.assertLess(i, h.index('class="rejilla-dip"'), f.name)
            head = h[:h.index("</head>")]
            self.assertNotIn("Quién votó qué", head, f.name)


if __name__ == "__main__":
    unittest.main()
