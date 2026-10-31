#!/usr/bin/env bash
# Backup diário (cron 02:00, instalado pelo instalar.sh em /etc/cron.d/mayafit-backup)
# Banco (pg_dump) + ARQUIVOS (storage: fotos, assinaturas, documentos, comprovantes). Envia para fora do servidor
# (bucket) quando houver gcloud e mantém 30 dias local.
#
# O storage é lido de STORAGE_DIR do .env (padrão backend/storage). O .env (com a MASTER_KEY) NÃO vai junto com o
# resto: guarde a MASTER_KEY num cofre à parte. BACKUP_INCLUIR_ENV=1 grava um tar do .env (modo 600) só no servidor.
set -euo pipefail
AMB="${1:-prod}"
APP_DIR="/home/deploy/mayafit/$AMB"
DESTINO="${BACKUP_DIR:-/home/deploy/backups/mayafit/$AMB}"
BUCKET="${BACKUP_BUCKET:-gs://CONFIGURAR-BUCKET/mayafit/$AMB}"   # placeholder: definir antes de usar
ENV_FILE="$APP_DIR/backend/.env"
DATABASE_URL="$(grep -E '^DATABASE_URL=' "$ENV_FILE" | cut -d= -f2-)"
STORAGE="$(grep -E '^STORAGE_DIR=' "$ENV_FILE" | cut -d= -f2- || true)"
STORAGE="${STORAGE:-$APP_DIR/backend/storage}"
[ -d "$STORAGE" ] || { echo "Pasta de arquivos $STORAGE não existe: backup abortado."; exit 1; }
umask 077
mkdir -p "$DESTINO"
DIA="$(date +%Y%m%d)"
pg_dump "${DATABASE_URL/+psycopg/}" -Fc -f "$DESTINO/banco_$DIA.dump"
tar -czf "$DESTINO/arquivos_$DIA.tar.gz" -C "$(dirname "$STORAGE")" "$(basename "$STORAGE")"
# confere que os dois arquivos abrem (um backup que não restaura não é backup)
pg_restore -l "$DESTINO/banco_$DIA.dump" >/dev/null
tar -tzf "$DESTINO/arquivos_$DIA.tar.gz" >/dev/null
if [ "${BACKUP_INCLUIR_ENV:-0}" = "1" ]; then
  tar -czf "$DESTINO/env_$DIA.tar.gz" -C "$APP_DIR/backend" .env
fi
if command -v gcloud >/dev/null && [[ "$BUCKET" != *CONFIGURAR-BUCKET* ]]; then
  gcloud storage cp -q "$DESTINO/banco_$DIA.dump" "$DESTINO/arquivos_$DIA.tar.gz" "$BUCKET/$DIA/"
fi
find "$DESTINO" -type f -mtime +30 -delete
echo "Backup $AMB $DIA ok (banco + $(du -sh "$STORAGE" | cut -f1) de arquivos)"
