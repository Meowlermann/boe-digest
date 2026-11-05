"""Contador coherente y aviso de recorte de /empleo/ (E-2 ítem 2)."""
import pathlib
import unittest

import empleo as em

JS = (pathlib.Path(em.__file__).parent / "assets" / "empleo.js").read_text(encoding="utf-8")


class Contador(unittest.TestCase):
    def test_n_de_m(self):
        self.assertIn('" de " + m', JS)
        self.assertIn('s.dataset[st.dias ? "m30" : "m"]', JS)
        self.assertIn('total + " de " + tm', JS)

    def test_aviso_recorte(self):
        self.assertIn('": se cargan " + nv + " de " + M', JS)
        h = em.chips_filtro([{"id": "BOE-A-2026-1", "tipo": "convocatoria", "titulo": "x", "dept": "X", "prov": [], "fecha": "2026-11-03", "proc": "", "url": "", "plazo": ""}], "2026-11-04", [("granada", "Granada", 3)], [])
        self.assertIn('class="aside-note em-recorte" hidden', h)

    def test_nota_provincia(self):
        h = em.chips_filtro([{"id": "BOE-A-2026-1", "tipo": "convocatoria", "titulo": "x", "dept": "X", "prov": [], "fecha": "2026-11-03", "proc": "", "url": "", "plazo": ""}], "2026-11-04", [("granada", "Granada", 3)], [])
        self.assertIn('aria-describedby="em-prov-ayuda"', h)
        self.assertIn("Solo cuenta las disposiciones cuyo título nombra la provincia.", h)

    def test_nota_cifras_en_fuente(self):
        src = pathlib.Path(em.__file__).read_text(encoding="utf-8")
        self.assertIn("Cómo leer las cifras", src)
        self.assertIn('data-m="{len(todas)}"', src)


if __name__ == "__main__":
    unittest.main()
