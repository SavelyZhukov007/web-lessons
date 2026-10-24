"""Единая точка входа проекта «кружки».

  python server.py                       # как раньше: uvicorn на 127.0.0.1:8000 с автоперезагрузкой
  python server.py serve --host 0.0.0.0 --port 8000 [--frontend builds/web] [--no-reload]
  python server.py build web|pwa|android|back|all [--out DIR] [--server-url http://IP:PORT] [--install] [--demo]   # результат в builds/
  python server.py admin create LOGIN [--password-stdin] | reset-password LOGIN [--password-stdin] | list
  python server.py seed [--file data/sample-data.json] [--dry-run]
  python server.py backup [--dir backups] [--keep 14] [--no-compress]  |  verify-backup FILE
  python server.py check-config

Совместимо с Python 3.10+ (Windows PowerShell и Linux)."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    if args.frontend:
        frontend = Path(args.frontend).resolve()
        if not (frontend / "index.html").exists():
            print(f"Ошибка: в {frontend} нет index.html (ожидается папка frontend или результат `build web`).", file=sys.stderr)
            return 2
        os.environ["CLUBS_FRONTEND_DIR"] = str(frontend)
    reload = not args.no_reload
    if reload and os.getenv("ENV", "development").lower() == "production":
        print("ENV=production: автоперезагрузка отключена.", file=sys.stderr)
        reload = False
    os.environ.setdefault("MDNS_PORT", str(args.port))
    if getattr(args, "mdns", False):
        os.environ["MDNS_ENABLED"] = "1"
    uvicorn.run("backend.app.main:app", host=args.host, port=args.port, reload=reload, app_dir=str(ROOT))
    return 0


def _build(args: argparse.Namespace) -> int:
    from tools.build.common import BuildError, python_version_ok

    try:
        python_version_ok()
        target = args.target
        out = Path(args.out).resolve() if args.out else None
        if getattr(args, "demo", False) and target in ("web", "pwa", "ios"):
            from tools.build.android import build_demo_web
            build_demo_web(out)
            return 0
        if target in ("web", "all"):
            from tools.build.web import build_web
            build_web(out if target == "web" else None)
        if target in ("pwa", "ios", "all"):
            from tools.build.pwa import build_pwa
            build_pwa(out if target in ("pwa", "ios") else None)
        if target in ("android", "all"):
            from tools.build.android import build_android
            apk = build_android(server_url=args.server_url, install=args.install, check_only=args.check_only, demo=args.demo,
                                with_demo=not args.no_demo, publish=not args.no_publish)
            if apk:
                print(f"\nAPK: {apk}")
        if target in ("back", "all"):
            from tools.build.back import build_back
            build_back(out if target == "back" else None)
    except BuildError as exc:
        print(f"\nОшибка сборки: {exc}", file=sys.stderr)
        return 1
    return 0


def _admin(args: argparse.Namespace) -> int:
    from backend.app import cli
    try:
        if args.admin_cmd == "create":
            print(cli.create_admin(args.login, password_stdin=args.password_stdin))
        elif args.admin_cmd == "reset-password":
            print(cli.reset_password(args.login, password_stdin=args.password_stdin))
        else:
            print(cli.list_admins())
    except cli.CliError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    return 0


def _seed(args: argparse.Namespace) -> int:
    from backend.app import cli
    try:
        stats = cli.seed(Path(args.file) if args.file else None, dry_run=args.dry_run)
    except cli.CliError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    for name, s in stats.items():
        print(f"{name}: создано {s['created']}, уже было {s['existing']}")
    if args.dry_run:
        print("(dry-run: изменения откатены)")
    return 0


def _backup(args: argparse.Namespace) -> int:
    from backend.app import cli
    try:
        print(cli.backup(Path(args.dir), keep=args.keep, compress=not args.no_compress))
    except cli.CliError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    return 0


def _verify_backup(args: argparse.Namespace) -> int:
    from backend.app import cli
    try:
        report = cli.verify_backup(Path(args.file))
    except cli.CliError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    print(report)
    return 0 if report["integrity"] == "ok" and report["revision"] == report["head"] else 1


def _check_config(_: argparse.Namespace) -> int:
    from backend.app import cli
    problems = cli.check_config()
    for p in problems:
        print("✗ " + p)
    print("Конфигурация в порядке." if not problems else f"Проблем: {len(problems)}")
    return 1 if problems else 0


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="server.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="запустить сервер (страницы + API)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--frontend", help="отдавать статику из этой папки (например builds/web) вместо frontend/")
    serve.add_argument("--mdns", action="store_true", help="объявить сервер в локальной сети (_itc-kruzhki._tcp) — демо-приложение найдёт его само; нужен пакет zeroconf")
    serve.add_argument("--no-reload", action="store_true", help="без автоперезагрузки (так запускают в проде)")
    serve.set_defaults(func=_serve)

    build = sub.add_parser("build", help="собрать: web (сайт) | pwa (установимое PWA; ios — псевдоним) | android (APK) | back (релиз бэкенда) | all")
    build.add_argument("target", choices=["web", "pwa", "ios", "android", "back", "all"])
    build.add_argument("--out", help="каталог результата для web/pwa/back (по умолчанию builds/web, builds/pwa, builds/back)")
    build.add_argument("--server-url", help="android: адрес сервера, вшитый как значение по умолчанию (иначе приложение спросит при запуске)")
    build.add_argument("--install", action="store_true", help="android: после сборки поставить APK через adb")
    build.add_argument("--check-only", action="store_true", help="android: только проверить окружение (JDK 21+, SDK, Node), не собирать")
    build.add_argument("--demo", action="store_true", help="офлайн-демо: локальный бэкенд в браузере (localStorage), случайные данные, админ без входа (android → только itc-kruzhki-demo-debug-<версия>.apk; web → builds/web-demo)")
    build.add_argument("--no-demo", action="store_true", help="android: не собирать демо-вариант вместе с основным APK")
    build.add_argument("--no-publish", action="store_true", help="android: не класть APK в каталог релизов (APP_RELEASES_DIR, по умолчанию releases/android) для /android/download")
    build.set_defaults(func=_build)

    admin = sub.add_parser("admin", help="администраторы")
    asub = admin.add_subparsers(dest="admin_cmd", required=True)
    for name in ("create", "reset-password"):
        p = asub.add_parser(name)
        p.add_argument("login")
        p.add_argument("--password-stdin", action="store_true", help="читать пароль из stdin (иначе ADMIN_PASSWORD или запрос)")
    asub.add_parser("list")
    admin.set_defaults(func=_admin)

    seed = sub.add_parser("seed", help="идемпотентно загрузить data/sample-data.json")
    seed.add_argument("--file")
    seed.add_argument("--dry-run", action="store_true")
    seed.set_defaults(func=_seed)

    backup = sub.add_parser("backup", help="консистентный бэкап SQLite с ротацией")
    backup.add_argument("--dir", default="backups")
    backup.add_argument("--keep", type=int, default=14)
    backup.add_argument("--no-compress", action="store_true")
    backup.set_defaults(func=_backup)

    verify = sub.add_parser("verify-backup", help="проверить, что бэкап открывается, цел и на актуальной ревизии схемы")
    verify.add_argument("file")
    verify.set_defaults(func=_verify_backup)

    check = sub.add_parser("check-config", help="проверить настройки окружения для прода")
    check.set_defaults(func=_check_config)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:  # без аргументов — прежнее поведение (разработка)
        return _serve(argparse.Namespace(host="127.0.0.1", port=8000, frontend=None, no_reload=False))
    parser = make_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
