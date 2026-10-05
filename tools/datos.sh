#!/usr/bin/env bash
# Acceso a los datos acumulados (data/, state/, debug/).
#
# Hoy viven en la rama huérfana «datos» del propio repositorio. Este script es
# el ÚNICO sitio que sabe dónde están: build.py los lee y escribe en ./data,
# ./state y ./debug como siempre. Cuando en la fase B pasen a almacenamiento
# externo, se cambia este fichero y nada más.
#
#   bash tools/datos.sh traer
#       Copia data/, state/ y debug/ de la rama datos al árbol de trabajo.
#       Si la rama no existe todavía, deja los que haya en el checkout y lo
#       dice (la crea `guardar` la primera vez).
#
#   bash tools/datos.sh guardar "mensaje del commit"
#       Hace commit de data/, state/ y debug/ en la rama datos y push, con
#       pull --rebase previo y un reintento. Si la rama no existe, la crea
#       huérfana con un primer commit «Datos iniciales» (el contenido que
#       había ANTES de este pase, guardado por `traer`) y encima el del pase.
#       Nunca toca main.
#
# Variables: DATOS_RAMA (por defecto «datos»; publicar.yml pone
# «datos-pruebas» fuera de main), DATOS_RAMA_BASE (de dónde se leen si
# DATOS_RAMA no existe; por defecto «datos»), DATOS_CLON (carpeta de trabajo
# de la rama; por defecto $RUNNER_TEMP/datos), DATOS_README (README de la
# rama; por defecto tools/LEEME-datos.md).
set -euo pipefail

RAMA="${DATOS_RAMA:-datos}"
# Si RAMA no existe, se leen los datos de esta (las pruebas fuera de main
# escriben en «datos-pruebas» partiendo de «datos», sin tocarla).
BASE="${DATOS_RAMA_BASE:-datos}"
CLON="${DATOS_CLON:-${RUNNER_TEMP:-/tmp}/datos}"
README="${DATOS_README:-tools/LEEME-datos.md}"
CARPETAS=(data state debug)
INICIAL="${CLON}.inicial"     # copia de lo que había antes del pase, para «Datos iniciales»

existe_rama() {
  git ls-remote --exit-code --heads origin "$RAMA" >/dev/null 2>&1
}

copiar() {   # copiar ORIGEN DESTINO: sustituye data/, state/ y debug/ de DESTINO
  for c in "${CARPETAS[@]}"; do
    rm -rf "${2:?}/$c"
    if [ -d "$1/$c" ]; then cp -a "$1/$c" "$2/$c"; else mkdir -p "$2/$c"; fi
  done
}

traer() {
  rm -rf "$CLON" "$INICIAL"
  git worktree prune
  if existe_rama; then
    # Historia completa: es pequeña y la necesita verificar.py para medir la rama.
    git fetch --quiet origin "+refs/heads/$RAMA:refs/remotes/origin/$RAMA"
    git worktree add --quiet --force -B "$RAMA" "$CLON" "origin/$RAMA"
    copiar "$CLON" .
    echo "datos: data/, state/ y debug/ traídos de la rama $RAMA ($(git -C "$CLON" rev-parse --short HEAD))."
  elif [ -n "$BASE" ] && [ "$BASE" != "$RAMA" ] && git ls-remote --exit-code --heads origin "$BASE" >/dev/null 2>&1; then
    # Rama de pruebas sin crear: se parte de los datos de producción, que se
    # leen pero no se tocan.
    git fetch --quiet --depth 1 origin "+refs/heads/$BASE:refs/remotes/origin/$BASE"
    git worktree add --quiet --detach "$CLON.base" "origin/$BASE"
    copiar "$CLON.base" .
    git worktree remove --force "$CLON.base"
    mkdir -p "$INICIAL"
    copiar . "$INICIAL"
    echo "datos: la rama $RAMA no existe; se parte de $BASE (solo lectura)."
  else
    mkdir -p "$INICIAL"
    copiar . "$INICIAL"
    echo "datos: la rama $RAMA no existe todavía; se usan los datos del checkout."
  fi
}

guardar() {
  local mensaje="${1:?mensaje del commit}"
  git config --global user.name "${GIT_AUTHOR_NAME:-BOE Digest bot}"
  git config --global user.email "${GIT_AUTHOR_EMAIL:-41898282+github-actions[bot]@users.noreply.github.com}"
  if [ ! -d "$CLON" ]; then
    if existe_rama; then
      echo "datos: la rama $RAMA ya existe pero no se trajo en este pase; no se guarda nada." >&2
      return 1
    fi
    # Primera vez: rama huérfana con lo que había antes del pase.
    git worktree add --quiet --detach "$CLON"
    git -C "$CLON" checkout --quiet --orphan "$RAMA"
    git -C "$CLON" rm -rf --quiet . >/dev/null 2>&1 || true
    find "$CLON" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
    copiar "${INICIAL}" "$CLON"
    cp "$README" "$CLON/README.md"
    git -C "$CLON" add -A
    git -C "$CLON" commit --quiet -m "Datos iniciales"
    echo "datos: creada la rama huérfana $RAMA con «Datos iniciales»."
  fi
  copiar . "$CLON"
  git -C "$CLON" add -A "${CARPETAS[@]}"
  if git -C "$CLON" diff --staged --quiet; then
    echo "datos: sin cambios en data/, state/ ni debug/."
  else
    git -C "$CLON" commit --quiet -m "$mensaje"
  fi
  for intento in 1 2; do
    if existe_rama; then
      git -C "$CLON" pull --quiet --rebase origin "$RAMA" || { git -C "$CLON" rebase --abort || true; }
    fi
    if git -C "$CLON" push --quiet origin "HEAD:refs/heads/$RAMA"; then
      echo "datos: push a $RAMA hecho ($(git -C "$CLON" rev-parse --short HEAD))."
      return 0
    fi
    echo "datos: el push a $RAMA falló (intento $intento)." >&2
    sleep 10
  done
  return 1
}

case "${1:-}" in
  traer) traer ;;
  guardar) shift; guardar "$@" ;;
  *) echo "uso: $0 traer | guardar \"mensaje\"" >&2; exit 2 ;;
esac
