from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SAFE_TEXT = re.compile(r"^[^\x00-\x1f\x7f]*$")


class Source(StrEnum):
    EDITOR = "editor"
    TERMINAL = "terminal"
    GIT = "git"
    TEST = "test"
    BUILD = "build"
    AI = "ai"
    MANUAL = "manual"


class Kind(StrEnum):
    HEARTBEAT = "heartbeat"
    GIT_SNAPSHOT = "git_snapshot"
    COMMIT = "commit"
    TEST_RUN = "test_run"
    BUILD = "build"
    AI_ACTIVITY = "ai_activity"
    MILESTONE = "milestone"


_ALLOWED_KINDS = {
    Source.EDITOR: {Kind.HEARTBEAT},
    Source.TERMINAL: {Kind.HEARTBEAT},
    Source.AI: {Kind.AI_ACTIVITY},
    Source.GIT: {Kind.GIT_SNAPSHOT, Kind.COMMIT},
    Source.TEST: {Kind.TEST_RUN},
    Source.BUILD: {Kind.BUILD},
    Source.MANUAL: {Kind.MILESTONE},
}

Safe64 = Annotated[str, Field(min_length=1, max_length=64)]
Safe128 = Annotated[str, Field(min_length=1, max_length=128)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EventIn(StrictModel):
    id: UUID
    occurred_at: datetime
    device_id: Safe64
    source: Source
    kind: Kind
    duration_seconds: int = Field(default=0, ge=0, le=900)
    project: Safe128 | None = None
    entity: Safe128 | None = None
    language: Safe64 | None = None
    tool: Safe64 | None = None
    branch: Safe128 | None = None
    success: bool | None = None
    magnitude: int | None = Field(default=None, ge=0, le=1000)
    label: Annotated[str, Field(min_length=1, max_length=160)] | None = None

    @field_validator("occurred_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a UTC offset")
        if value.utcoffset().total_seconds() != 0:
            raise ValueError("occurred_at must be UTC")
        return value.astimezone(timezone.utc)

    @field_validator("device_id", "project", "entity", "language", "tool", "branch", "label")
    @classmethod
    def sanitized_text(cls, value: str | None) -> str | None:
        if value is not None and not _SAFE_TEXT.fullmatch(value):
            raise ValueError("text must not contain control characters")
        return value

    @field_validator("device_id", "project", "entity", "language", "tool")
    @classmethod
    def no_paths(cls, value: str | None) -> str | None:
        if value is not None and ("/" in value or "\\" in value):
            raise ValueError("paths are not accepted")
        return value

    @model_validator(mode="after")
    def valid_shape(self) -> "EventIn":
        if self.kind not in _ALLOWED_KINDS[self.source]:
            raise ValueError(f"{self.kind} is not valid for source {self.source}")
        if self.source is Source.MANUAL:
            if not self.label:
                raise ValueError("milestones require label")
        elif self.label is not None:
            raise ValueError("label is only accepted for milestones")
        if self.success is not None and self.kind not in {Kind.TEST_RUN, Kind.BUILD}:
            raise ValueError("success is only accepted for tests and builds")
        if self.kind in {Kind.HEARTBEAT, Kind.AI_ACTIVITY} and self.duration_seconds == 0:
            raise ValueError("activity events require active duration")
        return self


class EventBatch(StrictModel):
    events: list[EventIn] = Field(min_length=1, max_length=500)


class BatchResult(StrictModel):
    received: int
    inserted: int
    duplicates: int


class MilestoneIn(StrictModel):
    title: Annotated[str, Field(min_length=1, max_length=160)]
    occurred_at: datetime | None = None
    device_id: Safe64 = "iphone"
    project: Safe128 | None = None
    magnitude: int = Field(default=1, ge=1, le=100)

    @field_validator("title", "device_id", "project")
    @classmethod
    def sanitize(cls, value: str | None) -> str | None:
        if value is not None and not _SAFE_TEXT.fullmatch(value):
            raise ValueError("text must not contain control characters")
        return value

    @field_validator("device_id", "project")
    @classmethod
    def no_paths(cls, value: str | None) -> str | None:
        if value is not None and ("/" in value or "\\" in value):
            raise ValueError("paths are not accepted")
        return value

    @field_validator("occurred_at")
    @classmethod
    def milestone_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None or value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
            raise ValueError("occurred_at must be UTC")
        return value.astimezone(timezone.utc)
