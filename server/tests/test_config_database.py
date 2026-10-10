from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from devloop_server.config import Settings, validate_bind_host
from devloop_server.database import Database


@pytest.mark.parametrize(
    "host", ["localhost", "127.0.0.1", "::1", "100.64.0.1", "100.127.255.254", "fd7a:115c:a1e0::1"]
)
def test_safe_bind_hosts(host: str) -> None:
    validate_bind_host(host)


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.2", "8.8.8.8", "example.com"])
def test_unsafe_bind_hosts_rejected(host: str) -> None:
    with pytest.raises(RuntimeError):
        validate_bind_host(host)


def test_settings_require_strong_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVLOOP_API_TOKEN", "short")
    with pytest.raises(RuntimeError, match="at least 32"):
        Settings.from_env()


def test_schema_initialization_is_idempotent_and_rejects_future_schema(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "database.sqlite3"
    database = Database(path)
    database.initialize()
    database.initialize()
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        columns = {row[1] for row in connection.execute("PRAGMA table_info(events)")}
        assert "payload" not in columns
        assert "command" not in columns
        assert "source_code" not in columns
        connection.execute("PRAGMA user_version = 99")
    with pytest.raises(RuntimeError, match="newer than supported"):
        database.initialize()
