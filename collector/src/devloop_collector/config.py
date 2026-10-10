from __future__ import annotations

import ipaddress
import os
import secrets
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Any
from urllib.parse import urlsplit


class ConfigError(ValueError):
    pass


_TAILSCALE_V4 = ipaddress.ip_network("100.64.0.0/10")
_TAILSCALE_V6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")


def _validate_api_url(value: object) -> str:
    if not isinstance(value, str):
        raise ConfigError("api_url must be a URL string")
    if "?" in value or "#" in value:
        raise ConfigError("api_url must not contain a query or fragment")
    try:
        parsed = urlsplit(value)
        # Accessing port validates malformed and out-of-range ports.
        _ = parsed.port
    except ValueError as exc:
        raise ConfigError("api_url is invalid") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.hostname is None:
        raise ConfigError("api_url must be an absolute http or https URL")
    if "@" in parsed.netloc or parsed.username is not None or parsed.password is not None:
        raise ConfigError("api_url must not embed credentials")
    if parsed.scheme == "http":
        host = parsed.hostname
        allowed = host.lower() == "localhost"
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None:
            allowed = (
                address.is_loopback
                or address in _TAILSCALE_V4
                or address in _TAILSCALE_V6
            )
        if not allowed:
            raise ConfigError(
                "http api_url is allowed only for loopback or literal Tailscale addresses"
            )
    return value.rstrip("/")


def _state_home(env: Mapping[str, str]) -> Path:
    return Path(env.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "devloop"


def default_config_path(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    return Path(env.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "devloop" / "config.toml"


@dataclass(frozen=True, slots=True)
class Config:
    api_url: str
    token: str | None
    device_id_file: Path
    spool_file: Path
    timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "api_url", _validate_api_url(self.api_url))

    @classmethod
    def load(cls, path: Path | None = None, env: Mapping[str, str] | None = None) -> "Config":
        env = os.environ if env is None else env
        config_path = path or default_config_path(env)
        file_data: dict[str, Any] = {}
        if config_path.exists():
            try:
                parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
            except (OSError, tomllib.TOMLDecodeError) as exc:
                raise ConfigError(f"cannot read config: {exc}") from exc
            if set(parsed) - {"collector"} or not isinstance(parsed.get("collector", {}), dict):
                raise ConfigError("config must contain only a [collector] table")
            file_data = parsed.get("collector", {})
            allowed = {"api_url", "token", "device_id_file", "spool_file", "timeout_seconds"}
            if set(file_data) - allowed:
                raise ConfigError("unknown collector config keys")
        state = _state_home(env)
        api_url = env.get("DEVLOOP_API_URL", file_data.get("api_url", "http://127.0.0.1:8000"))
        token = env.get("DEVLOOP_TOKEN", file_data.get("token"))
        device_path = Path(env.get("DEVLOOP_DEVICE_ID_FILE", file_data.get("device_id_file", state / "device_id"))).expanduser()
        spool_path = Path(env.get("DEVLOOP_SPOOL_FILE", file_data.get("spool_file", state / "spool.jsonl"))).expanduser()
        timeout_raw = env.get("DEVLOOP_TIMEOUT_SECONDS", file_data.get("timeout_seconds", 5.0))
        api_url = _validate_api_url(api_url)
        if token is not None and not isinstance(token, str):
            raise ConfigError("token must be a string")
        try:
            timeout = float(timeout_raw)
        except (TypeError, ValueError) as exc:
            raise ConfigError("timeout_seconds must be numeric") from exc
        if not 0.1 <= timeout <= 60:
            raise ConfigError("timeout_seconds must be between 0.1 and 60")
        return cls(api_url, token, device_path, spool_path, timeout)

    def device_id(self) -> str:
        try:
            value = self.device_id_file.read_text(encoding="ascii").strip()
            if len(value) == 32 and all(ch in "0123456789abcdef" for ch in value):
                return value
            raise ConfigError("device ID file is invalid")
        except FileNotFoundError:
            self.device_id_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            value = secrets.token_hex(16)
            # Exclusive creation avoids two concurrent collectors choosing different IDs.
            try:
                fd = os.open(self.device_id_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                return self.device_id()
            with os.fdopen(fd, "w", encoding="ascii") as handle:
                handle.write(value + "\n")
            return value
        except OSError as exc:
            raise ConfigError(f"cannot access device ID file: {exc}") from exc
