from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from typing import Callable

from .client import DeliveryError
from .events import Event, EventValidationError


class Spool:
    """A process-safe JSONL event spool for macOS and Linux."""

    def __init__(self, path: Path):
        self.path = path
        self.lock_path = path.with_suffix(path.suffix + ".lock")

    def _prepare(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _locked(self):
        self._prepare()
        lock = self.lock_path.open("a+", encoding="utf-8")
        os.chmod(self.lock_path, 0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        return lock

    def append(self, event: Event) -> None:
        # Round-trip validation prevents arbitrary keys ever reaching disk.
        safe = Event.from_dict(event.to_dict())
        lock = self._locked()
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(safe.to_dict(), separators=(",", ":"), ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            lock.close()

    def retry(self, sender: Callable[[Event], None], *, limit: int = 10) -> tuple[int, int, int]:
        """Attempt a bounded number of lines; return delivered, remaining, invalid."""
        if limit < 1:
            raise ValueError("retry limit must be positive")
        lock = self._locked()
        try:
            try:
                lines = self.path.read_text(encoding="utf-8").splitlines()
            except FileNotFoundError:
                return (0, 0, 0)
            remaining: list[str] = []
            delivered = invalid = 0
            for index, line in enumerate(lines):
                if index >= limit:
                    remaining.extend(lines[index:])
                    break
                try:
                    raw = json.loads(line)
                    event = Event.from_dict(raw)
                except (json.JSONDecodeError, EventValidationError):
                    invalid += 1
                    continue
                try:
                    sender(event)
                except DeliveryError as exc:
                    if exc.transient:
                        # Preserve the failed event and unattempted records exactly.
                        remaining.extend(lines[index:])
                        break
                    # Permanent auth/validation/other 4xx failures cannot heal.
                    invalid += 1
                except Exception:
                    # Unknown sender failures are conservatively transient.
                    remaining.extend(lines[index:])
                    break
                else:
                    delivered += 1
            self._rewrite_lines(remaining)
            return delivered, len(remaining), invalid
        finally:
            lock.close()

    def _rewrite_lines(self, lines: list[str]) -> None:
        if not lines:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            return
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                for line in lines:
                    handle.write(line + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
