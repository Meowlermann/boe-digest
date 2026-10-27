#!/usr/bin/env python3
"""
Observabilidad de la edición publicada (TC-009). Solo biblioteca estándar.

Dos piezas:

1. `cuenta_mensual()`: cuántos días con BOE se quedaron sin edición, por mes.
   build.py la escribe en datos/estado-ediciones.json, que se publica en
   https://terceracamara.es/datos/estado-ediciones.json.

2. `comprobar_produccion()`: lo que ve un lector en https://terceracamara.es/
   ahora mismo. La lanza .github/workflows/observabilidad.yml una vez al día,
   después del pase de la mañana; si hay un hallazgo grave, abre o comenta la
   incidencia «Edición ausente en producción» (tools/incidencia_salud.sh) y,
   cuando todo vuelve a estar bien, la cierra.

   - Edición del día: si hoy hay BOE, /ediciones/<hoy>.html responde 200.
   - Frescura: la entrada más reciente de /feed.xml es de hoy (o del último
     día con BOE si hoy no lo hay) y la portada enlaza a esa edición.

Cuándo hay BOE (comprobado el 27-10-2026): el BOE se publica de lunes a
sábado; en data/ no falta ninguna edición entre el 01-01-2026 y el
27-10-2026 salvo los domingos. Para el día de hoy se confirma además con la
API de datos abiertos del BOE (/datosabiertos/api/boe/sumario/AAAAMMDD, que
responde 404 si ese día no hay sumario); en la cuenta mensual, que mira
hacia atrás sin red, un día con BOE es cualquier día que no sea domingo.
Caso no cubierto: un sábado o festivo sin BOE cuenta como día sin edición
en la cuenta mensual; la lista `fechas` de cada mes permite revisarlo.

No recoge datos personales: solo lee páginas públicas del propio sitio y el
sumario público del BOE.

Uso:
    python observabilidad.py --markdown salud-produccion.md
    python observabilidad.py --hoy 2026-10-27 --hora 12:00   # fecha simulada
"""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

SITIO = "https://terceracamara.es"
API_SUMARIO = "https://www.boe.es/datosabiertos/api/boe/sumario/{}"
MADRID = ZoneInfo("Europe/Madrid")
# El pase de la mañana es a las 07:40 y tarda unos 15 min; antes de esta hora
# todavía es normal que la edición de hoy no esté.
HORA_LIMITE = dt.time(9, 30)
TIEMPO_ESPERA = 30          # segundos por petición
AGENTE = "TerceraCamara-observabilidad/1.0 (+https://terceracamara.es/)"
ESQUEMA = 1

GRAVE, AVISO = "grave", "aviso"


def dia_con_boe(d: dt.date) -> bool:
    """El BOE se publica de lunes a sábado (ver docstring del módulo)."""
    return d.weekday() != 6


def cuenta_mensual(fechas_con_edicion, desde: dt.date, hasta: dt.date) -> dict:
    """Días con BOE sin edición entre `desde` y `hasta` (incluidos), por mes."""
    hechas = {str(f) for f in fechas_con_edicion}
    meses: dict[str, dict] = {}
    d = desde
    while d <= hasta:
        if dia_con_boe(d):
            mes = meses.setdefault(d.strftime("%Y-%m"), {"dias_con_boe": 0, "sin_edicion": 0, "fechas": []})
            mes["dias_con_boe"] += 1
            if d.isoformat() not in hechas:
                mes["sin_edicion"] += 1
                mes["fechas"].append(d.isoformat())
        d += dt.timedelta(days=1)
    return {
        "esquema": ESQUEMA,
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "criterio": "día con BOE = de lunes a sábado; sin edición = no hay data/<fecha>.json",
        "meses": meses,
    }


def escribir_cuenta(data_dir: pathlib.Path, destino: pathlib.Path, hoy: dt.date) -> dict:
    """La escribe build.py en cada render. Empieza en la primera edición."""
    fechas = sorted(p.stem for p in data_dir.glob("????-??-??.json"))
    if not fechas:
        return {}
    cuenta = cuenta_mensual(fechas, dt.date.fromisoformat(fechas[0]), hoy)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(cuenta, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    return cuenta


# --- Producción ----------------------------------------------------------------

def obtener(url: str) -> tuple[int, str]:
    """(estado HTTP, cuerpo). 0 si no hay respuesta."""
    pet = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept": "application/json, */*"})
    try:
        with urllib.request.urlopen(pet, timeout=TIEMPO_ESPERA) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, ""


def hallazgo(nivel: str, detalle: str, que_hacer: str = "") -> dict:
    if nivel == GRAVE and que_hacer:
        detalle = f"{detalle} Qué hacer: {que_hacer}"
    return {"nivel": nivel, "detalle": detalle}


def hay_boe(d: dt.date, obtener_url=obtener) -> bool | None:
    """True/False según la API del BOE; None si no responde (se supone L-S)."""
    estado, _ = obtener_url(API_SUMARIO.format(d.strftime("%Y%m%d")))
    if estado == 200:
        return True
    if estado == 404:
        return False
    return None


def fecha_ultima_entrada(feed: str) -> dt.date | None:
    m = re.search(r"<item>.*?<pubDate>([^<]+)</pubDate>", feed, re.S)
    if not m:
        return None
    try:
        return email.utils.parsedate_to_datetime(m.group(1).strip()).astimezone(MADRID).date()
    except (TypeError, ValueError):
        return None


def comprobar_produccion(ahora: dt.datetime, obtener_url=obtener, sitio: str = SITIO) -> list[dict]:
    """Hallazgos sobre la web publicada en el instante `ahora` (hora de Madrid)."""
    hoy = ahora.date()
    hallazgos: list[dict] = []
    if ahora.time() < HORA_LIMITE:
        hallazgos.append(hallazgo(AVISO, f"Son las {ahora:%H:%M}: antes de las {HORA_LIMITE:%H:%M} "
                                         "no se exige la edición de hoy."))
        hoy -= dt.timedelta(days=1)
    boe = hay_boe(hoy, obtener_url)
    if boe is None:
        boe = dia_con_boe(hoy)
        hallazgos.append(hallazgo(AVISO, "La API de datos abiertos del BOE no responde: se supone "
                                         f"que {'hay' if boe else 'no hay'} BOE el {hoy} (lunes a sábado)."))
    # Última fecha con BOE en o antes de `hoy`: es la edición que debe estar.
    esperada = hoy if boe else hoy - dt.timedelta(days=1)
    while not dia_con_boe(esperada):
        esperada -= dt.timedelta(days=1)

    url_ed = f"{sitio}/ediciones/{esperada.isoformat()}.html"
    estado, _ = obtener_url(url_ed)
    if estado != 200:
        hallazgos.append(hallazgo(GRAVE, f"La edición del {esperada} no está publicada: {url_ed} responde "
                                         f"{estado or 'sin respuesta'}.",
                                  "revisa el último run de «Edición diaria» y «Publicar» en Actions; "
                                  "si no corrió, lánzalo con workflow_dispatch."))

    estado, feed = obtener_url(f"{sitio}/feed.xml")
    ultima = fecha_ultima_entrada(feed) if estado == 200 else None
    if ultima is None:
        hallazgos.append(hallazgo(GRAVE, f"/feed.xml no se puede leer (HTTP {estado or 'sin respuesta'}).",
                                  "revisa el último despliegue de «Publicar»."))
    elif ultima < esperada:
        hallazgos.append(hallazgo(GRAVE, f"/feed.xml no está al día: su última entrada es del {ultima} y "
                                         f"debería ser del {esperada} (o posterior).",
                                  "revisa si el último despliegue terminó bien."))

    estado, portada = obtener_url(f"{sitio}/")
    if estado != 200:
        hallazgos.append(hallazgo(GRAVE, f"La portada responde {estado or 'sin respuesta'}.",
                                  "revisa el último despliegue de «Publicar»."))
    elif f"/ediciones/{esperada.isoformat()}.html" not in portada:
        hallazgos.append(hallazgo(GRAVE, f"La portada no enlaza a la edición del {esperada}.",
                                  "revisa si el último despliegue es anterior al pase de hoy."))
    return hallazgos


def markdown(hallazgos: list[dict], ahora: dt.datetime) -> str:
    graves = [h for h in hallazgos if h["nivel"] == GRAVE]
    lineas = [f"Comprobación de producción del {ahora:%Y-%m-%d %H:%M} (hora de Madrid): "
              f"{len(graves)} grave(s), {len(hallazgos) - len(graves)} aviso(s).", ""]
    lineas += [f"- **{h['nivel']}**: {h['detalle']}" for h in hallazgos] or ["- Todo en orden."]
    return "\n".join(lineas) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hoy", help="fecha simulada AAAA-MM-DD (pruebas)")
    ap.add_argument("--hora", default=None, help="hora simulada HH:MM (con --hoy)")
    ap.add_argument("--sitio", default=SITIO)
    ap.add_argument("--markdown", help="fichero con el resumen (cuerpo de la incidencia)")
    a = ap.parse_args(argv)
    ahora = dt.datetime.now(MADRID)
    if a.hoy:
        h, m = (a.hora or "12:00").split(":")
        ahora = dt.datetime.combine(dt.date.fromisoformat(a.hoy), dt.time(int(h), int(m)), MADRID)
    hallazgos = comprobar_produccion(ahora, sitio=a.sitio.rstrip("/"))
    texto = markdown(hallazgos, ahora)
    print(texto)
    if a.markdown:
        pathlib.Path(a.markdown).write_text(texto, encoding="utf-8")
    graves = sum(h["nivel"] == GRAVE for h in hallazgos)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"graves={graves}\nfecha={ahora.date().isoformat()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
