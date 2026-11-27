"""PR de fichas (27-11-2026): ruta de navegación sin subrayado en ningún
estado, aviso «Legislatura disuelta» sin recuadro, resumen de escaños de
«Resultados oficiales» legible a 360 px y siglas literales del BOE. Sin red."""
import pathlib
import re
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import build  # noqa: E402
import resultados_29n as rs  # noqa: E402

CSS = (RAIZ / "assets" / "style.css").read_text(encoding="utf-8")


def _reglas(css=CSS):
    """[(selector, cuerpo)] de todas las reglas, también dentro de @media."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return [(sel.strip().split("{")[-1].strip(), cuerpo.replace(" ", "").replace("\n", ""))
            for sel, cuerpo in re.findall(r"([^{}]+)\{([^{}]*)\}", css)]


class RutaSinSubrayado(unittest.TestCase):
    ESTADOS = (":link", ":visited", ":hover", ":focus", ":focus-visible", ":active")

    def test_regla_base_todos_los_estados(self):
        base = [(s, c) for s, c in _reglas() if s.startswith(".miga a,") and ".miga a:visited" in s]
        self.assertEqual(len(base), 1)
        sel, cuerpo = base[0]
        for e in self.ESTADOS:
            self.assertIn(f".miga a{e}", sel)
        self.assertIn("text-decoration:none", cuerpo)
        self.assertIn("border-bottom:0", cuerpo)
        self.assertIn("font-weight:700", cuerpo)          # se distingue por peso

    def test_ninguna_regla_de_la_ruta_subraya(self):
        for sel, cuerpo in _reglas():
            if ".miga" not in sel:
                continue
            self.assertNotIn("underline", cuerpo, sel)
            m = re.search(r"border-bottom:([^;]+)", cuerpo)
            if m:
                self.assertIn(m.group(1), ("0", "none"), sel)
            self.assertFalse(re.search(r"(^|;)border:(?!0|none)", cuerpo), sel)

    def test_foco_con_outline(self):
        foco = [c for s, c in _reglas() if s == ".miga a:focus-visible"]
        self.assertTrue(foco and "outline:2px" in foco[0])
        self.assertNotIn("text-decoration", foco[0])

    def test_la_ficha_lleva_la_ruta(self):
        # La ruta «Portada › Parlamentarios» de las fichas sale en nav.miga.
        src = (RAIZ / "build.py").read_text(encoding="utf-8")
        self.assertIn("<a href=\"./\">Parlamentarios</a>", src)
        plantilla = build.TEMPLATE_NORMA.read_text(encoding="utf-8")
        self.assertIn('class="miga"', plantilla)


class AvisoSinRecuadro(unittest.TestCase):
    def test_sin_borde_fondo_ni_relleno(self):
        reglas = [(s, c) for s, c in _reglas() if ".aviso-leg" in s and ".aviso-leg a" not in s
                  and ".aviso-leg b" not in s]
        self.assertTrue(reglas)
        for sel, c in reglas:
            self.assertFalse(re.search(r"(^|;)border(-[a-z]+)?:(?!0(;|$)|none)", c), sel)
            self.assertFalse(re.search(r"(^|;)background(-color)?:(?!none|transparent)", c), sel)
            self.assertFalse(re.search(r"(^|;)padding(-[a-z]+)?:(?!0(;|$))", c), sel)
            self.assertFalse(re.search(r"(^|;)border-radius:(?!0(;|$))", c), sel)
            self.assertNotIn("box-shadow", c, sel)
        base = [c for s, c in reglas if s == ".aviso-leg"][0]
        for prop in ("border:0", "background:none", "padding:0"):
            self.assertIn(prop, base)

    def test_mismo_texto(self):
        a = build.AVISO_LEGISLATURA
        self.assertTrue(a.startswith('<p class="aviso-leg" role="note"><b>Legislatura disuelta.</b> El Real Decreto 806/2026 '
                                     'disolvió las Cortes de la XV Legislatura y convocó elecciones generales para el 29 de '
                                     'noviembre de 2026. Estos datos son de los diputados de la legislatura disuelta; las '
                                     'nuevas Cortes se constituirán el 23 de diciembre. '))
        self.assertEqual(build.plantilla_con_aviso('<dl class="ficha">').count("aviso-leg"), 1)


class ResumenA360(unittest.TestCase):
    D = {"candidaturas": [
        {"nombre": "PARTIDO FICTICIO UNO (PFU)", "votos": "300", "escanos": "16"},
        {"nombre": "COALICIÓN FICTICIA CON UN NOMBRE MUY LARGO SIN SIGLA ENTRE PARÉNTESIS", "votos": "200", "escanos": "10"},
        {"nombre": "FICTICIA-AGRUPACIÓN-DE-ELECTORES-UNIDA (FAEU-SUMA-PLURAL)", "votos": "100", "escanos": "6"},
        {"nombre": "SIN ESCAÑO (SE)", "votos": "50", "escanos": "0"}]}

    def test_sigla_pegada_a_sus_escanos(self):
        h = rs._reparto_html(self.D)
        self.assertEqual(h, '<span class="rof-reparto">Escaños: PFU&nbsp;16, COALICIÓN FICTICIA CON UN NOMBRE MUY LARGO '
                            'SIN SIGLA ENTRE PARÉNTESIS&nbsp;10, FAEU-SUMA-PLURAL&nbsp;6</span>')
        # Entre candidaturas, un espacio normal: ahí parte la línea.
        self.assertEqual(h.count(", "), 2)
        self.assertEqual(re.sub("<[^>]+>", "", h).replace("&nbsp;", " "),
                         "Escaños: " + rs.reparto_texto(self.D))

    def test_css_no_desborda(self):
        r = dict(_reglas())
        for sel in (".rof-reparto", ".rof-salto"):
            c = [v for s, v in _reglas() if s == sel and "overflow-wrap" in v]
            self.assertTrue(c, sel)
            self.assertIn("overflow-wrap:anywhere", c[0])
            self.assertIn("max-width:100%", c[0])
            self.assertNotIn("white-space:nowrap", c[0])
        self.assertIn("display:block", r[".rof-reparto"] if ".rof-reparto" in r else "")
        for sel, c in _reglas():
            if ".rof-reparto" in sel or ".rof-salto" in sel:
                self.assertNotIn("nowrap", c, sel)
                self.assertFalse(re.search(r"(^|;)(min-)?width:\d", c), sel)   # sin anchos fijos


class SiglasLiterales(unittest.TestCase):
    def test_regla_editorial(self):
        reglas = (RAIZ / "docs" / "REGLAS-EDITORIALES.md").read_text(encoding="utf-8")
        self.assertIn("literalmente como en el BOE (SUMAR, VOX", reglas)
        self.assertIn("No hay tabla de nombres", reglas)

    def test_sigla_del_boe_sin_tabla(self):
        self.assertEqual(rs.sigla("PARTIDO FICTICIO (PF-X)"), "PF-X")
        self.assertEqual(rs.sigla("SUMAR"), "SUMAR")
        self.assertEqual(rs.sigla("Nombre Sin Sigla"), "Nombre Sin Sigla")
