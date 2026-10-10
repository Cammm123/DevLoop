from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from devloop_server.app import create_app
from devloop_server.config import Settings

TOKEN = "a" * 32


@pytest.fixture
def client(tmp_path: Path):
    app = create_app(Settings(TOKEN, tmp_path / "devloop.sqlite3"))
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def event(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "id": str(uuid4()),
        "occurred_at": "2026-03-10T12:00:00Z",
        "device_id": "laptop-opaque-id",
        "source": "editor",
        "kind": "heartbeat",
        "duration_seconds": 900,
        "project": "devloop",
        "entity": "app.py",
        "language": "Python",
        "tool": "VS Code",
        "branch": "feature/private-api",
    }
    result.update(overrides)
    return result


def post_events(client: TestClient, auth: dict[str, str], events: list[dict[str, object]]):
    return client.post("/v1/events/batch", headers=auth, json={"events": events})


def test_health_and_security_headers(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert client.get("/docs").status_code == 404


def test_auth_required_and_wrong_token_rejected(client: TestClient) -> None:
    for method, path in [
        ("post", "/v1/events/batch"),
        ("post", "/v1/milestones"),
        ("get", "/v1/dashboard"),
    ]:
        response = getattr(client, method)(path)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
    assert client.get("/v1/dashboard", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_batch_ingestion_and_duplicate_idempotency(client: TestClient, auth: dict[str, str]) -> None:
    item = event()
    response = post_events(client, auth, [item, item])
    assert response.status_code == 200
    assert response.json() == {"received": 2, "inserted": 1, "duplicates": 1}
    second = post_events(client, auth, [item])
    assert second.json() == {"received": 1, "inserted": 0, "duplicates": 1}
    dashboard = client.get("/v1/dashboard?date=2026-03-10&timezone=UTC", headers=auth).json()
    assert dashboard["event_count"] == 1


@pytest.mark.parametrize(
    "change",
    [
        {"source": "git", "kind": "heartbeat"},
        {"occurred_at": "2026-03-10T12:00:00"},
        {"occurred_at": "2026-03-10T12:00:00-04:00"},
        {"duration_seconds": 901},
        {"duration_seconds": 0},
        {"entity": "src/secret.py"},
        {"project": "bad\ncommand"},
        {"label": "not a milestone"},
        {"success": True},
        {"payload": {"prompt": "secret"}},
        {"command": "rm -rf /"},
        {"source_code": "print('secret')"},
    ],
)
def test_strict_validation_and_privacy_restrictions(
    client: TestClient, auth: dict[str, str], change: dict[str, object]
) -> None:
    response = post_events(client, auth, [event(**change)])
    assert response.status_code == 422


def test_batch_bounds_and_body_limit(client: TestClient, auth: dict[str, str]) -> None:
    assert post_events(client, auth, []).status_code == 422
    response = client.post(
        "/v1/events/batch",
        headers={**auth, "Content-Length": "1000001"},
        content=b"{}",
    )
    assert response.status_code == 413
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_chunked_body_limit_does_not_trust_content_length(tmp_path: Path) -> None:
    app = create_app(Settings(TOKEN, tmp_path / "devloop.sqlite3"))
    chunks_sent = 0

    async def send_oversized_stream() -> httpx.Response:
        async def chunks():
            nonlocal chunks_sent
            for _ in range(20):
                chunks_sent += 1
                yield b"x" * 100_000

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/v1/events/batch",
                headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
                content=chunks(),
            )

    response = asyncio.run(send_oversized_stream())
    assert response.request.headers.get("content-length") is None
    assert response.request.headers["transfer-encoding"] == "chunked"
    assert response.status_code == 413
    assert response.json() == {"detail": "request body too large"}
    assert chunks_sent == 11  # The remaining streamed body was not consumed or schema-processed.
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_all_typed_events_and_scoring(client: TestClient, auth: dict[str, str]) -> None:
    events = [
        event(id=str(uuid4()), duration_seconds=900),
        event(id=str(uuid4()), source="git", kind="git_snapshot", duration_seconds=0, magnitude=3),
        event(id=str(uuid4()), source="git", kind="commit", duration_seconds=0, magnitude=2),
        event(id=str(uuid4()), source="test", kind="test_run", duration_seconds=0, success=True),
        event(id=str(uuid4()), source="test", kind="test_run", duration_seconds=0, success=False),
        event(id=str(uuid4()), source="build", kind="build", duration_seconds=0, success=True),
        event(id=str(uuid4()), source="build", kind="build", duration_seconds=0, success=False),
        event(
            id=str(uuid4()), source="manual", kind="milestone", duration_seconds=0,
            magnitude=2, label="Ship private sync", entity=None, language=None, tool=None,
        ),
        event(id=str(uuid4()), source="ai", kind="ai_activity", duration_seconds=300),
        event(id=str(uuid4()), source="terminal", kind="heartbeat", duration_seconds=300),
    ]
    response = post_events(client, auth, events)
    assert response.status_code == 200, response.text
    data = client.get("/v1/dashboard?date=2026-03-10&timezone=UTC", headers=auth).json()
    assert data["active_seconds"] == 1500
    assert data["output_points"] == 66  # editor 1 + snapshot 3 + commits 20 + tests 5 + builds 7 + milestone 30
    assert data["xp"] == 112
    assert data["rings"]["time"] == {"value": 1500, "goal": 3600, "progress": 0.4167}
    assert data["rings"]["output"] == {"value": 66, "goal": 20, "progress": 1.0}
    assert data["rings"]["consistency"] == {"value": 1, "goal": 5, "progress": 0.2}
    assert data["time"] == {"kind": "time", "value": 25.0, "goal": 60.0, "unit": "min"}
    assert data["output"] == {"kind": "output", "value": 66, "goal": 20, "unit": "pts"}
    assert data["consistency"] == {"kind": "consistency", "value": 1, "goal": 5, "unit": "days"}
    assert data["summary"] == {
        "active_minutes": 25,
        "commits": 2,
        "successful_checks": 2,
        "focus_sessions": 1,
    }


def test_test_and_build_runtime_is_not_active_time(client: TestClient, auth: dict[str, str]) -> None:
    events = [
        event(
            id=str(uuid4()), source="test", kind="test_run", duration_seconds=900,
            success=True, entity=None, language=None, tool=None,
        ),
        event(
            id=str(uuid4()), source="build", kind="build", duration_seconds=900,
            success=True, entity=None, language=None, tool=None,
        ),
    ]
    assert post_events(client, auth, events).status_code == 200

    data = client.get("/v1/dashboard?date=2026-03-10&timezone=UTC", headers=auth).json()
    assert data["active_seconds"] == 0
    assert data["rings"]["time"] == {"value": 0, "goal": 3600, "progress": 0.0}
    assert data["trend"][-1]["active_minutes"] == 0.0
    assert data["output_points"] == 10
    assert data["xp"] == 15  # Output XP only; elapsed check runtime adds no time XP.
    assert data["summary"]["focus_sessions"] == 0


def test_manual_milestone_endpoint_and_sanitized_recent_events(
    client: TestClient, auth: dict[str, str]
) -> None:
    response = client.post(
        "/v1/milestones",
        headers=auth,
        json={
            "title": "Released API/docs",
            "occurred_at": "2026-03-10T18:30:00Z",
            "device_id": "phone",
            "project": "devloop",
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "created"
    data = client.get("/v1/dashboard?date=2026-03-10&timezone=UTC", headers=auth).json()
    assert data["recent_events"] == [
        {
            "occurred_at": "2026-03-10T18:30:00Z",
            "source": "manual",
            "kind": "milestone",
            "label": "Released API/docs",
        }
    ]
    serialized = str(data)
    assert "device_id" not in serialized
    assert "branch" not in serialized
    assert client.post("/v1/milestones", headers=auth, json={"title": "bad\ntext"}).status_code == 422


def test_adaptive_goals_change_gradually_and_are_bounded(
    client: TestClient, auth: dict[str, str]
) -> None:
    events = []
    for day_offset in range(1, 29):
        day = datetime(2026, 3, 30, 12, tzinfo=timezone.utc) - timedelta(days=day_offset)
        for sequence in range(8):
            events.append(
                event(
                    id=str(uuid4()),
                    occurred_at=(day + timedelta(minutes=sequence)).isoformat().replace("+00:00", "Z"),
                    duration_seconds=900,
                )
            )
        events.append(
            event(
                id=str(uuid4()), occurred_at=day.isoformat().replace("+00:00", "Z"),
                source="git", kind="commit", duration_seconds=0, magnitude=10,
            )
        )
    assert post_events(client, auth, events).status_code == 200
    data = client.get("/v1/dashboard?date=2026-03-30&timezone=UTC", headers=auth).json()
    assert data["rings"]["time"]["goal"] == 4500
    # Daily output is 108 (100 commit + eight 15-minute editor blocks).
    assert data["rings"]["output"]["goal"] == 42
    assert data["rings"]["consistency"]["goal"] == 6


def test_streak_requires_meaningful_activity(client: TestClient, auth: dict[str, str]) -> None:
    events = [
        event(id=str(uuid4()), occurred_at=f"2026-03-{day:02d}T12:00:00Z", duration_seconds=900)
        for day in (7, 8, 9, 10)
    ]
    events.append(event(id=str(uuid4()), occurred_at="2026-03-06T12:00:00Z", duration_seconds=899))
    assert post_events(client, auth, events).status_code == 200
    data = client.get("/v1/dashboard?date=2026-03-10&timezone=UTC", headers=auth).json()
    assert data["streak_days"] == 4
    assert data["active_days_last_7"] == 4


def test_local_date_boundaries_include_dst_transition(client: TestClient, auth: dict[str, str]) -> None:
    # New York's 2026-03-08 day starts 05:00Z and, after spring-forward, ends 04:00Z.
    events = [
        event(id=str(uuid4()), occurred_at="2026-03-08T04:59:59Z", duration_seconds=100),
        event(id=str(uuid4()), occurred_at="2026-03-08T05:00:00Z", duration_seconds=200),
        event(id=str(uuid4()), occurred_at="2026-03-09T03:59:59Z", duration_seconds=300),
        event(id=str(uuid4()), occurred_at="2026-03-09T04:00:00Z", duration_seconds=400),
    ]
    assert post_events(client, auth, events).status_code == 200
    data = client.get(
        "/v1/dashboard?date=2026-03-08&timezone=America%2FNew_York", headers=auth
    ).json()
    assert data["active_seconds"] == 500
    assert data["event_count"] == 2


def test_empty_state_and_invalid_timezone(client: TestClient, auth: dict[str, str]) -> None:
    response = client.get("/v1/dashboard?date=2026-01-01&timezone=UTC", headers=auth)
    assert response.status_code == 200
    data = response.json()
    assert data["date"] == "2026-01-01"
    assert data["timezone"] == "UTC"
    assert data["rings"] == {
        "time": {"value": 0, "goal": 3600, "progress": 0.0},
        "output": {"value": 0, "goal": 20, "progress": 0.0},
        "consistency": {"value": 0, "goal": 5, "progress": 0.0},
    }
    assert data["active_seconds"] == data["output_points"] == data["event_count"] == 0
    assert data["xp"] == data["xp_in_level"] == data["streak"] == data["streak_days"] == 0
    assert data["level"] == 1
    assert len(data["trend"]) == 14
    assert data["languages"] == data["projects"] == data["achievements"] == []
    assert len(data["quests"]) == 3
    assert data["summary"] == {
        "active_minutes": 0, "commits": 0, "successful_checks": 0, "focus_sessions": 0
    }
    assert client.get("/v1/dashboard?timezone=Mars%2FOlympus", headers=auth).status_code == 422


def test_rich_dashboard_contract_is_deterministic_private_and_historical(
    client: TestClient, auth: dict[str, str]
) -> None:
    items: list[dict[str, object]] = []
    for day in range(1, 11):
        timestamp = f"2026-03-{day:02d}T12:00:00Z"
        items.append(event(
            id=str(uuid4()), occurred_at=timestamp, duration_seconds=900,
            project="devloop" if day < 10 else "other", language="Python" if day < 10 else "Swift",
            branch="private/never-return-this",
        ))
    items.extend([
        event(
            id=str(uuid4()), occurred_at="2026-03-10T12:01:00Z", source="git", kind="commit",
            duration_seconds=0, magnitude=2, project="devloop", entity=None, language=None,
        ),
        event(
            id=str(uuid4()), occurred_at="2026-03-10T12:02:00Z", source="test", kind="test_run",
            duration_seconds=0, success=True, project="devloop", entity=None, language=None,
        ),
        event(
            id=str(uuid4()), occurred_at="2026-03-05T13:00:00Z", source="manual", kind="milestone",
            duration_seconds=0, magnitude=1, label="Real release", entity=None, language=None, tool=None,
        ),
    ])
    assert post_events(client, auth, items).status_code == 200
    data = client.get("/v1/dashboard?date=2026-03-10&timezone=UTC", headers=auth).json()

    required = {
        "generated_at", "time", "output", "consistency", "xp", "level", "xp_in_level",
        "xp_for_next_level", "streak", "goals", "trend", "languages", "projects",
        "achievements", "quests", "summary",
    }
    assert required <= data.keys()
    assert data["generated_at"].endswith("Z")
    assert len(data["trend"]) == 14
    assert data["trend"][0]["date"] == "2026-02-25"
    assert data["trend"][-1] == {"date": "2026-03-10", "active_minutes": 15.0, "output_points": 25}
    assert sum(item["value"] for item in data["languages"]) == pytest.approx(100)
    assert sum(item["value"] for item in data["projects"]) == pytest.approx(100)
    assert data["summary"] == {
        "active_minutes": 15, "commits": 2, "successful_checks": 1, "focus_sessions": 0
    }
    assert data["streak"] == data["streak_days"] == 10
    assert data["xp"] > 112  # cumulative, rather than only the selected day's award
    assert data["level"] == data["xp"] // data["xp_for_next_level"] + 1
    assert data["xp_in_level"] == data["xp"] % data["xp_for_next_level"]
    assert [item["id"] for item in data["quests"]] == [
        "daily-focus", "daily-output", "weekly-consistency"
    ]
    achievement_ids = {item["id"] for item in data["achievements"]}
    assert {"first-activity", "streak-3", "streak-7"} <= achievement_ids
    milestone = next(item for item in data["achievements"] if item["title"] == "Real release")
    assert milestone["unlocked_at"] == "2026-03-05T13:00:00Z"
    serialized = str(data)
    assert "device_id" not in serialized
    assert "private/never-return-this" not in serialized
    assert "branch" not in serialized
