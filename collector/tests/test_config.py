import json
import stat

import pytest

from devloop_collector.config import Config, ConfigError


def test_config_file_env_override_and_stable_device(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        '[collector]\napi_url="https://local.invalid/api"\ntimeout_seconds=2\n', encoding="utf-8"
    )
    env = {
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "DEVLOOP_TOKEN": "secret",
        "DEVLOOP_SPOOL_FILE": str(tmp_path / "custom.jsonl"),
    }
    config = Config.load(config_file, env)
    assert config.api_url == "https://local.invalid/api"
    assert config.token == "secret"
    assert config.spool_file == tmp_path / "custom.jsonl"
    first = config.device_id()
    assert len(first) == 32
    assert config.device_id() == first
    assert stat.S_IMODE(config.device_id_file.stat().st_mode) == 0o600


def test_unknown_config_rejected(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[collector]\ncollect_source=true\n')
    with pytest.raises(ConfigError, match="unknown"):
        Config.load(path, {})


def test_invalid_existing_device_id_rejected(tmp_path):
    device = tmp_path / "device"
    device.write_text("my-human-readable-hostname")
    config = Config("http://localhost", None, device, tmp_path / "spool")
    with pytest.raises(ConfigError, match="invalid"):
        config.device_id()


@pytest.mark.parametrize("url", [
    "https://api.example.com",
    "https://api.example.com/base/path",
    "http://localhost:8000",
    "http://127.0.0.1",
    "http://[::1]:8000",
    "http://100.64.0.1",
    "http://100.127.255.254",
    "http://[fd7a:115c:a1e0::1234]",
])
def test_api_url_transport_allowed(tmp_path, url):
    path = tmp_path / "config.toml"
    path.write_text(f'[collector]\napi_url="{url}"\n')
    assert Config.load(path, {}).api_url == url


@pytest.mark.parametrize("url", [
    "http://example.com",
    "http://tailscale-host.local",
    "http://100.128.0.1",
    "http://[fd7a:115c:a1e1::1]",
    "ftp://127.0.0.1",
    "https://user:pass@example.com",
    "https://example.com?token=secret",
    "https://example.com#fragment",
    "https://example.com?",
])
def test_api_url_transport_rejected(tmp_path, url):
    path = tmp_path / "config.toml"
    path.write_text(f'[collector]\napi_url="{url}"\n')
    with pytest.raises(ConfigError):
        Config.load(path, {})
