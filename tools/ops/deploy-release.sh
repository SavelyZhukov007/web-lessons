#!/usr/bin/env bash
# Выкат релиза KipClub на сервер (прод или тест) с автоматическим объявлением «Что нового».
# Запуск на сервере из каталога стенда (STAGE — подготовленная папка с source/, latest.json и APK):
#   tools/ops/deploy-release.sh STAGE CHANNEL URL VERSION CODE
#   CHANNEL: pr (прод) | ib (тест), URL: https://club.kipfin.ru | http://lekora.ru:7443, VERSION: 1.9.016, CODE: 33
# Шаги: образ из source/ → бэкап БД с проверкой → APK в каталог релизов → новый контейнер (миграции при старте) →
# проверка /readyz, ревизии, build-info → публикация latest.json → проверка раздачи APK →
# `server.py announce-release vVERSION --send` (один раз на версию; повтор — duplicate). Любая ошибка до публикации —
# откат на прежний образ и прежний latest.json. Секреты, .env и docker compose не меняет.
set -euo pipefail
stage=$1 channel=$2 url=$3 version=$4 code=$5
tag="kipclub:v${version}${channel}"
prev="kipclub:before-v${version}${channel}"
name="kipclub-v${version}${channel}A.apk"
cd "${CLUBS_DIR:-/opt/clubs}"
exec 9>"/tmp/kipclub-deploy-${channel}.lock"
flock -n 9

old_image=$(docker inspect "$(docker compose ps -q app)" --format '{{.Image}}')
branding=0; [ "$channel" = ib ] && branding=1
revision=$(cat "$stage/revision" 2>/dev/null || echo unknown)
docker build --pull=false --build-arg "KIPCLUB_TEST_BUILD=$branding" --label "org.opencontainers.image.revision=$revision" \
  -t "$tag" "$stage/source"
expected=$(docker run --rm --entrypoint python "$tag" -c 'import json; print(json.load(open("/app/builds/web/build-info.json"))["build_id"])')
head=$(docker run --rm --entrypoint python "$tag" -c 'from backend.app.migrations import head_revision; print(head_revision())' | tr -d '\r')
docker run --rm --entrypoint python "$tag" -c "import json; n=json.load(open('/app/frontend/release-info.json')); assert n['version']=='v$version', n['version']; print('release-info', n['version'], n['announcement'])"

backup=$(docker compose exec -T app python server.py backup --dir /backups --keep 8 --prefix "before-v${version//./}" | tail -n1 | tr -d '\r')
docker compose exec -T app python server.py verify-backup "$backup"
printf '%s\n' "$backup" > "$stage/backup"
docker tag "$old_image" "$prev"

release_python() {
  if [ "$channel" = ib ] && [ "$(docker compose exec -T app printenv APP_RELEASES_DIR | tr -d '\r')" = /srv/releases ]; then
    APP_RELEASES_DIR="${RELEASES_HOST_DIR:-/opt/clubs/downloads}" RELEASE_STAGE="$stage" CODE="$code" python3 -c "$1"
  else
    docker compose run --rm -T --no-deps -u 0 -e CODE="$code" -v "$stage:/release-stage:ro" app python -c "$1"
  fi
}
release_python '
import hashlib,json,os,shutil
from pathlib import Path
s=Path(os.environ.get("RELEASE_STAGE") or "/release-stage")
d=Path(os.environ["APP_RELEASES_DIR"])
new=json.loads((s/"latest.json").read_text())
old=json.loads((d/"latest.json").read_text())
assert new["versionCode"] == int(os.environ["CODE"]) > old["versionCode"], (new["versionCode"], old["versionCode"])
assert hashlib.sha256((s/new["file"]).read_bytes()).hexdigest() == new["sha256"]
shutil.copyfile(d/"latest.json",d/"latest.before-release.json")
tmp=d/(new["file"]+".new")
shutil.copyfile(s/new["file"],tmp)
os.chmod(tmp,0o644)
os.replace(tmp,d/new["file"])
'
rollback() {
  rc=$?
  trap - ERR
  echo "Откат выката v${version}${channel}" >&2
  release_python '
import os,shutil
from pathlib import Path
d=Path(os.environ["APP_RELEASES_DIR"])
shutil.copyfile(d/"latest.before-release.json",d/"latest.rollback.tmp")
os.chmod(d/"latest.rollback.tmp",0o644)
os.replace(d/"latest.rollback.tmp",d/"latest.json")
' || true
  docker tag "$prev" clubs-app
  docker compose up -d --no-build --force-recreate app || true
  exit "$rc"
}
trap rollback ERR
docker tag "$tag" clubs-app
docker compose up -d --no-build --force-recreate app
ready=0
for _ in $(seq 1 45); do
  if curl --max-time 5 -fsS "$url/readyz" >/dev/null 2>&1; then ready=1; break; fi
  sleep 2
done
test "$ready" = 1
actual=$(curl --max-time 10 -fsS "$url/build-info.json" | python3 -c 'import sys,json; print(json.load(sys.stdin)["build_id"])')
test "$actual" = "$expected"
docker compose exec -T app python -c "from backend.app.migrations import current_revision; assert current_revision() == '$head', current_revision()"
release_python '
import os,shutil
from pathlib import Path
d=Path(os.environ["APP_RELEASES_DIR"])
tmp=d/"latest.release.tmp"
shutil.copyfile(Path(os.environ.get("RELEASE_STAGE") or "/release-stage")/"latest.json",tmp)
os.chmod(tmp,0o644)
os.replace(tmp,d/"latest.json")
'
curl --max-time 15 -fsS "$url/api/app/android" > "$stage/live.json"
python3 - "$stage" "$name" "$code" <<'PY'
import json,sys
from pathlib import Path
d=Path(sys.argv[1])
live=json.loads((d/"live.json").read_text())
new=json.loads((d/"latest.json").read_text())
assert live["versionCode"]==int(sys.argv[3]) and live["file"]==sys.argv[2] and live["sha256"]==new["sha256"], live
print(live["versionName"],live["sha256"])
PY
hash=$(curl --max-time 60 -fsS "$url/android/download" | sha256sum | cut -d' ' -f1)
test "$hash" = "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sha256"])' "$stage/latest.json")"
trap - ERR
echo "Deployment OK $url build $actual revision $head backup $backup"
# Объявление «Что нового»: веб, iPhone PWA и APK. Ошибка рассылки выкат не откатывает — фоновая проверка повторит.
if docker compose exec -T app python server.py announce-release "v${version}" --send > "$stage/announce.json"; then
  echo "announce: $(cat "$stage/announce.json")"
else
  echo "announce: не отправлено сейчас, повторит фоновая проверка release_notify" >&2
fi
