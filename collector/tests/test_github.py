import json
import os

from devloop_collector.events import Event
from devloop_collector.github import GitHubPush, fetch_pushes, load_seen, save_seen


DEVICE = "f" * 32


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, *args):
        return json.dumps(self.payload).encode()


def test_fetch_pushes_keeps_only_allowlisted_aggregate_metadata(monkeypatch):
    payload = [{
        "id": "12345",
        "type": "PushEvent",
        "created_at": "2026-10-10T12:00:00Z",
        "repo": {"name": "Cammm123/private-looking-name", "url": "secret"},
        "payload": {
            "ref": "refs/heads/main",
            "commits": [{"message": "must not survive", "author": {"email": "private@example.com"}}],
        },
    }, {"id": "2", "type": "IssuesEvent"}]
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: Response(payload))

    pushes = fetch_pushes("Cammm123")

    assert pushes == [GitHubPush("12345", "2026-10-10T12:00:00Z", "private-looking-name", "main")]
    assert "must not survive" not in repr(pushes)
    assert "private@example.com" not in repr(pushes)


def test_push_conversion_is_deterministic_and_conservative():
    push = GitHubPush("12345", "2026-10-10T12:00:00Z", "project", "main")
    first = push.to_event(username="Cammm123", device_id=DEVICE)
    second = push.to_event(username="cammm123", device_id=DEVICE)

    assert isinstance(first, Event)
    assert first == second
    assert first.kind == "commit"
    assert first.magnitude == 1
    assert first.project == "project"


def test_seen_state_round_trip_is_private(tmp_path):
    path = tmp_path / "state" / "github.json"
    save_seen(path, {"2", "1"})

    assert load_seen(path) == {"1", "2"}
    assert os.stat(path).st_mode & 0o777 == 0o600
