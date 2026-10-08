#!/usr/bin/env bash
# Comprueba los registros DNS de envío de correo de terceracamara.es.
#
#   bash tools/comprobar_dns.sh [dominio]
#
# - SPF: tiene que haber UN ÚNICO registro TXT «v=spf1 …» (con dos, fallan los
#   dos y se deja de recibir el correo de datos@, que reenvía ImprovMX) y debe
#   incluir a ImprovMX (spf.improvmx.com) y a MailerLite (_spf.mlsend.com).
# - DMARC: se informa de lo que haya en _dmarc (recomendado p=none con rua a datos@).
# - DKIM de MailerLite: se informa de litesrv._domainkey si existe.
# Sale con error solo si el SPF no es único o no incluye a los dos.
# Lo lanza .github/workflows/dns.yml; escribe el resumen en GITHUB_STEP_SUMMARY.
set -uo pipefail
DOMINIO="${1:-terceracamara.es}"
SALIDA="${GITHUB_STEP_SUMMARY:-/dev/stdout}"
txt() { dig +short TXT "$1" | sed 's/^"//; s/"$//; s/" "//g'; }

SPF=$(txt "$DOMINIO" | grep -i '^v=spf1' || true)
N=$(printf '%s\n' "$SPF" | grep -c . || true)
DMARC=$(txt "_dmarc.$DOMINIO" | grep -i '^v=DMARC1' || true)
DKIM=$(dig +short TXT "litesrv._domainkey.$DOMINIO" | head -c 120 || true)
MX=$(dig +short MX "$DOMINIO" | sort)

{
  echo "### DNS de correo de $DOMINIO"
  echo
  echo "- Registros SPF: **$N**"
  printf '%s\n' "$SPF" | sed 's/^/  - `/; s/$/`/'
  echo "- DMARC: \`${DMARC:-(ninguno)}\`"
  echo "- DKIM MailerLite (litesrv._domainkey): \`${DKIM:-(ninguno)}\`"
  echo "- MX: $(echo $MX)"
} >> "$SALIDA"

ERROR=0
if [ "$N" -ne 1 ]; then
  echo "::error::Hay $N registros SPF en $DOMINIO: tiene que haber exactamente uno (fusiónalos)."; ERROR=1
fi
echo "$SPF" | grep -qi 'include:spf.improvmx.com' || { echo "::error::El SPF no incluye a ImprovMX (include:spf.improvmx.com)."; ERROR=1; }
echo "$SPF" | grep -qi 'mlsend.com' || { echo "::error::El SPF no incluye a MailerLite (include:_spf.mlsend.com)."; ERROR=1; }
[ -n "$DMARC" ] || echo "::warning::No hay registro DMARC (_dmarc.$DOMINIO)."
exit $ERROR
