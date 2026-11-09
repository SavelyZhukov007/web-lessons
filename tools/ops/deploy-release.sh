#!/usr/bin/env bash
# From the server: deploy-release.sh STAGE pr|ib URL VERSION VERSION_CODE
# STAGE contains source/ (Git archive), revision (commit), latest.json and the APK.
set -euo pipefail
stage=$(realpath "${1:?stage directory}") channel=${2:?channel} url=${3:?site URL}
version=${4:?version} code=${5:?version code}
[[ $channel = pr || $channel = ib ]]
[[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ && $code =~ ^[0-9]+$ ]]
ops="$stage/source/tools/ops"
tag="kipclub:v${version}${channel}"
prev="kipclub:before-v${version}${channel}"
name="kipclub-v${version}${channel}A.apk"
cd "${CLUBS_DIR:-/opt/clubs}"
exec 9>./.kipclub-deploy.lock
flock -n 9

one_off() { docker compose run --rm -T --no-deps app "$@"; }
active=$(docker compose ps -q app)
[[ -n $active ]]
old_image=$(docker inspect "$active" --format '{{.Image}}')
compose_image=$(docker inspect "$active" --format '{{.Config.Image}}')
old_build=$(curl --max-time 10 -fsS "$url/build-info.json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["build_id"])')
old_head=$(curl --max-time 10 -fsS "$url/readyz" | python3 -c 'import json,sys; print(json.load(sys.stdin)["revision"])')
release_dir=$(docker compose exec -T app printenv APP_RELEASES_DIR)
host_release_dir=$(docker inspect "$active" --format "{{range .Mounts}}{{if and (eq .Type \"bind\") (eq .Destination \"$release_dir\")}}{{.Source}}{{end}}{{end}}")

release_files() {
  if [[ -n $host_release_dir ]]; then
    APP_RELEASES_DIR="$host_release_dir" python3 "$ops/release-files.py" "$stage" "$@"
  else
    docker compose run --rm -T --no-deps -u 0 -v "$stage:/release-stage:ro" \
      app python /release-stage/source/tools/ops/release-files.py /release-stage "$@"
  fi
}
release_hold() {
  one_off python -c '
import sys
from backend.app.services.release_notify import state_file
path = state_file().with_name("release-notify.hold")
if sys.argv[1] == "on":
    path.touch(exist_ok=False)
else:
    path.unlink(missing_ok=True)
' "$1"
}

branding=0; [[ $channel != ib ]] || branding=1
revision=$(cat "$stage/revision")
[[ $revision =~ ^[0-9a-f]{40}$ ]]
docker build --pull=false --build-arg "KIPCLUB_TEST_BUILD=$branding" --label "org.opencontainers.image.revision=$revision" \
  -t "$tag" "$stage/source"
expected=$(docker run --rm --entrypoint python "$tag" -c 'import json; print(json.load(open("/app/builds/web/build-info.json"))["build_id"])')
head=$(docker run --rm --entrypoint python "$tag" -c 'from backend.app.migrations import head_revision; print(head_revision())')
release_files stage "$name" "$code" "v$version"
docker tag "$old_image" "$prev"
release_hold on

stopped=0
retagged=0
migration_started=0
public_start=0
manifest_changed=0
backup=""

rollback() {
  rc=$?
  trap - EXIT
  if [[ $rc = 0 ]]; then return; fi
  if [[ $migration_started = 1 && $public_start = 1 ]]; then
    echo "Public startup attempted after migration. Keeping the new image and database. Backup: $backup. Release announcement is on hold." >&2
    exit "$rc"
  fi
  echo "Restoring previous deployment $old_build ($old_head)" >&2
  if [[ $manifest_changed = 1 ]] && ! release_files rollback; then
    echo "Could not restore the previous APK manifest. Release announcement is on hold." >&2
    exit "$rc"
  fi
  if [[ $retagged = 1 ]] && ! docker tag "$prev" "$compose_image"; then
    echo "Could not restore the previous image tag. Backup: $backup" >&2
    exit "$rc"
  fi
  if [[ $migration_started = 1 ]] && ! one_off python server.py restore "$backup" --yes; then
    echo "Database restoration failed. Keeping app stopped. Backup: $backup" >&2
    exit "$rc"
  fi
  if [[ $stopped = 1 || $retagged = 1 ]]; then
    if ! docker compose up -d --no-build --no-deps --force-recreate app ||
       ! python3 "$ops/check-release.py" "$url" "$old_build" "$old_head"; then
      echo "Previous deployment failed its readiness check. Backup: $backup" >&2
      exit "$rc"
    fi
  fi
  release_hold off || echo "Could not remove the release announcement hold." >&2
  exit "$rc"
}
trap rollback EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

backup_cmd=(docker compose exec -T app)
if [[ $head != "$old_head" ]]; then
  # Quiesce writes before taking the snapshot used for an automatic restore.
  stopped=1
  docker compose stop app
  backup_cmd=(one_off)
fi
backup=$("${backup_cmd[@]}" python server.py backup --dir /backups --keep 8 --prefix "before-v${version//./}" | tail -n1)
[[ $backup = /backups/*.sqlite3.gz ]]
"${backup_cmd[@]}" python server.py verify-backup "$backup"
printf '%s\n' "$backup" > "$stage/backup"

retagged=1
docker tag "$tag" "$compose_image"
if [[ $stopped = 1 ]]; then
  manifest_changed=1
  release_files publish
  migration_started=1
  # The candidate listens on loopback and does not start background workers.
  docker compose run --rm -T --no-deps -v "$stage:/release-stage:ro" app \
    python /release-stage/source/tools/ops/check-release.py "$url" "$expected" "$head" /release-stage/latest.json --candidate
fi

# From here onward the new app may accept writes, even if startup reports an error.
public_start=1
docker compose up -d --no-build --no-deps --force-recreate app
if [[ $manifest_changed = 0 ]]; then
  python3 "$ops/check-release.py" "$url" "$expected" "$head"
  manifest_changed=1
  release_files publish
fi
python3 "$ops/check-release.py" "$url" "$expected" "$head" "$stage/latest.json"
docker inspect "$(docker compose ps -q app)" --format '{{.Image}} {{index .Config.Labels "org.opencontainers.image.revision"}}' > "$stage/image"
curl --max-time 10 -fsS "$url/build-info.json" > "$stage/web.json"
curl --max-time 10 -fsS "$url/api/app/android" > "$stage/live.json"
trap - EXIT INT TERM
echo "Deployment OK $url build $expected revision $head backup $backup"

release_hold off
if docker compose exec -T app python server.py announce-release "v${version}" --send > "$stage/announce.json"; then
  cat "$stage/announce.json"
else
  echo "Announcement command failed. The watcher will check the durable release key before attempting delivery." >&2
fi
