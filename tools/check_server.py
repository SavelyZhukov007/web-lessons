#!/usr/bin/env python3
import sys
import requests
from urllib.parse import urljoin


def check_endpoint(session, base_url, path, timeout):
    full_url = urljoin(base_url.rstrip("/"), path)
    try:
        resp = session.get(full_url, timeout=timeout)
        if 200 <= resp.status_code < 300:
            print(f"OK: {path} — status {resp.status_code}")
            return True
        else:
            print(f"FAIL: {path} — status {resp.status_code}")
            return False
    except requests.exceptions.Timeout:
        print(f"FAIL: {path} — timeout")
        return False
    except requests.exceptions.ConnectionError:
        print(f"FAIL: {path} — connection failed")
        return False
    except Exception as e:
        print(f"FAIL: {path} — error: {e}")
        return False


def main():
    if len(sys.argv) != 2:
        print("Usage: python tools/check_server.py <server_address>")
        sys.exit(1)

    base_url = sys.argv
    timeout = 5
    paths = ["/healthz", "/readyz"]

    session = requests.Session()
    all_ok = True

    for path in paths:
        ok = check_endpoint(session, base_url, path, timeout)
        if not ok:
            all_ok = False

    if all_ok:
        print("Server is available, application is ready to work")
        sys.exit(0)
    else:
        print("Check failed: there are problems with one or more endpoints")
        sys.exit(1)


if __name__ == "__main__":
    main()

