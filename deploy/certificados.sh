#!/usr/bin/env bash
#
# Endereços e HTTPS do MayaFit (um banco por estúdio). Roda como root, pelo instalar.sh e a cada 5 minutos pelo
# timer mayafit-certificados@<amb>.timer:
#
#   sudo bash deploy/certificados.sh prod
#
# 1. Lê os endereços: o principal e o do admin (do .env) + todos os domínios dos estúdios ativos no banco de controle
#    (<slug>.<DOMINIO_BASE> e domínios próprios).
# 2. Para cada endereço sem certificado, pede um ao Let's Encrypt pelo desafio HTTP (webroot). O DNS precisa apontar para
#    este servidor: no *.<DOMINIO_BASE> o registro coringa já resolve; domínio próprio depende do cliente.
#    Quem falhar fica para a próxima volta (no máximo uma tentativa por hora, para não estourar o limite do Let's Encrypt).
# 3. Regera /etc/nginx/sites-available/mayafit-<amb> (porta 80: desafio + redireciona; 443: um bloco por endereço com
#    certificado) e só recarrega o nginx se mudou e se o `nginx -t` aprovar. Sem `map` global, sem default_server:
#    o servidor é compartilhado com outros sistemas.
#
set -euo pipefail

AMB="${1:?informe o ambiente: prod ou hml}"
DIR="/home/deploy/mayafit/$AMB"
ENV="$DIR/backend/.env"
SITE="/etc/nginx/sites-available/mayafit-$AMB"
SNIPPET="/etc/nginx/snippets/mayafit-$AMB-locations.conf"
WEBROOT="/var/www/mayafit-acme"
ESTADO="/var/lib/mayafit-certificados/$AMB"
EMAIL_LE="${EMAIL_LETSENCRYPT:-mayacorp22@gmail.com}"

[ "$(id -u)" = "0" ] || { echo "Rode com sudo."; exit 1; }
[ -f "$ENV" ] || { echo "Não achei $ENV."; exit 1; }
val() { grep -E "^$1=" "$ENV" | tail -1 | cut -d= -f2- | tr -d '"'; }
API_PORTA="$(val API_PORTA)"; WEB_PORTA="$(val WEB_PORTA)"
PRINCIPAL="$(val DOMINIO_PRINCIPAL)"; ADMIN="$(val DOMINIO_ADMIN)"; BASE_DOM="$(val DOMINIO_BASE)"
[ -n "$API_PORTA" ] && [ -n "$WEB_PORTA" ] && [ -n "$PRINCIPAL" ] || { echo "API_PORTA, WEB_PORTA e DOMINIO_PRINCIPAL no .env."; exit 1; }
mkdir -p "$WEBROOT" "$ESTADO" /etc/nginx/snippets

# ---------------------------------------------------------------- endereços
HOSTS="$PRINCIPAL $ADMIN"
if sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='mayafit_controle'" | grep -q 1; then
  HOSTS="$HOSTS $(sudo -u postgres psql -d mayafit_controle -tAc \
    "SELECT d.host FROM dominio d JOIN cliente c ON c.id = d.cliente_id WHERE c.status <> 'inativo' ORDER BY d.id" | tr '\n' ' ')"
fi
HOSTS="$(echo "$HOSTS" | tr ' ' '\n' | grep -E '^[a-z0-9.-]+\.[a-z]{2,}$' | awk '!v[$0]++' | tr '\n' ' ')"

tem_cert() { [ -s "/etc/letsencrypt/live/$1/fullchain.pem" ]; }

gerar() {  # escreve o site com os certificados que existem agora
  local tmp; tmp="$(mktemp)"
  {
    echo "# MayaFit ($AMB) — GERADO por deploy/certificados.sh em $(date '+%d/%m/%Y %H:%M'). Não edite à mão."
    echo "limit_req_zone \$binary_remote_addr zone=mayafit_${AMB}_auth:10m rate=10r/m;"
    echo "limit_req_zone \$binary_remote_addr zone=mayafit_${AMB}_geral:10m rate=20r/s;"
    echo
    echo "server {"
    echo "    listen 80;"
    echo "    listen [::]:80;"
    echo "    server_name $HOSTS;"
    echo "    server_tokens off;"
    echo "    location /.well-known/acme-challenge/ { root $WEBROOT; }"
    echo "    location / { return 301 https://\$host\$request_uri; }"
    echo "}"
    for h in $HOSTS; do
      tem_cert "$h" || continue
      echo
      echo "server {"
      echo "    listen 443 ssl http2;"     # nginx 1.24 do servidor: http2 vai no listen
      echo "    listen [::]:443 ssl http2;"
      echo "    server_name $h;"
      echo "    ssl_certificate /etc/letsencrypt/live/$h/fullchain.pem;"
      echo "    ssl_certificate_key /etc/letsencrypt/live/$h/privkey.pem;"
      echo "    include /etc/letsencrypt/options-ssl-nginx.conf;"
      echo "    include $SNIPPET;"
      echo "}"
    done
  } > "$tmp"
  echo "$tmp"
}

aplicar() {  # troca o site só se mudou e o nginx aprovar; senão desfaz
  local novo="$1" antigo_bkp=""
  sed "s|__API__|$API_PORTA|g; s|__WEB__|$WEB_PORTA|g; s|__AMB__|$AMB|g" "$DIR/deploy/nginx/mayafit-locations.conf" > "$SNIPPET.novo"
  if [ -f "$SITE" ] && cmp -s <(grep -v '^# MayaFit' "$SITE") <(grep -v '^# MayaFit' "$novo") \
     && [ -f "$SNIPPET" ] && cmp -s "$SNIPPET" "$SNIPPET.novo"; then
    rm -f "$novo" "$SNIPPET.novo"; return 0
  fi
  [ -f "$SITE" ] && antigo_bkp="$(mktemp)" && cp "$SITE" "$antigo_bkp"
  [ -f "$SNIPPET" ] && cp "$SNIPPET" "$SNIPPET.bkp"
  mv "$SNIPPET.novo" "$SNIPPET"
  install -m 644 "$novo" "$SITE"; rm -f "$novo"
  ln -sf "$SITE" "/etc/nginx/sites-enabled/mayafit-$AMB"
  if nginx -t 2>/tmp/mayafit-nginx-$AMB.txt; then
    systemctl reload nginx
    echo "nginx recarregado ($(grep -c 'listen 443' "$SITE") endereço(s) com HTTPS)."
  else
    echo "O nginx recusou a configuração nova; voltei a anterior (os outros sites seguem intactos):"
    cat /tmp/mayafit-nginx-$AMB.txt
    if [ -n "$antigo_bkp" ]; then install -m 644 "$antigo_bkp" "$SITE"; else rm -f "$SITE" "/etc/nginx/sites-enabled/mayafit-$AMB"; fi
    [ -f "$SNIPPET.bkp" ] && mv "$SNIPPET.bkp" "$SNIPPET"
    exit 1
  fi
}

[ -f /etc/letsencrypt/options-ssl-nginx.conf ] || { echo "Falta /etc/letsencrypt/options-ssl-nginx.conf (vem com python3-certbot-nginx)."; exit 1; }

# 1ª passada: garante a porta 80 com o desafio para todos os endereços
aplicar "$(gerar)"

# certificados que faltam (uma tentativa por hora por endereço)
for h in $HOSTS; do
  tem_cert "$h" && continue
  marca="$ESTADO/$h.tentativa"
  if [ -f "$marca" ] && [ "$(( $(date +%s) - $(stat -c %Y "$marca") ))" -lt 3600 ]; then continue; fi
  touch "$marca"
  if certbot certonly --webroot -w "$WEBROOT" -d "$h" --non-interactive --agree-tos -m "$EMAIL_LE" --quiet        --deploy-hook "systemctl reload nginx"; then   # a renovação automática do certbot recarrega o nginx
    echo "certificado emitido: $h"; rm -f "$marca"
  else
    echo "sem certificado ainda para $h (DNS apontado para este servidor?); tento de novo em 1 hora"
  fi
done

# 2ª passada: blocos 443 para quem já tem certificado
aplicar "$(gerar)"
