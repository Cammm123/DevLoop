from __future__ import annotations

import math
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, ClassVar


class EventValidationError(ValueError):
    """Raised when input is not a valid, privacy-safe DevLoop event."""


_SOURCES = {"editor", "terminal", "git", "test", "build", "ai", "manual"}
_KIND_SOURCES = {
    "heartbeat": {"editor", "terminal"},
    "git_snapshot": {"git"},
    "commit": {"git"},
    "test_run": {"test"},
    "build": {"build"},
    "ai_activity": {"ai"},
    "milestone": {"manual"},
}
_OPTIONAL_BY_KIND = {
    "heartbeat": {"project", "entity", "language", "tool"},
    "git_snapshot": {"project", "branch", "magnitude"},
    "commit": {"project", "branch", "magnitude"},
    "test_run": {"project", "tool", "success", "magnitude"},
    "build": {"project", "tool", "success", "magnitude"},
    "ai_activity": {"project", "tool"},
    "milestone": {"project", "label"},
}
_FIELDS = {
    "id", "occurred_at", "device_id", "source", "kind", "duration_seconds",
    "project", "entity", "language", "tool", "branch", "success", "magnitude", "label",
}
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_WS_RE = re.compile(r"\s+")
_SAFE_DEVICE_RE = re.compile(r"^[0-9a-f]{32}$")


def _clean_text(value: Any, field: str, limit: int, *, basename: bool = False) -> str:
    if not isinstance(value, str):
        raise EventValidationError(f"{field} must be a string")
    value = unicodedata.normalize("NFKC", value)
    if basename:
        # Never transmit a directory path. Handle both POSIX and Windows separators.
        value = value.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    value = _WS_RE.sub(" ", _CONTROL_RE.sub("", value)).strip()
    if not value:
        raise EventValidationError(f"{field} must not be empty")
    if "://" in value or value.startswith(("git@", "ssh:")):
        raise EventValidationError(f"{field} must not contain a URL or repository remote")
    return value[:limit]


def clamp_duration(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EventValidationError("duration_seconds must be a number")
    value = float(value)
    if not math.isfinite(value):
        raise EventValidationError("duration_seconds must be finite")
    return min(900, max(0, int(round(value))))


def _timestamp(value: Any) -> str:
    if not isinstance(value, str):
        raise EventValidationError("occurred_at must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EventValidationError("occurred_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise EventValidationError("occurred_at must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class Event:
    id: str
    occurred_at: str
    device_id: str
    source: str
    kind: str
    duration_seconds: int
    project: str | None = None
    entity: str | None = None
    language: str | None = None
    tool: str | None = None
    branch: str | None = None
    success: bool | None = None
    magnitude: int | None = None
    label: str | None = None

    field_names: ClassVar[frozenset[str]] = frozenset(_FIELDS)

    @classmethod
    def create(
        cls, *, device_id: str, source: str, kind: str, duration_seconds: int | float = 0,
        occurred_at: str | None = None, event_id: str | None = None, **optional: Any,
    ) -> "Event":
        raw = {
            "id": event_id or str(uuid.uuid4()), "occurred_at": occurred_at or utc_now(),
            "device_id": device_id, "source": source, "kind": kind,
            "duration_seconds": duration_seconds, **optional,
        }
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: Any) -> "Event":
        if not isinstance(raw, dict):
            raise EventValidationError("event must be a JSON object")
        unknown = set(raw) - _FIELDS
        if unknown:
            raise EventValidationError(f"unknown event fields: {', '.join(sorted(unknown))}")
        missing = {"id", "occurred_at", "device_id", "source", "kind", "duration_seconds"} - set(raw)
        if missing:
            raise EventValidationError(f"missing event fields: {', '.join(sorted(missing))}")
        try:
            event_id = str(uuid.UUID(raw["id"] if isinstance(raw["id"], str) else ""))
        except (ValueError, AttributeError) as exc:
            raise EventValidationError("id must be a UUID") from exc
        device_id = raw["device_id"]
        if not isinstance(device_id, str) or not _SAFE_DEVICE_RE.fullmatch(device_id):
            raise EventValidationError("device_id must be a 32-character opaque hex ID")
        source, kind = raw["source"], raw["kind"]
        if source not in _SOURCES or kind not in _KIND_SOURCES or source not in _KIND_SOURCES[kind]:
            raise EventValidationError("invalid source/kind combination")
        supplied_optional = {key for key in raw if key in (_FIELDS - {"id", "occurred_at", "device_id", "source", "kind", "duration_seconds"}) and raw[key] is not None}
        disallowed = supplied_optional - _OPTIONAL_BY_KIND[kind]
        if disallowed:
            raise EventValidationError(f"fields not allowed for {kind}: {', '.join(sorted(disallowed))}")

        values: dict[str, Any] = {}
        for key, limit, basename in (
            ("project", 80, True), ("entity", 120, True), ("language", 40, False),
            ("tool", 60, False), ("branch", 120, False), ("label", 120, False),
        ):
            value = raw.get(key)
            values[key] = None if value is None else _clean_text(value, key, limit, basename=basename)
        success = raw.get("success")
        if success is not None and not isinstance(success, bool):
            raise EventValidationError("success must be a boolean")
        magnitude = raw.get("magnitude")
        if magnitude is not None:
            if isinstance(magnitude, bool) or not isinstance(magnitude, int) or not 0 <= magnitude <= 1000:
                raise EventValidationError("magnitude must be an integer from 0 through 1000")
        return cls(
            id=event_id, occurred_at=_timestamp(raw["occurred_at"]), device_id=device_id,
            source=source, kind=kind, duration_seconds=clamp_duration(raw["duration_seconds"]),
            success=success, magnitude=magnitude, **values,
        )

    def to_dict(self) -> dict[str, Any]:
        data = {name: getattr(self, name) for name in _FIELDS}
        return {key: data[key] for key in (
            "id", "occurred_at", "device_id", "source", "kind", "duration_seconds",
            "project", "entity", "language", "tool", "branch", "success", "magnitude", "label",
        ) if data[key] is not None}
