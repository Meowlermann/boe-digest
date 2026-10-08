#!/usr/bin/env python3
"""Versión para correo del resumen semanal (semana.py).

Genera, a partir del MISMO JSON congelado que pinta /semana/AAAA-Snn.html
(data/semanas/AAAA-Snn.json):

  - un HTML apto para clientes de correo: maquetado con tablas, CSS en línea
    (los clientes de correo ignoran <style> y hojas externas), sin JavaScript,
    sin imágenes ni tipografías remotas y con un ancho máximo de 600 px;
  - una versión en texto plano con el mismo contenido y las direcciones
    completas de los enlaces.

No envía nada. El envío (y el enlace de baja del proveedor) es cosa de la
PR del boletín; aquí el pie lleva BAJA_MARCADOR si se pide con --baja.

Uso:
    python tools/semana_email.py                      # la última semana congelada
    python tools/semana_email.py --semana 2026-S40 --salida /tmp/correo
        -> /tmp/correo/2026-S40.html y /tmp/correo/2026-S40.txt
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import pathlib
import sys
import textwrap

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import semana  # noqa: E402

SITIO = "https://terceracamara.es"
ANCHO = 600
ROJO = "#c81e2c"
TINTA = "#1a1a1a"
GRIS = "#5c5c5c"
FONDO = "#f4f1ea"
FUENTE = "Georgia, 'Times New Roman', serif"
SANS = "Arial, Helvetica, sans-serif"


def _esc(t) -> str:
    return html.escape(str(t or ""), quote=True)


def _absoluta(url_sitio: str, fuente: str, raiz: pathlib.Path) -> str:
    """La página del sitio si existe en el render; si no, la fuente oficial."""
    if url_sitio:
        rel = url_sitio.split("#", 1)[0].lstrip("/")
        objetivo = rel + "index.html" if (not rel or rel.endswith("/")) else rel
        if (raiz / objetivo).is_file():
            return SITIO + "/" + url_sitio.lstrip("/")
    return fuente or ""


def bloques(sem: dict, raiz: pathlib.Path = RAIZ) -> list:
    """El contenido común a las dos versiones: [(titulo, nota, [(texto, url, detalle, cita)])]."""
    s = sem["secciones"]
    u = lambda url, fuente="": _absoluta(url, fuente, raiz)          # noqa: E731
    fecha = semana._fecha_corta
    salida = []
    if s.get("normas"):
        salida.append(("Leyes y reales decretos en el BOE", "", [
            (n["titulo"], u(n["url"], n["fuente"]),
             f"{n['rango']} · BOE del {fecha(n['fecha'])}"
             + (f" · Titular editorial (IA): «{n['editorial']}»" if n.get("editorial") else ""), "")
            for n in s["normas"]]))
    vt = s.get("votaciones") or {}
    if vt.get("ajustadas"):
        salida.append(("Las votaciones más ajustadas",
                       f"De las {vt['total']} votaciones del Pleno con detalle nominal.", [
            (v["asunto"], u(v["url"], v["fuente"]),
             f"{fecha(v['f'])} · {v['tot'][0]} sí, {v['tot'][1]} no, {v['tot'][2]} abstenciones · "
             f"diferencia de {v['margen']} voto{'s' if v['margen'] != 1 else ''}", "")
            for v in vt["ajustadas"]]))
    if vt.get("disidencias"):
        salida.append(("Votos distintos a los de su grupo", "", [
            (v["asunto"], u(v["url"], v["fuente"]),
             f"{fecha(v['f'])} · " + "; ".join(
                 f"{p['nombre']} ({p['grupo']}): {semana.VOTO[p['voto']]}, su grupo "
                 f"{semana.VOTO[p['voto_grupo']]}" for p in v["personas"][:12]), "")
            for v in vt["disidencias"]]))
    pr = s.get("preguntas") or {}
    if pr.get("orales"):
        salida.append(("Lo que se preguntó en la sesión de control",
                       f"Preguntas orales tal como se formularon ({pr['n_orales']} en la semana).", [
            (f"«{o['texto']}»", u(o["url"]),
             f"{o['autor']}{' (' + o['grupo'] + ')' if o['grupo'] else ''} · contesta {o['contesta']}", "")
            for o in pr["orales"]]))
    if pr.get("contestadas"):
        salida.append(("Respuestas escritas publicadas",
                       f"{pr['n_contestadas']} contestaciones registradas; aquí, las que más tardaron.", [
            (q["titulo"], q["url"],
             f"{q['exp']} · {q['grupo']} · contestada el {fecha(q['contestada'])}"
             + (f", {q['dias']} días después de publicarse" if q.get("dias") is not None else ""),
             q.get("cita", "")) for q in pr["contestadas"]]))
    if pr.get("pendientes"):
        p = pr["pendientes"]
        salida.append(("Pendientes con el plazo superado",
                       f"Al cierre del domingo, {p['total']} preguntas escritas tenían la fecha límite de la "
                       f"ficha oficial superada y ninguna contestación registrada. No se presenta como un "
                       f"incumplimiento: puede haber prórrogas o contestaciones pendientes de reflejarse.", [
            (q["titulo"], q["url"], f"{q['exp']} · {q['grupo']} · fecha límite {fecha(q['limite'])}", "")
            for q in p["lista"]]))
    if s.get("tramitacion"):
        salida.append(("Cambios en la tramitación", "", [
            (f"{t['tipo']}: {t['titulo']}", u(t["url"], t["fuente"]), f"{fecha(t['f'])} · {t['hito']}", "")
            for t in s["tramitacion"]]))
    nb = s.get("nombramientos") or {}
    if nb.get("lista"):
        salida.append(("Nombramientos y ceses",
                       f"{nb['total']} en el BOE de la semana; aquí, los de real decreto, orden o acuerdo.", [
            (n["persona"], u(n["url"], n["fuente"]),
             f"{n['acto'].capitalize()} · {n['cargo']}{' · ' + n['emisor'] if n['emisor'] else ''}", "")
            for n in nb["lista"]]))
    return salida


def _a(texto: str, url: str, estilo: str) -> str:
    if not url:
        return _esc(texto)
    return f'<a href="{_esc(url)}" style="{estilo}">{_esc(texto)}</a>'


def html_correo(sem: dict, raiz: pathlib.Path = RAIZ, baja: str = "") -> str:
    url_semana = f"{SITIO}/semana/{sem['semana']}.html"
    tit = semana.titulo(sem)
    filas = []
    c = sem["secciones"].get("cifra")
    if c:
        filas.append(
            f'<tr><td style="padding:20px 24px;background:{TINTA};color:#ffffff;font-family:{SANS};">'
            f'<p style="margin:0 0 4px;font-size:12px;letter-spacing:1px;text-transform:uppercase;color:#f0b7bc;">'
            f'La cifra de la semana</p>'
            f'<p style="margin:0;font-size:40px;line-height:44px;font-weight:bold;">{c["valor"]}</p>'
            f'<p style="margin:6px 0 0;font-size:15px;line-height:21px;">{_esc(c["texto"])}'
            + (f': «{_esc(c["asunto"])}»' if c.get("asunto") else "") + '.</p></td></tr>')
    for titulo_b, nota, items in bloques(sem, raiz):
        lista = "".join(
            f'<tr><td style="padding:0 0 14px;font-family:{FUENTE};font-size:16px;line-height:23px;color:{TINTA};">'
            + _a(texto, url, f"color:{TINTA};text-decoration:underline;")
            + f'<br><span style="font-family:{SANS};font-size:12px;line-height:17px;color:{GRIS};">{_esc(det)}</span>'
            + (f'<br><span style="font-family:{FUENTE};font-style:italic;font-size:14px;line-height:20px;'
               f'color:{GRIS};">«{_esc(cita)}»</span>' if cita else "")
            + '</td></tr>' for texto, url, det, cita in items)
        filas.append(
            f'<tr><td style="padding:22px 24px 6px;">'
            f'<h2 style="margin:0 0 6px;font-family:{SANS};font-size:13px;letter-spacing:1px;'
            f'text-transform:uppercase;color:{ROJO};">{_esc(titulo_b)}</h2>'
            + (f'<p style="margin:0 0 12px;font-family:{SANS};font-size:13px;line-height:18px;color:{GRIS};">'
               f'{_esc(nota)}</p>' if nota else "")
            + f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{lista}</table>'
            '</td></tr>')
    pie = (f'Lo que va entre comillas es literal de la fuente oficial. Resumen construido con reglas fijas, '
           f'mismo trato para todos los grupos. <a href="{url_semana}" style="color:{GRIS};">Ver en la web</a> · '
           f'<a href="{SITIO}/privacidad.html" style="color:{GRIS};">Privacidad</a>'
           + (f' · <a href="{_esc(baja)}" style="color:{GRIS};">Darse de baja</a>' if baja else ""))
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>{_esc(tit)}</title>
</head>
<body style="margin:0;padding:0;background:{FONDO};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{FONDO};">
<tr><td align="center" style="padding:16px 8px;">
<table role="presentation" width="{ANCHO}" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:{ANCHO}px;background:#ffffff;">
<tr><td style="padding:20px 24px 14px;border-top:6px solid {ROJO};">
<p style="margin:0;font-family:{SANS};font-size:22px;font-weight:bold;letter-spacing:1px;color:{TINTA};">LA TERCERA <span style="color:{ROJO};">CÁMARA</span></p>
<h1 style="margin:10px 0 0;font-family:{FUENTE};font-size:22px;line-height:28px;font-weight:normal;color:{TINTA};">{_esc(tit)}</h1>
</td></tr>
{"".join(filas)}
<tr><td style="padding:18px 24px 24px;border-top:1px solid #e3ded3;font-family:{SANS};font-size:12px;line-height:18px;color:{GRIS};">{pie}</td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""


def texto_correo(sem: dict, raiz: pathlib.Path = RAIZ, baja: str = "") -> str:
    envolver = lambda t, sangria="": textwrap.fill(t, 72, initial_indent=sangria,                 # noqa: E731
                                                   subsequent_indent=sangria)
    lineas = ["LA TERCERA CÁMARA", envolver(semana.titulo(sem)), "=" * 72, ""]
    c = sem["secciones"].get("cifra")
    if c:
        lineas += ["LA CIFRA DE LA SEMANA",
                   envolver(f"{c['valor']} {c['texto']}" + (f": «{c['asunto']}»" if c.get("asunto") else "") + "."),
                   ""]
    for titulo_b, nota, items in bloques(sem, raiz):
        lineas += [titulo_b.upper(), "-" * len(titulo_b)]
        if nota:
            lineas += [envolver(nota), ""]
        for texto, url, det, cita in items:
            lineas.append(textwrap.fill(texto, 72, initial_indent="* ", subsequent_indent="  "))
            lineas.append(envolver(det, "  "))
            if cita:
                lineas.append(envolver(f"«{cita}»", "  "))
            if url:
                lineas.append(f"  {url}")
            lineas.append("")
    lineas += ["-" * 72,
               envolver("Lo que va entre comillas es literal de la fuente oficial. Resumen construido con "
                        "reglas fijas, mismo trato para todos los grupos."),
               f"En la web: {SITIO}/semana/{sem['semana']}.html",
               f"Privacidad: {SITIO}/privacidad.html"]
    if baja:
        lineas.append(f"Darse de baja: {baja}")
    return "\n".join(lineas) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Versión para correo del resumen semanal.")
    ap.add_argument("--semana", help="AAAA-Snn; por defecto, la última congelada")
    ap.add_argument("--salida", default=str(RAIZ / "debug" / "correo"), help="carpeta de salida")
    ap.add_argument("--baja", default="", help="URL o marcador del enlace de baja del proveedor")
    args = ap.parse_args(argv)
    sem = semana.cargar(args.semana) if args.semana else next(iter(semana.todas()), None)
    if not sem:
        print("No hay ninguna semana congelada en data/semanas/.")
        return 1
    salida = pathlib.Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    (salida / f"{sem['semana']}.html").write_text(html_correo(sem, RAIZ, args.baja), encoding="utf-8")
    (salida / f"{sem['semana']}.txt").write_text(texto_correo(sem, RAIZ, args.baja), encoding="utf-8")
    print(f"Correo de la semana {sem['semana']} en {salida}/ ({sem['semana']}.html y .txt).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
