"""Reprocesado del histórico del BOE: una descarga del sumario por día y
varios extractores que la aprovechan.

Antes cada extractor (nombramientos) tenía su propio bucle de descargas. Con
un segundo extractor (provincias) eso duplicaba las peticiones al BOE para los
mismos días. Aquí el sumario de cada día se pide UNA vez a la API de datos
abiertos, con las secciones que pidan entre todos, y se entrega a cada
extractor. Solo toca los ficheros de state/: ni data/ ni las ediciones.

Un extractor es un módulo con:
  - SECCIONES: códigos de sección de la API que necesita («1», «2A», «3»…);
  - procesar_dia(entradas, fecha, fuente, log) -> (incluidos, descartes),
    que extrae y guarda en su estado de forma idempotente.
"""

from __future__ import annotations

import datetime as dt
import importlib
import time

API_SUMARIO = "https://www.boe.es/datosabiertos/api/boe/sumario/{aaaammdd}"
EXTRACTORES = ("nombramientos", "provincias")


def sumario_api(fecha: dt.date, get, log=print, secciones=("2A", "2B")) -> list[dict] | None:
    """Las entradas de las secciones pedidas del sumario, de la API de datos
    abiertos. None si la API no responde (festivo, domingo o caída)."""
    r = get(API_SUMARIO.format(aaaammdd=fecha.strftime("%Y%m%d")), tries=2,
            headers={"Accept": "application/json"})
    if not r:
        return None
    try:
        datos = r.json()["data"]["sumario"]
    except Exception as exc:                                  # noqa: BLE001
        log(f"sumario: la API del BOE no devolvió JSON legible ({exc})")
        return None

    def lista(x):
        return x if isinstance(x, list) else ([x] if x else [])

    entradas = []
    for diario in lista(datos.get("diario")):
        for sec in lista(diario.get("seccion")):
            if sec.get("codigo") not in secciones:
                continue
            for dep in lista(sec.get("departamento")):
                # Los elementos pueden colgar del departamento o de un epígrafe.
                grupos = [(ep.get("nombre", ""), lista(ep.get("item")))
                          for ep in lista(dep.get("epigrafe"))]
                grupos.append(("", lista(dep.get("item"))))
                for epigrafe, items in grupos:
                    for it in items:
                        pdf = it.get("url_pdf") or {}
                        try:
                            paginas = int(pdf.get("pagina_final")) - int(pdf.get("pagina_inicial")) + 1
                        except (TypeError, ValueError):
                            paginas = 0
                        entradas.append({
                            "codigo": sec.get("codigo"),
                            "seccion": sec.get("nombre", ""),
                            "dept": dep.get("nombre", ""),
                            "epigrafe": epigrafe,
                            "titulo": it.get("titulo", ""),
                            "ident": it.get("identificador", ""),
                            "url": it.get("url_html") or "",
                            "paginas": paginas,
                        })
    return entradas


def reprocesar(desde: dt.date, hasta: dt.date, get, log=print, pausa: float = 1.5,
               extractores=("nombramientos",)) -> dict:
    """Recorre los sumarios de `desde` a `hasta` y pasa cada uno a los
    extractores pedidos. Devuelve los totales de cada extractor. La pausa es
    entre días: respeto a la web del BOE, como el resto del pipeline."""
    mods = {n: importlib.import_module(n) for n in extractores}
    secciones = tuple(sorted({s for m in mods.values() for s in m.SECCIONES}))
    totales = {n: {"dias": 0, "incluidos": 0, "sin_boe": 0, "descartes": {}} for n in mods}
    d = desde
    while d <= hasta:
        entradas = sumario_api(d, get, log, secciones)
        for n, m in mods.items():
            t = totales[n]
            if entradas is None:
                t["sin_boe"] += 1
                continue
            propias = [e for e in entradas if e.get("codigo") in m.SECCIONES]
            incluidos, descartes = m.procesar_dia(propias, d, "api", log)
            t["dias"] += 1
            t["incluidos"] += incluidos
            for k, v in (descartes or {}).items():
                t["descartes"][k] = t["descartes"].get(k, 0) + v
        if entradas is None:
            log(f"sumario {d}: sin sumario (domingo, festivo o API caída)")
        time.sleep(pausa)
        d += dt.timedelta(days=1)
    for n, m in mods.items():
        if hasattr(m, "resumen_reproceso"):
            totales[n].update(m.resumen_reproceso())
        log(f"{n}: reprocesado {desde} → {hasta}: {totales[n]}")
    return totales
