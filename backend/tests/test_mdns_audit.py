"""mDNS-объявление (необязательный zeroconf) и аудит в файл: запуск не ломается при ошибках сети/пакета."""
import builtins
import json
import logging
import socket

from backend.app.services import audit, mdns


class _Zc:
    def __init__(self):
        self.calls = []

    def register_service(self, info):
        self.calls.append(("reg", info))

    def unregister_service(self, info):
        self.calls.append(("unreg", info))

    def close(self):
        self.calls.append(("close",))


def test_service_info_properties(monkeypatch):
    monkeypatch.setenv("MDNS_PORT", "8123")
    info = mdns.service_info(ip="192.168.1.5")
    assert info.port == 8123 and socket.inet_ntoa(info.addresses[0]) == "192.168.1.5"
    assert info.type == mdns.SERVICE and info.properties[b"app"]


def test_local_ip_fallback(monkeypatch):
    class S:
        def __init__(self, *a):
            pass

        def connect(self, addr):
            raise OSError("no route")

        def close(self):
            pass
    monkeypatch.setattr(mdns.socket, "socket", S)
    assert mdns._local_ip() == "127.0.0.1"


def test_start_register_and_stop(monkeypatch):
    import zeroconf
    zc = _Zc()
    monkeypatch.setattr(zeroconf, "Zeroconf", lambda: zc)
    monkeypatch.setattr(mdns, "_local_ip", lambda: "10.0.0.7")
    handle = mdns.start()
    assert handle and zc.calls[0][0] == "reg"
    mdns.stop(handle)
    assert [c[0] for c in zc.calls] == ["reg", "unreg", "close"]
    mdns.stop(None)


def test_start_survives_network_error(monkeypatch, caplog):
    import zeroconf

    def boom():
        raise OSError("multicast disabled")
    monkeypatch.setattr(zeroconf, "Zeroconf", boom)
    with caplog.at_level(logging.WARNING, logger="clubs.mdns"):
        assert mdns.start() is None
    assert "mDNS не запущен" in caplog.text


def test_start_without_zeroconf(monkeypatch, caplog):
    real = builtins.__import__

    def fake(name, *a, **k):
        if name == "zeroconf":
            raise ImportError(name)
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake)
    with caplog.at_level(logging.WARNING, logger="clubs.mdns"):
        assert mdns.start() is None
    assert "zeroconf не установлен" in caplog.text


def test_audit_writes_file_and_never_raises(tmp_path, monkeypatch):
    path = tmp_path / "audit.log"
    monkeypatch.setenv("AUDIT_LOG_FILE", str(path))
    monkeypatch.setattr(audit, "_file_handler_for", None)
    before = list(audit.logger.handlers)
    try:
        audit.log("test_event", admin_id=7)
        for h in audit.logger.handlers:
            h.flush()
        rec = json.loads(path.read_text(encoding="utf-8").strip().splitlines()[-1])
        assert rec["event"] == "test_event" and rec["admin_id"] == 7
        monkeypatch.setattr(audit.logger, "info", lambda *a: (_ for _ in ()).throw(RuntimeError("x")))
        audit.log("broken")  # не бросает
    finally:
        for h in audit.logger.handlers[:]:
            if h not in before:
                audit.logger.removeHandler(h)
                h.close()
