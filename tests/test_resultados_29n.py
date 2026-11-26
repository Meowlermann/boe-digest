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
FUENTE = {"id": "BOE-A-2099-00000", "titulo": "Resolución FICTICIA de prueba",
          "literal": "BOE núm. 999, de 31/12/2099"}


def _circs():
    return [c["circunscripcion"] for c in el.cargar()["circunscripciones"]]


def _ficticio():
    xml = (FICT / "jec_ficticia.xml").read_text(encoding="utf-8")
    txt = (FICT / "jec_ficticia.txt").read_text(encoding="utf-8")
    return rs.construir(xml, txt, FUENTE, _circs())


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

    def test_bloque(self):
        c = self.con["albacete.html"]["CUERPO"]
        self.assertEqual(c.count('<h2 id="rof-tit">Resultados oficiales</h2>'), 1)
        self.assertIn("<td>11.111</td><td>2</td>", c)
        self.assertIn("<td>99</td><td>—</td>", c)
        self.assertIn("https://www.boe.es/diario_boe/txt.php?id=BOE-A-2099-00000", c)
        self.assertIn("BOE núm. 999, de 31/12/2099", c)
        self.assertNotIn("%", c[c.index('class="rof"'):c.index("</section>")])   # sin porcentajes
        self.assertLess(c.index('class="rof"'), c.index('class="elec-cand"'))

    def test_75_intacto(self):
        for n in self.sin:
            for k in ("TITLE", "META_DESC", "CANONICAL", "HEADLINE"):
                self.assertEqual(self.con[n][k], self.sin[n][k], (n, k))
            self.assertNotIn("robots", self.con[n]["CUERPO"])

    def test_resto_igual(self):
        # Fuera del bloque, la página es la misma.
        for n in ("albacete.html", "teruel.html", "index.html"):
            c = re.sub(r'<section class="rof".*?</section>', "", self.con[n]["CUERPO"], flags=re.S)
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


class FicticiosSoloEnTests(unittest.TestCase):
    def test_curated_limpio(self):
        for p in (RAIZ / "curated").rglob("*"):
            if p.is_file() and p.suffix in (".json", ".md", ".txt"):
                t = p.read_text(encoding="utf-8", errors="ignore")
                self.assertNotIn("FICT-A", t, p)
                self.assertNotIn("BOE-A-2099-", t, p)


if __name__ == "__main__":
    unittest.main()
