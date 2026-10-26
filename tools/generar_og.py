"""Genera assets/og-default.png (1200x630), la imagen por defecto para
compartir en redes (og:image / twitter:image).

Se ejecuta a mano UNA vez y el PNG se commitea: el build no lo regenera, así
que Pillow no es dependencia del sitio (requirements.txt no cambia).

    python tools/generar_og.py [ruta_fuente_titular] [ruta_fuente_texto]

Sin argumentos usa Oswald y Work Sans si están instaladas, o la fuente por
defecto de Pillow. Colores: los de assets/style.css (--red, --ink, --bg).
"""
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


def main():
    tit = sys.argv[1] if len(sys.argv) > 1 else FUENTES / "Oswald/Oswald-VariableFont_wght.ttf"
    txt = sys.argv[2] if len(sys.argv) > 2 else FUENTES / "Work Sans/WorkSans-VariableFont_wght.ttf"
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
