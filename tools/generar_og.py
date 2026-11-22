"""Genera assets/og-default.png (1200x630), la imagen por defecto para
compartir en redes (og:image / twitter:image), y con --elecciones las 52
imágenes por circunscripción del 29-N (assets/og/elecciones-2026/<slug>.png,
tanda E5) más su indice.json.

Se ejecuta a mano UNA vez y el PNG se commitea: el build no lo regenera, así
que Pillow no es dependencia del sitio (requirements.txt no cambia).

    python tools/generar_og.py [ruta_fuente_titular] [ruta_fuente_texto]
    python tools/generar_og.py --elecciones [ruta_fuente_titular] [ruta_fuente_texto]

Con --elecciones el texto sale tal cual de curated/elecciones_2026.json
(elecciones.textos_og): nombre de la circunscripción, «Elecciones generales
29-N», escaños, candidaturas proclamadas y la fecha del Real Decreto. Ninguna
cifra se calcula aquí. Hay que volver a ejecutarlo si cambia ese JSON: el test
compara indice.json con los datos y avisa. Misma entrada, mismo PNG.

Sin argumentos usa Oswald y Work Sans si están instaladas, o la fuente por
defecto de Pillow. Colores: los de assets/style.css (--red, --ink, --bg).
"""
import json
import pathlib
import sys

from PIL import Image, ImageDraw, ImageFont

ANCHO, ALTO = 1200, 630
ROJO, TINTA, FONDO = "#c81e2c", "#14171c", "#eef0e8"
FUENTES = pathlib.Path("/usr/share/fonts/truetype/sand-box/google")


def fuente(ruta, tam, peso=None):
    try:
        f = ImageFont.truetype(str(ruta), tam)
        if peso:
            try:
                f.set_variation_by_name(peso)
            except Exception:                                  # noqa: BLE001
                pass
        return f
    except Exception:                                          # noqa: BLE001
        return ImageFont.load_default(tam)


RAIZ = pathlib.Path(__file__).resolve().parent.parent


def _ajustar(d, texto, ruta, tam, peso, ancho):
    """La fuente más grande (desde tam, de 2 en 2) con la que texto cabe en ancho."""
    while tam > 40:
        f = fuente(ruta, tam, peso)
        if d.textlength(texto, font=f) <= ancho:
            return f
        tam -= 2
    return fuente(ruta, tam, peso)


def imagen_provincia(t: dict, tit, txt) -> Image.Image:
    """Misma composición que og-default: franja roja, nombre grande, pie oscuro.
    Sin subrayados ni tarjetas."""
    im = Image.new("RGB", (ANCHO, ALTO), FONDO)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, ANCHO, 120], fill=ROJO)
    d.text((70, 60), t["antetitulo"].upper(), font=fuente(txt, 34, "SemiBold"),
           fill="white", anchor="lm")
    d.text((70, 330), t["nombre"], font=_ajustar(d, t["nombre"], tit, 150, "Bold", ANCHO - 140),
           fill=TINTA, anchor="ls")
    d.text((70, 420), t["cifras"], font=_ajustar(d, t["cifras"], txt, 46, "SemiBold", ANCHO - 140),
           fill=ROJO, anchor="ls")
    d.text((70, 480), t["fecha"].capitalize(), font=fuente(txt, 34, "Medium"), fill=TINTA, anchor="ls")
    d.rectangle([0, ALTO - 24, ANCHO, ALTO], fill=TINTA)
    d.text((70, 575), "La Tercera Cámara", font=fuente(tit, 40, "Bold"), fill=TINTA, anchor="ls")
    d.text((ANCHO - 70, 575), "terceracamara.es", font=fuente(txt, 32, "SemiBold"),
           fill=ROJO, anchor="rs")
    # Paleta de 64 colores sin tramado: unas cuatro veces menos peso y el mismo
    # resultado en cada ejecución.
    return im.quantize(colors=64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)


def elecciones(tit, txt):
    sys.path.insert(0, str(RAIZ))
    import build
    import elecciones as el
    textos = el.textos_og(el.cargar(), build.nombre_circunscripcion, build._slug_txt)
    carpeta = RAIZ / el.OG_CARPETA
    carpeta.mkdir(parents=True, exist_ok=True)
    for slug, t in textos.items():
        imagen_provincia(t, tit, txt).save(carpeta / f"{slug}.png", optimize=True)
    (carpeta / "indice.json").write_text(
        json.dumps(textos, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(carpeta, len(textos), "imágenes")


def main():
    args = [a for a in sys.argv[1:] if a != "--elecciones"]
    tit = args[0] if len(args) > 0 else FUENTES / "Oswald/Oswald-VariableFont_wght.ttf"
    txt = args[1] if len(args) > 1 else FUENTES / "Work Sans/WorkSans-VariableFont_wght.ttf"
    if "--elecciones" in sys.argv[1:]:
        return elecciones(tit, txt)
    im = Image.new("RGB", (ANCHO, ALTO), FONDO)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, ANCHO, 120], fill=ROJO)
    d.text((70, 60), "BOE · CORTES · GOBIERNO", font=fuente(txt, 34, "SemiBold"),
           fill="white", anchor="lm")
    d.text((70, 300), "LA TERCERA", font=fuente(tit, 150, "Bold"), fill=TINTA, anchor="ls")
    d.text((70, 455), "CÁMARA", font=fuente(tit, 150, "Bold"), fill=ROJO, anchor="ls")
    d.text((70, 535), "Lo que publica el BOE y lo que hacen tus representantes, cada día.",
           font=fuente(txt, 34, "Medium"), fill=TINTA, anchor="ls")
    d.rectangle([0, ALTO - 24, ANCHO, ALTO], fill=TINTA)
    d.text((ANCHO - 70, 585), "terceracamara.es", font=fuente(txt, 32, "SemiBold"),
           fill=ROJO, anchor="rs")
    salida = pathlib.Path(__file__).resolve().parent.parent / "assets" / "og-default.png"
    im.save(salida, optimize=True)
    print(salida, im.size)


if __name__ == "__main__":
    main()
