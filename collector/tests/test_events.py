import uuid

import pytest

from devloop_collector.events import Event, EventValidationError


DEVICE = "a" * 32


def test_serialization_and_duration_clamps():
    event = Event.create(
        device_id=DEVICE, source="editor", kind="heartbeat", duration_seconds=9999,
        occurred_at="2026-01-02T03:04:05+02:00", event_id=str(uuid.UUID(int=1)),
        project="/private/work/my project", entity=r"C:\secret\src\main.py",
        language=" Python\n", tool="VS Code",
    )
    assert event.duration_seconds == 900
    assert event.project == "my project"
    assert event.entity == "main.py"
    assert event.occurred_at == "2026-01-02T01:04:05.000Z"
    assert event.to_dict() == {
        "id": "00000000-0000-0000-0000-000000000001",
        "occurred_at": "2026-01-02T01:04:05.000Z",
        "device_id": DEVICE,
        "source": "editor",
        "kind": "heartbeat",
        "duration_seconds": 900,
        "project": "my project",
        "entity": "main.py",
        "language": "Python",
        "tool": "VS Code",
    }
    assert Event.create(device_id=DEVICE, source="ai", kind="ai_activity", duration_seconds=-2, tool="local").duration_seconds == 0


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "3", True])
def test_invalid_durations(bad):
    with pytest.raises(EventValidationError):
        Event.create(device_id=DEVICE, source="ai", kind="ai_activity", duration_seconds=bad, tool="AI")


def test_fixed_schema_rejects_unknown_and_wrong_kind_fields():
    base = Event.create(device_id=DEVICE, source="manual", kind="milestone", label="Done").to_dict()
    with pytest.raises(EventValidationError, match="unknown event fields"):
        Event.from_dict({**base, "prompt": "secret"})
    with pytest.raises(EventValidationError, match="not allowed"):
        Event.from_dict({**base, "branch": "main"})
    with pytest.raises(EventValidationError, match="source/kind"):
        Event.create(device_id=DEVICE, source="ai", kind="commit")


def test_sanitization_bounds_controls_and_rejects_remotes():
    event = Event.create(
        device_id=DEVICE, source="manual", kind="milestone",
        label="  shipped\n\tfeature\x00  " + "x" * 200,
    )
    assert "\n" not in event.label
    assert len(event.label) == 120
    with pytest.raises(EventValidationError, match="URL or repository remote"):
        Event.create(device_id=DEVICE, source="git", kind="commit", branch="https://host/repo", magnitude=1)
    with pytest.raises(EventValidationError, match="remote"):
        Event.create(device_id=DEVICE, source="git", kind="commit", branch="git@example:repo", magnitude=1)


def test_invalid_identifier_timestamp_and_magnitude():
    with pytest.raises(EventValidationError):
        Event.create(device_id="human-laptop", source="manual", kind="milestone", label="x")
    with pytest.raises(EventValidationError):
        Event.create(device_id=DEVICE, source="manual", kind="milestone", occurred_at="yesterday", label="x")
    with pytest.raises(EventValidationError):
        Event.create(device_id=DEVICE, source="test", kind="test_run", magnitude=-1, success=True)
    with pytest.raises(EventValidationError):
        Event.create(device_id=DEVICE, source="test", kind="test_run", magnitude=1001, success=True)
