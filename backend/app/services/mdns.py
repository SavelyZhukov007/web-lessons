"""Объявление сервера в локальной сети через mDNS/DNS-SD (_itc-kruzhki._tcp) — чтобы демо-приложение нашло его само.

Включается MDNS_ENABLED=1 (по умолчанию выключено; в production не нужно). Пакет zeroconf — необязательная зависимость:
нет пакета — пишем предупреждение и работаем дальше. Порт — MDNS_PORT или PORT (по умолчанию 8000).
"""
from __future__ import annotations

import logging
import os
import socket

from .. import settings

log = logging.getLogger("clubs.mdns")
SERVICE = "_itc-kruzhki._tcp.local."


def _local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # пакет не отправляется: только выбор интерфейса
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def service_info(port: int | None = None, ip: str | None = None):
    from zeroconf import ServiceInfo

    from ..routers.app_api import API_VERSION, APP_ID, SERVER_VERSION, server_id
    port = port or int(os.getenv("MDNS_PORT") or os.getenv("PORT") or 8000)
    ip = ip or _local_ip()
    name = settings.server_name()
    sid = server_id()
    return ServiceInfo(SERVICE, f"{name} ({sid[:6]}).{SERVICE}", addresses=[socket.inet_aton(ip)], port=port,
                       properties={"app": APP_ID, "name": name, "version": SERVER_VERSION, "api": str(API_VERSION), "id": sid},
                       server=f"itc-{sid[:8]}.local.")


def start():
    try:
        from zeroconf import Zeroconf
    except ImportError:
        log.warning("MDNS_ENABLED=1, но пакет zeroconf не установлен (pip install zeroconf) — объявление в сети выключено")
        return None
    try:
        zc = Zeroconf()
        info = service_info()
        zc.register_service(info)
        log.info("mDNS: %s на %s:%s", SERVICE, socket.inet_ntoa(info.addresses[0]), info.port)
        return (zc, info)
    except Exception as e:  # сеть без multicast и т.п. — не мешаем запуску
        log.warning("mDNS не запущен: %s", e)
        return None


def stop(handle) -> None:
    if not handle:
        return
    zc, info = handle
    try:
        zc.unregister_service(info)
    finally:
        zc.close()
