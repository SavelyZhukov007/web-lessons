#!/usr/bin/env bash
# Проверка, что бэкап реально восстанавливается (не трогая прод-БД): копия во временный файл,
# restore в него, integrity_check и счётчики строк.
#   tools/ops/verify-restore.sh /backups/<файл>.sqlite3.gz
set -euo pipefail
FILE="${1:?путь к бэкапу внутри тома /backups}"
SERVICE="${SERVICE:-app}"
docker compose exec -T "$SERVICE" python - "$FILE" <<'PY'
import sys, sqlite3, tempfile
from pathlib import Path
from backend.app import cli
src = Path(sys.argv[1])
tmp = Path(tempfile.mkdtemp()) / "probe.sqlite3"
print(cli.restore(src, target=tmp))
con = sqlite3.connect(tmp)
print({t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("clubs", "sessions", "session_exceptions")})
PY
