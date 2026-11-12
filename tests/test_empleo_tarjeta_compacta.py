"""Tarjeta compacta de las fichas por organismo (E-1, 04-11-2026): tipo, fecha, título llano,
organismo, plazo LITERAL o el texto fijo, BOE-A y «Ver en el BOE». Comprueba
que lleva los mismos datos que la tarjeta anterior (Qué/Quién/Cuándo), sin
campos nuevos ni inventados, y objetivos táctiles de 44 px. Sin red."""
import html
import pathlib
import re
import sys
import tempfile
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import empleo as em  # noqa: E402
import empleo_campos  # noqa: E402
from test_empleo import h_prueba  # noqa: E402

CSS = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")
LIT = "20 días hábiles contados a partir del siguiente al de la publicación de este extracto en el «Boletín Oficial del Estado»"


class TarjetaCompacta(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.carpeta = pathlib.Path(self.tmp.name) / "empleo"
        self.regs = {
            "BOE-A-2026-1": {"fecha": "2026-10-27", "tipo": "convocatoria", "dept": "MINISTERIO X", "prov": [],
                             "titulo": "Resolución por la que se convoca proceso selectivo para ingreso en el Cuerpo X",
                             "plazo": LIT},
            "BOE-A-2026-2": {"fecha": "2026-10-26", "tipo": "convocatoria", "dept": "MINISTERIO X", "prov": [],
                             "titulo": "Resolución por la que se convoca proceso selectivo para ingreso en el Cuerpo Y"},
            "BOE-A-2026-3": {"fecha": "2026-10-25", "tipo": "admitidos", "dept": "MINISTERIO X", "prov": [],
                             "titulo": "Resolución por la que se aprueba la lista de admitidos del Cuerpo X"},
        }
        h, _ = h_prueba(self.carpeta)
        h["hoy"] = "2026-10-28"
        em.generar_paginas(h, {"version": 1, "registros": self.regs, "dias": {}})
        # Las tarjetas compactas siguen en la ficha de organismo; /empleo/ va en filas.
        self.idx = (self.carpeta / "ministerio-x.html").read_text(encoding="utf-8")
        self.cards = dict((m[1], m[0]) for m in re.findall(
            r'(<li class="em-card[^>]*>.*?</li>)', self.idx) and
            [(c, re.search(r"BOE-A-\d{4}-\d+", c).group(0)) for c in
             re.findall(r'<li class="em-card[^>]*>.*?</li>', self.idx)])

    def tearDown(self):
        self.tmp.cleanup()

    def test_estructura(self):
        self.assertEqual(len(self.cards), 3)
        for i, c in self.cards.items():
            for k in ('class="em-c-cab"', 'class="em-etq em-etq-', '<time datetime="', 'class="em-c-tit"',
                      f'<span class="em-c-id">{i}</span>', '>Ver en el BOE</a></div></li>'):
                self.assertIn(k, c, (i, k))
            self.assertEqual(c.count("<a "), 1)

    def test_plazo_literal_o_texto_fijo_nunca_calculado(self):
        pl = em.plazo_tarjeta(self.regs["BOE-A-2026-1"])
        c1, c2, c3 = (self.cards[f"BOE-A-2026-{n}"] for n in (1, 2, 3))
        if pl:
            self.assertIn(f"<b>Plazo:</b> {html.escape(pl, quote=False)}", c1)
            self.assertEqual(pl, empleo_campos.plazo_llano(LIT))
        else:
            self.assertIn(em.SIN_PLAZO, c1)
        self.assertIn("No figura en el resumen: consúltalo en el BOE", c2)
        self.assertNotIn("em-c-plazo", c3)   # listas: no tienen plazo de solicitud (igual que antes)
        for c in (c1, c2):
            self.assertNotRegex(c, r"(?i)cierra|fin de plazo|hasta el \d|plazo abierto|finalizad")

    def test_sin_campos_nuevos(self):
        # Textos visibles = los mismos datos que la tarjeta anterior: tipo,
        # fecha y «(hace…)», qué es, organismo, plazo, id y botón.
        for i, c in self.cards.items():
            r = self.regs[i]
            et, _ = em.etiqueta_llana(r)
            txt = re.sub(r"<[^>]+>", "|", c)
            vis = [html.unescape(t).strip() for t in txt.split("|") if t.strip()]
            permitidos = {et, "Publicada el", i, "Ver en el BOE", "Plazo:", em.SIN_PLAZO}
            for v in vis:
                ok = (v in permitidos or v.startswith("(") or "2026" in v or v == em.nombre_organismo(r)
                      or v in html.unescape(c) and (v in em.que_es(r, []) or v in (em.plazo_tarjeta(r) or "")))
                self.assertTrue(ok, (i, v))

    def test_tactil_44(self):
        self.assertIn(".em-card .em-boe{ min-height:44px; min-width:44px; }", CSS)
        self.assertIn(".em-card summary{ min-height:44px;", CSS)
        self.assertRegex(CSS, r"\.em-fb\{ min-height:44px; min-width:44px;")

    def test_colores_existentes_sin_degradado_ni_subrayado(self):
        blq = CSS[CSS.index("/* Tarjeta compacta (E-1"):CSS.index(".em-card summary{ min-height:44px")]
        for k in ("gradient", "underline", "turquoise", "#40e0d0"):
            self.assertNotIn(k, blq)
        self.assertIn(".ix-lista > li.em-card.em-c-oposicion{ border-top:3px solid var(--fiscal); }", blq)
        self.assertIn(".ix-lista > li.em-card.em-c-concurso,.ix-lista > li.em-card.em-c-convocatoria{ border-top:3px solid var(--senado); }", blq)


if __name__ == "__main__":
    unittest.main()
