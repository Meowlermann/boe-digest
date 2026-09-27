"""Pruebas de las expresiones de nombramientos.py con títulos reales.

Todos los títulos son literales del sumario del BOE (sección II), del 1 al 12
de septiembre de 2026, con su identificador para poder comprobarlos. Se
ejecutan con `python -m unittest tests.test_nombramientos` y no necesitan
red: analizar() solo mira el texto del título.
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import nombramientos as nb  # noqa: E402

# (título, esperado). Esperado es None si se descarta, con el motivo en
# «motivo»; si no, los campos que tiene que dar analizar().
CASOS = [
    # --- ceses de altos cargos (reales decretos)
    ("Real Decreto 712/2026, de 1 de septiembre, por el que se dispone el cese de doña Rocío "
     "Báguena Rodríguez como Secretaria General de Transporte Terrestre.",
     {"tipo": "cese", "persona": "Rocío Báguena Rodríguez",
      "cargo": "Secretaria General de Transporte Terrestre"}),
    ("Real Decreto 715/2026, de 1 de septiembre, por el que se dispone el cese de doña Leire "
     "Iglesias Santiago como Presidenta de CASA 47 Entidad Pública Empresarial.",
     {"tipo": "cese", "persona": "Leire Iglesias Santiago",
      "cargo": "Presidenta de CASA 47 Entidad Pública Empresarial"}),
    ("Resolución de 8 de septiembre de 2026, de la Presidencia de la Agencia Estatal de "
     "Administración Tributaria, por la que se dispone el cese de don Carlos José Dorrego Anta "
     "como Subdirector General de Procedimientos Especiales del Departamento de Recaudación.",
     {"tipo": "cese", "persona": "Carlos José Dorrego Anta",
      "cargo": "Subdirector General de Procedimientos Especiales del Departamento de Recaudación"}),
    # --- nombramientos
    ("Real Decreto 714/2026, de 1 de septiembre, por el que se nombra Secretaria General de "
     "Transporte Terrestre a doña Sara Hernández del Olmo.",
     {"tipo": "nombramiento", "persona": "Sara Hernández del Olmo",
      "cargo": "Secretaria General de Transporte Terrestre"}),
    ("Real Decreto 716/2026, de 1 de septiembre, por el que se nombra Secretaria de Estado de "
     "Vivienda y Agenda Urbana a doña Leire Iglesias Santiago.",
     {"tipo": "nombramiento", "persona": "Leire Iglesias Santiago",
      "cargo": "Secretaria de Estado de Vivienda y Agenda Urbana"}),
    ("Orden AUC/928/2026, de 28 de agosto, por la que se nombra Directora del Gabinete del "
     "Secretario de Estado para la Unión Europea a doña Alicia Cocero Mora.",
     {"tipo": "nombramiento", "persona": "Alicia Cocero Mora",
      "cargo": "Directora del Gabinete del Secretario de Estado para la Unión Europea"}),
    ("Decreto de 7 de julio de 2026, del Fiscal General del Estado, por el que se nombra Delegado "
     "de la Fiscalía Especial Antidroga en la Fiscalía de Área de Algeciras a don Juan Jacobo "
     "Cisneros del Prado.",
     {"tipo": "nombramiento", "persona": "Juan Jacobo Cisneros del Prado",
      "cargo": "Delegado de la Fiscalía Especial Antidroga en la Fiscalía de Área de Algeciras"}),
    ("Resolución de 5 de agosto de 2026, de la Universidad de Las Palmas de Gran Canaria, por la "
     "que se nombra Catedrático de Universidad, con plaza vinculada, a don Antonio Naranjo Hernández.",
     {"tipo": "nombramiento", "persona": "Antonio Naranjo Hernández",
      "cargo": "Catedrático de Universidad (plaza vinculada)"}),
    ("Resolución de 1 de septiembre de 2026, de la Universidad de Salamanca, por la que se nombra "
     "Catedrático de Universidad a don Fernando Sancho de Salas.",
     {"tipo": "nombramiento", "persona": "Fernando Sancho de Salas",
      "cargo": "Catedrático de Universidad"}),
    ("Resolución de 31 de julio de 2026, de la Dirección General de Seguridad Jurídica y Fe "
     "Pública, por la que se nombra Notario Archivero de Protocolos del Distrito Notarial de Icod "
     "de los Vinos, al notario con residencia en dicha localidad, don Javier Pichel Pichel.",
     {"tipo": "nombramiento", "persona": "Javier Pichel Pichel",
      "cargo": "Notario Archivero de Protocolos del Distrito Notarial de Icod de los Vinos"}),
    # --- destinos de magistrados
    ("Real Decreto 676/2026, de 29 de julio, por el que se adjudica en propiedad la plaza de "
     "Magistrada de la Sala de lo Social del Tribunal Superior de Justicia de Castilla-La Mancha "
     "a doña María Luz Rico Recondo.",
     {"tipo": "nombramiento", "acto": "destino", "persona": "María Luz Rico Recondo",
      "cargo": "Plaza de Magistrada de la Sala de lo Social del Tribunal Superior de Justicia de Castilla-La Mancha"}),
    ("Real Decreto 674/2026, de 29 de julio, por el que se adjudica en propiedad la plaza de Jueza "
     "de adscripción territorial del Tribunal Superior de Justicia de Madrid a la Magistrada doña "
     "Carolina Encabo Lizaur.",
     {"tipo": "nombramiento", "acto": "destino", "persona": "Carolina Encabo Lizaur",
      "cargo": "Plaza de Jueza de adscripción territorial del Tribunal Superior de Justicia de Madrid"}),
    # --- jubilaciones y excedencias
    ("Acuerdo de 2 de junio de 2026, de la Comisión Permanente del Consejo General del Poder "
     "Judicial, por el que se declara la jubilación forzosa del Magistrado don Juan Ramón Berdugo "
     "Gómez de la Torre.",
     {"tipo": "otro", "acto": "jubilación", "persona": "Juan Ramón Berdugo Gómez de la Torre",
      "cargo": "Magistrado"}),
    ("Acuerdo de 27 de abril de 2026, de la Comisión Permanente del Consejo General del Poder "
     "Judicial, por el que se declara la jubilación voluntaria anticipada del Magistrado don "
     "Felipe Peñalba Otaduy.",
     {"tipo": "otro", "acto": "jubilación", "persona": "Felipe Peñalba Otaduy", "cargo": "Magistrado"}),
    ("Resolución de 20 de agosto de 2026, de la Dirección General de Seguridad Jurídica y Fe "
     "Pública, por la que se declara la jubilación del notario de Madrid don Miguel Vicente-Almazán "
     "Pérez de Petinto.",
     {"tipo": "otro", "acto": "jubilación", "persona": "Miguel Vicente-Almazán Pérez de Petinto",
      "cargo": "Notario de Madrid"}),
    ("Resolución de 25 de agosto de 2026, de la Dirección General de Seguridad Jurídica y Fe "
     "Pública, por la que se declara la jubilación de doña María Victoria Arizmendi Gutiérrez, "
     "registradora del Registro Mercantil de Madrid VI.",
     {"tipo": "otro", "acto": "jubilación", "persona": "María Victoria Arizmendi Gutiérrez",
      "cargo": "Registradora del Registro Mercantil de Madrid VI"}),
    ("Resolución de 27 de agosto de 2026, de la Dirección General de Seguridad Jurídica y Fe "
     "Pública, por la que se declara en situación de excedencia voluntaria al notario de Alcorcón "
     "don Alfonso García-Perrote Latorre.",
     {"tipo": "otro", "acto": "excedencia voluntaria", "persona": "Alfonso García-Perrote Latorre",
      "cargo": "Notario de Alcorcón"}),
    # --- descartes
    ("Resolución de 28 de julio de 2026, de la Secretaría de Estado de Función Pública, por la que "
     "se nombra personal funcionario de carrera, por el sistema general de acceso libre, promoción "
     "interna y para el cambio de régimen jurídico del personal laboral fijo incluido en el Anexo "
     "II del IV Convenio Único para el personal laboral de la Administración General del Estado, "
     "en el Cuerpo Facultativo de Conservadores de Museos.",
     None, "sin nombre propio"),
    ("Resolución de 4 de agosto de 2026, de la Universidad de Las Palmas de Gran Canaria, por la "
     "que se nombran Catedráticas y Catedráticos de Universidad.",
     None, "sin nombre propio"),
    ("Resolución de 25 de agosto de 2026, de la Subsecretaría, por la que se resuelve la "
     "convocatoria de libre designación, efectuada por Resolución de 13 de julio de 2026.",
     None, "sin nombre propio"),
    ("Orden EFD/919/2026, de 27 de agosto, por la que se corrigen errores en la Orden EFD/751/2026, "
     "de 16 de julio, por la que, a propuesta de la Conselleria de Educación, Cultura y "
     "Universidades de la Comunitat Valenciana, se nombra funcionario de carrera del Cuerpo de "
     "Profesores de Enseñanza Secundaria a don Marcos Plaza Camacho.",
     None, "corrección de errores"),
    ("Orden PJC/949/2026, de 21 de agosto, por la que se acuerda la pérdida, por renuncia, de la "
     "condición de funcionaria del Cuerpo de Auxilio Judicial de la Administración de Justicia de "
     "doña Silvia Aldama San Martín.",
     None, "pérdida de la condición de funcionario"),
]


class PruebaNombramientos(unittest.TestCase):
    def test_titulos_reales(self):
        for caso in CASOS:
            titulo, esperado = caso[0], caso[1]
            reg, motivo = nb.analizar(titulo)
            with self.subTest(titulo=titulo[:90]):
                if esperado is None:
                    self.assertIsNone(reg)
                    self.assertEqual(motivo, caso[2])
                else:
                    self.assertIsNotNone(reg, motivo)
                    for k, v in esperado.items():
                        self.assertEqual(reg[k], v, k)

    def test_extraer_idempotente_y_seccion(self):
        ent = [
            {"codigo": "2A", "seccion": "II. Autoridades y personal. - A. Nombramientos",
             "dept": "MINISTERIO DE TRANSPORTES Y MOVILIDAD SOSTENIBLE", "titulo": CASOS[0][0],
             "ident": "BOE-A-2026-18401", "url": "", "paginas": 1},
            {"codigo": "2B", "seccion": "II. Autoridades y personal. - B. Oposiciones y concursos",
             "dept": "UNIVERSIDADES", "titulo": CASOS[19][0], "ident": "BOE-A-2026-18402",
             "url": "", "paginas": 2},
            {"codigo": "1", "seccion": "I. Disposiciones generales", "dept": "X",
             "titulo": CASOS[3][0], "ident": "BOE-A-2026-18403", "url": ""},
        ]
        regs = nb.extraer(ent, "2026-09-02", log=lambda *_: None)
        self.assertEqual([r["id"] for r in regs], ["BOE-A-2026-18401"])
        self.assertEqual(regs[0]["rango"], "Real Decreto")
        self.assertEqual(regs[0]["clave"], "rocio baguena rodriguez")

    def test_titular(self):
        regs = [{"tipo": "nombramiento", "acto": "nombramiento", "rango": "Real Decreto"}] * 6 + \
               [{"tipo": "cese", "acto": "cese", "rango": "Real Decreto"}] * 4
        self.assertEqual(nb.titular_bloque(regs), "EL GOBIERNO NOMBRA A 6 ALTOS CARGOS Y CESA A 4")


if __name__ == "__main__":
    unittest.main()
