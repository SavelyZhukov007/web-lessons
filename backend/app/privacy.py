"""Обезличивание для журналов приложения: IP обрезается до сети /24 (IPv4) и /48 (IPv6), User-Agent не пишется.
Полный IP остаётся только в памяти процесса для ограничения частоты (client_logs.allow, feedback.allow)."""
from __future__ import annotations

import ipaddress


def mask_ip(host: str | None) -> str:
    """'203.0.113.57' → '203.0.113.0/24', '2001:db8:1:2::5' → '2001:db8:1::/48'; не IP (тестовый клиент, unix-сокет) → '-'."""
    if not host:
        return "-"
    try:
        ip = ipaddress.ip_address(host.strip().strip("[]").split("%", 1)[0])
    except ValueError:
        return "-"
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    prefix = 24 if ip.version == 4 else 48
    return str(ipaddress.ip_network(f"{ip}/{prefix}", strict=False))
