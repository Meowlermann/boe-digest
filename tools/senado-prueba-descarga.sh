#!/usr/bin/env bash
# Prueba de lectura de los ficheros abiertos del Senado desde un runner
# de GitHub Actions. No publica, no escribe en datos/ ni en Pages.
# Guarda código HTTP, cabeceras, tamaño, primeros bytes y si el XML es válido.
set -euo pipefail

OUT="${SENADO_PRUEBA_DIR:-${RUNNER_TEMP:-/tmp}/senado-prueba}"
mkdir -p "$OUT"
# Identificación propia; no se imita un navegador para esquivar el bloqueo.
UA="boe-digest-prueba-descarga/1.0 (+https://github.com/Meowlermann/boe-digest)"
BASE="https://www.senado.es/web/ficopendataservlet"

# tipoFich documentados en el catálogo de datos.gob.es y en OpenSpain para la
# XV legislatura, más la votación de la sesión 60 que cita el estudio.
# Se pide legis=15 en el servlet también en los que el catálogo publica a
# veces sin legislatura (agenda, hemiciclo).
URLS=(
  "tipoFich4-composicion ${BASE}?tipoFich=4&legis=15"
  "tipoFich5-organigrama ${BASE}?tipoFich=5&legis=15"
  "tipoFich7-comisiones ${BASE}?tipoFich=7&legis=15"
  "tipoFich9-iniciativas ${BASE}?tipoFich=9&legis=15"
  "tipoFich10-fichas-composicion ${BASE}?tipoFich=10&legis=15"
  "tipoFich14-sesiones ${BASE}?tipoFich=14&legis=15"
  "tipoFich15-interpelaciones ${BASE}?tipoFich=15&legis=15"
  "tipoFich16-mociones ${BASE}?tipoFich=16&legis=15"
  "tipoFich17-tesauro ${BASE}?tipoFich=17&legis=15"
  "tipoFich18-leyes ${BASE}?tipoFich=18&legis=15"
  "tipoFich19-agenda ${BASE}?tipoFich=19&legis=15"
  "tipoFich20-hemiciclo ${BASE}?tipoFich=20&legis=15"
  "votaciones-ses60 https://www.senado.es/legis15/votaciones/ses_60.xml"
)

validar_xml() {
  python3 - "$1" << 'PY'
import sys
from pathlib import Path
from xml.etree import ElementTree as ET
raw = Path(sys.argv[1]).read_bytes()
try:
    ET.fromstring(raw)
except ET.ParseError as exc:
    print(f"invalido: {exc}")
    sys.exit(2)
except Exception as exc:
    print(f"invalido: {exc}")
    sys.exit(2)
print("valido")
PY
}

primeros_bytes() {
  python3 - "$1" << 'PY'
import sys
from pathlib import Path
b = Path(sys.argv[1]).read_bytes()[:200]
print(b.decode("utf-8", errors="replace").replace("\n", "\\n"))
PY
}

RESUMEN="$OUT/resumen.txt"
{
  echo "Prueba de descarga del Senado"
  echo "Fecha (UTC): $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "Runner: ${RUNNER_NAME:-local} ${RUNNER_OS:-} ${RUNNER_ARCH:-}"
  echo
} > "$RESUMEN"

for item in "${URLS[@]}"; do
  nombre="${item%% *}"
  url="${item#* }"
  cuerpo="$OUT/${nombre}.cuerpo"
  cabeceras="$OUT/${nombre}.cabeceras"
  meta="$OUT/${nombre}.meta.txt"
  # Un solo GET por URL, sin reintentos agresivos ni proxies.
  # Un 403 es un resultado útil, no un fallo del script.
  set +e
  http=$(curl -sS -L --max-time 60 --compressed \
    -A "$UA" \
    -D "$cabeceras" \
    -o "$cuerpo" \
    -w "%{http_code}" \
    "$url")
  curl_rc=$?
  set -e
  size=0
  [[ -f "$cuerpo" ]] && size=$(wc -c < "$cuerpo" | tr -d ' ')
  primeros=""
  [[ -f "$cuerpo" && "$size" -gt 0 ]] && primeros=$(primeros_bytes "$cuerpo")
  xml_estado="sin_cuerpo"
  if [[ -f "$cuerpo" && "$size" -gt 0 ]]; then
    set +e
    xml_out=$(validar_xml "$cuerpo")
    set -e
    xml_estado="$xml_out"
  fi
  {
    echo "nombre: $nombre"
    echo "url: $url"
    echo "curl_rc: $curl_rc"
    echo "http: $http"
    echo "bytes: $size"
    echo "xml: $xml_estado"
    echo "primeros_bytes:"
    echo "$primeros"
  } > "$meta"
  {
    echo "======= $nombre ======="
    echo "url: $url"
    echo "curl_rc: $curl_rc  http: $http  bytes: $size  xml: $xml_estado"
    echo "primeros: $primeros"
    echo
  } >> "$RESUMEN"
  sleep 1
done

echo "Listo. Salida en $OUT"
cat "$RESUMEN"
