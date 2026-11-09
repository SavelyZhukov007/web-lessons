#!/usr/bin/env bash
# Explicit operator step, TEST only until production approval. Does not edit compose/env/secrets.
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
for name in kipclub-backup.service kipclub-backup.timer; do
  source="$root/deploy/$name"
  target="/etc/systemd/system/$name"
  if [ -f "$target" ]; then
    cmp -s "$source" "$target" || { echo "Existing $target differs: inspect it, not overwritten" >&2; exit 1; }
  else
    sudo -n install -m 0644 "$source" "$target"
  fi
done
sudo -n systemd-analyze verify /etc/systemd/system/kipclub-backup.service /etc/systemd/system/kipclub-backup.timer
sudo -n systemctl daemon-reload
sudo -n systemctl enable --now kipclub-backup.timer
systemctl show kipclub-backup.timer -p ActiveState -p NextElapseUSecRealtime
