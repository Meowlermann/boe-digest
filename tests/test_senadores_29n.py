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
FUENTE = {"id": "BOE-A-2099-00000", "titulo": "Resolución FICTICIA de prueba",
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


if __name__ == "__main__":
    unittest.main()
