"""Pruebas del resumen semanal (semana.py), de su versión para correo
(tools/semana_email.py) y de la comprobación (i) de verificar.py. Sin red: una
semana de prueba (la 40 de 2026, del 28-9 al 4-10) montada en una carpeta
temporal con la forma real de cada fichero.
"""
import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

RAIZ_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_REPO))
sys.path.insert(0, str(RAIZ_REPO / "tools"))

import congreso_datos as cd  # noqa: E402
import nombramientos as nb  # noqa: E402
import preguntas as pq  # noqa: E402
import respuestas as rp  # noqa: E402
import semana  # noqa: E402
import semana_email  # noqa: E402
import tramitacion as tr  # noqa: E402
import verificar as v  # noqa: E402

PP, PSOE = cd.COD_GRUPO["GP"], cd.COD_GRUPO["GS"]
LUNES = dt.date(2026, 10, 5)          # día del pase que congela la semana 40


def _escribir(ruta: pathlib.Path, datos) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")


def montar(raiz: pathlib.Path) -> None:
    _escribir(raiz / "data" / "2026-09-29.json", {"id": "2026-09-29", "boe": {
        "fechaISO": "2026-09-29", "stories": [
            {"ref": "BOE-A-2026-1", "headline": "LEY DE PRUEBA", "url": "https://www.boe.es/x1",
             "titulo_oficial": "Ley 4/2026, de 28 de septiembre, de prueba."},
            {"ref": "BOE-A-2026-2", "headline": "UNA ORDEN",
             "titulo_oficial": "Orden ABC/1/2026, de 1 de septiembre, sin rango de ley."}]}})
    _escribir(raiz / "state" / "redaccion.json", {"piezas": {"BOE-A-2026-1": {"titular": "Titular de Gemini"}}})
    det = {
        "u1": {"f": "2026-09-30", "s": 202, "n": 8, "t": "Mociones", "a": "Moción ajustada", "tot": [171, 170, 6, 3],
               "g": {"GP": [1, 0, 0, 0], "GS": [0, 2, 0, 0]}, "v": "SNS"},
        "u2": {"f": "2026-10-01", "s": 203, "n": 1, "t": "Dictámenes", "a": "Votación holgada", "tot": [300, 40, 0, 10],
               "g": {"GP": [1, 0, 0, 0], "GS": [2, 0, 0, 0]}, "v": "SSS"},
        "u0": {"f": "2026-09-01", "s": 190, "n": 1, "t": "Anterior", "a": "Fuera de la semana", "tot": [1, 0, 0, 0],
               "g": {}, "v": ""},
    }
    _escribir(raiz / "state" / "congreso.json", {
        "detalle": det, "det_nombres": ["ana", "luis", "eva"],
        "censo": {"ana": {"natural": "Ana Pérez", "slug": "ana-perez", "grupo": PP},
                  "luis": {"natural": "Luis Gil", "slug": "luis-gil", "grupo": PSOE},
                  "eva": {"natural": "Eva Ruiz", "slug": "eva-ruiz", "grupo": PSOE}}})
    _escribir(raiz / "state" / "respuestas" / "2026.json", {"esquema": 1, "sesiones": {}, "escritas": {}, "orales": {
        "180/000001": {"s": "2026-09-30", "h": "09:10", "a": "Ana Pérez", "g": "GP", "t": "¿Va a dimitir?",
                       "gob": "Pedro Sánchez Pérez-Castejón", "cargo": "Presidente del Gobierno"},
        "180/000002": {"s": "2026-09-30", "h": "09:00", "a": "Luis Gil", "g": "GS", "t": "¿Qué hará el ministerio?",
                       "gob": "Fernando Grande-Marlaska Gómez", "cargo": "Ministro del Interior"},
        "180/000003": {"s": "2026-09-23", "a": "X", "t": "Otra semana", "cargo": "Ministro del Interior"}}})
    _escribir(raiz / "state" / "preguntas_escritas.json", {"esquema": 1, "listado": {"completo": True}, "exp": {
        "184/000001": {"a": ["Pérez, Ana"], "g": ["GP"], "t": "Contestada en la semana", "pr": "2026-06-01",
                       "p": "2026-06-10", "c": "2026-10-01", "lim": "2026-07-10"},
        "184/000002": {"a": ["Gil, Luis"], "g": ["GS"], "t": "Pendiente vencida", "pr": "2026-08-01",
                       "p": "2026-09-01", "c": None, "lim": "2026-10-02"},
        "184/000003": {"a": ["Gil, Luis"], "g": ["GS"], "t": "Contestada después del domingo", "pr": "2026-08-01",
                       "p": "2026-09-01", "c": "2026-10-06", "lim": "2026-09-20"},
        "184/000004": {"a": ["Gil, Luis"], "g": ["GS"], "t": "Plazo vigente", "pr": "2026-09-01",
                       "p": "2026-09-20", "c": None, "lim": "2026-10-20"}}})
    _escribir(raiz / "state" / "tramitacion.json", {"version": tr.VERSION, "ini": {
        "121/000099": {"t": "Proyecto de Ley de prueba.", "tipo": "Proyecto de ley",
                       "pasos": [["Comisión · Enmiendas", "2026-09-29", "2026-10-15"],
                                 ["Comisión · Publicación", "2026-09-01", "2026-09-29"]],
                       "plazos": [["2026-09-30", "18:00", "De enmiendas"],
                                  ["2026-10-07", "18:00", "Ampliación de enmiendas al articulado"]]}}})
    _escribir(raiz / "state" / "nombramientos.json", {"version": nb.VERSION, "dias": {}, "registros": {
        "BOE-A-2026-10": {"acto": "nombramiento", "cargo": "Delegado del Gobierno", "clave": "jose x",
                          "persona": "José X", "fecha": "2026-09-30", "rango": "Real Decreto",
                          "emisor": "PRESIDENCIA", "url": "https://www.boe.es/n10"},
        "BOE-A-2026-11": {"acto": "nombramiento", "cargo": "Profesor Titular", "clave": "marta y",
                          "persona": "Marta Y", "fecha": "2026-10-01", "rango": "Resolución",
                          "url": "https://www.boe.es/n11"}}})


class Semana(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.raiz = pathlib.Path(self.tmp.name)
        montar(r)
        rp._CACHE.clear()
        self.parches = [
            mock.patch.object(semana, "ROOT", r), mock.patch.object(semana, "DATA", r / "data"),
            mock.patch.object(semana, "DIR", r / "data" / "semanas"),
            mock.patch.object(pq, "ESTADO_ESCRITAS", r / "state" / "preguntas_escritas.json"),
            mock.patch.object(rp, "DIR", r / "state" / "respuestas"),
            mock.patch.object(tr, "ESTADO", r / "state" / "tramitacion.json"),
            mock.patch.object(nb, "ESTADO", r / "state" / "nombramientos.json"),
        ]
        for p in self.parches:
            p.start()

    def tearDown(self):
        for p in self.parches:
            p.stop()
        rp._CACHE.clear()
        self.tmp.cleanup()

    def test_fechas(self):
        self.assertEqual(semana.lunes_de("2026-W40"), dt.date(2026, 9, 28))
        self.assertEqual(semana.lunes_de("2026-S40"), dt.date(2026, 9, 28))
        self.assertEqual(semana.ultima_cerrada(LUNES), "2026-S40")
        self.assertEqual(semana.ultima_cerrada(dt.date(2026, 10, 4)), "2026-S39")
        self.assertEqual(v.semana_cerrada("2026-10-05"), "2026-S40")
        self.assertEqual(semana.rango_texto(dt.date(2026, 9, 28), dt.date(2026, 10, 4)),
                         "del 28 de septiembre al 4 de octubre de 2026")
        self.assertEqual(semana.rango_texto(dt.date(2026, 10, 5), dt.date(2026, 10, 11)),
                         "del 5 al 11 de octubre de 2026")

    def test_secciones(self):
        s = semana.construir("2026-W40", LUNES)
        self.assertEqual(s["errores"], [])
        sec = s["secciones"]
        self.assertEqual([n["ref"] for n in sec["normas"]], ["BOE-A-2026-1"])
        self.assertEqual(sec["normas"][0]["editorial"], "Titular de Gemini")
        aj = sec["votaciones"]["ajustadas"]
        self.assertEqual([x["margen"] for x in aj], [1, 260])
        dis = sec["votaciones"]["disidencias"]
        self.assertEqual(len(dis), 1)
        self.assertEqual([(p["nombre"], p["voto"], p["voto_grupo"]) for p in dis[0]["personas"]],
                         [("Eva Ruiz", "S", "N")])
        pr = sec["preguntas"]
        self.assertEqual([o["exp"] for o in pr["orales"]], ["180/000001", "180/000002"])   # presidente primero
        self.assertEqual([q["exp"] for q in pr["contestadas"]], ["184/000001"])
        # Vencida al domingo: la 2 (sin contestar) y la 3 (contestada el lunes siguiente).
        self.assertEqual(pr["pendientes"]["total"], 2)
        self.assertEqual(pr["pendientes"]["vencieron_en_la_semana"], 1)
        clases = sorted((t["clase"], t["f"]) for t in sec["tramitacion"])
        self.assertEqual(clases, [("ampliacion", "2026-09-30"), ("paso", "2026-09-29")])
        self.assertEqual(sec["nombramientos"]["total"], 2)
        self.assertEqual([n["persona"] for n in sec["nombramientos"]["lista"]], ["José X"])
        self.assertEqual(sec["nombramientos"]["resto"], 1)
        self.assertEqual((sec["cifra"]["regla"], sec["cifra"]["valor"]), (1, 1))
        self.assertIn("decidió", sec["cifra"]["texto"])

    def test_semana_antigua_sin_pendientes(self):
        """Reconstruida meses después, no da pendientes (el estado se poda)."""
        s = semana.construir("2026-W40", dt.date(2027, 1, 10))
        self.assertNotIn("pendientes", s["secciones"].get("preguntas", {}))

    def test_votaciones_incompletas_no_se_resumen(self):
        datos = json.loads((self.raiz / "state" / "congreso.json").read_text())
        del datos["detalle"]["u0"]
        _escribir(self.raiz / "state" / "congreso.json", datos)
        self.assertNotIn("votaciones", semana.construir("2026-W40", LUNES)["secciones"])

    def test_cifra_sin_votacion_ajustada(self):
        sec = {"votaciones": {"ajustadas": [{"margen": 50}]},
               "preguntas": {"pendientes": {"total": 7}}}
        self.assertEqual(semana._cifra(sec)["regla"], 2)
        self.assertEqual(semana._cifra({"normas": [1, 2]})["valor"], 2)
        self.assertIsNone(semana._cifra({}))

    def test_asegurar_idempotente(self):
        with mock.patch.object(semana, "PRIMERA", "2026-W39"):
            hechas = semana.asegurar(LUNES, log=lambda *_: None)
            self.assertEqual(hechas, ["2026-S40"])          # la 39 no tiene ediciones
            ruta = self.raiz / "data" / "semanas" / "2026-S40.json"
            antes = ruta.read_text()
            self.assertEqual(semana.asegurar(LUNES, log=lambda *_: None), [])
            # Otro día de la misma semana: tampoco cambia (congelada).
            self.assertEqual(semana.asegurar(dt.date(2026, 10, 8), log=lambda *_: None), [])
            self.assertEqual(ruta.read_text(), antes)

    def test_paginas_feed_y_correo(self):
        with mock.patch.object(semana, "PRIMERA", "2026-W40"):
            semana.asegurar(LUNES, log=lambda *_: None)
        escritas, feeds = {}, {}

        def pagina(_plantilla, carpeta, nombre, frag):
            escritas[nombre] = frag

        import build
        salidas = semana.generar_paginas({
            "esc_html": build.esc_html, "esc_attr": build.esc_attr, "fmt_date_es": build.fmt_date_es,
            "jsonld_script": build.jsonld_script, "pagina_suelta": pagina, "plantilla": "",
            "site_url": "https://terceracamara.es/", "carpeta": self.raiz / "semana", "raiz": self.raiz,
            "escribir": lambda ruta, texto: feeds.__setitem__(ruta.name, texto),
            "registrar_feed": lambda *a: None})
        self.assertEqual([x["url"] for x in salidas], ["https://terceracamara.es/semana/2026-S40.html",
                                                       "https://terceracamara.es/semana/"])
        self.assertEqual(escritas["2026-S40.html"]["TITLE"],
                         "La semana en las Cortes y el BOE (del 28 de septiembre al 4 de octubre de 2026)")
        self.assertIn('"@type":"Report"', escritas["2026-S40.html"]["JSONLD"])
        cuerpo = escritas["2026-S40.html"]["CUERPO"]
        self.assertIn("«¿Va a dimitir?»", cuerpo)
        self.assertIn("No se presenta como un incumplimiento", cuerpo)
        # La norma no tiene página en esta raíz de prueba: enlaza a la fuente oficial.
        self.assertIn('href="https://www.boe.es/x1"', cuerpo)
        self.assertEqual(v.problemas_canal(feeds["feed.xml"]), [])

        sem = semana.cargar("2026-S40")
        correo = semana_email.html_correo(sem, self.raiz, baja="{$unsubscribe}")
        self.assertNotIn("<script", correo.lower())
        self.assertNotIn("<style", correo.lower())
        self.assertIn("max-width:600px", correo)
        self.assertIn("<table", correo)
        self.assertIn("{$unsubscribe}", correo)
        texto = semana_email.texto_correo(sem, self.raiz)
        self.assertIn("LA CIFRA DE LA SEMANA", texto)
        self.assertIn("https://www.boe.es/x1", texto)
        # Párrafos envueltos a 72 columnas; solo las direcciones pueden ser más largas.
        self.assertTrue(all(len(l) <= 72 for l in texto.splitlines() if "http" not in l))


class ComprobacionSemana(unittest.TestCase):
    def test_falta_y_existe(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = pathlib.Path(d)
            h = v.comprobar_semana(raiz, "2026-10-05")
            self.assertEqual(len(h), 1)
            self.assertEqual(h[0]["nivel"], v.GRAVE)
            self.assertIn("2026-S40", h[0]["detalle"])
            (raiz / "semana").mkdir()
            (raiz / "semana" / "2026-S40.html").write_text("<html></html>")
            self.assertEqual(v.comprobar_semana(raiz, "2026-10-05"), [])
            self.assertEqual(v.comprobar_semana(raiz, "2026-10-11"), [])   # domingo: sigue la 40

    def test_solo_en_la_salud_diaria(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = pathlib.Path(d)
            (raiz / "tools").mkdir()
            ci = v.ejecutar(raiz, "ci", "2026-10-05")
            diario = v.ejecutar(raiz, "diario", "2026-10-05")
        self.assertFalse(any(h["comprobacion"] == "semana" for h in ci["hallazgos"]))
        self.assertTrue(any(h["comprobacion"] == "semana" for h in diario["hallazgos"]))


if __name__ == "__main__":
    unittest.main()
