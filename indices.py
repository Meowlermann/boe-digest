"""Piezas comunes de las páginas índice (normas, plazos, materias…).

Antes cada índice era la misma caja gris con una lista de viñetas. Aquí están
los componentes que las sustituyen, todos HTML estático generado aquí:

  - cifras(): la fila de cifras grandes bajo la entradilla;
  - barra_filtro(): el buscador instantáneo y los chips por tipo, que filtra
    en el navegador las filas marcadas con data-f (tipo) y data-t (texto).
    Lo hace assets/indices.js; sin JavaScript la lista se ve entera;
  - fila(): una tarjeta por elemento, con toda la fila como enlace;
  - series(): agrupa disposiciones casi idénticas del mismo día y del mismo
    órgano (las dieciséis de la Fiesta Nacional en embajadas) para plegarlas
    en una sola tarjeta. Es determinista: misma firma de título, no parecido.

Nada de esto lleva modelos ni dependencias. Las clases van con prefijo ix- en
assets/style.css.
"""
from __future__ import annotations

import re

SCRIPT = '<script src="/assets/indices.js" defer></script>'
MIN_SERIE = 3        # por debajo de esto no se pliega nada


def _e(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def cifras(items: list[tuple]) -> str:
    """[(valor, etiqueta, acento?)] -> fila de cifras. La primera con acento
    va en rojo: es la que responde a la pregunta de la página."""
    return '<div class="ix-cifras">' + "".join(
        f'<div class="ix-cifra{" ix-acento" if ac else ""}"><b>{_e(v)}</b><span>{_e(l)}</span></div>'
        for v, l, ac in items) + '</div>'


def barra_filtro(chips: list[tuple], placeholder: str) -> str:
    """chips = [(clave, etiqueta, n, token_color|'')]; la primera es «todas» (*)."""
    botones = "".join(
        f'<button type="button" data-f="{_e(k)}" aria-pressed="{"true" if i == 0 else "false"}"'
        + (f' style="--c:var(--{c})" class="ix-punto"' if c else "")
        + f'>{_e(l)} <b>{n}</b></button>'
        for i, (k, l, n, c) in enumerate(chips))
    return ('<div class="ix-filtro" hidden><label class="ix-busca">'
            '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/>'
            '<path d="m20 20-3.5-3.5"/></svg>'
            f'<input type="search" placeholder="{_e(placeholder)}" aria-label="Filtrar la lista"></label>'
            + (f'<div class="ix-chips" role="group" aria-label="Filtrar por tipo">{botones}</div>'
               if len(chips) > 2 else "")
            + '<span class="ix-n" aria-live="polite"></span></div>')


def grupo(titulo: str, n: int, filas: str, ancla: str = "") -> str:
    return (f'<section class="ix-grupo"{f" id={chr(34)}{_e(ancla)}{chr(34)}" if ancla else ""}>'
            f'<h2 class="ix-gh">{_e(titulo)} <span>{n}</span></h2>'
            f'<ol class="ix-lista">{filas}</ol></section>')


def texto_filtro(*partes: str) -> str:
    return " ".join(p for p in partes if p).lower()


def fila(href: str, titular: str, meta: list[str], *, tipo: str = "", texto: str = "",
         clase: str = "", color: str = "", antes: str = "", despues: str = "",
         externo: bool = False, ancla: str = "") -> str:
    """Una tarjeta. `meta` son fragmentos YA escapados (pueden llevar <span>)."""
    attrs = f' class="ix-fila{(" " + clase) if clase else ""}"'
    if ancla:
        attrs += f' id="{_e(ancla)}"'
    if tipo:
        attrs += f' data-f="{_e(tipo)}"'
    attrs += f' data-t="{_e(texto or titular.lower())}"'
    if color:
        attrs += f' style="--c:var(--{color})"'
    destino = ' target="_blank" rel="noopener"' if externo else ""
    return (f'<li{attrs}>{antes}<div class="ix-cuerpo">'
            f'<a class="ix-tit" href="{_e(href)}"{destino}>{_e(titular)}</a>'
            + (f'<div class="ix-meta">{"".join(meta)}</div>' if meta else "")
            + f'{despues}</div></li>')


def etiqueta(texto: str, clase: str = "") -> str:
    return f'<span class="ix-tag{(" " + clase) if clase else ""}">{_e(texto)}</span>'


def organo(dept: str, limite: int = 70) -> str:
    """«MINISTERIO DE HACIENDA» -> «Ministerio de Hacienda», sin gritar."""
    if not dept:
        return ""
    t = dept.title()
    for w in ("De", "Del", "La", "Las", "Los", "El", "Y", "E", "Para", "Con", "En", "A"):
        t = re.sub(rf"(?<=\s){w}(?=\s)", w.lower(), t)
    return t if len(t) <= limite else t[:limite - 1].rstrip() + "…"


_FECHA = re.compile(r"\bde \d{1,2} de [a-záéíóú]+ de \d{4},?", re.I)
_PAL = re.compile(r"[\wÁÉÍÓÚÑáéíóúñü]+")


def firma_serie(titulo_oficial: str, dept: str) -> tuple | None:
    """Mismo órgano, mismo arranque y mismo final del título oficial (sin la
    fecha): «Resolución … por la que se publica el Convenio entre la Embajada
    de España en X y Y, para la celebración de la Fiesta Nacional de España».
    Títulos cortos no forman serie: se parecen demasiado por casualidad."""
    pal = _PAL.findall(_FECHA.sub(" ", titulo_oficial or "").lower())
    if len(pal) < 15:
        return None
    return (dept or "", " ".join(pal[:8]), " ".join(pal[-6:]))


def series(elementos: list, firma) -> list[list]:
    """Agrupa conservando el orden de la primera aparición. Devuelve una lista
    de grupos; los de un solo elemento se quedan como están."""
    grupos: dict = {}
    orden: list = []
    for x in elementos:
        k = firma(x)
        if k is None:
            orden.append([x])
            continue
        if k not in grupos:
            grupos[k] = [x]
            orden.append(grupos[k])
        else:
            grupos[k].append(x)
    salida = []
    for g in orden:
        if len(g) >= MIN_SERIE:
            salida.append(g)
        else:
            salida.extend([x] for x in g)
    return salida


def fila_serie(grupo_: list, titular, href, ref, *, tipo: str, color: str, meta_extra: str) -> str:
    """Una tarjeta apilada que se despliega con las N disposiciones."""
    x0 = grupo_[0]
    texto = texto_filtro(*(titular(x) + " " + ref(x) for x in grupo_), meta_extra.lower())
    items = "".join(
        f'<li><a href="{_e(href(x))}">{_e(titular(x))}</a><span class="ix-mono">{_e(ref(x))}</span></li>'
        for x in grupo_)
    return (f'<li class="ix-fila ix-serie" data-f="{_e(tipo)}" data-t="{_e(texto)}"'
            + (f' style="--c:var(--{color})"' if color else "") + '>'
            f'<details><summary><div class="ix-cuerpo"><span class="ix-tit">{_e(titular(x0))}</span>'
            f'<div class="ix-meta">{etiqueta(f"Serie · {len(grupo_)} disposiciones", "ix-cat")}'
            f'<span>{_e(meta_extra)}</span><span class="ix-mas">y {len(grupo_) - 1} más como esta</span>'
            f'</div></div></summary><ol class="ix-sub">{items}</ol></details></li>')


def histograma(conteos: list[int], etiquetas: list[str], anclas: list[str], titulo: str,
               marcas: dict[int, str]) -> str:
    """Barras por día con enlace a cada día; `marcas` = {índice: rótulo del eje}."""
    mx = max(conteos or [0]) or 1
    barras = "".join(
        f'<a class="ix-hb{" ix-hoy" if i == 0 else ""}" href="#{_e(a)}" data-n="{n}" '
        f'style="--h:{n / mx * 100:.0f}%" title="{_e(e)}: {n}"><i></i></a>'
        if n else f'<span class="ix-hb" data-n="0" title="{_e(e)}: 0"><i></i></span>'
        for i, (n, e, a) in enumerate(zip(conteos, etiquetas, anclas)))
    eje = "".join(f'<span style="left:{i / len(conteos) * 100:.2f}%">{_e(t)}</span>'
                  for i, t in marcas.items() if i / len(conteos) < .88)   # que no se corte al borde
    return (f'<figure class="ix-hist"><figcaption>{_e(titulo)}</figcaption>'
            f'<div class="ix-hbars">{barras}</div><div class="ix-heje">{eje}</div></figure>')
