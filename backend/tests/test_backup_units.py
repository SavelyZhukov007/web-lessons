from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_daily_docker_backup_uses_actual_restore_checked_cli():
    service = (ROOT / "deploy/kipclub-backup.service").read_text()
    assert "docker compose exec -T app python server.py backup --dir /backups --keep 14 --prefix clubs" in service
    assert "server.py restore" not in service and "WorkingDirectory=/opt/clubs" in service
    timer = (ROOT / "deploy/kipclub-backup.timer").read_text()
    assert "OnCalendar=*-*-* 03:30:00 Europe/Moscow" in timer
    assert "Persistent=true" in timer and "RandomizedDelaySec=180" in timer


def test_backup_installer_will_not_overwrite_existing_operator_config():
    installer = (ROOT / "tools/ops/install-daily-backup.sh").read_text()
    assert "cmp -s" in installer and "not overwritten" in installer
    assert "systemd-analyze verify" in installer and "enable --now kipclub-backup.timer" in installer
    assert "compose.yml" not in installer and ".env" not in installer and "restart app" not in installer
