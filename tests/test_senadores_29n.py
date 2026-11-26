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
        self.assertEqual(islas, ["MALLORCA", "MENORCA", "EIVISSA", "FORMENTERA"])  # literal del encabezado

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
    """Número de senadores por provincia del artículo 165 de la LOREG vigente
    (https://www.boe.es/buscar/act.php?id=BOE-A-1985-11672#acientosesentaycinco),
    con el apartado 2 que redacta la LO 2/2026 (BOE-A-2026-14329, en vigor desde
    el 3-7-2026): «tres en Gran Canaria, Mallorca y Tenerife; uno en Ibiza,
    Formentera, Menorca, Fuerteventura, La Gomera, El Hierro, Lanzarote y La
    Palma»; cuatro por provincia; dos en Ceuta y dos en Melilla. 209 en total
    (208 hasta la LO 2/2026, cuando Ibiza y Formentera eran una sola)."""

    def _esperado(self, prov):
        if prov in sn.ISLAS:
            return sum(sn.ISLAS[prov].values())
        return sn.SENADORES_CIUDAD.get(prov, sn.SENADORES_PROVINCIA)

    def test_tabla(self):
        provs = _provs()
        self.assertEqual(len(provs), 52)
        self.assertEqual(sum(self._esperado(p) for p in provs), 209)
        self.assertEqual(sn.ISLAS["Balears (Illes)"], {"MALLORCA": 3, "MENORCA": 1, "IBIZA": 1, "FORMENTERA": 1})
        self.assertEqual(sum(len(v) for v in sn.ISLAS.values()), 11)   # art. 161.2: once islas
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


def _g(isla, n):
    return {"isla": isla, "senadores": [{"nombre": f"Don Ficticio {i}", "formacion": "F", "votos": str(10 - i)}
                                        for i in range(n)]}


class ComoSeVota(unittest.TestCase):
    """Informe 50 y art. 166.1.a LOREG: «Los electores pueden dar su voto a un
    máximo de tres candidatos en las circunscripciones provinciales, dos en Gran
    Canaria, Mallorca, Tenerife, Ceuta y Melilla, y uno en las restantes
    circunscripciones insulares.» Los senadores que salen, de los datos."""

    def test_provincial(self):
        self.assertEqual(sn.como_se_vota("Albacete", [_g(None, 4)]),
                         "Cada votante marca hasta tres nombres; salen los cuatro más votados.")

    def test_ceuta_y_melilla_dos(self):
        for c in ("Ceuta", "Melilla"):
            self.assertEqual(sn.como_se_vota(c, [_g(None, 2)]),
                             "Cada votante marca hasta dos nombres; salen los dos más votados.")

    def test_islas_mayores_dos_y_menores_uno(self):
        for isla in ("GRAN CANARIA", "MALLORCA", "TENERIFE"):
            self.assertEqual(sn.votos_maximos("x", isla), 2)
        for isla in ("MENORCA", "IBIZA", "EIVISSA", "FORMENTERA", "FUERTEVENTURA", "LANZAROTE", "LA PALMA", "LA GOMERA",
                     "EL HIERRO"):
            self.assertEqual(sn.votos_maximos("x", isla), 1)

    def test_tenerife(self):
        g = [_g("TENERIFE", 3), _g("LA PALMA", 1), _g("LA GOMERA", 1), _g("EL HIERRO", 1)]
        self.assertEqual(sn.islas_texto(g),
                         "Aquí se vota por islas: 3 senadores en Tenerife y 1 en La Palma, La Gomera y El Hierro.")
        self.assertEqual(sn.como_se_vota("Santa Cruz de Tenerife", g),
                         "Aquí se vota por islas: 3 senadores en Tenerife y 1 en La Palma, La Gomera y El Hierro. "
                         "En Tenerife cada votante marca hasta dos nombres y salen los tres más votados; "
                         "en La Palma, La Gomera y El Hierro marca un nombre y sale el más votado.")

    def test_las_palmas(self):
        g = [_g("GRAN CANARIA", 3), _g("LANZAROTE", 1), _g("FUERTEVENTURA", 1)]
        self.assertEqual(sn.islas_texto(g),
                         "Aquí se vota por islas: 3 senadores en Gran Canaria y 1 en Lanzarote y Fuerteventura.")

    def test_baleares_desde_los_datos(self):
        # Del fichero ficticio leído como una proclamación: islas y senadores.
        g = _ficticio()["provincias"]["Balears (Illes)"]
        self.assertEqual(sn.islas_texto(g),
                         "Aquí se vota por islas: 3 senadores en Mallorca y 1 en Menorca, Eivissa y Formentera.")
        self.assertEqual(sn.como_se_vota("Balears (Illes)", g),
                         "Aquí se vota por islas: 3 senadores en Mallorca y 1 en Menorca, Eivissa y Formentera. "
                         "En Mallorca cada votante marca hasta dos nombres y salen los tres más votados; "
                         "en Menorca, Eivissa y Formentera marca un nombre y sale el más votado.")

    def test_ibiza_y_formentera_juntas_ya_no(self):
        # LO 2/2026: una proclamación con «EIVISSA-FORMENTERA» (la de 2023) ya
        # no casa con la ley vigente y Baleares no se publica.
        g = [_g("MALLORCA", 3), _g("MENORCA", 1), _g("EIVISSA-FORMENTERA", 1)]
        self.assertIn("islas leídas", sn._comprobar("Balears (Illes)", g))
        g = [_g("MALLORCA", 3), _g("MENORCA", 1), _g("IBIZA", 1), _g("FORMENTERA", 1)]
        self.assertEqual(sn._comprobar("Balears (Illes)", g), "")
        self.assertIn("2 senadores", sn._comprobar("Balears (Illes)", g[:3] + [_g("FORMENTERA", 2)]))

    def test_sale_de_los_datos_no_fijo(self):
        # Si la proclamación trae otro número de senadores, la frase cambia.
        self.assertIn("salen los dos más votados", sn.como_se_vota("Soria", [_g(None, 2)]))
        self.assertIn("2 senadores en Tenerife", sn.islas_texto([_g("TENERIFE", 2), _g("EL HIERRO", 1)]))
        self.assertEqual(sn.islas_texto([_g(None, 4)]), "")

    def test_en_el_bloque(self):
        h = build._bloque_senadores(_ficticio(), el.circ_congreso("Santa Cruz de Tenerife"))
        self.assertIn('<p class="sen-como">Aquí se vota por islas: 3 senadores en Tenerife y 1 en La Palma, '
                      'La Gomera y El Hierro.', h)
        self.assertLess(h.index("sen-como"), h.index("<h3>TENERIFE</h3>"))
        h = build._bloque_senadores(_ficticio(), "Soria")
        self.assertIn('<p class="sen-como">Cada votante marca hasta tres nombres; salen los cuatro más votados.</p>', h)

    def test_css(self):
        css = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")
        for sel, cuerpo in re.findall(r"([^{}]+)\{([^}]*)\}", css):
            if "sen-como" in sel:
                self.assertNotIn("underline", cuerpo)
                self.assertNotIn("border", cuerpo)
                self.assertNotIn("background", cuerpo)


def _paginas_elecciones(senadores, resultados):
    escritas = {}

    def suelta(pl, carpeta, nombre, frag):
        escritas[nombre] = frag["CUERPO"]
    h = {"pagina_suelta": suelta, "plantilla": "<footer>" + el.LEMA_IA + "</footer>",
         "site_url": "https://terceracamara.es/", "carpeta": pathlib.Path(tempfile.gettempdir()),
         "jsonld_script": lambda xs: "", "nombre": build.nombre_circunscripcion, "slug": build._slug_txt,
         "resultados": resultados, "senadores": senadores}
    el.generar_paginas(h, el.cargar(), [])
    return escritas


def _resultados_ficticios():
    import importlib.util
    spec = importlib.util.spec_from_file_location("trf", RAIZ / "tests" / "test_resultados_29n.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m._ficticio()


class Salto(unittest.TestCase):
    """«Tus senadores ↓» junto a «Resultados oficiales ↓», en las páginas de
    /elecciones/2026/. El bloque está en la ficha de provincia de /diputados/,
    así que el enlace lleva a esa ficha y a su ancla. Solo con datos."""

    @classmethod
    def setUpClass(cls):
        cls.rof = _resultados_ficticios()          # Albacete y Soria
        cls.ambos = _paginas_elecciones(_ficticio(), cls.rof)
        cls.solo_sen = _paginas_elecciones(_ficticio(), None)
        cls.nada = _paginas_elecciones(None, None)

    def _salto(self, slug):
        return f'<a href="/diputados/provincia-{slug}.html#tus-senadores">Tus senadores&nbsp;↓</a>'

    def test_junto_a_resultados(self):
        c = self.ambos["soria.html"]
        self.assertTrue(c.startswith('<p class="rof-salto"><a href="#resultados">Resultados oficiales&nbsp;↓</a> '
                                     '<span class="rof-sep" aria-hidden="true">·</span> ' + self._salto("soria")))
        self.assertEqual(c.count("Tus senadores&nbsp;↓"), 1)
        self.assertLess(c.index("Tus senadores"), c.index('class="rof-reparto"'))

    def test_solo_senadores_sin_resultados(self):
        c = self.ambos["ceuta.html"]
        self.assertTrue(c.startswith('<p class="rof-salto">' + self._salto("ceuta") + "</p>"))
        self.assertNotIn("Resultados oficiales&nbsp;↓", c)
        self.assertTrue(self.solo_sen["s-c-tenerife.html"].startswith(
            '<p class="rof-salto">' + self._salto("s-c-tenerife") + "</p>"))

    def test_solo_con_datos(self):
        c = self.ambos["albacete.html"]                      # resultados sí, senadores no
        self.assertIn("Resultados oficiales&nbsp;↓", c)
        self.assertNotIn("Tus senadores", c)
        con = sorted(n for n, c in self.solo_sen.items() if "Tus senadores&nbsp;↓" in c)
        self.assertEqual(con, ["balears-illes.html", "ceuta.html", "s-c-tenerife.html", "soria.html"])
        for n, c in self.nada.items():
            self.assertNotIn("Tus senadores", c, n)
            self.assertNotIn("rof-salto", c, n)

    def test_el_ancla_existe_en_la_ficha(self):
        # La ficha de provincia a la que apunta lleva el bloque con ese id.
        for prov_cong, slug in (("Soria", "soria"), ("Ceuta", "ceuta"), ("S/C Tenerife", "s-c-tenerife")):
            self.assertEqual(build._slug_txt(prov_cong), slug)
            self.assertIn('id="tus-senadores"', build._bloque_senadores(_ficticio(), prov_cong))
        self.assertEqual(sn.ANCLA, "tus-senadores")

    def test_mismo_estilo_sin_subrayado(self):
        css = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")
        reglas = [sel for sel, cuerpo in re.findall(r"([^{}]+)\{([^}]*)\}", css)
                  if ".rof-salto a" in sel and "text-decoration:none" in cuerpo.replace(" ", "")]
        self.assertTrue(reglas)
        for estado in (":hover", ":focus", ":focus-visible", ":active"):
            self.assertIn(f".rof-salto a{estado}", reglas[0])


class Eleccion(unittest.TestCase):
    """La elección que se cita sale del título de la proclamación cargada; nada
    de «29-N» fijo."""

    def _bloque(self, titulo):
        d = _ficticio()
        d["fuente"] = {**d["fuente"], "titulo": titulo}
        return build._bloque_senadores(d, "Soria")

    def test_otra_eleccion_sin_29n(self):
        h = self._bloque("Resolución de 30 de agosto de 2023, de la Presidencia de la Junta Electoral Central, por "
                         "la que se publica el resumen de los resultados de las elecciones al Congreso de los "
                         "Diputados y al Senado convocadas por Real Decreto 400/2023, de 29 de mayo, y celebradas "
                         "el 23 de julio de 2023, conforme a las actas")
        self.assertNotIn("29-N", h)
        self.assertNotIn("29 de noviembre", h)
        self.assertIn("por Soria en las elecciones generales del 23 de julio de 2023, tal como", h)

    def test_la_del_29n_si_la_cita(self):
        h = self._bloque("Resolución FICTICIA … convocadas por Real Decreto 806/2026, de 5 de octubre, y celebradas "
                         "el 29 de noviembre de 2026, conforme a las actas")
        self.assertIn("en las elecciones generales del 29 de noviembre de 2026, tal como", h)

    def test_sin_fecha_no_se_supone(self):
        h = self._bloque("Resolución FICTICIA sin fecha de elección (Real Decreto 806/2026)")
        self.assertIn("Senadores proclamados electos por Soria, tal como", h)
        self.assertNotIn("29-N", h)

    def test_ningun_29n_fijo_en_el_modulo(self):
        src = (RAIZ / "senadores.py").read_text(encoding="utf-8")
        self.assertNotIn("del 29-N", src)


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
