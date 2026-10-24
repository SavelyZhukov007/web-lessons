"""Совместимость: `python -m backend.scripts.create_admin --login x` → `python server.py admin create x` (см. backend/app/cli.py)."""
from __future__ import annotations

import argparse

from backend.app import cli


def main() -> int:
    parser = argparse.ArgumentParser(description="Создание администратора")
    parser.add_argument("--login", required=True)
    parser.add_argument("--password-stdin", action="store_true", help="прочитать пароль из stdin (неинтерактивно)")
    args = parser.parse_args()
    try:
        print(cli.create_admin(args.login, password_stdin=args.password_stdin))
    except cli.CliError as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
