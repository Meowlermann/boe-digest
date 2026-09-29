"""Diagnóstico de acceso al Senado desde GitHub Actions.

Pide cada URL una vez, con un User-Agent que dice quién pide (no se hace pasar
por un navegador), y apunta código HTTP, cabecera Server, tipo y tamaño. No
reintenta ni cambia de IP ni de cabeceras: el objetivo es saber qué vías
normales de acceso responden desde un servidor, no rodear un bloqueo.

Se ejecuta con .github/workflows/senado-diagnostico.yml y escribe una tabla
en el resumen del job y en debug/senado-diagnostico.json (como artefacto).
"""
import datetime as dt
import json
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build  # noqa: E402

UA = "terceracamara-diagnostico/1.0 (+https://terceracamara.es; datos@terceracamara.es)"
OPENDATA = "https://www.senado.es/web/ficopendataservlet?tipoFich={t}&legis=15"

URLS = [
    ("Índice de boletines (SENADO_IDX)", build.SENADO_IDX),
    *[(f"BOCG Senado núm. {n} (SENADO_PDF)", build.SENADO_PDF.format(n=n))
      for n in build._numeros_probables(dt.date.today())[:3]],
    ("Datos abiertos: sesiones plenarias", OPENDATA.format(t=14)),
    ("Datos abiertos: iniciativas legislativas", OPENDATA.format(t=9)),
    ("Datos abiertos: interpelaciones", OPENDATA.format(t=15)),
    ("Datos abiertos: mociones", OPENDATA.format(t=16)),
    ("Datos abiertos: composición del hemiciclo", "https://www.senado.es/web/ficopendataservlet?tipoFich=20"),
    ("Datos abiertos: catálogo (página)",
     "https://www.senado.es/web/relacionesciudadanos/datosabiertos/catalogodatos/index.html"),
    ("Datos abiertos: fichero estático /opendata/", "https://www.senado.es/opendata/chis1.xml"),
    ("Dominio sin www", "https://senado.es/"),
]


def probar(nombre, url):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30, allow_redirects=True)
        cuerpo = r.content
        real = r.status_code == 200 and len(cuerpo) > 2000 and b"Access Denied" not in cuerpo[:3000]
        return {"nombre": nombre, "url": url, "codigo": r.status_code,
                "server": r.headers.get("Server", ""), "tipo": r.headers.get("Content-Type", ""),
                "bytes": len(cuerpo), "contenido_real": real, "final": r.url if r.url != url else ""}
    except Exception as exc:                                  # noqa: BLE001
        return {"nombre": nombre, "url": url, "codigo": None, "error": str(exc)[:200]}


def main():
    filas = [probar(n, u) for n, u in URLS]
    os.makedirs("debug", exist_ok=True)
    with open("debug/senado-diagnostico.json", "w", encoding="utf-8") as f:
        json.dump({"fecha": dt.datetime.now(dt.timezone.utc).isoformat(), "via": "directa",
                   "user_agent": UA, "resultados": filas}, f, ensure_ascii=False, indent=2)
    tabla = ["| URL | Código | Server | Tipo | Bytes | ¿Contenido real? |", "|---|---|---|---|---|---|"]
    for x in filas:
        tabla.append(f"| {x['nombre']} | {x.get('codigo') or x.get('error', '')} | {x.get('server', '')} | "
                     f"{(x.get('tipo') or '')[:30]} | {x.get('bytes', '')} | "
                     f"{'sí' if x.get('contenido_real') else 'no'} |")
    texto = "\n".join(tabla)
    print(texto)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write("## Senado: acceso directo desde Actions\n\n" + texto + "\n")


if __name__ == "__main__":
    main()
