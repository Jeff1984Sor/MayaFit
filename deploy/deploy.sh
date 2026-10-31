#!/usr/bin/env bash
#
# Deploy do MayaFit no servidor (VPS compartilhada com outros sistemas).
#
# Passos sempre na mesma ordem e, em produção, uma tag vN como ponto de retorno.
# Nada vai para produção sem ter passado pela homologação.
#
# Uso (no servidor, como o usuário deploy, dentro de /home/deploy/mayafit/<amb>):
#     ./deploy/deploy.sh hml            # branch develop -> hml-mayafit.mayacorp.com.br  (domínio placeholder)
#     ./deploy/deploy.sh prod           # branch main    -> mayafit.mayacorp.com.br  (cria tag vN)
#     ./deploy/deploy.sh prod --sem-tag
#
set -euo pipefail

AMB="${1:?informe o ambiente: hml ou prod}"
case "$AMB" in
  hml)  BRANCH="${BRANCH:-develop}" ;;
  prod) BRANCH="${BRANCH:-main}" ;;
  *) echo "Ambiente inválido: $AMB"; exit 1 ;;
esac
CRIAR_TAG=0
[ "$AMB" = "prod" ] && CRIAR_TAG=1
[ "${2:-}" = "--sem-tag" ] && CRIAR_TAG=0

APP_DIR="${APP_DIR:-$HOME/mayafit/$AMB}"
SERVICOS="mayafit-api@$AMB mayafit-worker@$AMB mayafit-web@$AMB"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
cd "$APP_DIR"
API_PORTA="$(grep -E '^API_PORTA=' backend/.env | cut -d= -f2)"

echo "=== 1/7  Situação atual ($AMB) ==="
VERSAO_ANTERIOR="$(cat backend/VERSION 2>/dev/null || echo dev)"
COMMIT_ANTERIOR="$(git rev-parse --short HEAD)"
echo "    no ar: $VERSAO_ANTERIOR ($COMMIT_ANTERIOR)"
# HEAD solto = um rollback deixou o servidor numa tag. Avisa e volta para a branch do ambiente.
if ! git symbolic-ref -q HEAD >/dev/null; then
  echo "    ATENÇÃO: o servidor está com HEAD solto (provável rollback anterior). O deploy volta para '$BRANCH'."
  read -r -p "    Continuar? [s/N] " r
  [ "$r" = "s" ] || exit 1
fi
rm -f .rollback-ativo
if [ -n "$(git status --porcelain -uno)" ]; then
  echo "    ATENÇÃO: arquivos versionados modificados no servidor:"
  git status --short -uno
  read -r -p "    Continuar? [s/N] " r
  [ "$r" = "s" ] || exit 1
fi

echo "=== 2/7  Código ($BRANCH) ==="
git fetch -q origin
git fetch -q origin --tags 2>/dev/null || true
git checkout -q "$BRANCH"
git pull -q --ff-only origin "$BRANCH"
COMMIT_NOVO="$(git rev-parse --short HEAD)"
git log --oneline "$COMMIT_ANTERIOR..$COMMIT_NOVO" | sed 's/^/      /'

echo "=== 3/7  Backend: dependências e testes (gate) ==="
cd backend
"$UV" sync --frozen -q
if ! "$UV" run python -m pytest -q; then
  echo "    Testes falharam. Deploy abortado (nada foi reiniciado)."
  exit 1
fi

echo "=== 4/7  Migrations ==="
# (o .env é lido pela própria aplicação; não dar `source`: o bash corrompe valores com colchetes/aspas)
"$UV" run python -m alembic check >/dev/null 2>&1 || echo "    (aviso: há modelo sem migration gerada, confira)"
"$UV" run python -m alembic upgrade head
cd ..

echo "=== 5/7  Frontend: build ==="
cd frontend
npm ci --silent
npm run build >/dev/null
cd ..

echo "=== 6/7  Versão ==="
if [ "$CRIAR_TAG" = "1" ]; then
  ULTIMA="$(git tag --list 'v[0-9]*' | sed 's/^v//' | sort -n | tail -1)"
  PROXIMA="v$(( ${ULTIMA:-0} + 1 ))"
  echo "$PROXIMA" > backend/VERSION
  # identidade só para a tag (o usuário deploy do servidor não tem git config global)
  GIT_ID=(-c user.name="Deploy MayaFit" -c user.email="deploy@localhost")
  git "${GIT_ID[@]}" tag -a "$PROXIMA" -m "Deploy $PROXIMA em $(date '+%d/%m/%Y %H:%M')"
  if git push -q origin "$PROXIMA" 2>/dev/null; then
    echo "    tag $PROXIMA publicada"
  else
    echo "    tag $PROXIMA só local (o rollback funciona igual)"
  fi
else
  echo "$AMB-$COMMIT_NOVO" > backend/VERSION
fi

echo "=== 7/7  Reiniciando ==="
sudo systemctl restart $SERVICOS
sleep 4
systemctl is-active $SERVICOS
CODIGO="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$API_PORTA/api/health" || echo 000)"
echo "    /api/health: HTTP $CODIGO"
if [ "$CODIGO" != "200" ]; then
  echo "    A API NÃO respondeu. Para voltar:  ./deploy/rollback.sh $AMB $VERSAO_ANTERIOR"
  exit 1
fi
echo "    OK: $(cat backend/VERSION) no ar em $AMB."
