"""Bloque «Resultados oficiales» del 29-N (resultados_29n.py).

Las entradas son FICTICIAS (tests/ficticios_resultados/): ni cifras ni nombres
existen. Comprueba que el bloque solo sale de la copia fija, que sin copia no se
pinta nada, que una circunscripción dudosa queda fuera, que las cifras van
literales, y que no se tocan title, description, canonical, robots ni H1.
Sin red."""
import json
import pathlib
import re
import sys
import tempfile
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))
import build  # noqa: E402
import elecciones as el  # noqa: E402
import resultados_29n as rs  # noqa: E402

FICT = RAIZ / "tests" / "ficticios_resultados"
FUENTE = {"id": "BOE-A-2099-00000",
          "titulo": "Resolución FICTICIA de prueba (resultados de las elecciones convocadas por Real Decreto 806/2026)",
          "literal": "BOE núm. 999, de 31/12/2099"}


def _circs():
    return [c["circunscripcion"] for c in el.cargar()["circunscripciones"]]


def _ficticio():
    xml = (FICT / "jec_ficticia.xml").read_text(encoding="utf-8")
    txt = (FICT / "jec_ficticia.txt").read_text(encoding="utf-8")
    return rs.construir(xml, txt, FUENTE, _circs())


def _manual():
    return json.loads((FICT / "manual_ficticio.json").read_text(encoding="utf-8"))


def _paginas(resultados):
    escritas = {}

    def suelta(pl, carpeta, nombre, frag):
        escritas[nombre] = frag
    h = {"pagina_suelta": suelta, "plantilla": "<footer>" + el.LEMA_IA + "</footer>",
         "site_url": "https://terceracamara.es/", "carpeta": pathlib.Path(tempfile.gettempdir()),
         "jsonld_script": lambda xs: "", "nombre": build.nombre_circunscripcion, "slug": build._slug_txt,
         "resultados": resultados}
    el.generar_paginas(h, el.cargar(), [])
    return escritas


class Lectura(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = _ficticio()

    def test_solo_entran_las_que_cuadran(self):
        self.assertEqual(sorted(self.d["circunscripciones"]), ["Albacete", "Soria"])

    def test_dudosas_fuera_con_motivo(self):
        ex = self.d["excluidas"]
        self.assertIn("línea no reconocida", ex["Teruel"])                       # nota en la relación
        self.assertIn("electos 2", ex["Cuenca"])                                  # 3 escaños, 2 electos
        self.assertIn("real decreto", ex["Provincia Inventada"])                 # nombre que no casa
        self.assertNotIn("Total estatal", ex)

    def test_cifras_y_nombres_literales(self):
        a = self.d["circunscripciones"]["Albacete"]
        self.assertEqual(a["escanos"], "3")
        self.assertEqual(a["candidaturas"][0], {"nombre": "Candidatura Ficticia A (FICT-A)",
                                                "votos": "11.111", "escanos": "2"})
        # Cuadro sin escaños: votos sí, escaños None (no se inventa un 0).
        self.assertEqual(a["candidaturas"][-1], {"nombre": "Candidatura Ficticia C sin escaño (FICT-C)",
                                                 "votos": "99", "escanos": None})
        self.assertEqual([e["nombre"] for e in a["electos"]],
                         ["Doña Ficticia Uno Ejemplo", "Don Ficticio Dos Ejemplo", "Doña Ficticia Tres Ejemplo"])
        # Celda vacía: la candidatura no se presentaba allí.
        s = self.d["circunscripciones"]["Soria"]
        self.assertNotIn("Candidatura Ficticia C sin escaño (FICT-C)", [k["nombre"] for k in s["candidaturas"]])

    def test_el_senado_no_se_mezcla(self):
        nombres = [e["nombre"] for c in self.d["circunscripciones"].values() for e in c["electos"]]
        self.assertNotIn("Don Ficticio Diez Ejemplo", nombres)

    def test_valida(self):
        self.assertEqual(rs.validar(self.d), [])
        self.assertTrue(rs.validar({**self.d, "fuente": {"id": "inventado", "literal": "x"}}))

    def test_documento_que_no_es_la_proclamacion(self):
        import generar_resultados_29n as g
        xml = (FICT / "jec_ficticia.xml").read_text(encoding="utf-8")
        self.assertEqual(g.comprobar_documento(xml)[1], "BOE núm. 999, de 31/12/2099")
        with self.assertRaises(ValueError):
            g.comprobar_documento(xml.replace("Real Decreto 806/2026", "Real Decreto 400/2023"))


class SinCopia(unittest.TestCase):
    def test_no_existe_copia_real_en_el_repo(self):
        # La copia fija solo se crea con la proclamación publicada. Si existe,
        # tiene que ser válida y no contener nada de los ficticios.
        if rs.DATOS.exists():
            t = rs.DATOS.read_text(encoding="utf-8")
            self.assertNotIn("ictici", t)
            self.assertNotIn("BOE-A-2099-", t)
            self.assertEqual(rs.validar(json.loads(t)), [])

    def test_cargar_sin_fichero_es_none(self):
        self.assertIsNone(rs.cargar(pathlib.Path(tempfile.gettempdir()) / "no-existe-resultados.json"))

    def test_sin_copia_ningun_bloque(self):
        for nombre, frag in _paginas(None).items():
            self.assertNotIn('class="rof"', frag["CUERPO"], nombre)
            self.assertNotIn("Resultados oficiales</h2>", frag["CUERPO"], nombre)

    def test_build_sin_copia(self):
        if not rs.DATOS.exists():
            self.assertIsNone(build._resultados_29n())


class Render(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.con = _paginas(_ficticio())
        cls.sin = _paginas(None)

    def test_solo_en_las_que_estan(self):
        con = [n for n, f in self.con.items() if 'class="rof"' in f["CUERPO"]]
        self.assertEqual(sorted(con), ["albacete.html", "soria.html"])

    def test_salto_arriba_solo_con_datos(self):
        salto = '<p class="rof-salto"><a href="#resultados">Resultados oficiales&nbsp;↓</a>'
        for n, f in self.con.items():
            c = f["CUERPO"]
            if n in ("albacete.html", "soria.html"):
                self.assertTrue(c.startswith(salto), n)            # arriba del todo
                self.assertEqual(c.count(salto), 1, n)
                # El reparto va justo debajo del enlace, en el mismo párrafo.
                fin = c.index("</p>")
                self.assertIn('<span class="rof-reparto">Escaños: ', c[:fin], n)
                self.assertEqual(c.count('id="resultados"'), 1, n)  # el ancla existe, una vez
            else:
                self.assertNotIn("rof-salto", c, n)
        for n, f in self.sin.items():
            self.assertNotIn("rof-salto", f["CUERPO"], n)

    def test_tras_el_indice(self):
        c = self.con["albacete.html"]["CUERPO"]
        self.assertLess(c.index('class="elec-indice"'), c.index('class="rof"'))
        self.assertLess(c.index('class="rof"'), c.index('class="elec-cand"'))
        self.assertLess(c.index('class="elec-intro"'), c.index('class="elec-indice"'))

    def test_css_salto_sin_subrayado(self):
        css = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")
        reglas = {s.strip(): c for s, c in re.findall(r"([^{}]+)\{([^}]*)\}", css)}
        clave = [s for s in reglas if ".rof-salto a:hover" in s]
        self.assertEqual(len(clave), 1)
        selectores = [x.strip() for x in clave[0].split(",")]
        for estado in ("a", "a:hover", "a:focus", "a:focus-visible"):
            self.assertIn(f".rof-salto {estado}", selectores)
        for sel, cuerpo in reglas.items():
            if ".rof-salto" in sel:
                self.assertNotIn("underline", cuerpo, sel)
        self.assertIn("text-decoration:none", reglas[clave[0]])

    def test_bloque(self):
        c = self.con["albacete.html"]["CUERPO"]
        self.assertEqual(c.count('<h2 id="rof-tit">Resultados oficiales</h2>'), 1)
        self.assertIn("<td>11.111</td><td>2</td>", c)
        self.assertIn("<td>99</td><td>0</td>", c)
        self.assertIn("https://www.boe.es/diario_boe/txt.php?id=BOE-A-2099-00000", c)
        self.assertIn("BOE núm. 999, de 31/12/2099", c)
        self.assertNotIn("%", c[c.index('class="rof"'):c.index("</section>")])   # sin porcentajes

    def test_75_intacto(self):
        for n in self.sin:
            for k in ("TITLE", "META_DESC", "CANONICAL", "HEADLINE"):
                self.assertEqual(self.con[n][k], self.sin[n][k], (n, k))
            self.assertNotIn("robots", self.con[n]["CUERPO"])

    def test_resto_igual(self):
        # Fuera del bloque, la página es la misma.
        for n in ("albacete.html", "teruel.html", "index.html"):
            c = re.sub(r'<section class="rof".*?</section>|<p class="rof-salto">.*?</p>', "",
                       self.con[n]["CUERPO"], flags=re.S)
            self.assertEqual(c, self.sin[n]["CUERPO"], n)

    def test_css_sin_subrayado_ni_tarjeta(self):
        css = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")
        reglas = [r for r in re.findall(r"([^{}]+)\{([^}]*)\}", css) if re.search(r"\.rof\b|\.rof-", r[0])]
        self.assertTrue(reglas)
        for sel, cuerpo in reglas:
            self.assertNotIn("underline", cuerpo, sel)
            self.assertNotIn("box-shadow", cuerpo, sel)
            self.assertNotIn("border-radius", cuerpo, sel)
        self.assertIn("text-decoration:none", dict((s.strip(), c) for s, c in reglas)[".rof-fuente a"])


class OrdenYReparto(unittest.TestCase):
    """Informe 48: la tabla va por escaños y, a igualdad, por votos; un único
    signo («0») para quien no tiene escaño; resumen del reparto encima."""

    D = {"escanos": "7", "candidaturas": [
        {"nombre": "Candidatura Ficticia Columna Uno (FC1)", "votos": "53.632", "escanos": "0"},
        {"nombre": "Candidatura Ficticia Columna Dos (FC2)", "votos": "174.770", "escanos": "3"},
        {"nombre": "Candidatura Ficticia Columna Tres (FC3)", "votos": "165.590", "escanos": "3"},
        {"nombre": "Candidatura Ficticia Sin Columna", "votos": "82.805", "escanos": "1"},
        {"nombre": "Candidatura Ficticia Cuadro III (FC5)", "votos": "60.000", "escanos": None},
        {"nombre": "Candidatura Ficticia Empate A (FEA)", "votos": "100", "escanos": None},
        {"nombre": "Candidatura Ficticia Empate B (FEB)", "votos": "100", "escanos": None}],
        "electos": [{"nombre": f"Don Ficticio {i}", "formacion": "X"} for i in range(7)]}

    def test_orden_escanos_y_desempate_por_votos(self):
        self.assertEqual([rs.sigla(k["nombre"]) for k in rs.ordenadas(self.D)],
                         ["FC2", "FC3", "Candidatura Ficticia Sin Columna", "FC5", "FC1", "FEA", "FEB"])
        # FC2 y FC3 empatan a 3 escaños: primero la de más votos. FC5 (sin
        # columna de escaños) y FC1 («0») empatan a 0: primero la de más votos.
        # FEA y FEB empatan en todo: se respeta el orden del BOE.

    def test_tabla_ordenada_en_el_html(self):
        h = rs.bloque_html({"fuente": FUENTE, "circunscripciones": {"Albacete": self.D}}, "Albacete", "Albacete")
        filas = re.findall(r'<tr><th scope="row">(.*?)</th><td>(.*?)</td><td>(.*?)</td></tr>', h)
        self.assertEqual([(rs.sigla(n), e) for n, _, e in filas],
                         [("FC2", "3"), ("FC3", "3"), ("Candidatura Ficticia Sin Columna", "1"),
                          ("FC5", "0"), ("FC1", "0"), ("FEA", "0"), ("FEB", "0")])

    def test_un_solo_signo_sin_escano(self):
        h = rs.bloque_html({"fuente": FUENTE, "circunscripciones": {"Albacete": self.D}}, "Albacete", "Albacete")
        tabla = h[h.index("<table"):h.index("</table>")]
        self.assertNotIn("—", tabla)
        self.assertNotIn("–", tabla)
        self.assertNotIn("<td></td>", tabla)
        self.assertEqual(rs.escanos({"escanos": None}), "0")
        self.assertEqual(rs.escanos({"escanos": ""}), "0")
        self.assertEqual(rs.escanos({"escanos": "16"}), "16")

    def test_reparto(self):
        # Solo las que tienen escaño, en el orden de la tabla, con la sigla y
        # los escaños tal cual; sin porcentajes ni totales calculados.
        self.assertEqual(rs.reparto_texto(self.D), "FC2 3, FC3 3, Candidatura Ficticia Sin Columna 1")
        h = rs.bloque_html({"fuente": FUENTE, "circunscripciones": {"Albacete": self.D}}, "Albacete", "Albacete")
        resumen = ('<p class="rof-resumen"><span class="rof-reparto">Escaños: FC2&nbsp;3, FC3&nbsp;3, '
                   'Candidatura Ficticia Sin Columna&nbsp;1</span></p>')
        self.assertEqual(h.count(resumen), 1)
        self.assertLess(h.index(resumen), h.index("<table"))
        salto = rs.salto_html({"fuente": FUENTE, "circunscripciones": {"Albacete": self.D}}, "Albacete")
        self.assertIn('Resultados oficiales&nbsp;↓</a><span class="rof-reparto">Escaños: FC2&nbsp;3, FC3&nbsp;3,', salto)
        self.assertNotIn("%", salto + resumen)

    def test_sigla(self):
        self.assertEqual(rs.sigla("Partido Popular (PP)"), "PP")
        self.assertEqual(rs.sigla("Partit dels Socialistes de Catalunya (PSC-PSOE) (PSC)"), "PSC")
        self.assertEqual(rs.sigla("Sin sigla"), "Sin sigla")

    def test_ficticio_reparto(self):
        d = _ficticio()["circunscripciones"]["Albacete"]
        self.assertEqual(rs.reparto_texto(d), "FICT-A 2, FICT-B 1")

    def test_reparto_sin_subrayado(self):
        css = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")
        for sel, cuerpo in re.findall(r"([^{}]+)\{([^}]*)\}", css):
            if "rof-reparto" in sel or "rof-resumen" in sel:
                self.assertNotIn("underline", cuerpo, sel)
                self.assertNotIn("border", cuerpo, sel)
                self.assertNotIn("background", cuerpo, sel)


class Manual(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = rs.combinar(_ficticio(), _manual(), set(_circs()))

    def test_entra_la_curada(self):
        self.assertEqual(sorted(self.d["circunscripciones"]), ["Albacete", "Soria", "Teruel"])
        self.assertTrue(self.d["circunscripciones"]["Teruel"]["manual"])

    def test_descartadas(self):
        m = self.d["manual_descartadas"]
        self.assertIn("página", m["Cuenca"])
        self.assertIn("automática", m["Albacete"])                 # manda la automática
        self.assertIn("misma proclamación", m["Huesca"])
        self.assertNotIn("Duplicado", json.dumps(self.d["circunscripciones"], ensure_ascii=False))

    def test_no_cuadra_no_se_publica(self):
        m = _manual()
        m["circunscripciones"]["Teruel"]["electos"].pop()
        d = rs.combinar(_ficticio(), m, set(_circs()))
        self.assertNotIn("Teruel", d["circunscripciones"])
        self.assertIn("electos 1", d["manual_descartadas"]["Teruel"])

    def test_render_con_pagina_y_nota(self):
        h = rs.bloque_html(self.d, "Teruel", "Teruel")
        self.assertIn("(BOE núm. 999, de 31/12/2099, página 1).", h)
        self.assertIn('<span class="rof-nota">(proclamado electo tras una renuncia ficticia)</span>', h)
        self.assertNotIn("página", rs.bloque_html(self.d, "Albacete", "Albacete"))

    def test_borrador_para_curar(self):
        b = _ficticio()["borradores"]
        self.assertEqual(b["Teruel"]["fuente"], {"id": "BOE-A-2099-00000", "pagina": "1"})
        self.assertEqual(b["Teruel"]["electos"], [])                # se copian a mano del PDF
        self.assertEqual(b["Cuenca"]["fuente"]["pagina"], "2")


class NuncaEnProduccion(unittest.TestCase):
    """Los datos de 2023 (capturas de prueba) y la marca «DATOS DE PRUEBA 2023»
    no pueden llegar a un render: cargar() solo acepta la proclamación de las
    elecciones del Real Decreto 806/2026 y rechaza la marca."""

    def _escribe(self, datos, manual=None):
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "r.json").write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        if manual is not None:
            (tmp / "m.json").write_text(json.dumps(manual, ensure_ascii=False), encoding="utf-8")
        return tmp / "r.json", tmp / "m.json"

    def test_otra_convocatoria_no_carga(self):
        d = _ficticio()
        d["fuente"] = {**d["fuente"], "titulo": "Resolución (elecciones convocadas por Real Decreto 400/2023)"}
        self.assertIsNone(rs.cargar(*self._escribe(d)))

    def test_marca_de_prueba_no_carga(self):
        d = _ficticio()
        d["fuente"] = {**d["fuente"], "literal": "DATOS DE PRUEBA 2023 · " + d["fuente"]["literal"]}
        self.assertIsNone(rs.cargar(*self._escribe(d)))
        m = _manual()
        m["circunscripciones"]["Teruel"]["electos"][1]["nombre"] += " DATOS DE PRUEBA 2023"
        ok = rs.cargar(*self._escribe(_ficticio(), m))
        self.assertNotIn("Teruel", ok["circunscripciones"])

    def test_manual_sola_no_pinta(self):
        r, m = self._escribe(_ficticio(), _manual())
        r.unlink()
        self.assertIsNone(rs.cargar(r, m))

    def test_build_usa_cargar(self):
        # build no tiene otra vía: si cargar() da None, el bloque no existe.
        orig = rs.cargar
        try:
            rs.cargar = lambda *a, **k: None
            self.assertIsNone(build._resultados_29n())
        finally:
            rs.cargar = orig

    def test_repo_sin_datos_2023_ni_marca(self):
        for p in list((RAIZ / "curated").rglob("*")) + [RAIZ / "resultados_29n.py", RAIZ / "elecciones.py",
                                                       RAIZ / "build.py"]:
            if p.is_file() and p.suffix in (".json", ".py", ".md", ".txt"):
                t = p.read_text(encoding="utf-8", errors="ignore")
                self.assertNotIn("DATOS DE PRUEBA 2023", t, p)
                self.assertNotIn("BOE-A-2023-18907", t if p.parent.name == "curated" else "", p)
        self.assertFalse(rs.DATOS.exists() and "BOE-A-2023-18907" in rs.DATOS.read_text(encoding="utf-8"))


class FicticiosSoloEnTests(unittest.TestCase):
    def test_curated_limpio(self):
        for p in (RAIZ / "curated").rglob("*"):
            if p.is_file() and p.suffix in (".json", ".md", ".txt"):
                t = p.read_text(encoding="utf-8", errors="ignore")
                self.assertNotIn("FICT-A", t, p)
                self.assertNotIn("BOE-A-2099-", t, p)
                self.assertNotIn("ictici", t, p)


if __name__ == "__main__":
    unittest.main()
