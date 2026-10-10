from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .models import EventIn

_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class StoredEvent:
    id: str
    occurred_at: datetime
    source: str
    kind: str
    duration_seconds: int
    project: str | None
    entity: str | None
    language: str | None
    tool: str | None
    branch: str | None
    success: bool | None
    magnitude: int | None
    label: str | None


class Database:
    def __init__(self, path: Path):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > _SCHEMA_VERSION:
                raise RuntimeError(
                    f"database schema {version} is newer than supported {_SCHEMA_VERSION}"
                )
            if version < 1:
                connection.executescript(
                    """
                    BEGIN IMMEDIATE;
                    CREATE TABLE events (
                        id TEXT PRIMARY KEY NOT NULL,
                        occurred_at TEXT NOT NULL,
                        device_id TEXT NOT NULL,
                        source TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        duration_seconds INTEGER NOT NULL CHECK(duration_seconds BETWEEN 0 AND 900),
                        project TEXT,
                        entity TEXT,
                        language TEXT,
                        tool TEXT,
                        branch TEXT,
                        success INTEGER CHECK(success IN (0, 1) OR success IS NULL),
                        magnitude INTEGER,
                        label TEXT,
                        received_at TEXT NOT NULL
                    ) STRICT;
                    CREATE INDEX events_occurred_at_idx ON events(occurred_at);
                    PRAGMA user_version = 1;
                    COMMIT;
                    """
                )
        os.chmod(self.path, 0o600)

    def insert_events(self, events: Iterable[EventIn]) -> int:
        rows = [
            (
                str(event.id),
                _iso(event.occurred_at),
                event.device_id,
                event.source.value,
                event.kind.value,
                event.duration_seconds,
                event.project,
                event.entity,
                event.language,
                event.tool,
                event.branch,
                None if event.success is None else int(event.success),
                event.magnitude,
                event.label,
                _iso(datetime.now().astimezone()),
            )
            for event in events
        ]
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            before = connection.total_changes
            connection.executemany(
                """
                INSERT OR IGNORE INTO events (
                    id, occurred_at, device_id, source, kind, duration_seconds,
                    project, entity, language, tool, branch, success, magnitude,
                    label, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            return connection.total_changes - before

    def events_between(self, start: datetime, end: datetime) -> list[StoredEvent]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, occurred_at, source, kind, duration_seconds, project,
                       entity, language, tool, branch, success, magnitude, label
                FROM events
                WHERE occurred_at >= ? AND occurred_at < ?
                ORDER BY occurred_at ASC, id ASC
                """,
                (_iso(start), _iso(end)),
            ).fetchall()
        return [
            StoredEvent(
                id=row["id"],
                occurred_at=datetime.fromisoformat(row["occurred_at"].replace("Z", "+00:00")),
                source=row["source"],
                kind=row["kind"],
                duration_seconds=row["duration_seconds"],
                project=row["project"],
                entity=row["entity"],
                language=row["language"],
                tool=row["tool"],
                branch=row["branch"],
                success=None if row["success"] is None else bool(row["success"]),
                magnitude=row["magnitude"],
                label=row["label"],
            )
            for row in rows
        ]

    def check(self) -> bool:
        with self.connect() as connection:
            return connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
