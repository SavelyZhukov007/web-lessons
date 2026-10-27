#!/usr/bin/env bash
# Бэкап БД прода с проверкой. Запуск на сервере из /opt/clubs:
#   tools/ops/backup.sh pre-migrate   # перед git pull / compose build (новые миграции)
#   tools/ops/backup.sh pre-import    # перед ручной публикацией импорта
# Печатает путь к файлу внутри контейнера (/backups/...). Секреты не читает и не выводит.
set -euo pipefail
PREFIX="${1:-pre-migrate}"
case "$PREFIX" in clubs|pre-migrate|pre-import) ;; *) echo "prefix: clubs|pre-migrate|pre-import" >&2; exit 2;; esac
SERVICE="${SERVICE:-app}"
FILE=$(docker compose exec -T "$SERVICE" python server.py backup --dir /backups --keep "${KEEP:-10}" --prefix "$PREFIX" | tail -n1 | tr -d '\r')
echo "backup: $FILE"
# verify-backup возвращает 1, если ревизия != head кода в контейнере; до миграции они совпадают
docker compose exec -T "$SERVICE" python server.py verify-backup "$FILE"
echo "$FILE"
