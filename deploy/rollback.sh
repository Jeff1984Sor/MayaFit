#!/usr/bin/env bash
# Volta um ambiente para uma versão anterior:   ./deploy/rollback.sh prod v7
# Depois de resolver o problema, volte para a branch normal:   ./deploy/rollback.sh prod --retomar
#
# Não desfaz migrations: se a versão nova criou colunas, elas ficam (o código antigo as ignora).
# O rollback deixa o repositório com HEAD solto na tag (é o que "estar na versão vN" significa). Para não esquecer isso:
#   - grava .rollback-ativo (com a branch de origem) e imprime um aviso;
#   - o próximo ./deploy/deploy.sh avisa e volta sozinho para a branch;
#   - --retomar volta para a branch sem fazer deploy novo.
set -euo pipefail
AMB="${1:?ambiente (hml|prod)}"
ARG="${2:?versão (ex.: v7) ou --retomar}"
APP_DIR="${APP_DIR:-$HOME/mayafit/$AMB}"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
case "$AMB" in hml) BRANCH_PADRAO=develop ;; prod) BRANCH_PADRAO=main ;; *) echo "Ambiente inválido"; exit 1 ;; esac
cd "$APP_DIR"

if [ "$ARG" = "--retomar" ]; then
  BRANCH="$(cut -d' ' -f1 .rollback-ativo 2>/dev/null || echo "$BRANCH_PADRAO")"
  git checkout -q "$BRANCH"
  rm -f .rollback-ativo
  echo "Repositório de volta na branch $BRANCH. Rode ./deploy/deploy.sh $AMB para publicar o que está nela."
  exit 0
fi

VERSAO="$ARG"
if ! git rev-parse -q --verify "refs/tags/$VERSAO" >/dev/null; then
  echo "Tag $VERSAO não existe. Últimas:"
  git tag --list 'v*' | sort -V | tail -5
  exit 1
fi
ORIGEM="$(git symbolic-ref -q --short HEAD || cut -d' ' -f1 .rollback-ativo 2>/dev/null || echo "$BRANCH_PADRAO")"
git checkout -q "$VERSAO"
echo "$ORIGEM $VERSAO" > .rollback-ativo
(cd backend && "$UV" sync --frozen -q)
(cd frontend && npm ci --silent && npm run build >/dev/null)
echo "$VERSAO" > backend/VERSION
sudo systemctl restart "mayafit-api@$AMB" "mayafit-worker@$AMB" "mayafit-web@$AMB"
sleep 4
API_PORTA="$(grep -E '^API_PORTA=' backend/.env | cut -d= -f2)"
CODIGO="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$API_PORTA/api/health" || echo 000)"
echo "/api/health: HTTP $CODIGO"
echo
echo "================================================================"
echo " ATENÇÃO: $AMB está em $VERSAO com o repositório em HEAD SOLTO."
echo " Não faça commits aqui. Quando o problema for resolvido:"
echo "     ./deploy/rollback.sh $AMB --retomar    (volta para a branch $ORIGEM)"
echo "     ./deploy/deploy.sh $AMB                (publica a versão corrigida)"
echo "================================================================"
[ "$CODIGO" = "200" ] || { echo "A API não respondeu após o rollback. Confira: journalctl -u mayafit-api@$AMB -n 50"; exit 1; }
