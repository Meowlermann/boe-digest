"""UX-1: Empleo en la barra principal y en la barra inferior móvil de todas
las páginas, comprobado por verificar.py (q) menu. UX-4: cinco entradas,
≤9 enlaces por nivel, sin URL repetidas y destinos que existen. Sin red."""
import re
import pathlib
import sys
import tempfile
import unittest

RAIZ_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_REPO))
sys.path.insert(0, str(RAIZ_REPO / "tools"))

import build  # noqa: E402
import verificar as v  # noqa: E402


def pagina(nav: str) -> str:
    return f"<!doctype html><html lang=\"es\"><body>{nav}<main>x</main></body></html>"


class TestMenu(unittest.TestCase):
    def test_render_nav_lleva_empleo_en_las_dos_barras(self):
        nav = build.render_nav()
        self.assertEqual(v.problemas_menu(pagina(nav)), [])
        tab = v.RE_TABBAR.search(nav).group(1)
        self.assertEqual(tab.count("<a "), 5)
        self.assertEqual(len(set(re.findall(r'href="([^"]+)"', tab))), 5)

    def test_plantillas_llevan_la_navegacion(self):
        for nombre in ("template.html", "template_edicion.html", "template_norma.html",
                       "template_archivo.html"):
            self.assertIn("__SSR_NAV__", (RAIZ_REPO / nombre).read_text(encoding="utf-8"), nombre)

    def test_falta_en_la_barra_movil(self):
        nav = build.render_nav().replace('<a href="/empleo/" data-pilar="empleo">', '<a href="/x/">', 1)
        self.assertTrue(any("barra inferior" in p for p in v.problemas_menu(pagina(nav))))

    def test_falta_en_la_barra_principal(self):
        nav = build.render_nav().replace('class="pilar-b" href="/empleo/"', 'class="pilar-b" href="/x/"', 1)
        self.assertTrue(any("barra principal" in p for p in v.problemas_menu(pagina(nav))))

    # ------------------------------------------------------------ UX-4
    def _pilares(self, nav=None):
        nav = nav or build.render_nav()
        return v.RE_PILAR.findall(v.RE_PILARES.search(nav).group(1))

    def test_cinco_entradas_en_orden(self):
        nombres = [v.RE_PILAR_B.search(c).group(3) for _k, c in self._pilares()]
        self.assertEqual(tuple(nombres), v.MENU_ENTRADAS)
        self.assertEqual(v.MENU_ENTRADAS, ("Hoy", "Empleo", "Parlamento", "Buscar", "Más"))

    def test_ningun_nivel_pasa_de_nueve_y_sin_repetidas(self):
        self.assertEqual(build.MENU_MAX_ENLACES, v.MENU_MAX_ENLACES)
        nav = build.render_nav()
        self.assertLessEqual(len(self._pilares()), 9)
        for clave, cuerpo in self._pilares():
            self.assertLessEqual(len(re.findall(r'href="', cuerpo)), 9, clave)
        hrefs = re.findall(r'href="([^"]+)"', v.RE_PILARES.search(nav).group(1))
        self.assertEqual(len(hrefs), len(set(hrefs)))
        self.assertNotIn("chip-n", nav)                     # grupos y materias, en sus índices
        self.assertNotIn("grupo-", nav)
        self.assertNotIn("/temas/", nav.replace('href="/temas/"', ""))

    def test_se_mantienen_sesiones_y_empleo(self):
        nav = build.render_nav()
        self.assertIn('href="/empleo/"', nav)
        if build.sesiones_publicadas():
            self.assertIn('href="/sesiones/"', nav)

    def test_paneles_son_botones_con_aria(self):
        for clave, cuerpo in self._pilares():
            if '<div class="panel' in cuerpo:
                self.assertIn(f'<button type="button" class="pilar-b" aria-expanded="false" '
                              f'aria-controls="panel-{clave}">', cuerpo)
                self.assertIn(f'id="panel-{clave}"', cuerpo)
            else:
                self.assertNotIn("aria-expanded", cuerpo)

    def test_barra_movil_sigue_al_menu(self):
        nav = build.render_nav()
        tab = v.RE_TABBAR.search(nav).group(1)
        self.assertEqual(re.findall(r'data-pilar="([^"]+)"', tab), [k for k, _ in self._pilares()])

    def test_detecta_panel_de_mas_de_nueve(self):
        nav = build.render_nav()
        extra = "".join(f'<li><a href="/x{i}/"><b>x</b></a></li>' for i in range(5))
        nav = nav.replace('<ul class="panel-l">', '<ul class="panel-l">' + extra, 1)
        self.assertTrue(any("máximo 9" in p for p in v.problemas_menu(pagina(nav))))

    def test_detecta_repetida_y_sexta_entrada(self):
        nav = build.render_nav().replace(
            '<li class="pilar pilar-directo" data-pilar="buscar">',
            '<li class="pilar pilar-directo" data-pilar="votos"><a class="pilar-b" href="/empleo/">'
            '<span>Votos</span></a></li><li class="pilar pilar-directo" data-pilar="buscar">', 1)
        ps = v.problemas_menu(pagina(nav))
        self.assertTrue(any("debe ser" in p for p in ps), ps)

    def test_detecta_aria_expanded_en_enlace_directo(self):
        nav = build.render_nav().replace('class="pilar-b" href="/empleo/"',
                                         'class="pilar-b" aria-expanded="false" href="/empleo/"', 1)
        self.assertTrue(any("sin panel" in p for p in v.problemas_menu(pagina(nav))))

    def test_destinos_del_menu(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = pathlib.Path(d)
            nav = build.render_nav()
            (raiz / "index.html").write_text(pagina(nav), encoding="utf-8")
            ps = v.problemas_destinos_menu(raiz, pagina(nav))
            self.assertTrue(any("/empleo/" in p and "no existe" in p for p in ps))
            self.assertTrue(any("h-boe" in p for p in ps))     # portada sin el ancla
            for href in set(re.findall(r'href="([^"#]+)', nav)):
                f = raiz / (href.lstrip("/") + "index.html" if href.endswith("/") else href.lstrip("/"))
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(pagina('<h2 id="h-boe"></h2><h2 id="h-cortes"></h2>'), encoding="utf-8")
            self.assertEqual(v.problemas_destinos_menu(raiz, pagina(nav)), [])

    def test_sin_navegacion_es_grave(self):
        self.assertEqual(len(v.problemas_menu(pagina(""))), 2)

    def test_fragmento_no_cuenta(self):
        self.assertEqual(v.problemas_menu("<div>fragmento</div>"), [])

    def test_comprobar_menu_en_disco(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = pathlib.Path(d)
            (raiz / "a.html").write_text(pagina(build.render_nav()), encoding="utf-8")
            (raiz / "b.html").write_text(pagina(""), encoding="utf-8")
            hs = v.comprobar_menu(raiz, [raiz / "a.html", raiz / "b.html"])
            self.assertEqual({h["fichero"] for h in hs if "barra" in h["detalle"]}, {"b.html"})
            # a.html está bien montada, pero en este directorio vacío sus destinos no existen.
            self.assertTrue(all("no existe" in h["detalle"] or "id=" in h["detalle"]
                                for h in hs if h["fichero"] == "a.html"))
            self.assertTrue(all(h["nivel"] == v.GRAVE for h in hs))


if __name__ == "__main__":
    unittest.main()
