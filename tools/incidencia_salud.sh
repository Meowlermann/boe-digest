#!/usr/bin/env bash
# Abre, actualiza o cierra la incidencia «Salud de la edición» según el
# resultado de tools/verificar.py. Lo llaman daily.yml y archivo.yml con el
# GITHUB_TOKEN del workflow (permissions: issues: write); no usa otro token.
#
#   tools/incidencia_salud.sh <graves> <fecha> <resumen.md>
#
# - Con graves y sin incidencia abierta con la etiqueta «salud»: la abre.
# - Con graves y una ya abierta: comenta en ella con la fecha (no abre otra).
# - Sin graves y una abierta: comenta «Resuelto el <fecha>» y la cierra.
#
# GitHub avisa por correo al dueño del repositorio de las incidencias nuevas
# (si sigue el repositorio, que es lo predeterminado para el dueño): no hace
# falta nada más para recibir el aviso.
set -euo pipefail

GRAVES="${1:?número de graves}"
FECHA="${2:?fecha}"
RESUMEN="${3:?fichero con el resumen en Markdown}"
ETIQUETA="salud"
TITULO="Salud de la edición"
# El cuerpo de una incidencia admite 65.536 caracteres.
MAX_BYTES=60000

gh label create "$ETIQUETA" --force --color D93F0B \
  --description "Hallazgos graves de tools/verificar.py en la edición publicada" >/dev/null

ABIERTA=$(gh issue list --label "$ETIQUETA" --state open --limit 1 \
            --json number --jq '.[0].number // empty')

CUERPO="${RUNNER_TEMP:-/tmp}/incidencia-salud.md"
{
  echo "Hallazgos graves en la edición del **$FECHA** ([ejecución]($GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID))."
  echo
  head -c "$MAX_BYTES" "$RESUMEN"
} > "$CUERPO"

if [ "$GRAVES" -gt 0 ]; then
  if [ -n "$ABIERTA" ]; then
    gh issue comment "$ABIERTA" --body-file "$CUERPO"
    echo "Comentado en la incidencia #$ABIERTA."
  else
    gh issue create --title "$TITULO" --label "$ETIQUETA" --body-file "$CUERPO"
  fi
elif [ -n "$ABIERTA" ]; then
  gh issue comment "$ABIERTA" --body "Resuelto el $FECHA"
  gh issue close "$ABIERTA"
  echo "Incidencia #$ABIERTA cerrada."
else
  echo "Sin graves y sin incidencia abierta: nada que hacer."
fi
