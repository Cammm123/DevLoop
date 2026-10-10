import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from devloop_collector.client import APIClient, DeliveryError
from devloop_collector.config import Config
from devloop_collector.events import Event


class Handler(BaseHTTPRequestHandler):
    received = []
    status = 201
    location: str | None = None

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        self.__class__.received.append((self.path, dict(self.headers), self.rfile.read(length)))
        self.send_response(self.__class__.status)
        if self.__class__.location:
            self.send_header("Location", self.__class__.location)
        self.end_headers()
        self.wfile.write(b"ignored response contents")

    def log_message(self, *_args):
        pass


@pytest.fixture
def server():
    Handler.received = []
    Handler.status = 201
    Handler.location = None
    instance = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=instance.serve_forever)
    thread.start()
    try:
        yield instance
    finally:
        instance.shutdown()
        thread.join()


def test_api_client_posts_minimal_event_and_bearer(tmp_path, server):
    config = Config(
        f"http://127.0.0.1:{server.server_port}", "private-token",
        tmp_path / "device", tmp_path / "spool", 1,
    )
    event = Event.create(
        device_id="c" * 32, source="editor", kind="heartbeat", duration_seconds=2,
        entity="main.py",
    )
    APIClient(config).send(event)
    path, headers, body = Handler.received[0]
    assert path == "/v1/events/batch"
    assert headers["Authorization"] == "Bearer private-token"
    payload = json.loads(body)
    assert payload == {"events": [event.to_dict()]}
    serialized = body.decode()
    for forbidden in ("prompt", "response", "command", "remote", "environment", "source_code"):
        assert forbidden not in serialized


def test_http_conflict_is_idempotent_success(tmp_path, server):
    Handler.status = 409
    config = Config(f"http://127.0.0.1:{server.server_port}", None, tmp_path / "d", tmp_path / "s", 1)
    event = Event.create(device_id="d" * 32, source="manual", kind="milestone", label="done")
    APIClient(config).send(event)


def test_http_error_does_not_expose_body(tmp_path, server):
    Handler.status = 500
    config = Config(f"http://127.0.0.1:{server.server_port}", None, tmp_path / "d", tmp_path / "s", 1)
    event = Event.create(device_id="d" * 32, source="manual", kind="milestone", label="done")
    with pytest.raises(DeliveryError) as error:
        APIClient(config).send(event)
    assert "ignored response contents" not in str(error.value)
    assert error.value.transient is True


@pytest.mark.parametrize(
    ("status", "transient"),
    [(400, False), (401, False), (408, True), (425, True), (429, True), (503, True)],
)
def test_http_error_classification(tmp_path, server, status, transient):
    Handler.status = status
    config = Config(f"http://127.0.0.1:{server.server_port}", None, tmp_path / "d", tmp_path / "s")
    event = Event.create(device_id="d" * 32, source="manual", kind="milestone", label="done")
    with pytest.raises(DeliveryError) as error:
        APIClient(config).send(event)
    assert error.value.transient is transient
    assert error.value.permanent is not transient


def test_redirect_is_not_followed(tmp_path, server):
    Handler.status = 307
    Handler.location = "http://example.com/collect"
    config = Config(f"http://127.0.0.1:{server.server_port}", None, tmp_path / "d", tmp_path / "s")
    event = Event.create(device_id="d" * 32, source="manual", kind="milestone", label="done")
    with pytest.raises(DeliveryError) as error:
        APIClient(config).send(event)
    assert error.value.permanent
    assert len(Handler.received) == 1
