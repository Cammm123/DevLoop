from __future__ import annotations

import json
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

import uvicorn

COLLECTOR_SRC = Path(__file__).resolve().parents[2] / "collector" / "src"
sys.path.insert(0, str(COLLECTOR_SRC))

from devloop_collector.client import APIClient  # noqa: E402
from devloop_collector.config import Config  # noqa: E402
from devloop_collector.events import Event  # noqa: E402
from devloop_server.app import create_app  # noqa: E402
from devloop_server.config import Settings  # noqa: E402

TOKEN = "integration-token-that-is-at-least-32-characters"


def test_real_collector_posts_to_real_server_and_updates_dashboard(tmp_path: Path) -> None:
    app = create_app(Settings(TOKEN, tmp_path / "devloop.sqlite3"))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="on"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.01)
        assert server.started

        collector_config = Config(
            f"http://127.0.0.1:{port}", TOKEN,
            tmp_path / "device-id", tmp_path / "spool.jsonl", 2,
        )
        event = Event.create(
            device_id="a" * 32,
            source="editor",
            kind="heartbeat",
            duration_seconds=900,
            project="devloop",
            entity="DashboardView.swift",
            language="Swift",
            tool="Xcode",
        )
        APIClient(collector_config).send(event)
        # Sending the same UUID again must be harmless.
        APIClient(collector_config).send(event)

        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/dashboard?date={event.occurred_at[:10]}&timezone=UTC",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            dashboard = json.load(response)

        assert dashboard["event_count"] == 1
        assert dashboard["active_seconds"] == 900
        assert dashboard["output_points"] == 1
        assert dashboard["recent_events"][0]["label"] == "DashboardView.swift"
        assert len(dashboard["trend"]) == 14
        assert dashboard["languages"] == [{"name": "Swift", "value": 100.0}]
        assert dashboard["projects"] == [{"name": "devloop", "value": 100.0}]
        assert dashboard["time"]["kind"] == "time"
        assert dashboard["summary"]["active_minutes"] == 15
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
        assert not thread.is_alive()
