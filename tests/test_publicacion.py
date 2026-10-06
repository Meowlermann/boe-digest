"""Pruebas de la publicación por artefacto, sin red.

`python -m unittest tests.test_publicacion`:
  - tools/montar_sitio.py: qué entra en _site y cuándo se niega a montarlo;
  - tools/datos.sh: la rama datos (creación huérfana, traer y guardar) contra
    un repositorio «origin» local, sin GitHub.
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

RAIZ_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_REPO / "tools"))

import montar_sitio as ms  # noqa: E402

LISTA = """# prueba
!index.html
sitemap*.xml
!normas
!CNAME
robots.txt
"""


class TestMontarSitio(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = pathlib.Path(self._tmp.name) / "repo"
        self.destino = pathlib.Path(self._tmp.name) / "_site"
        for rel, texto in {"index.html": "<html></html>", "sitemap.xml": "<x/>",
                           "sitemap-2.xml": "<x/>", "normas/a.html": "a", "normas/sub/b.html": "b",
                           "CNAME": "terceracamara.es\n", "build.py": "print()",
                           "state/x.json": "{}", "data/2026-10-05.json": "{}"}.items():
            p = self.raiz / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(texto, encoding="utf-8")
        self.lista = self.raiz / "publicables.txt"
        self.lista.write_text(LISTA, encoding="utf-8")
        self._parche = mock.patch.object(ms, "LISTA", self.lista)
        self._parche.start()

    def tearDown(self):
        self._parche.stop()
        self._tmp.cleanup()

    def montados(self):
        return sorted(p.relative_to(self.destino).as_posix()
                      for p in self.destino.rglob("*") if p.is_file())

    def test_solo_lo_publicable(self):
        problemas, r = ms.montar(self.raiz, self.destino)
        self.assertEqual(problemas, [])
        self.assertEqual(self.montados(), ["CNAME", "index.html", "normas/a.html",
                                           "normas/sub/b.html", "sitemap-2.xml", "sitemap.xml"])
        self.assertEqual(r["ficheros"], 6)

    def test_lectura_de_la_lista(self):
        self.assertEqual(ms.leer_publicables(self.lista)[:2], [("index.html", True), ("sitemap*.xml", False)])
        self.assertTrue(ms.cubre(["sitemap*.xml", "normas"], "sitemap-3.xml"))
        self.assertFalse(ms.cubre(["sitemap*.xml", "normas"], "state"))

    def test_falta_algo_obligatorio(self):
        shutil.rmtree(self.raiz / "normas")
        problemas, _ = ms.montar(self.raiz, self.destino)
        self.assertEqual(len(problemas), 1)
        self.assertIn("normas", problemas[0])

    def test_opcional_que_falta_no_es_problema(self):
        problemas, _ = ms.montar(self.raiz, self.destino)       # robots.txt no existe
        self.assertEqual(problemas, [])

    def test_dominio(self):
        (self.raiz / "CNAME").write_text("otro.example\n", encoding="utf-8")
        problemas, _ = ms.montar(self.raiz, self.destino)
        self.assertIn("terceracamara.es", problemas[0])

    def test_limite_de_pages(self):
        with mock.patch.object(ms, "LIMITE_PAGES_BYTES", 10):
            problemas, _ = ms.montar(self.raiz, self.destino)
        self.assertIn("1 GB", problemas[0])

    def test_main_sale_con_error(self):
        (self.raiz / "index.html").unlink()
        with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": ""}), mock.patch("sys.stdout"):
            codigo = ms.main(["--raiz", str(self.raiz), "--destino", str(self.destino)])
        self.assertEqual(codigo, 1)

    def test_lista_real(self):
        # La lista del repositorio tiene lo imprescindible para que Pages sirva el dominio.
        entradas = dict(ms.leer_publicables(RAIZ_REPO / "tools" / "publicables.txt"))
        for obligatorio in ("index.html", "CNAME", "sitemap.xml", "assets"):
            self.assertTrue(entradas.get(obligatorio), obligatorio)
        for nunca in ("data", "state", "debug", "tests", "tools"):
            self.assertNotIn(nunca, entradas)


@unittest.skipUnless(shutil.which("git") and shutil.which("bash"), "hace falta git y bash")
class TestRamaDatos(unittest.TestCase):
    """tools/datos.sh contra un «origin» local (un repositorio bare)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = pathlib.Path(self._tmp.name)
        self.origin = base / "origin.git"
        self.trabajo = base / "trabajo"
        self.entorno = {**os.environ, "RUNNER_TEMP": str(base / "temp"),
                        "GIT_AUTHOR_NAME": "prueba", "GIT_AUTHOR_EMAIL": "p@ejemplo.es",
                        "GIT_COMMITTER_NAME": "prueba", "GIT_COMMITTER_EMAIL": "p@ejemplo.es",
                        "HOME": str(base)}
        (base / "temp").mkdir()
        self.git(base, "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.git(base, "clone", "-q", str(self.origin), str(self.trabajo))
        for rel, texto in {"data/2026-10-04.json": '{"id": "2026-10-04"}', "state/s.json": "{}",
                           "debug/last-run.json": "{}", "build.py": "print()",
                           "tools/datos.sh": (RAIZ_REPO / "tools" / "datos.sh").read_text(encoding="utf-8"),
                           "tools/LEEME-datos.md": "# Rama datos\n",
                           "tools/compactar_datos.sh": (RAIZ_REPO / "tools" / "compactar_datos.sh").read_text(encoding="utf-8")}.items():
            p = self.trabajo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(texto, encoding="utf-8")
        self.git(self.trabajo, "add", "-A")
        self.git(self.trabajo, "commit", "-q", "-m", "main")
        self.git(self.trabajo, "push", "-q", "origin", "main")

    def tearDown(self):
        self._tmp.cleanup()

    def git(self, cwd, *args):
        return subprocess.run(["git", *args], cwd=cwd, env=getattr(self, "entorno", None),
                              check=True, capture_output=True, text=True).stdout.strip()

    def datos(self, *args):
        return subprocess.run(["bash", "tools/datos.sh", *args], cwd=self.trabajo, env=self.entorno,
                              check=True, capture_output=True, text=True).stdout

    def test_ciclo_completo(self):
        # 1. Sin rama datos: se usan los del checkout.
        self.assertIn("no existe todavía", self.datos("traer"))
        # 2. El pase escribe la edición de hoy y guarda: rama huérfana con dos commits.
        (self.trabajo / "data" / "2026-10-05.json").write_text('{"id": "2026-10-05"}', encoding="utf-8")
        self.assertIn("creada la rama huérfana", self.datos("guardar", "Edición del 2026-10-05"))
        log = self.git(self.origin, "log", "--format=%s", "datos").splitlines()
        self.assertEqual(log, ["Edición del 2026-10-05", "Datos iniciales"])
        # «Datos iniciales» es lo que había antes del pase, con su README.
        inicial = self.git(self.origin, "ls-tree", "-r", "--name-only", "datos~1").splitlines()
        self.assertEqual(sorted(inicial), ["README.md", "data/2026-10-04.json",
                                           "debug/last-run.json", "state/s.json"])
        # Huérfana: no comparte historia con main ni lleva código.
        self.assertEqual(self.git(self.origin, "rev-list", "--count", "datos"), "2")
        self.assertNotIn("build.py", self.git(self.origin, "ls-tree", "--name-only", "datos"))
        # main no ha recibido nada.
        self.assertEqual(self.git(self.origin, "log", "--format=%s", "main"), "main")

        # 3. Otro pase: traer sustituye los datos del checkout por los de la rama.
        shutil.rmtree(self.trabajo / "data")
        (self.trabajo / "data").mkdir()
        self.assertIn("traídos de la rama datos", self.datos("traer"))
        self.assertTrue((self.trabajo / "data" / "2026-10-05.json").exists())
        # Sin cambios no hay commit.
        self.assertIn("sin cambios", self.datos("guardar", "Edición del 2026-10-05"))
        self.assertEqual(self.git(self.origin, "rev-list", "--count", "datos"), "2")
        # Con cambios, un commit encima.
        (self.trabajo / "state" / "s.json").write_text('{"n": 1}', encoding="utf-8")
        self.datos("guardar", "Edición del 2026-10-06")
        self.assertEqual(self.git(self.origin, "log", "-1", "--format=%s", "datos"), "Edición del 2026-10-06")

    def test_rama_de_pruebas_no_toca_datos(self):
        self.datos("traer")
        self.datos("guardar", "Edición del 2026-10-05")
        antes = self.git(self.origin, "rev-parse", "datos")
        self.entorno["DATOS_RAMA"] = "datos-pruebas"
        self.assertIn("se parte de datos", self.datos("traer"))
        (self.trabajo / "state" / "s.json").write_text('{"prueba": 1}', encoding="utf-8")
        self.datos("guardar", "Prueba")
        self.assertEqual(self.git(self.origin, "rev-parse", "datos"), antes)
        self.assertEqual(self.git(self.origin, "log", "--format=%s", "datos-pruebas").splitlines(),
                         ["Prueba", "Datos iniciales"])

    def compactar(self, *args, **entorno):
        return subprocess.run(["bash", "tools/compactar_datos.sh", *args], cwd=self.trabajo,
                              env={**self.entorno, **entorno}, check=True, capture_output=True,
                              text=True).stdout

    def test_compactar(self):
        self.datos("traer")
        (self.trabajo / "data" / "2026-10-05.json").write_text('{"id": "2026-10-05"}', encoding="utf-8")
        self.datos("guardar", "Edición del 2026-10-05")
        arbol = self.git(self.origin, "rev-parse", "datos^{tree}")
        # Por debajo de los umbrales no toca nada.
        self.assertIn("No hace falta", self.compactar())
        self.assertEqual(self.git(self.origin, "rev-list", "--count", "datos"), "2")
        # Por encima: un solo commit con el mismo árbol, y main intacta.
        main = self.git(self.origin, "rev-parse", "main")
        self.assertIn("Compactada", self.compactar(MAX_COMMITS="1"))
        self.assertEqual(self.git(self.origin, "rev-list", "--count", "datos"), "1")
        self.assertEqual(self.git(self.origin, "rev-parse", "datos^{tree}"), arbol)
        self.assertEqual(self.git(self.origin, "rev-parse", "main"), main)
        self.assertIn("Datos compactados", self.git(self.origin, "log", "-1", "--format=%s", "datos"))
        # Y el siguiente pase sigue escribiendo encima con normalidad.
        self.datos("traer")
        (self.trabajo / "state" / "s.json").write_text('{"n": 2}', encoding="utf-8")
        self.datos("guardar", "Edición del 2026-10-06")
        self.assertEqual(self.git(self.origin, "rev-list", "--count", "datos"), "2")


if __name__ == "__main__":
    unittest.main()
