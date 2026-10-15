"""TODO: Артём и Кирилл: интерактивный ввод пароля, стойкий хеш, без паролей в аргументах/логах.
Запуск из корня: python -m backend.scripts.create_admin
"""
from __future__ import annotations

import argparse
from getpass import getpass
from sqlalchemy import select
from backend.app.auth import hash_password, normalize_login, validate_password
from backend.app.database import SessionLocal, init_db
from backend.app.models.admin import Admin


def _prompt_login(value: str | None) -> str:
    raw_value = value if value is not None else input("Логин администратора: ")
    try:
        return normalize_login(raw_value)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


def _prompt_password() -> str:
    password = getpass("Пароль администратора: ")
    password_confirmation = getpass("Повторите пароль: ")
    if password != password_confirmation:
        raise SystemExit("Пароли не совпадают")
    try:
        validate_password(password)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    return password


def main() -> int:
    parser = argparse.ArgumentParser(description="Создание администратора для админки")
    parser.add_argument("--login", help="Логин администратора; если не указан, будет интерактивный ввод")
    args = parser.parse_args()

    init_db()
    login_name = _prompt_login(args.login)
    password_hash = hash_password(_prompt_password())

    with SessionLocal() as db:
        existing = db.scalar(select(Admin).where(Admin.login == login_name))
        if existing is not None:
            raise SystemExit("Администратор с таким логином уже существует")
        db.add(Admin(login=login_name, password_hash=password_hash))
        db.commit()

    print(f"Администратор '{login_name}' успешно создан.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
