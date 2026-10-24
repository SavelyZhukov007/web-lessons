"""`python -m backend.scripts.seed [--file data/sample-data.json] [--dry-run]` — идемпотентная загрузка демо-данных."""
from __future__ import annotations

import argparse
from pathlib import Path

from backend.app import cli


def main() -> int:
    parser = argparse.ArgumentParser(description="Загрузка data/sample-data.json в БД (повторный запуск безопасен)")
    parser.add_argument("--file", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="выполнить и откатить: показать, что было бы создано")
    args = parser.parse_args()
    try:
        stats = cli.seed(args.file, dry_run=args.dry_run)
    except cli.CliError as exc:
        raise SystemExit(str(exc)) from exc
    for name, s in stats.items():
        print(f"{name}: создано {s['created']}, уже было {s['existing']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
