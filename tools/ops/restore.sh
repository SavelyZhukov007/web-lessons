#!/usr/bin/env bash
# Восстановление БД из бэкапа (останавливает приложение на время записи):
#   tools/ops/restore.sh /backups/pre-migrate-YYYYMMDD-HHMMSS.sqlite3.gz [--yes]
# Без --yes только проверяет файл (verify-backup) и показывает план.
set -euo pipefail
FILE="${1:?путь к бэкапу внутри тома /backups}"
CONFIRM="${2:-}"
SERVICE="${SERVICE:-app}"
docker compose exec -T "$SERVICE" python server.py verify-backup "$FILE" || echo "внимание: ревизия бэкапа отличается от head кода — после восстановления нужен код той же версии"
if [ "$CONFIRM" != "--yes" ]; then
  echo "план: страховочный бэкап → stop $SERVICE → restore $FILE → start $SERVICE → /readyz"; exit 0
fi
"$(dirname "$0")/backup.sh" clubs >/dev/null  # страховка текущего состояния
docker compose stop "$SERVICE"
docker compose run --rm --no-deps "$SERVICE" python server.py restore "$FILE" --yes
docker compose start "$SERVICE"
for i in $(seq 1 30); do
  if docker compose exec -T "$SERVICE" python -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/readyz').status==200 else 1)" 2>/dev/null; then
    echo "restore ok"; exit 0; fi
  sleep 2
done
echo "readyz не поднялся — смотри docker compose logs $SERVICE" >&2; exit 1
