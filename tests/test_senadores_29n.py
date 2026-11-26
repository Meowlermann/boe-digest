"""«Tus senadores» en las fichas de provincia (senadores.py).

Las entradas son FICTICIAS (tests/ficticios_senadores/): ni personas ni votos
existen. Comprueba que los nombres solo salen de la copia fija de la
proclamación, que sin copia no se pinta nada, que una provincia que no está
clara no se publica (ni a medias), y que el bloque no toca title, description,
canonical, robots ni H1 (#75). Sin red."""
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
import senadores as sn  # noqa: E402

FICT = RAIZ / "tests" / "ficticios_senadores"
FUENTE = {"id": "BOE-A-2099-00000",
          "titulo": "Resolución FICTICIA de prueba (resultados de las elecciones convocadas por Real Decreto 806/2026)",
          "literal": "BOE núm. 999, de 31/12/2099"}


def _provs():
    return [c["circunscripcion"] for c in el.cargar()["circunscripciones"]]


def _ficticio():
    claras, dudosas = sn.parsear((FICT / "jec_ficticia.txt").read_text(encoding="utf-8"), _provs())
    return {"fuente": FUENTE, "provincias": claras, "excluidas": dudosas}


class Lectura(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = _ficticio()

    def test_claras(self):
        self.assertEqual(sorted(self.d["provincias"]),
                         ["Balears (Illes)", "Ceuta", "Santa Cruz de Tenerife", "Soria"])

    def test_no_claras_fuera(self):
        ex = self.d["excluidas"]
        self.assertIn("línea no reconocida", ex["Teruel"])          # formación en dos renglones
        self.assertIn("esperados 4", ex["Cuenca"])                 # tres senadores leídos
        self.assertIn("ISLA INVENTADA", ex["Palmas (Las)"])         # isla desconocida
        self.assertNotIn("Palmas (Las)", self.d["provincias"])      # ni a medias (Gran Canaria sí se leyó)
        self.assertIn("no aparece", ex["Madrid"])

    def test_literal(self):
        s = self.d["provincias"]["Soria"]
        self.assertEqual(s, [{"isla": None, "senadores": [
            {"nombre": "Doña Ficticia Uno Ejemplo", "formacion": "CANDIDATURA FICTICIA A", "votos": "1.111"},
            {"nombre": "Don Ficticio Dos Ejemplo", "formacion": "CANDIDATURA FICTICIA A", "votos": "1.100"},
            {"nombre": "Doña Ficticia Tres Ejemplo", "formacion": "CANDIDATURA FICTICIA B", "votos": "999"},
            {"nombre": "Don Ficticio Cuatro Ejemplo", "formacion": "CANDIDATURA FICTICIA B", "votos": "998"}]}])
        islas = [g["isla"] for g in self.d["provincias"]["Balears (Illes)"]]
        self.assertEqual(islas, ["MALLORCA", "MENORCA", "EIVISSA-FORMENTERA"])

    def test_ni_diputados_ni_candidatos_sin_escano(self):
        todos = json.dumps(self.d["provincias"], ensure_ascii=False)
        self.assertNotIn("Diputado Ejemplo", todos)
        self.assertNotIn("Sin Escaño", todos)

    def test_valida(self):
        self.assertEqual(sn.validar(self.d), [])
        malo = json.loads(json.dumps(self.d))
        malo["provincias"]["Soria"][0]["senadores"].pop()
        self.assertTrue(sn.validar(malo))

    def test_documento_que_no_es_la_proclamacion(self):
        import generar_senadores as g
        xml = ("<titulo>Resolución de la Presidencia de la Junta Electoral Central, por la que se publica "
               "el resumen de los resultados de las elecciones al Congreso de los Diputados y al Senado "
               "convocadas por Real Decreto 806/2026 (FICTICIO)</titulo><diario_numero>999</diario_numero>"
               "<fecha_publicacion>20991231</fecha_publicacion>")
        self.assertEqual(g.comprobar_documento(xml)[1], "BOE núm. 999, de 31/12/2099")
        with self.assertRaises(ValueError):
            g.comprobar_documento(xml.replace("806/2026", "400/2023"))


def _manual():
    return json.loads((FICT / "manual_ficticio.json").read_text(encoding="utf-8"))


class Articulo165(unittest.TestCase):
    """Número de senadores por provincia del artículo 165 de la LOREG: cuatro
    por provincia; tres en Gran Canaria, Mallorca y Tenerife; uno en Ibiza-
    Formentera, Menorca, Fuerteventura, La Gomera, El Hierro, Lanzarote y La
    Palma; dos en Ceuta y dos en Melilla. 208 en total."""

    def _esperado(self, prov):
        if prov in sn.ISLAS:
            return sum(sn.ISLAS[prov].values())
        return sn.SENADORES_CIUDAD.get(prov, sn.SENADORES_PROVINCIA)

    def test_tabla(self):
        provs = _provs()
        self.assertEqual(len(provs), 52)
        self.assertEqual(sum(self._esperado(p) for p in provs), 208)
        self.assertEqual(sn.ISLAS["Balears (Illes)"], {"MALLORCA": 3, "MENORCA": 1, "EIVISSA-FORMENTERA": 1})
        self.assertEqual(sn.ISLAS["Palmas (Las)"], {"GRAN CANARIA": 3, "FUERTEVENTURA": 1, "LANZAROTE": 1})
        self.assertEqual(sn.ISLAS["Santa Cruz de Tenerife"],
                         {"TENERIFE": 3, "LA PALMA": 1, "LA GOMERA": 1, "EL HIERRO": 1})
        self.assertEqual(sn.SENADORES_CIUDAD, {"Ceuta": 2, "Melilla": 2})
        self.assertEqual(sum(1 for p in provs if p not in sn.ISLAS and p not in sn.SENADORES_CIUDAD), 47)

    def _todas(self, datos):
        for prov, grupos in (datos.get("provincias") or {}).items():
            n = sum(len(g["senadores"]) for g in grupos)
            self.assertEqual(n, self._esperado(prov), prov)

    def test_lo_publicado_cumple(self):
        self._todas(_ficticio())
        self._todas(sn.combinar(_ficticio(), _manual(), set(_provs())))
        if sn.DATOS.exists():
            d = sn.cargar()
            self.assertIsNotNone(d)
            self._todas(d)

    def test_manual_con_otro_numero_fuera(self):
        d = sn.combinar(_ficticio(), _manual(), set(_provs()))
        self.assertNotIn("Cuenca", d["provincias"])
        self.assertIn("esperados 4", d["manual_descartadas"]["Cuenca"])


class Orden(unittest.TestCase):
    """Informe 48: por votos, de más a menos; a igualdad, el orden del BOE. Un
    solo signo: siempre los votos del BOE, nunca una raya."""

    def _datos(self, senadores):
        return {"fuente": FUENTE, "provincias": {"Soria": [{"isla": None, "senadores": senadores}]}}

    def test_por_votos_y_desempate_estable(self):
        ss = [{"nombre": "Don Ficticio C", "formacion": "F", "votos": "998"},
              {"nombre": "Doña Ficticia A", "formacion": "F", "votos": "1.111"},
              {"nombre": "Don Ficticio D", "formacion": "F", "votos": "998"},
              {"nombre": "Doña Ficticia B", "formacion": "F", "votos": "1.100"}]
        h = build._bloque_senadores(self._datos(ss), "Soria")
        orden = re.findall(r"<li>(D[^<]*)<", h)
        self.assertEqual(orden, ["Doña Ficticia A", "Doña Ficticia B", "Don Ficticio C", "Don Ficticio D"])

    def test_sin_rayas(self):
        h = build._bloque_senadores(_ficticio(), el.circ_congreso("Santa Cruz de Tenerife"))
        lista = re.sub(r'<p class="sen-fuente">.*?</p>', "", h, flags=re.S)
        self.assertNotIn("—", lista)
        self.assertNotIn("–", lista)
        self.assertEqual(len(re.findall(r"· [\d.]+ votos</span>", h)), 6)   # 3 + 1 + 1 + 1 (art. 165)


class Manual(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = sn.combinar(_ficticio(), _manual(), set(_provs()))

    def test_entra_la_curada(self):
        self.assertIn("Teruel", self.d["provincias"])
        self.assertEqual(self.d["manual"], {"Teruel": "2"})

    def test_descartadas(self):
        m = self.d["manual_descartadas"]
        self.assertIn("página", m["Madrid"])
        self.assertIn("automática", m["Soria"])
        self.assertNotIn("Duplicado", json.dumps(self.d["provincias"], ensure_ascii=False))

    def test_otra_fuente_fuera(self):
        man = _manual()
        man["provincias"]["Teruel"]["fuente"]["id"] = "BOE-A-2099-11111"
        d = sn.combinar(_ficticio(), man, set(_provs()))
        self.assertNotIn("Teruel", d["provincias"])

    def test_render_con_pagina_y_nota(self):
        h = build._bloque_senadores(self.d, "Teruel")
        self.assertIn("(BOE núm. 999, de 31/12/2099, página 2).", h)
        self.assertIn('<span class="sen-nota">(proclamada electa tras una renuncia ficticia)</span>', h)
        self.assertNotIn("página", build._bloque_senadores(self.d, "Soria"))

    def test_paginas_para_curar(self):
        p = sn.paginas_por_provincia((FICT / "jec_ficticia.txt").read_text(encoding="utf-8"), _provs())
        self.assertEqual(p["Teruel"], ["2"])
        self.assertEqual(p["Soria"], ["1"])


class NuncaEnProduccion(unittest.TestCase):
    """Los datos de 2023 (capturas de prueba) y la marca «DATOS DE PRUEBA 2023»
    no pueden llegar a un render: cargar() solo acepta la proclamación de las
    elecciones del Real Decreto 806/2026 y rechaza la marca."""

    def _escribe(self, datos, manual=None):
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "s.json").write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        if manual is not None:
            (tmp / "m.json").write_text(json.dumps(manual, ensure_ascii=False), encoding="utf-8")
        return tmp / "s.json", tmp / "m.json"

    def test_valida_la_buena(self):
        self.assertIsNotNone(sn.cargar(*self._escribe(_ficticio())))

    def test_otra_convocatoria_no_carga(self):
        d = _ficticio()
        d["fuente"] = {**d["fuente"], "titulo": "Resolución (elecciones convocadas por Real Decreto 400/2023)"}
        self.assertIsNone(sn.cargar(*self._escribe(d)))

    def test_marca_de_prueba_no_carga(self):
        d = _ficticio()
        d["fuente"] = {**d["fuente"], "literal": "DATOS DE PRUEBA 2023 · " + d["fuente"]["literal"]}
        self.assertIsNone(sn.cargar(*self._escribe(d)))
        m = _manual()
        m["provincias"]["Teruel"]["grupos"][0]["senadores"][0]["nombre"] += " DATOS DE PRUEBA 2023"
        self.assertNotIn("Teruel", sn.cargar(*self._escribe(_ficticio(), m))["provincias"])

    def test_manual_sola_no_pinta(self):
        s, m = self._escribe(_ficticio(), _manual())
        s.unlink()
        self.assertIsNone(sn.cargar(s, m))

    def test_build_usa_cargar(self):
        orig = sn.cargar
        try:
            sn.cargar = lambda *a, **k: None
            self.assertIsNone(build._senadores_29n())
        finally:
            sn.cargar = orig

    def test_repo_sin_datos_2023_ni_marca(self):
        for p in list((RAIZ / "curated").rglob("*")) + [RAIZ / "senadores.py", RAIZ / "build.py"]:
            if p.is_file() and p.suffix in (".json", ".py", ".md", ".txt"):
                t = p.read_text(encoding="utf-8", errors="ignore")
                self.assertNotIn("DATOS DE PRUEBA 2023", t, p)
                if p.parent.name == "curated":
                    self.assertNotIn("BOE-A-2023-18907", t, p)


class Render(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = _ficticio()

    def test_sin_copia_nada(self):
        self.assertEqual(build._bloque_senadores(None, "Soria"), "")
        self.assertIsNone(sn.cargar(pathlib.Path(tempfile.gettempdir()) / "no-existe-senadores.json"))
        if not sn.DATOS.exists():
            self.assertIsNone(build._senadores_29n())

    def test_provincia_fuera_nada(self):
        self.assertEqual(build._bloque_senadores(self.d, "Teruel"), "")
        self.assertEqual(build._bloque_senadores(self.d, "Palmas (Las)"), "")

    def test_bloque(self):
        h = build._bloque_senadores(self.d, "Soria")
        self.assertEqual(h.count('<h2 id="sen-tit">Tus senadores</h2>'), 1)
        self.assertIn("Doña Ficticia Uno Ejemplo<span class=\"sen-det\">CANDIDATURA FICTICIA A · 1.111 votos", h)
        self.assertIn("https://www.boe.es/diario_boe/txt.php?id=BOE-A-2099-00000", h)
        self.assertNotIn("senado.es", h)
        self.assertNotIn("<h1", h)

    def test_nombre_del_congreso(self):
        # La ficha usa «S/C Tenerife»; la copia, el nombre del real decreto.
        h = build._bloque_senadores(self.d, el.circ_congreso("Santa Cruz de Tenerife"))
        for isla in ("TENERIFE", "LA PALMA", "LA GOMERA", "EL HIERRO"):
            self.assertIn(f"<h3>{isla}</h3>", h)

    def test_va_en_el_cuerpo_de_la_ficha(self):
        src = (RAIZ / "build.py").read_text(encoding="utf-8")
        i = src.index("+ _bloque_senadores(datos_sen, prov)")
        # Dentro de cuerpo_extra, tras «¿Quién votó qué?»; meta_desc va después.
        self.assertLess(src.index("cuerpo_extra=bloque_elecciones.get(prov"), i)
        self.assertLess(i, src.index("meta_desc=desc_p or"))

    def test_css_sin_subrayado_ni_tarjeta(self):
        css = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")
        reglas = [r for r in re.findall(r"([^{}]+)\{([^}]*)\}", css) if re.search(r"\.sen-", r[0])]
        self.assertTrue(reglas)
        for sel, cuerpo in reglas:
            self.assertNotIn("underline", cuerpo, sel)
            self.assertNotIn("box-shadow", cuerpo, sel)
            self.assertNotIn("border-radius", cuerpo, sel)


class FicticiosSoloEnTests(unittest.TestCase):
    def test_curated_limpio(self):
        if sn.DATOS.exists():
            t = sn.DATOS.read_text(encoding="utf-8")
            self.assertNotIn("ictici", t)
            self.assertEqual(sn.validar(json.loads(t)), [])
        for p in (RAIZ / "curated").rglob("*"):
            if p.is_file() and p.suffix in (".json", ".md", ".txt"):
                t = p.read_text(encoding="utf-8", errors="ignore")
                self.assertNotIn("CANDIDATURA FICTICIA", t, p)
                self.assertNotIn("BOE-A-2099-", t, p)
                self.assertNotIn("ictici", t, p)


if __name__ == "__main__":
    unittest.main()
