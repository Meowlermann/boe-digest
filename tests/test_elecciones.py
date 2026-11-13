"""Tanda E2: parser determinista de escaños (RD 806/2026), candidaturas al
Congreso (BOE-A-2026-23103) y su corrección (BOE-A-2026-23383); cruce con los
diputados salientes y páginas /elecciones/2026/. Sin red."""
import pathlib
import re
import sys
import tempfile
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import elecciones as el  # noqa: E402

E = "\u2003"


def doc(parrafos: str) -> str:
    return f'<html><body><div id="textoxslt">{parrafos}</div></body></html>'


def p(clase, texto):
    return f'<p class="{clase}">{texto}</p>'


CANDIDATURAS = doc(
    p("centro_negrita", "JUNTA ELECTORAL DE HUESCA")
    + p("parrafo_2", "La Junta Electoral Provincial de Huesca… ha acordado proclamar…")
    + p("centro_negrita", "JUNTA ELECTORAL DE HUESCA")
    + p("centro_cursiva", "CONGRESO DE LOS DIPUTADOS")
    + p("centro_redonda", "1. PARTIDO SOCIALISTA OBRERO ESPAÑOL (PSOE)")
    + p("parrafo_2", f"1.{E}Ana Uno Dos.") + p("parrafo", "2. Bea Tres (CHA).") + p("parrafo", "3. Carla (Cari) Cuatro.")
    + p("parrafo_2", "Suplentes:") + p("parrafo_2", "1. Dora Cinco (Independiente).")
    + p("centro_redonda", "2. FALANGE ESPAÑOLA DE LAS J.O.N.S. (FE de las JONS)")
    + p("parrafo_2", "No proclamada.")
    + p("centro_redonda", "3. SE ACABÓ LA FIESTA (SALF)")
    + p("parrafo_2", "1. Eva Seis.") + p("parrafo", "2. Milagros Roca Pérez.") + p("parrafo", "3. Gil Ocho.")
    + p("centro_redonda", "4. SENADO DE PROGRESO (SDP (PSOE-IU-MS))")
    + p("parrafo_2", "1. Hugo Nueve.") + p("parrafo", "2. Ines Diez.") + p("parrafo", "3. Juan Once.")
    + p("centro_cursiva", "SENADO")
    + p("centro_redonda", "1. PARTIDO POPULAR (PP)") + p("parrafo_2", "1.") + p("parrafo", "Senador Uno.")
    + p("centro_negrita", "JUNTA ELECTORAL DE CEUTA")
    + p("centro_cursiva", "CONGRESO DE LOS DIPUTADOS")
    + p("centro_redonda", "1. PARTIDO POPULAR (PP)")
    + p("parrafo_2", "Titular:") + p("parrafo_2", "1. Kiko Doce.")
    + p("parrafo_2", "Suplente:") + p("parrafo_2", "1. Lola Trece.")
    + p("centro_negrita", "JUNTA ELECTORAL DE LAS PALMAS")
    + p("centro_cursiva", "CONGRESO DE LOS DIPUTADOS")
    + p("centro_redonda", "1. FRENTE OBRERO") + p("parrafo_2", "1. Mar Catorce.")
    + p("parrafo_2", "Circunscripción electoral: Lanzarote")
    + p("centro_cursiva", "SENADO")
    + p("centro_redonda", "1. VOX (VOX)") + p("parrafo_2", "1. Nadie Quince.")
    + '<dl><dt>Publicado en:</dt><dd>«BOE» núm. 273, de 3 de noviembre de 2026, páginas 1 a 9</dd></dl>')

RD = doc(
    p("parrafo", "Se convocan elecciones a ambas Cámaras, que se celebrarán el domingo 29 de noviembre de 2026.")
    + "<table><tr><th>Circunscripción</th><th>Diputados</th></tr>"
    "<tr><td>Huesca.</td><td>Tres.</td></tr><tr><td>Palmas (Las).</td><td>Uno.</td></tr>"
    "<tr><td>Ceuta.</td><td>Uno.</td></tr></table>"
    + '<dl><dt>Publicado en:</dt><dd>«BOE» núm. 248, de 6 de octubre de 2026, páginas 1 a 2</dd></dl>')

RD_ANT = doc(
    p("parrafo", "Se convocan elecciones a ambas Cámaras, que se celebrarán el domingo 23 de julio de 2023.")
    + "<table><tr><th>Circunscripción</th><th>Diputados</th></tr>"
    "<tr><td>Huesca</td><td>3</td></tr><tr><td>Palmas (Las)</td><td>2</td></tr>"
    "<tr><td>Ceuta</td><td>1</td></tr></table>"
    + '<dl><dt>Publicado en:</dt><dd>«BOE» núm. 128, de 30 de mayo de 2023, páginas 1 a 2</dd></dl>')

CORRECCION = doc(
    p("centro_negrita", "JUNTA ELECTORAL DE HUESCA")
    + p("centro_cursiva", "CONGRESO DE LOS DIPUTADOS")
    + p("parrafo_2", "En la candidatura:") + p("centro_redonda", f"3.{E}SE ACABÓ LA FIESTA (SALF)")
    + p("parrafo_2", "Donde dice:") + p("parrafo_2", f"«2.{E}Milagros Roca Pérez.»")
    + p("parrafo_2", "Debe decir:") + p("parrafo_2", f"«2.{E}Milagros Roca López.»")
    + p("parrafo_2", "En la candidatura") + p("parrafo_2", "Donde dice:")
    + p("centro_redonda", f"«4.{E}SENADO DE PROGRESO (SDP (PSOE-IU-MS) )»")
    + p("parrafo_2", "Debe decir:") + p("centro_redonda", f"«4.{E}SENADO DE PROGRESO (SDP)»")
    + p("parrafo_2", "En la candidatura:") + p("centro_redonda", "1. PARTIDO SOCIALISTA OBRERO ESPAÑOL (PSOE)")
    + p("parrafo_2", "Donde dice:") + p("parrafo_2", "«2. Bea Tres.»")
    + p("parrafo_2", "Debe decir:") + p("parrafo_2", "«2. Bea Tres Tres.»")
    + p("parrafo_2", "Donde dice:") + p("parrafo_2", "«2. Bea Tres (CHA).»")
    + p("parrafo_2", "Debe decir:") + p("parrafo_2", "«2. Bea Tres Tres.»")
    + p("centro_cursiva", "SENADO")
    + p("parrafo_2", "En la candidatura:") + p("centro_redonda", "1. PARTIDO POPULAR (PP)")
    + p("parrafo_2", "Donde dice:") + p("parrafo_2", "«1. Algo que no existe.»")
    + p("parrafo_2", "Debe decir:") + p("parrafo_2", "«1. Otra cosa.»")
    + '<dl><dt>Publicado en:</dt><dd>«BOE» núm. 278, de 7 de noviembre de 2026, páginas 1 a 2</dd></dl>')


class Numeros(unittest.TestCase):
    def test_letra(self):
        for t, n in (("Uno.", 1), ("Dos.", 2), ("Dieciséis.", 16), ("Treinta y dos.", 32),
                     ("Treinta y ocho.", 38), ("Once", 11), ("37", 37), ("4", 4)):
            self.assertEqual(el.numero_en_letra(t), n)
        with self.assertRaises(ValueError):
            el.numero_en_letra("Muchos.")


class Parser(unittest.TestCase):
    def test_rd(self):
        rd = el.parsear_rd(RD)
        self.assertEqual(rd["fecha_literal"], "domingo 29 de noviembre de 2026")
        self.assertEqual(rd["escanos"], [["Huesca", 3, "Tres"], ["Palmas (Las)", 1, "Uno"], ["Ceuta", 1, "Uno"]])

    def test_solo_congreso_y_junta_repetida(self):
        b = el.bloques_congreso(CANDIDATURAS)
        self.assertEqual(sorted(b), ["CEUTA", "HUESCA", "LAS PALMAS"])
        self.assertEqual(len(b["HUESCA"]), 4)          # el Senado no entra
        self.assertEqual(len(b["LAS PALMAS"]), 1)      # «Circunscripción electoral» no entra

    def test_estructura(self):
        b = el.bloques_congreso(CANDIDATURAS)
        psoe = el.estructurar(b["HUESCA"][0])
        self.assertEqual((psoe["orden"], psoe["nombre"], psoe["sigla"]), (1, "PARTIDO SOCIALISTA OBRERO ESPAÑOL", "PSOE"))
        # La sigla en mayúsculas tras el nombre se quita; apodos y notas con minúsculas, no.
        self.assertEqual(psoe["titulares"], ["Ana Uno Dos", "Bea Tres", "Carla (Cari) Cuatro"])
        self.assertEqual(psoe["suplentes"], ["Dora Cinco (Independiente)"])
        fe = el.estructurar(b["HUESCA"][1])
        self.assertFalse(fe["proclamada"])
        self.assertEqual(fe["titulares"], [])
        sdp = el.estructurar(b["HUESCA"][3])
        self.assertEqual((sdp["nombre"], sdp["sigla"]), ("SENADO DE PROGRESO", "SDP (PSOE-IU-MS)"))
        ceuta = el.estructurar(b["CEUTA"][0])
        self.assertEqual((ceuta["titulares"], ceuta["suplentes"]), (["Kiko Doce"], ["Lola Trece"]))
        fo = el.estructurar(b["LAS PALMAS"][0])
        self.assertEqual((fo["nombre"], fo["sigla"]), ("FRENTE OBRERO", ""))

    def test_numeracion_saltada_falla(self):
        with self.assertRaises(ValueError):
            el.estructurar(["1. X (X)", "1. Uno.", "3. Tres."])

    def test_publicacion(self):
        self.assertEqual(el.parsear_publicacion(CORRECCION),
                         {"literal": "BOE núm. 278, de 7 de noviembre de 2026", "fecha": "2026-11-07"})


class Correccion(unittest.TestCase):
    def setUp(self):
        self.b = el.bloques_congreso(CANDIDATURAS)
        self.c = el.parsear_correccion(CORRECCION)

    def test_parseo(self):
        self.assertEqual(len(self.c), 5)
        self.assertEqual(self.c[0]["candidatura"], "3. SE ACABÓ LA FIESTA (SALF)")
        self.assertIsNone(self.c[1]["candidatura"])
        self.assertEqual(self.c[4]["camara"], "otra")

    def test_aplica_congreso_y_registra(self):
        hechas = el.aplicar_correccion(self.b, self.c)
        self.assertEqual([h["estado"] for h in hechas], ["aplicada", "aplicada", "aplicada", "ya aplicada"])
        h = {el.estructurar(x)["orden"]: el.estructurar(x) for x in self.b["HUESCA"]}
        self.assertEqual(h[3]["titulares"][1], "Milagros Roca López")
        self.assertEqual(h[4]["sigla"], "SDP")
        self.assertEqual(h[1]["titulares"][1], "Bea Tres Tres")

    def test_ambigua_falla(self):
        b = {"HUESCA": [["1. X (X)", "1. Ana.", "Suplentes:", "1. Ana."]]}
        c = [{"junta": "HUESCA", "camara": "congreso", "candidatura": None,
              "donde": ["1. Ana."], "debe": ["1. Bea."]}]
        with self.assertRaises(ValueError):
            el.aplicar_correccion(b, c)

    def test_sin_encaje_falla(self):
        self.c[0]["donde"] = ["2. Nadie."]
        with self.assertRaises(ValueError):
            el.aplicar_correccion(self.b, self.c)

    def test_construir(self):
        d = el.construir(RD, CANDIDATURAS, CORRECCION, RD_ANT)
        self.assertEqual([c["circunscripcion"] for c in d["circunscripciones"]], ["Huesca", "Palmas (Las)", "Ceuta"])
        self.assertEqual(d["publicaciones"][el.ID_CORRECCION]["fecha"], "2026-11-07")
        self.assertEqual([c["escanos_anterior"] for c in d["circunscripciones"]], [3, 2, 1])
        self.assertEqual(el.anomalias(d), [])


class Juntas(unittest.TestCase):
    def test_nombres(self):
        circs = [c for c, _n, _l in el.parsear_rd(RD)["escanos"]] + [
            "Alicante/Alacant", "Araba/Álava", "Balears (Illes)", "Coruña (A)", "Rioja (La)",
            "Castellón/Castelló", "Valencia/València", "Santa Cruz de Tenerife"]
        for junta, circ in (("LAS PALMAS", "Palmas (Las)"), ("ALICANTE", "Alicante/Alacant"),
                            ("ÁLAVA", "Araba/Álava"), ("ILLES BALEARS", "Balears (Illes)"),
                            ("A CORUÑA", "Coruña (A)"), ("LA RIOJA", "Rioja (La)"),
                            ("CASTELLÓN", "Castellón/Castelló"), ("VALENCIA", "Valencia/València"),
                            ("SANTA CRUZ DE TENERIFE", "Santa Cruz de Tenerife"), ("HUESCA", "Huesca")):
            self.assertEqual(el.junta_a_circunscripcion(junta, circs), circ)
        self.assertEqual(el.circ_congreso("Santa Cruz de Tenerife"), "S/C Tenerife")


class DatosFijos(unittest.TestCase):
    """curated/elecciones_2026.json, generado con tools/elecciones_2026.py."""

    @classmethod
    def setUpClass(cls):
        cls.d = el.cargar()
        cls.c = {c["circunscripcion"]: c for c in cls.d["circunscripciones"]}

    def test_totales(self):
        self.assertEqual(len(self.d["circunscripciones"]), 52)
        self.assertEqual(sum(c["escanos"] for c in self.d["circunscripciones"]), 350)
        self.assertEqual(self.d["fecha_literal"], "domingo 29 de noviembre de 2026")
        self.assertEqual(self.c["Madrid"]["escanos"], 38)
        self.assertEqual(self.c["Soria"]["escanos"], 2)
        self.assertEqual(self.c["Ceuta"]["escanos"], 1)
        self.assertEqual(self.c["Melilla"]["escanos"], 1)

    def test_reparto_anterior(self):
        cambian = {c["circunscripcion"]: (c["escanos_anterior"], c["escanos"])
                   for c in self.d["circunscripciones"] if c["escanos_anterior"] != c["escanos"]}
        self.assertEqual(cambian, {"Madrid": (37, 38), "Cádiz": (9, 8)})
        self.assertEqual(sum(c["escanos_anterior"] for c in self.d["circunscripciones"]), 350)
        self.assertEqual(self.d["fuentes"]["rd_anterior"], "BOE-A-2023-12663")

    def test_listas_completas(self):
        self.assertEqual(el.anomalias(self.d), [])
        for c in self.d["circunscripciones"]:
            self.assertTrue(any(k["proclamada"] for k in c["candidaturas"]), c["circunscripcion"])
            ordenes = [k["orden"] for k in c["candidaturas"]]
            self.assertEqual(ordenes, list(range(1, len(ordenes) + 1)), c["circunscripcion"])

    def test_correcciones_del_congreso(self):
        self.assertEqual(len(self.d["correcciones_congreso"]), 9)

        def cand(circ, orden):
            return next(k for k in self.c[circ]["candidaturas"] if k["orden"] == orden)
        self.assertEqual(cand("Huesca", 5)["titulares"][1], "Milagros Roca López")
        self.assertEqual(cand("Rioja (La)", 5)["titulares"],
                         ["Francisco Castro Portolés", "María Eugenia Oleaga Muguerza",
                          "Gonzalo Alonso Alonso", "Lucía Sáenz Burgos"])
        self.assertEqual(cand("Rioja (La)", 5)["suplentes"], ["José Ángel Sáenz Díaz"])
        self.assertEqual((cand("Navarra", 1)["nombre"], cand("Navarra", 1)["sigla"]),
                         ("EUSKAL HERRIA BILDU", "EH BILDU"))
        self.assertEqual(cand("Navarra", 8)["suplentes"][1], "Noelia González Salmerón")   # es suplente
        self.assertEqual(cand("Navarra", 11)["nombre"], "FRENTE AMPLIO-FRONTE ZABALA")
        self.assertEqual(cand("Tarragona", 7)["titulares"][0], "Ester Roca Domedel")
        self.assertEqual(cand("Teruel", 1)["titulares"][0], "Herminio Rufino Sancho Íñiguez")
        self.assertEqual(cand("Valencia/València", 3)["titulares"][2], "Jose Francisco Domenech Gomis")


class Cruce(unittest.TestCase):
    def setUp(self):
        self.d = el.construir(RD, CANDIDATURAS, CORRECCION, RD_ANT)

    def test_exacto_si_parecido_no(self):
        fichas = [{"natural": "Ana Uno Dos", "circunscripcion": "Huesca", "slug": "ana"},
                  {"natural": "Eva María Seis", "circunscripcion": "Huesca", "slug": "eva"},
                  {"natural": "Kiko Doce", "circunscripcion": "Madrid", "slug": "kiko"},
                  {"natural": "Carla Cuatro", "circunscripcion": "Huesca", "slug": "carla"}]
        s = el.cruzar_salientes(self.d, fichas)
        self.assertEqual([x["ficha"]["slug"] for x in s["Huesca"]], ["ana", "carla"])
        self.assertEqual([x["ficha"]["slug"] for x in s["Ceuta"]], ["kiko"])   # exacto, otra provincia

    def test_nombre_repetido_no_se_marca(self):
        fichas = [{"natural": "Ana Uno Dos", "circunscripcion": "Huesca", "slug": "a1"},
                  {"natural": "Ana Uno Dos", "circunscripcion": "Ceuta", "slug": "a2"}]
        self.assertEqual(el.cruzar_salientes(self.d, fichas), {})


class Render(unittest.TestCase):
    def setUp(self):
        self.d = el.construir(RD, CANDIDATURAS, CORRECCION, RD_ANT)

    def test_bloque_ficha(self):
        fichas = [{"natural": "Ana Uno Dos", "circunscripcion": "Huesca", "slug": "ana"}]
        s = el.cruzar_salientes(self.d, fichas)
        html = el.bloque_ficha(self.d, "Huesca", s["Huesca"], "Huesca", "huesca")
        self.assertIn("Elecciones 29-N", html)
        self.assertIn("domingo 29 de noviembre de 2026", html)
        self.assertIn(el.url_boe(el.ID_RD), html)
        self.assertIn(el.url_boe(el.ID_CANDIDATURAS), html)
        self.assertIn(el.url_boe(el.ID_CORRECCION), html)
        self.assertIn("elige <b>3</b> diputados", html)
        self.assertNotIn("FALANGE", html)                      # no proclamada: fuera del bloque
        self.assertLess(html.index("PSOE"), html.index("SALF"))  # orden del BOE
        self.assertIn('href="ana.html"', html)
        self.assertIn('/elecciones/2026/huesca.html', html)
        self.assertNotIn("tarjeta", html)
        self.assertNotIn("BOE BOE-", html)
        self.assertEqual(re.sub(r"<[^>]+>", "", html).count(el.ID_CANDIDATURAS), 1)   # visible, una vez
        self.assertNotIn("reparto cambia", html)               # Huesca: 3 y 3
        self.assertIn("Sin IA", html)

    def test_reparto_que_cambia_con_las_dos_cifras(self):
        html = el.bloque_ficha(self.d, "Palmas (Las)", [], "Las Palmas", "palmas-las")
        self.assertIn("elige <b>1</b> diputado (", html)      # singular
        self.assertIn("el 29-N hay 1 escaño en juego, frente a los 2 de la legislatura que acaba", html)
        self.assertIn(el.url_boe(el.ID_RD_ANTERIOR), html)

    def test_sigla_aparte_solo_si_aporta(self):
        k = {"nombre": "PODEMOS", "sigla": "PAZ,CASA Y TRABAJO"}
        self.assertIn("Sigla en el BOE: PAZ,CASA Y TRABAJO", el._sigla_aparte(k))
        self.assertEqual(el._sigla_aparte({"nombre": "VOX", "sigla": "VOX"}), "")
        self.assertEqual(el._sigla_aparte({"nombre": "FRENTE OBRERO", "sigla": ""}), "")
        self.assertEqual(el._corto({"nombre": "PARTIDO SOCIALISTA OBRERO ESPAÑOL", "sigla": "PSOE"}), "PSOE")
        self.assertEqual(el._corto(k), "PODEMOS")

    def test_paginas(self):
        escritas, plantillas = {}, {}

        def suelta(pl, carpeta, nombre, frag):
            escritas[nombre] = frag
            plantillas[nombre] = pl
        h = {"pagina_suelta": suelta,
             "plantilla": "<footer><b>" + el.LEMA_IA + "</b></footer>", "site_url": "https://terceracamara.es/", "carpeta": pathlib.Path(tempfile.gettempdir()),
             "jsonld_script": lambda xs: str(xs), "nombre": lambda c: c, "slug": lambda c: c.lower().split()[0]}
        salidas = el.generar_paginas(h, self.d, [])
        self.assertEqual(len(salidas), 4)
        self.assertEqual(salidas[-1]["url"], "https://terceracamara.es/elecciones/2026/")
        self.assertTrue(all(s["lastmod"] == "2026-11-07" for s in salidas))
        hu = escritas["huesca.html"]["CUERPO"]
        self.assertIn("Milagros Roca López", hu)
        self.assertIn("«No proclamada»", hu)
        self.assertNotIn("<a", escritas["index.html"]["FUENTE"])   # el pie no lleva enlaces subrayados
        self.assertIn("huesca.html", escritas["index.html"]["CUERPO"])
        for nombre, pl in plantillas.items():                       # sin el lema de IA
            self.assertNotIn("redactados con IA", pl, nombre)
            self.assertIn(el.SIN_IA, pl, nombre)
        hub = escritas["index.html"]["CUERPO"]
        self.assertIn("Dónde cambia el reparto respecto a 2023", hub)
        self.assertIn("(en 2023, 2)", hub)
        self.assertEqual(re.sub(r"<[^>]+>", "", hub).count(el.ID_CANDIDATURAS), 1)
        self.assertNotIn("Fuente", escritas["index.html"]["FUENTE"])   # la fuente, una sola vez


class Singular(unittest.TestCase):
    def test_entradilla_de_ficha_con_un_diputado(self):
        src = (RAIZ / "build.py").read_text(encoding="utf-8")
        self.assertIn('f"El diputado por {prov} en la {LEGISLATURA_DISUELTA}, con su actividad y sus votos."', src)


if __name__ == "__main__":
    unittest.main()
