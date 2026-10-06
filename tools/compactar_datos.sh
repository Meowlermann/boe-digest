#!/usr/bin/env bash
# Compacta la rama datos: si su historia pasa de MAX_COMMITS commits o de
# MAX_MB megabytes, la reescribe como UN commit con el estado actual (el mismo
# árbol que la punta de ahora) y hace push forzado a esa rama.
#
# Es la ÚNICA excepción a la regla de no forzar push (AGENTS.md): solo esta
# rama, solo desde .github/workflows/compactar-datos.yml, y con
# --force-with-lease contra la punta que se acaba de medir, para no pisar un
# pase que haya escrito entretanto. El contenido no cambia: solo se pierde la
# historia de la rama datos (no la de main).
#
#   bash tools/compactar_datos.sh [--forzar]
set -euo pipefail

RAMA="${DATOS_RAMA:-datos}"
MAX_COMMITS="${MAX_COMMITS:-300}"     # ~100 días a tres pases diarios
MAX_MB="${MAX_MB:-150}"               # historia en disco (git rev-list --disk-usage)
FORZAR="${1:-}"

git fetch --quiet origin "+refs/heads/$RAMA:refs/remotes/origin/$RAMA"
PUNTA=$(git rev-parse "origin/$RAMA")
COMMITS=$(git rev-list --count "origin/$RAMA")
BYTES=$(git rev-list --disk-usage --objects "origin/$RAMA")
MB=$(( BYTES / 1024 / 1024 ))
echo "Rama $RAMA: $COMMITS commits, $MB MB de historia (umbrales: $MAX_COMMITS commits, $MAX_MB MB)."
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  echo "Rama \`$RAMA\`: $COMMITS commits, $MB MB de historia (umbrales: $MAX_COMMITS commits, $MAX_MB MB)." >> "$GITHUB_STEP_SUMMARY"
fi

if [ "$FORZAR" != "--forzar" ] && [ "$COMMITS" -le "$MAX_COMMITS" ] && [ "$MB" -le "$MAX_MB" ]; then
  echo "No hace falta compactar."
  exit 0
fi

git config user.name "${GIT_AUTHOR_NAME:-BOE Digest bot}" 
git config user.email "${GIT_AUTHOR_EMAIL:-41898282+github-actions[bot]@users.noreply.github.com}"
NUEVO=$(git commit-tree "origin/$RAMA^{tree}" \
  -m "Datos compactados el $(date +%Y-%m-%d) ($COMMITS commits, $MB MB de historia)")
# Mismo árbol, sin historia. Solo se fuerza si la rama sigue donde la medimos.
git push --force-with-lease="refs/heads/$RAMA:$PUNTA" origin "$NUEVO:refs/heads/$RAMA"
echo "Compactada: $PUNTA -> $NUEVO."
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  echo "Compactada en un commit: \`$PUNTA\` → \`$NUEVO\`." >> "$GITHUB_STEP_SUMMARY"
fi
