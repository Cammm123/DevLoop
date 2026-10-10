import json
import stat

from devloop_collector.client import DeliveryError
from devloop_collector.events import Event
from devloop_collector.spool import Spool


DEVICE = "b" * 32


def make_event():
    return Event.create(device_id=DEVICE, source="ai", kind="ai_activity", duration_seconds=4, tool="AI")


def test_offline_spool_and_retry_preserves_id(tmp_path):
    spool = Spool(tmp_path / "state" / "retry.jsonl")
    event = make_event()
    spool.append(event)
    assert stat.S_IMODE(spool.path.stat().st_mode) == 0o600

    def offline(_event):
        raise RuntimeError("offline")

    assert spool.retry(offline) == (0, 1, 0)
    queued = json.loads(spool.path.read_text())
    assert queued["id"] == event.id

    received = []
    assert spool.retry(received.append) == (1, 0, 0)
    assert received[0].id == event.id
    assert not spool.path.exists()


def test_retry_drops_invalid_lines_without_sending(tmp_path):
    spool = Spool(tmp_path / "spool.jsonl")
    spool.path.write_text(
        '{"prompt":"must never survive"}\nnot-json\n', encoding="utf-8"
    )
    received = []
    assert spool.retry(received.append) == (0, 0, 2)
    assert received == []
    assert not spool.path.exists()


def test_multiple_retry_partial_failure(tmp_path):
    spool = Spool(tmp_path / "spool.jsonl")
    first, second = make_event(), make_event()
    spool.append(first)
    spool.append(second)

    def sender(event):
        if event.id == second.id:
            raise RuntimeError

    assert spool.retry(sender) == (1, 1, 0)
    assert json.loads(spool.path.read_text())["id"] == second.id


def test_transient_failure_stops_and_preserves_unattempted_records(tmp_path):
    spool = Spool(tmp_path / "spool.jsonl")
    events = [make_event() for _ in range(3)]
    for event in events:
        spool.append(event)
    calls = []

    def sender(event):
        calls.append(event.id)
        raise DeliveryError("offline", transient=True)

    assert spool.retry(sender, limit=10) == (0, 3, 0)
    assert calls == [events[0].id]
    assert [json.loads(line)["id"] for line in spool.path.read_text().splitlines()] == [
        event.id for event in events
    ]


def test_permanent_failure_is_dropped_and_retry_is_bounded(tmp_path):
    spool = Spool(tmp_path / "spool.jsonl")
    events = [make_event() for _ in range(4)]
    for event in events:
        spool.append(event)

    def sender(_event):
        raise DeliveryError("bad request", transient=False)

    assert spool.retry(sender, limit=2) == (0, 2, 2)
    assert [json.loads(line)["id"] for line in spool.path.read_text().splitlines()] == [
        event.id for event in events[2:]
    ]
