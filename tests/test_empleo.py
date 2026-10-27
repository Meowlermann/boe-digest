"""TC-013: empleo público v1 (BOE II.B) con tres sumarios reales guardados
(27, 24 y 20 de octubre de 2026; solo la sección II.B, de la API de datos
abiertos)."""
import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import empleo as em  # noqa: E402
import provincias as pv  # noqa: E402

DATOS = RAIZ / "tests" / "datos_empleo"
FECHAS = {"20261027": dt.date(2026, 10, 27), "20261024": dt.date(2026, 10, 24),
          "20261020": dt.date(2026, 10, 20)}


def sumario(clave):
    return json.loads((DATOS / f"sumario-{clave}.json").read_text(encoding="utf-8"))


def ids_crudos(datos):
    """Identificadores II.B contados a mano sobre el JSON, sin pasar por el módulo."""
    ids = []

    def recorrer(x):
        if isinstance(x, dict):
            if "identificador" in x and "titulo" in x:
                ids.append(x["identificador"])
            for v in x.values():
                recorrer(v)
        elif isinstance(x, list):
            for v in x:
                recorrer(v)
    for d in datos["diario"]:
        recorrer([s for s in d["seccion"] if s["codigo"] == "2B"])
    return ids


def h_prueba(carpeta, hoy="2026-10-27"):
    escritos = {}

    def pagina_suelta(_pl, carpeta, nombre, frag):
        carpeta.mkdir(exist_ok=True)
        html = "\n".join(f"{k}={v}" for k, v in frag.items())
        (carpeta / nombre).write_text(html, encoding="utf-8")

    def escribir(ruta, texto):
        escritos[ruta.name] = texto
        ruta.write_text(texto, encoding="utf-8")

    return {"esc_html": lambda s: str(s), "esc_attr": lambda s: str(s),
            "fmt_date_es": lambda s: s, "jsonld_script": lambda o: json.dumps(o, ensure_ascii=False),
            "pagina_suelta": pagina_suelta, "plantilla": "", "site_url": "https://terceracamara.es/",
            "carpeta": carpeta, "escribir": escribir, "hoy": hoy,
            "ref_provincias": pv.cargar_referencia()["provincias"]}, escritos


class TestExtraer(unittest.TestCase):
    def test_cien_por_cien_de_la_iib(self):
        for clave, fecha in FECHAS.items():
            with self.subTest(clave):
                datos = sumario(clave)
                crudos = ids_crudos(datos)
                self.assertGreater(len(crudos), 20)
                regs = em.extraer(em.entradas_de_sumario(datos), fecha, log=lambda *_: None)
                self.assertEqual(sorted(r["id"] for r in regs), sorted(set(crudos)))
                for r in regs:
                    self.assertTrue((r.get("url") or em.url_boe(r["id"])).startswith("https://www.boe.es/"))
                    self.assertEqual(r["fecha"], fecha.isoformat())

    def test_titulos_repetidos_no_se_pierden(self):
        # 20-10-2026: dos acuerdos del CGPJ con el mismo comienzo de título.
        regs = em.extraer(em.entradas_de_sumario(sumario("20261020")), FECHAS["20261020"],
                          log=lambda *_: None)
        cgpj = [r for r in regs if r["dept"].startswith("CONSEJO GENERAL DEL PODER JUDICIAL")]
        self.assertGreaterEqual(len(cgpj), 2)

    def test_tipos(self):
        casos = {
            "Resolución de 19 de octubre de 2026, de la Subsecretaría, por la que se aprueba la relación "
            "definitiva de personas admitidas y excluidas": "admitidos",
            "Resolución de 22 de octubre de 2026, de la Subsecretaría, por la que se convoca la provisión "
            "de puesto de trabajo por el sistema de libre designación.": "provision",
            "Resolución de 21 de octubre de 2026, de la Subsecretaría, por la que se convoca proceso "
            "selectivo para ingreso, por el sistema general de acceso libre": "convocatoria",
            "Resolución de 1 de octubre de 2026, del Ayuntamiento de Lepe (Huelva), referente a la "
            "convocatoria para proveer varias plazas.": "convocatoria",
            "Resolución de 2 de octubre de 2026, por la que se publica la relación de aprobados": "resultados",
            "Resolución de 2 de octubre de 2026, por la que se nombra el tribunal calificador": "tribunal",
        }
        for titulo, esperado in casos.items():
            self.assertEqual(em.tipo(titulo), esperado, titulo)

    def test_provincia_del_titulo(self):
        e = [{"codigo": "2B", "ident": "BOE-A-2026-1", "dept": "ADMINISTRACIÓN LOCAL", "epigrafe": "",
              "titulo": "Resolución de 1 de octubre de 2026, del Ayuntamiento de Lepe (Huelva), "
                        "referente a la convocatoria para proveer varias plazas."}]
        self.assertEqual(em.extraer(e, "2026-10-01", log=lambda *_: None)[0]["prov"], ["huelva"])

    def test_otras_secciones_fuera(self):
        e = [{"codigo": "2A", "ident": "BOE-A-2026-1", "titulo": "x"}]
        self.assertEqual(em.extraer(e, "2026-10-01", log=lambda *_: None), [])


class TestEstado(unittest.TestCase):
    def test_idempotente_y_poda(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = pathlib.Path(d) / "empleo.json"
            regs = em.extraer(em.entradas_de_sumario(sumario("20261027")), FECHAS["20261027"],
                              log=lambda *_: None)
            em.incorporar(regs, FECHAS["20261027"], "api", ruta, hoy=dt.date(2026, 10, 27))
            e = em.incorporar(regs, FECHAS["20261027"], "api", ruta, hoy=dt.date(2026, 10, 27))
            self.assertEqual(len(e["registros"]), len(regs))
            viejo = [{**regs[0], "id": "BOE-A-2024-1", "fecha": "2024-01-02"}]
            em.incorporar(viejo, "2024-01-02", "api", ruta, hoy=dt.date(2026, 10, 27))
            self.assertNotIn("BOE-A-2024-1", em.cargar(ruta)["registros"])


class TestPaginas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        ruta = pathlib.Path(self.tmp.name) / "empleo.json"
        self.todos = []
        for clave, fecha in FECHAS.items():
            regs = em.extraer(em.entradas_de_sumario(sumario(clave)), fecha, log=lambda *_: None)
            self.todos += regs
            em.incorporar(regs, fecha, "api", ruta, hoy=dt.date(2026, 10, 27))
        self.estado = em.cargar(ruta)
        self.carpeta = pathlib.Path(self.tmp.name) / "empleo"

    def tearDown(self):
        self.tmp.cleanup()

    def test_cada_disposicion_enlaza_al_boe_en_el_indice(self):
        h, _ = h_prueba(self.carpeta)
        salidas = em.generar_paginas(h, self.estado)
        indice = (self.carpeta / "index.html").read_text(encoding="utf-8")
        for r in self.todos:
            self.assertIn(r.get("url") or em.url_boe(r["id"]), indice)
        urls = {s["url"] for s in salidas}
        self.assertIn("https://terceracamara.es/empleo/", urls)
        self.assertIn("https://terceracamara.es/empleo/ministerio-del-interior.html", urls)
        self.assertIn("CollectionPage", indice)
        self.assertNotIn("JobPosting", indice)

    def test_canales(self):
        h, escritos = h_prueba(self.carpeta)
        anuncios = em.canales(h, self.estado)
        self.assertIn(("empleo", "index.html"), anuncios)
        self.assertIn("index.xml", escritos)
        self.assertIn("<feed", escritos["index.xml"])
        self.assertEqual(escritos["index.xml"].count("<entry>"), 50)   # feeds.MAX_ENTRADAS

    def test_sin_datos_no_hay_paginas(self):
        h, _ = h_prueba(self.carpeta)
        # El pie enlaza a /empleo/: el índice existe aunque el estado esté vacío.
        salidas = em.generar_paginas(h, {"version": 1, "registros": {}, "dias": {}})
        self.assertEqual([s["url"] for s in salidas], ["https://terceracamara.es/empleo/"])
        self.assertIn("Aún no hay disposiciones", (self.carpeta / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
