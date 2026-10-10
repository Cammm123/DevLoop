from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    api_token: str
    database_path: Path
    bind_host: str = "127.0.0.1"
    bind_port: int = 8765

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("DEVLOOP_API_TOKEN", "")
        if len(token) < 32:
            raise RuntimeError("DEVLOOP_API_TOKEN must contain at least 32 characters")
        host = os.getenv("DEVLOOP_BIND_HOST", "127.0.0.1")
        validate_bind_host(host)
        try:
            port = int(os.getenv("DEVLOOP_BIND_PORT", "8765"))
        except ValueError as exc:
            raise RuntimeError("DEVLOOP_BIND_PORT must be an integer") from exc
        if not 1 <= port <= 65535:
            raise RuntimeError("DEVLOOP_BIND_PORT must be between 1 and 65535")
        path = Path(os.getenv("DEVLOOP_DATABASE_PATH", "./data/devloop.sqlite3")).expanduser()
        return cls(token, path, host, port)


def validate_bind_host(host: str) -> None:
    """Only permit loopback and literal Tailscale addresses, never wildcard/public binds."""
    if host == "localhost":
        return
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise RuntimeError(
            "DEVLOOP_BIND_HOST must be localhost, a loopback IP, or a literal Tailscale IP"
        ) from exc
    tailscale_v4 = ipaddress.ip_network("100.64.0.0/10")
    tailscale_v6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")
    if not (address.is_loopback or address in tailscale_v4 or address in tailscale_v6):
        raise RuntimeError("refusing non-loopback, non-Tailscale bind address")
