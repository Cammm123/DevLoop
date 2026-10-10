import io
import json

import pytest

from devloop_collector.cli import _event_from_payload, main
from devloop_collector.events import EventValidationError


DEVICE = "e" * 32


def test_stdin_fixed_schema_builds_event():
    event = _event_from_payload({
        "type": "heartbeat", "duration_seconds": 12, "source": "editor",
        "project": "/work/app", "file": "/work/app/private.py", "language": "Python",
        "editor": "VS Code",
    }, DEVICE)
    assert event.project == "app"
    assert event.entity == "private.py"
    assert event.kind == "heartbeat"


@pytest.mark.parametrize("payload", [
    {"type": "heartbeat", "duration_seconds": 1, "command": "rm -rf /"},
    {"type": "ai_activity", "duration_seconds": 1, "tool": "AI", "prompt": "secret"},
    {"type": "milestone", "title": "x", "environment": {"TOKEN": "secret"}},
    {"type": "anything", "payload": "arbitrary"},
])
def test_stdin_rejects_arbitrary_or_private_fields(payload):
    with pytest.raises(EventValidationError):
        _event_from_payload(payload, DEVICE)


def test_offline_cli_queues_validated_event(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("DEVLOOP_API_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("DEVLOOP_TIMEOUT_SECONDS", "0.1")
    monkeypatch.delenv("DEVLOOP_TOKEN", raising=False)
    result = main(["heartbeat", "--duration", "30", "--project", "/secret/demo", "--file", "/secret/main.py"])
    assert result == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "queued"
    spool = tmp_path / "state" / "devloop" / "spool.jsonl"
    queued = json.loads(spool.read_text())
    assert queued["project"] == "demo"
    assert queued["entity"] == "main.py"
    assert "/secret" not in spool.read_text()


def test_cli_stdin_unknown_field_fails_without_spooling(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr("sys.stdin", io.StringIO('{"type":"heartbeat","duration_seconds":2,"output":"secret"}'))
    assert main(["stdin"]) == 2
    assert "unknown stdin fields" in capsys.readouterr().err
    assert not (tmp_path / "state" / "devloop" / "spool.jsonl").exists()
