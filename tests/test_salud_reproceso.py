"""El chequeo de salud no corre ni abre incidencias en reproceso o render (#100)."""
import pathlib
import re
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
PUBLICAR = (RAIZ / ".github/workflows/publicar.yml").read_text(encoding="utf-8")
DIARIO = (RAIZ / ".github/workflows/daily.yml").read_text(encoding="utf-8")


def if_del_paso(nombre):
    """Devuelve la condición `if` del paso de publicar.yml, en una sola línea."""
    m = re.search(
        rf"^      - name: {re.escape(nombre)}\n((?:        .*\n)*)",
        PUBLICAR,
        re.M,
    )
    if not m:
        raise AssertionError(f"no está el paso {nombre!r} en publicar.yml")
    bloque = m.group(1)
    mif = re.search(r"^        if:\s*(>-?|)\s*\n((?:          .+\n)*)", bloque, re.M)
    if mif and mif.group(1) in {">", ">-"}:
        return " ".join(linea.strip() for linea in mif.group(2).splitlines() if linea.strip())
    mif = re.search(r"^        if:\s*(.+)\n", bloque, re.M)
    if not mif:
        raise AssertionError(f"el paso {nombre!r} no tiene if")
    return mif.group(1).strip()


class TestCondiciones(unittest.TestCase):
    def test_incidencia_excluye_render_reprocesar_y_nombramientos(self):
        cond = if_del_paso("Incidencia de salud")
        self.assertIn("always()", cond)
        self.assertIn("env.MODO != 'render'", cond)
        self.assertIn("steps.salud.outputs.graves", cond)
        self.assertIn("reprocesar", cond)
        self.assertIn("nombramientos", cond)
        # Las pasadas diarias no están excluidas por nombre.
        self.assertNotIn("diario", cond)

    def test_verificar_excluye_reprocesar_y_nombramientos(self):
        cond = if_del_paso("Verificar")
        self.assertIn("always()", cond)
        self.assertIn("reprocesar", cond)
        self.assertIn("nombramientos", cond)
        # En render y en diario el modo no es «archivo», así que el chequeo sigue.
        self.assertIn("(inputs.modo || 'render') != 'archivo'", cond)

    def test_diario_sigue_abriendo_incidencias(self):
        self.assertIn("modo: diario", DIARIO)
        self.assertIn("issues: write", DIARIO)
        # El paso de incidencia no ha cambiado su invocación.
        self.assertIn("bash tools/incidencia_salud.sh", PUBLICAR)


if __name__ == "__main__":
    unittest.main()
