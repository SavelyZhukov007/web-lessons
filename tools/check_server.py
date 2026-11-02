#!/usr/bin/env python3
"""Проверка доступности сервера KipClub: GET /healthz и /readyz (только стандартная библиотека)."""
import sys
import urllib.error
import urllib.request

PATHS = ("/healthz", "/readyz")


def endpoint_url(base_url: str, path: str) -> str:
    """Склеивает адрес, сохраняя префикс пути базы: http://h/clubs + /healthz → http://h/clubs/healthz."""
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def check_endpoint(base_url, path, timeout, opener=urllib.request.urlopen):
    full_url = endpoint_url(base_url, path)
    try:
        with opener(urllib.request.Request(full_url, method="GET"), timeout=timeout) as resp:
            status = resp.status
    except urllib.error.HTTPError as e:
        status = e.code
    except TimeoutError:
        print(f"FAIL: {path} — timeout")
        return False
    except (urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, TimeoutError):
            print(f"FAIL: {path} — timeout")
        else:
            print(f"FAIL: {path} — connection failed")
        return False
    if 200 <= status < 300:
        print(f"OK: {path} — status {status}")
        return True
    print(f"FAIL: {path} — status {status}")
    return False


def main(argv=None, opener=urllib.request.urlopen) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("Usage: python tools/check_server.py <server_address>")
        return 1
    results = [check_endpoint(argv[0], path, 5, opener) for path in PATHS]
    if all(results):
        print("Server is available, application is ready to work")
        return 0
    print("Check failed: there are problems with one or more endpoints")
    return 1


if __name__ == "__main__":
    sys.exit(main())
