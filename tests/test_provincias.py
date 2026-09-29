"""Pruebas de provincias.menciones() y de la clasificación del BOE.

Se ejecutan con `python -m unittest tests.test_provincias` y no necesitan red:
solo miran el texto. Cada caso dice qué provincias y qué comunidades tiene que
dar y por qué, sobre todo en los ambiguos: la regla es que es mejor quedarse
corto que asignar mal.
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import provincias as pv  # noqa: E402

# (texto, provincias esperadas, comunidades esperadas)
CASOS = [
    # --- nombres oficiales y variantes bilingües o tradicionales
    ("Convenio entre el Ministerio del Interior y el Ayuntamiento de Girona.", {"girona"}, set()),
    ("Obras en la carretera N-II a su paso por Gerona.", {"girona"}, set()),
    ("Estación de Lleida y accesos desde Lérida.", {"lleida"}, set()),
    ("Actuaciones en el puerto de A Coruña y en La Coruña.", {"coruna-a"}, set()),
    ("Resolución sobre el aeropuerto de Ourense (Orense).", {"ourense"}, set()),
    ("Subvención a la Diputación Foral de Bizkaia para el metro de Bilbao.", {"bizkaia"}, set()),
    ("Convenio con el Ayuntamiento de Vitoria-Gasteiz.", {"araba-alava"}, set()),
    ("Obras de la variante de Castelló de la Plana.", {"castellon-castello"}, set()),
    ("Ayudas a los municipios de Alacant y de Gipuzkoa.", {"alicante-alacant", "gipuzkoa"}, set()),
    ("Plan de vivienda en Guipúzcoa y Vizcaya.", {"gipuzkoa", "bizkaia"}, set()),
    # --- islas y capitales compuestas: gana el término más largo
    ("Declaración de zona afectada en la isla de La Palma.", {"s-c-tenerife"}, set()),
    ("Aeropuerto de Palma de Mallorca.", {"balears-illes"}, set()),
    ("Puerto de Las Palmas de Gran Canaria.", {"palmas-las"}, set()),
    ("Carreteras de Lanzarote y Fuerteventura.", {"palmas-las"}, set()),
    # --- ambiguos: solo con contexto
    ("Bien de interés cultural en Toledo.", {"toledo"}, set()),
    ("Pregunta al Gobierno sobre el Banco Santander.", set(), set()),
    ("Obras del puerto de Santander.", {"cantabria"}, set()),
    ("Real Decreto por el que se nombra a don José de León Pérez.", set(), set()),
    ("Informe del diputado Soria sobre la financiación.", set(), set()),
    ("Soria Ya pide un tren directo.", set(), set()),
    ("Teruel Existe reclama la autovía.", set(), set()),
    ("Retransmisión del partido del FC Barcelona-Athletic Club.", set(), set()),
    ("Cuenca Hidrográfica del Segura: normas de explotación.", set(), set()),
    ("Parador de Cuenca: obras de rehabilitación.", {"cuenca"}, set()),
    ("Vía verde a su paso por Zamora.", {"zamora"}, set()),
    ("Declara la villa de Espinosa de los Monteros (Burgos) bien de interés cultural.", {"burgos"}, set()),
    ("Pregunta sobre la estación de tren en Valencia.", {"valencia-valencia"}, set()),
    # --- comunidades autónomas: a la comunidad, no a cada provincia
    ("Ayudas a Castilla y León por los incendios forestales.", set(), {"castilla-y-leon"}),
    ("Convenio con la Comunitat Valenciana para la dana.", set(), {"comunitat-valenciana"}),
    ("Transferencias a la Comunidad Valenciana y a Canarias.", set(),
     {"comunitat-valenciana", "canarias"}),
    ("Ley 3/2026 de la Generalitat de Catalunya.", set(), {"cataluna"}),
    # --- uniprovinciales: la comunidad es también su provincia
    ("Convenio con la Comunidad de Madrid.", {"madrid"}, {"comunidad-de-madrid"}),
    ("Ley Foral de la Comunidad Foral de Navarra.", {"navarra"}, {"comunidad-foral-de-navarra"}),
    ("Plan hidrológico de la Región de Murcia.", {"murcia"}, {"region-de-murcia"}),
    # --- mayúsculas y tildes
    ("OBRAS EN LA AUTOVÍA A-66 EN SALAMANCA", {"salamanca"}, set()),
    ("Actuaciones en Jaen y en Cadiz sin tildes.", {"jaen", "cadiz"}, set()),
    ("granada y cuenca en minúscula no son provincias.", set(), set()),
]

CATEGORIAS = [
    ("Real Decreto por el que se declara zona afectada gravemente por una emergencia de "
     "protección civil la isla de La Palma.", "zona-afectada"),
    ("Resolución por la que se publica el Convenio entre el Ministerio de Cultura y el "
     "Ayuntamiento de Teruel.", "convenio"),
    ("Real Decreto por el que se regula la concesión directa de una subvención al Cabildo de "
     "Lanzarote.", "subvencion"),
    ("Decreto por el que se declara bien de interés cultural el castillo de Burgos.", "patrimonio"),
    ("Resolución por la que se formula declaración de impacto ambiental del proyecto en Huelva.",
     "medio-ambiente"),
    ("Resolución por la que se aprueba el estudio informativo de la autovía A-11 en Zamora.",
     "infraestructuras"),
    ("Orden por la que se declaran de interés general las obras de la presa de Almería.",
     "interes-general"),
    ("Resolución por la que se publica la relación de puestos de trabajo de Sevilla.", "otras"),
    ("Resolución de la Autoridad Portuaria de Pasaia por la que se publica la Adenda del Convenio "
     "de ocupación temporal con la Diputación Foral de Gipuzkoa.", "convenio"),
    ("Real Decreto por el que se regula la concesión directa de subvenciones para actuaciones de "
     "interés general en Ceuta y Melilla.", "subvencion"),
]


class TestMenciones(unittest.TestCase):
    def test_casos(self):
        self.assertGreaterEqual(len(CASOS), 25)
        for texto, provs, comunidades in CASOS:
            with self.subTest(texto=texto):
                a = pv.analizar(texto)
                self.assertEqual(a["provincias"], provs)
                self.assertEqual(a["ccaa"], comunidades)

    def test_categorias(self):
        for titulo, esperada in CATEGORIAS:
            with self.subTest(titulo=titulo):
                self.assertEqual(pv.categoria(titulo), esperada)

    def test_referencia_completa(self):
        """Los 52 slugs de la referencia son los de diputados/provincia-*.html."""
        ref = pv.cargar_referencia()
        slugs = {p["slug"] for p in ref["provincias"]}
        self.assertEqual(len(slugs), 52)
        carpeta = pathlib.Path(__file__).resolve().parent.parent / "diputados"
        ficheros = {f.name[len("provincia-"):-5] for f in carpeta.glob("provincia-*.html")}
        if ficheros:
            self.assertEqual(slugs, ficheros)

    def test_extraer(self):
        entradas = [
            {"seccion": "III. Otras disposiciones", "dept": "MINISTERIO DE CULTURA",
             "titulo": "Resolución por la que se publica el Convenio con el Ayuntamiento de Girona.",
             "ident": "BOE-A-2026-1", "url": ""},
            {"seccion": "III. Otras disposiciones", "dept": "COMUNIDAD AUTÓNOMA DE ANDALUCÍA",
             "titulo": "Resolución por la que se incoa expediente de bien de interés cultural.",
             "ident": "BOE-A-2026-2", "url": ""},
            {"seccion": "III. Otras disposiciones", "dept": "ADMINISTRACIÓN LOCAL",
             "titulo": "Resolución del Ayuntamiento de Girona.", "ident": "BOE-A-2026-3", "url": ""},
            {"seccion": "V. Anuncios", "dept": "MINISTERIO", "titulo": "Anuncio en Girona.",
             "ident": "BOE-B-2026-4", "url": ""},
        ]
        regs = pv.extraer(entradas, "2026-09-01", log=lambda *_a: None)
        self.assertEqual([r["id"] for r in regs], ["BOE-A-2026-1", "BOE-A-2026-2"])
        self.assertEqual(regs[0]["provincias"], ["girona"])
        self.assertEqual(regs[1]["ccaa"], ["andalucia"])
        self.assertEqual(regs[1]["cat"], "patrimonio")


    def test_mapa_geometria(self):
        # Una forma por circunscripción de la referencia, ni una más ni una menos.
        import json
        geo = json.loads(pv.MAPA_FICHERO.read_text(encoding="utf-8"))
        slugs = {p["slug"] for p in pv.cargar_referencia()["provincias"]}
        self.assertEqual(set(geo["provincias"]), slugs)
        self.assertTrue({"ceuta", "melilla"} <= set(geo["centros"]))

    def test_cortes_mapa(self):
        self.assertEqual(pv.cortes_mapa([0, 0]), [])
        self.assertEqual(pv.cortes_mapa([0, 3, 3, 4]), [(3, 3), (4, 4)])
        rangos = pv.cortes_mapa([0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55])
        self.assertEqual(len(rangos), 5)
        self.assertEqual(rangos[0][0], 1)
        self.assertEqual(rangos[-1][1], 55)
        for (_a, b), (c, _d) in zip(rangos, rangos[1:]):
            self.assertLess(b, c)                      # sin solapes
        self.assertEqual(pv.nivel_mapa(0, rangos), 0)
        self.assertEqual(pv.nivel_mapa(55, rangos), 5)
        self.assertEqual(pv.nivel_mapa(4, rangos), pv.nivel_mapa(5, rangos))


    def test_agregados_ccaa(self):
        # La unión no cuenta dos veces lo que nombra dos provincias de la misma comunidad.
        res = [{"p": {"slug": "alicante-alacant", "ccaa": "comunitat-valenciana"}, "diputados": 12,
                "preg_ids": {"184/1", "184/2"}, "boe_ids": {"A"}},
               {"p": {"slug": "valencia-valencia", "ccaa": "comunitat-valenciana"}, "diputados": 16,
                "preg_ids": {"184/2", "184/3"}, "boe_ids": {"A", "B"}},
               {"p": {"slug": "madrid", "ccaa": "madrid"}, "diputados": 37,
                "preg_ids": set(), "boe_ids": {"C"}}]
        ag = pv.agregados_ccaa(res, {"comunitat-valenciana": {"184/9"}}, {"madrid": {"C", "D"}})
        self.assertEqual(ag["comunitat-valenciana"]["dip"], 28)
        self.assertEqual(ag["comunitat-valenciana"]["preg"], 4)
        self.assertEqual(ag["comunitat-valenciana"]["boe"], 2)
        self.assertEqual(ag["madrid"]["boe"], 2)
        self.assertEqual(ag["madrid"]["provincias"], ["madrid"])


if __name__ == "__main__":
    unittest.main()
