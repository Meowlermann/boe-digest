"""UX-4 (8): módulo de empleo en la portada. Cuenta las convocatorias del BOE
de la edición (boe.fechaISO), solo si es también el último BOE de
state/empleo.json; sin convocatorias, no se pinta. Sin red."""
import pathlib
import sys
import unittest

RAIZ_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_REPO))

import build  # noqa: E402
import empleo as em  # noqa: E402


def reg(fecha, tipo="convocatoria", titulo="Resolución por la que se convoca proceso selectivo"):
    return {"fecha": fecha, "tipo": tipo, "titulo": titulo, "dept": "MINISTERIO", "epigrafe": ""}


def estado(*regs):
    return {"registros": {f"BOE-A-{i}": r for i, r in enumerate(regs)}, "dias": {}}


DIA = {"boe": {"fechaISO": "2026-10-29"}}


class TestEmpleoPortada(unittest.TestCase):
    def test_cuenta_solo_convocatorias_del_dia(self):
        e = estado(reg("2026-10-29"), reg("2026-10-29"), reg("2026-10-29", "provision"),
                   reg("2026-10-29", "admitidos"), reg("2026-10-28"))
        self.assertEqual(em.convocatorias_del_dia(e, "2026-10-29"), 2)

    def test_desiertas_no_cuentan(self):
        from unittest import mock
        e = estado(reg("2026-10-29"), reg("2026-10-29", titulo="DESIERTA"))
        with mock.patch.object(em.empleo_campos, "fuera_de_abiertos",
                               side_effect=lambda r: r.get("titulo") == "DESIERTA"):
            self.assertEqual(em.convocatorias_del_dia(e, "2026-10-29"), 1)

    def test_estado_por_detras_no_pinta_cifra_de_otro_dia(self):
        e = estado(reg("2026-10-28"), reg("2026-10-28"))
        self.assertEqual(em.convocatorias_del_dia(e, "2026-10-29"), 0)
        self.assertEqual(build.render_empleo_portada_ssr(DIA, e), "")

    def test_estado_por_delante_tampoco(self):
        e = estado(reg("2026-10-29"), reg("2026-10-30"))
        self.assertEqual(em.convocatorias_del_dia(e, "2026-10-29"), 0)

    def test_sin_convocatorias_no_hay_bloque(self):
        e = estado(reg("2026-10-29", "provision"))
        self.assertEqual(build.render_empleo_portada_ssr(DIA, e), "")
        self.assertEqual(build.render_empleo_portada_ssr({}, e), "")

    def test_bloque_con_cifra_fecha_y_enlace(self):
        h = build.render_empleo_portada_ssr(DIA, estado(*[reg("2026-10-29")] * 1, reg("2026-10-29")))
        self.assertIn("<b>2 convocatorias</b>", h)
        self.assertIn("29 de octubre de 2026", h)
        self.assertEqual(h.count('href="/empleo/"'), 1)
        self.assertNotIn("<script", h)
        self.assertNotRegex(h, r"(?i)plazo|cierra|hasta el")
        h1 = build.render_empleo_portada_ssr(DIA, estado(reg("2026-10-29")))
        self.assertIn("<b>1 convocatoria</b>", h1)

    def test_plantilla_lleva_el_hueco(self):
        self.assertIn("__SSR_EMPLEO_HOY__", (RAIZ_REPO / "template.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
