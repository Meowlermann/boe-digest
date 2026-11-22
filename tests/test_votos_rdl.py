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
    {"clave": "uno", "natural": "Ana Uno", "nombre": "Uno, Ana", "slug": "ana-uno", "alta": "08/08/2023",
     "circunscripcion": "Coruña (A)"},
    {"clave": "dos", "natural": "Bea Dos", "nombre": "Dos, Bea", "slug": "bea-dos", "alta": "08/08/2023",
     "circunscripcion": "Coruña (A)"},
    {"clave": "tres", "natural": "Carla Tres", "nombre": "Tres, Carla", "slug": "carla-tres", "alta": "15/09/2026",
     "circunscripcion": "Coruña (A)"},
]
VOT = {"fecha": "23/9/2026", "fecha_iso": "2026-09-23", "titulo": vr.TITULO,
       "texto": "Real Decreto-ley 23/2026, de 8 de septiembre, por el que se adoptan medidas <urgentes>.",
       "json": "https://www.congreso.es/webpublica/opendata/votaciones/Leg15/Sesion200/x.json",
       "pdf": "https://www.congreso.es/webpublica/opendata/votaciones/Leg15/Sesion200/x.pdf",
       "dia": vr.DIA_URL.format(fecha="23/09/2026"), "expediente": "130/000054",
       "resultado": "Derogado", "votos": {"uno": "S", "dos": "X", "otro": "N"}, "antes_alta": []}
BAJA = {"nombre": "Otro Baja, Olga", "natural": "Olga Otro Baja", "circunscripcion": "Coruña (A)",
        "alta": "11/08/2023", "baja": "11/09/2026",
        "fuente": "https://www.congreso.es/webpublica/opendata/diputados/DiputadosDeBaja__1.json"}
FUENTES = {"pagina": "https://www.congreso.es/es/opendata/diputados", "bajas": BAJA["fuente"], "diputadas": ""}


class Bloque(unittest.TestCase):
    def h(self, extra=None, circ="Coruña (A)", **cambios):
        datos = {"votaciones": [{**VOT, **cambios}], **(extra or {})}
        return vr.bloque_html(datos, GENTE, "A Coruña", circ)

    def test_estructura_nota_y_por_que(self):
        h = self.h()
        self.assertIn('<h2 id="prov-votos">¿Quién votó qué en A Coruña?</h2>', h)
        self.assertIn(vr.NOTA, h)
        self.assertIn("Se eligen los decretos-leyes porque en esas votaciones el Pleno decide directamente "
                      "si una norma aprobada por el Gobierno sigue en vigor.", h)
        # Texto oficial tal cual (escapado), con el número del RDL en negrita.
        self.assertIn("<b>Real Decreto-ley 23/2026</b>, de 8 de septiembre, por el que se adoptan "
                      "medidas &lt;urgentes&gt;.", h)
        self.assertNotIn("<script", h)

    def test_plegado_con_details_y_solo_la_primera_abierta(self):
        vs = [{**VOT, "fecha": f"{d}/9/2026", "resultado": r} for d, r in ((23, "Derogado"), (16, ""), (9, "Convalidado"))]
        h = vr.bloque_html({"votaciones": vs}, GENTE, "A Coruña", "Coruña (A)")
        self.assertEqual(h.count('<details class="pv-vot"'), 3)
        self.assertEqual(h.count('<details class="pv-vot" open>'), 1)
        self.assertTrue(h.index('<details class="pv-vot" open>') < h.index('<details class="pv-vot">'))
        # Summary: número del RDL, fecha y resultado tal cual; sin resultado si no viene.
        self.assertIn('<summary class="pv-sum"><b>Real Decreto-ley 23/2026</b> · 23/9/2026 · Derogado</summary>', h)
        self.assertIn('<summary class="pv-sum"><b>Real Decreto-ley 23/2026</b> · 16/9/2026</summary>', h)
        # Dentro de cada desplegable sigue la agrupación por sentido del voto.
        for trozo in h.split("<details")[1:]:
            self.assertIn('<span class="pv-v">Sí:</span>', trozo)

    def test_votos_y_sin_dato(self):
        h = self.h()
        self.assertIn('<span class="pv-v">Sí:</span> <a href="ana-uno.html">Ana Uno</a>', h)
        self.assertIn('<span class="pv-v">No vota:</span> <a href="bea-dos.html">Bea Dos</a>', h)
        self.assertIn('<li class="pv-sin"><span class="pv-v">Sin dato</span> (no aparece en el listado '
                      'oficial de esta votación): <a href="carla-tres.html">Carla Tres</a> '
                      '(alta en el Congreso: 15/09/2026)</li>', h)
        self.assertNotIn("otro", h)
        self.assertNotIn("No:", h)
        self.assertNotIn("no figura", h.lower())
        self.assertNotIn("%", h)

    def test_sustituto_antes_del_alta(self):
        for genero, rotulo in (("f", "Aún no era diputada"), ("m", "Aún no era diputado"),
                               ("", "Aún no había tomado posesión")):
            h = self.h({"generos": {"tres": genero} if genero else {}}, antes_alta=["tres"])
            self.assertIn(f'<li class="pv-sin"><span class="pv-v">{rotulo}:</span> '
                          '<a href="carla-tres.html">Carla Tres</a> (alta en el Congreso: 15/09/2026)</li>', h)
            self.assertNotIn("Sin dato", h)

    def test_antes_del_alta_compara_fechas_oficiales(self):
        self.assertTrue(vr.antes_del_alta("2026-09-09", "15/09/2026"))
        self.assertFalse(vr.antes_del_alta("2026-09-15", "15/09/2026"))
        self.assertFalse(vr.antes_del_alta("2026-09-23", "15/09/2026"))
        self.assertFalse(vr.antes_del_alta("2026-09-09", ""))

    def test_baja_en_su_circunscripcion(self):
        extra = {"bajas": {"otro": BAJA}, "generos": {"otro": "f"}, "fuentes_diputados": FUENTES}
        h = self.h(extra)
        self.assertIn('<span class="pv-v">No:</span> Olga Otro Baja <span class="pv-baja">'
                      '(ya no es diputada desde el 11/09/2026)</span>', h)
        self.assertIn('href="https://www.congreso.es/es/opendata/diputados"', h)
        # En otra circunscripción no sale.
        h2 = self.h(extra, circ="Lugo")
        self.assertNotIn("Olga", h2)
        self.assertNotIn("datos abiertos de diputados", h2)
        # Sin género, forma neutra.
        h3 = self.h({**extra, "generos": {}})
        self.assertIn("(causó baja en el Congreso el 11/09/2026)", h3)

    def test_baja_sin_voto_en_esa_votacion_no_sale(self):
        extra = {"bajas": {"otro": BAJA}, "generos": {"otro": "f"}, "fuentes_diputados": FUENTES}
        h = self.h(extra, votos={"uno": "S", "dos": "X"})
        self.assertNotIn("Olga", h)

    def test_no_atribuidos_no_salen(self):
        h = self.h({"no_atribuidos": [{"clave": "otro", "motivo": "x", "votaciones": ["23/9/2026"]}]})
        self.assertNotIn("otro", h)

    def test_enlaces_oficiales(self):
        h = self.h()
        for clave in ("json", "pdf"):
            self.assertIn(f'href="{VOT[clave]}"', h)
        self.assertIn(">votaciones del día</a>", h)
        self.assertIn("_iniciativas_id=130/000054", h)
        for href in re.findall(r'href="([^"]+)"', h):
            self.assertTrue(href.startswith("https://www.congreso.es/") or href.endswith(".html"), href)

    def test_resultado_solo_si_viene(self):
        self.assertIn("Resultado, según el expediente del Congreso: Derogado.", self.h())
        sin = self.h(resultado="", pdf="", expediente="")
        for x in ("Resultado", "Convalidad", "Derogad", "PDF", "expediente"):
            self.assertNotIn(x, sin)

    def test_orden_alfabetico_sin_tildes_al_final(self):
        gente = GENTE + [{"clave": "cuatro", "natural": "Eva Álvarez", "nombre": "Álvarez, Eva",
                          "slug": "eva-alvarez", "circunscripcion": "Coruña (A)"}]
        h = vr.bloque_html({"votaciones": [{**VOT, "votos": {"uno": "S", "cuatro": "S"}}]}, gente, "X")
        self.assertLess(h.index("Eva Álvarez"), h.index("Ana Uno"))

    def test_sin_copia_no_hay_bloque(self):
        self.assertEqual(vr.bloque_html(None, GENTE, "Madrid"), "")
        self.assertEqual(vr.bloque_html({"votaciones": []}, GENTE, "Madrid"), "")

    def test_css_sin_tarjetas_ni_subrayados_y_con_foco(self):
        css = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")
        self.assertIn(".prov-votos a{color:var(--red-ink,var(--red));text-decoration:none", css)
        self.assertRegex(css, r"\.pv-sum:focus-visible\{outline:2px solid")
        self.assertNotRegex(css, r"\.pv-sum:focus\{[^}]*outline:none")
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


class CopiaFijaSustitutosYBajas(unittest.TestCase):
    def setUp(self):
        self.datos = vr.cargar()
        if not self.datos:
            self.skipTest("sin curated/votos_rdl.json")

    def test_bajas_con_fuente_y_fechas(self):
        bajas = self.datos.get("bajas") or {}
        for k, b in bajas.items():
            self.assertTrue(b["fuente"].startswith("https://www.congreso.es/webpublica/opendata/diputados/"), k)
            self.assertTrue(b["circunscripcion"], k)
            self.assertTrue(vr._fecha_ddmmaaaa(b["baja"]) and vr._fecha_ddmmaaaa(b["alta"]), k)
            self.assertIn(self.datos["generos"].get(k), ("f", "m"), k)
            for v in self.datos["votaciones"]:
                if k in v["votos"]:
                    self.assertLessEqual(v["fecha_iso"], vr._fecha_ddmmaaaa(b["baja"]), k)
        # Los dos casos del informe 43.
        self.assertEqual(bajas["taboadela alvarez obdulia"]["circunscripcion"], "Coruña (A)")
        self.assertEqual(bajas["taboadela alvarez obdulia"]["baja"], "11/09/2026")
        self.assertEqual(bajas["navarro lopez pedro"]["circunscripcion"], "Zaragoza")
        self.assertEqual(self.datos["generos"]["taboadela alvarez obdulia"], "f")
        self.assertEqual(self.datos["generos"]["navarro lopez pedro"], "m")
        self.assertEqual(self.datos.get("no_atribuidos"), [])

    def test_antes_del_alta(self):
        por_fecha = {v["fecha"] + v["texto"][:20]: set(v["antes_alta"]) for v in self.datos["votaciones"]}
        taibo = [k for k, s in por_fecha.items() if "taibo monelos diego" in s]
        bondia = [k for k, s in por_fecha.items() if "bondia pinos maria elena" in s]
        self.assertEqual(len(taibo), 7)     # RDL 14 a 20
        self.assertEqual(len(bondia), 6)    # RDL 14 a 19
        for v in self.datos["votaciones"]:
            self.assertFalse(set(v["antes_alta"]) & set(v["votos"]))


class Pintadas(unittest.TestCase):
    def test_fichas_de_provincia(self):
        fichas = sorted((RAIZ / "diputados").glob("provincia-*.html"))
        if not fichas or not vr.cargar():
            self.skipTest("fichas de provincia sin pintar (build.py --render)")
        self.assertEqual(len(fichas), 52)
        for f in fichas:
            h = f.read_text(encoding="utf-8")
            self.assertEqual(h.count('<section class="prov-votos"'), 1, f.name)
            self.assertEqual(h.count('<details class="pv-vot"'), vr.N_VOTACIONES, f.name)
            self.assertEqual(h.count('<details class="pv-vot" open>'), 1, f.name)
            self.assertNotIn("Sin dato", h, f.name)
            i = h.index('<section class="prov-votos"')
            self.assertLess(i, h.index('class="rejilla-dip"'), f.name)
            head = h[:h.index("</head>")]
            self.assertNotIn("Quién votó qué", head, f.name)
        coruna = (RAIZ / "diputados" / "provincia-coruna-a.html").read_text(encoding="utf-8")
        self.assertEqual(coruna.count("Obdulia Taboadela Álvarez <span class=\"pv-baja\">(ya no es diputada "
                                      "desde el 11/09/2026)</span>"), 7)
        self.assertEqual(coruna.count('<span class="pv-v">Aún no era diputado:</span>'), 7)
        zaragoza = (RAIZ / "diputados" / "provincia-zaragoza.html").read_text(encoding="utf-8")
        self.assertEqual(zaragoza.count("Pedro Navarro López <span class=\"pv-baja\">(ya no es diputado "
                                        "desde el 01/09/2026)</span>"), 6)
        self.assertEqual(zaragoza.count('<span class="pv-v">Aún no era diputada:</span>'), 6)
        self.assertNotIn("Taboadela", zaragoza)


if __name__ == "__main__":
    unittest.main()
