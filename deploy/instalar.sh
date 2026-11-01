#!/usr/bin/env bash
#
# Primeira instalação do MayaFit (um banco por estúdio) num servidor que JÁ RODA outros sistemas.
# Regra: não atualizar, reiniciar nem reconfigurar nada que já exista. Só acrescentar.
#
#   sudo ADMIN_EMAIL=voce@exemplo.com ADMIN_NOME="Seu Nome" bash instalar.sh prod
#
# Endereços (DNS já apontado para este servidor, inclusive o coringa *.DOMINIO_BASE):
#   principal  mayafit.mayacorp.com.br         login de qualquer estúdio (o login acha o estúdio)
#   admin      admin.mayafit.mayacorp.com.br   Admin MayaFit
#   estúdios   <slug>.mayafit.mayacorp.com.br  sistema, site, app do aluno e totem de cada estúdio
#
# Bancos (PostgreSQL deste servidor): mayafit_prod (principal, fica vazio), mayafit_controle (estúdios, planos,
# cobrança) e mayafit_<slug> (um por estúdio, criado pelo próprio sistema: o usuário do banco ganha CREATEDB).
# Só produção por enquanto: o controle e os bancos dos estúdios têm nome fixo (um ambiente multi por servidor).
#
set -euo pipefail

AMB="${1:?informe o ambiente: prod}"
case "$AMB" in
  prod) BRANCH=main; API_PORTA=10061; WEB_PORTA=10062; BASE_DOM=mayafit.mayacorp.com.br ;;
  *) echo "Só prod usa um banco por estúdio neste servidor (o banco de controle tem nome fixo)."; exit 1 ;;
esac
PRINCIPAL="${DOMINIO_PRINCIPAL:-$BASE_DOM}"
ADMIN="${DOMINIO_ADMIN:-admin.$BASE_DOM}"
: "${ADMIN_EMAIL:?informe ADMIN_EMAIL (e-mail de quem administra o Admin MayaFit)}"
ADMIN_NOME="${ADMIN_NOME:-Administração MayaFit}"
ADMIN_LOGIN="${ADMIN_LOGIN:-admin}"
REPO="${REPO:-https://github.com/Jeff1984Sor/MayaFit.git}"
USUARIO=deploy
BASE=/home/$USUARIO/mayafit
DIR="$BASE/$AMB"
BANCO="mayafit_$AMB"
ROLE="mayafit_$AMB"

[ "$(id -u)" = "0" ] || { echo "Rode com sudo."; exit 1; }
id "$USUARIO" >/dev/null 2>&1 || { echo "Usuário $USUARIO não existe."; exit 1; }
como() { sudo -u "$USUARIO" -H bash -lc "$1"; }

echo "=== MayaFit ($AMB) → $DIR · $PRINCIPAL · $ADMIN · *.$BASE_DOM ==="

echo "--- 1/9 Conferindo o servidor (nada é alterado nesta etapa)"
for p in "$API_PORTA" "$WEB_PORTA"; do
  if ss -ltn "( sport = :$p )" | grep -q LISTEN; then echo "    Porta $p já está em uso. Abortado sem alterar nada."; exit 1; fi
done
[ -e "$DIR" ] && { echo "    $DIR já existe. Para atualizar use: ./deploy/deploy.sh $AMB"; exit 1; }
[ -e "/etc/nginx/sites-available/mayafit-$AMB" ] && { echo "    O site nginx mayafit-$AMB já existe. Abortado."; exit 1; }
for b in "$BANCO" mayafit_controle mayafit_mayacorp; do
  if sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$b'" | grep -q 1; then
    echo "    O banco $b já existe. Abortado (não apago bancos)."; exit 1
  fi
done
for h in "$PRINCIPAL" "$ADMIN" "teste-dns.$BASE_DOM"; do
  getent hosts "$h" >/dev/null || { echo "    O DNS de $h ainda não resolve. Abortado."; exit 1; }
done
echo "    Portas livres, pasta e bancos novos, DNS resolvendo. OK."

echo "--- 2/9 Pacotes: instala só o que falta, sem atualizar o que existe"
FALTAM=""
for pkg in git curl openssl nginx postgresql-client certbot python3-certbot-nginx; do
  dpkg -s "$pkg" >/dev/null 2>&1 || FALTAM="$FALTAM $pkg"
done
if [ -n "$FALTAM" ]; then
  echo "    instalando:$FALTAM"
  apt-get install -y -qq --no-upgrade $FALTAM >/dev/null
fi
NPM_BIN="$(como 'command -v npm' || true)"
NODE_VER="$(como 'node -v' 2>/dev/null || echo v0)"
[ -n "$NPM_BIN" ] && [ "$(echo "$NODE_VER" | cut -d. -f1 | tr -d v)" -ge 20 ] || {
  echo "    Node.js >= 20 necessário para o usuário $USUARIO (encontrado: $NODE_VER). Abortado."; exit 1; }
NODE_DIR="$(dirname "$NPM_BIN")"
echo "    Node $NODE_VER ($NODE_DIR)"
como 'command -v uv >/dev/null || [ -x ~/.local/bin/uv ] || curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null'
UV="/home/$USUARIO/.local/bin/uv"
[ -x "$UV" ] || UV="$(como 'command -v uv')"

echo "--- 3/9 Código ($BRANCH)"
como "mkdir -p '$BASE' && git clone -q -b '$BRANCH' '$REPO' '$DIR'"

echo "--- 4/9 Banco principal $BANCO e usuário $ROLE (com CREATEDB: o sistema cria o banco de cada estúdio novo)"
SENHA_BANCO="$(openssl rand -hex 24)"
if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$ROLE'" | grep -q 1; then
  sudo -u postgres psql -q -c "ALTER ROLE $ROLE WITH LOGIN CREATEDB PASSWORD '$SENHA_BANCO'"
else
  sudo -u postgres psql -q -c "CREATE ROLE $ROLE WITH LOGIN CREATEDB PASSWORD '$SENHA_BANCO'"
fi
sudo -u postgres psql -q -c "CREATE DATABASE $BANCO OWNER $ROLE ENCODING 'UTF8'"

echo "--- 5/9 Configuração de servidor (.env só com o que é de servidor; integrações ficam nas telas)"
MASTER_KEY="$(python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
como "cat > '$DIR/backend/.env'" <<ENV
AMBIENTE=$AMB
DEBUG=false
API_PORTA=$API_PORTA
WEB_PORTA=$WEB_PORTA
DOMINIO_PRINCIPAL=$PRINCIPAL
DOMINIO_ADMIN=$ADMIN
DOMINIO_BASE=$BASE_DOM
ALLOWED_HOSTS=["$PRINCIPAL","$ADMIN","*.$BASE_DOM","127.0.0.1"]
DATABASE_URL=postgresql+psycopg://$ROLE:$SENHA_BANCO@127.0.0.1:5432/$BANCO
STORAGE_DIR=$DIR/backend/storage
FRONTEND_URL=https://$PRINCIPAL
CORS_ORIGINS=["https://$PRINCIPAL","https://$ADMIN"]
JWT_SECRET=$(openssl rand -hex 48)
MASTER_KEY=$MASTER_KEY
RATE_LIMIT_ATIVO=true
WORKER_EMBUTIDO=false
MIGRAR_NA_SUBIDA=false
ENV
como "chmod 600 '$DIR/backend/.env'"
como "cat > '$DIR/frontend/.env.production'" <<ENV
INTERNAL_API_URL=http://127.0.0.1:$API_PORTA/api
NEXT_PUBLIC_AMBIENTE=$AMB
NEXT_PUBLIC_VERSAO=$AMB
WEB_PORTA=$WEB_PORTA
ENV
como "chmod 600 '$DIR/frontend/.env.production'"

echo "--- 6/9 Backend: dependências, migrations, banco de controle e o Admin MayaFit"
como "cd '$DIR/backend' && '$UV' sync --frozen -q && '$UV' run python -m alembic upgrade head"
como "cd '$DIR/backend' && '$UV' run python -m app.controle.cli ativar"
# sem senha: o comando imprime o link para quem administra criar a própria senha (nenhuma senha passa por aqui)
como "cd '$DIR/backend' && '$UV' run python -m app.controle.cli novo-admin-mayacorp --admin-nome '$ADMIN_NOME' \
  --admin-email '$ADMIN_EMAIL' --login '$ADMIN_LOGIN' --dominio '$ADMIN'" | tee /tmp/mayafit-admin-$AMB.txt

echo "--- 7/9 Frontend: build"
como "cd '$DIR/frontend' && npm ci --silent && npm run build >/dev/null"

echo "--- 8/9 Serviços (systemd) — só acrescenta, não mexe nos existentes"
for svc in api worker web certificados; do
  sed "s|__BASE__|$BASE|g; s|__USUARIO__|$USUARIO|g; s|__NODE_DIR__|$NODE_DIR|g" "$DIR/deploy/systemd/mayafit-$svc@.service" \
    > "/etc/systemd/system/mayafit-$svc@.service"
done
cp "$DIR/deploy/systemd/mayafit-certificados@.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now "mayafit-api@$AMB" "mayafit-worker@$AMB" "mayafit-web@$AMB"
echo "0 2 * * * $USUARIO $DIR/deploy/backup.sh prod >> /home/$USUARIO/mayafit/backup.log 2>&1" > /etc/cron.d/mayafit-backup

echo "--- 9/9 nginx e HTTPS (principal, admin e cada estúdio; o timer cuida dos endereços novos)"
bash "$DIR/deploy/certificados.sh" "$AMB"
systemctl enable --now "mayafit-certificados@$AMB.timer"

sleep 3
CODIGO="$(curl -s -o /dev/null -w '%{http_code}' "https://$PRINCIPAL/api/health" || echo 000)"
echo
echo "=== Pronto: MayaFit $AMB (https://$PRINCIPAL/api/health → HTTP $CODIGO) ==="
echo "    Admin MayaFit: https://$ADMIN (login '$ADMIN_LOGIN'; link para criar a senha logo acima e em /tmp/mayafit-admin-$AMB.txt)"
echo "    No admin: Configurações › E-mail (SMTP), Cobranças (Mercado Pago), Planos e indicação (senha do usuário Suporte)."
echo "    GUARDE a MASTER_KEY (em $DIR/backend/.env) num cofre: sem ela os segredos cifrados precisam ser recadastrados."
