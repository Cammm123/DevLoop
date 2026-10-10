from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .events import Event


class GitHubSyncError(RuntimeError):
    """GitHub activity could not be fetched or safely interpreted."""


_USER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
_NAMESPACE = uuid.UUID("90ad0d9b-8a1a-44d8-a70e-869c94280920")


@dataclass(frozen=True, slots=True)
class GitHubPush:
    event_id: str
    occurred_at: str
    project: str
    branch: str

    def to_event(self, *, username: str, device_id: str) -> Event:
        # GitHub's public event feed deliberately omits per-push commit counts.
        # Count each push conservatively as one commit and use a deterministic
        # UUID so server idempotency survives loss of the local cursor file.
        stable_id = str(uuid.uuid5(_NAMESPACE, f"{username.lower()}:{self.event_id}"))
        return Event.create(
            device_id=device_id,
            source="git",
            kind="commit",
            duration_seconds=0,
            occurred_at=self.occurred_at,
            event_id=stable_id,
            project=self.project,
            branch=self.branch,
            magnitude=1,
        )


def default_state_file(username: str) -> Path:
    state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return state_home / "devloop" / f"github-{username.lower()}.json"


def fetch_pushes(username: str, *, token: str | None = None, timeout: float = 10) -> list[GitHubPush]:
    if not _USER_RE.fullmatch(username):
        raise GitHubSyncError("invalid GitHub username")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "devloop-collector/0.1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"https://api.github.com/users/{username}/events?per_page=100", headers=headers
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise GitHubSyncError(f"GitHub returned HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        raise GitHubSyncError("GitHub activity is unavailable") from None
    if not isinstance(payload, list):
        raise GitHubSyncError("GitHub returned an invalid event feed")

    pushes: list[GitHubPush] = []
    for raw in payload:
        if not isinstance(raw, dict) or raw.get("type") != "PushEvent":
            continue
        event_id = raw.get("id")
        occurred_at = raw.get("created_at")
        repo = raw.get("repo")
        push_payload = raw.get("payload")
        if not isinstance(event_id, str) or not isinstance(occurred_at, str):
            continue
        if not isinstance(repo, dict) or not isinstance(push_payload, dict):
            continue
        repo_name = repo.get("name")
        ref = push_payload.get("ref")
        if not isinstance(repo_name, str) or not isinstance(ref, str):
            continue
        project = repo_name.rsplit("/", 1)[-1]
        branch = ref.removeprefix("refs/heads/").rsplit("/", 1)[-1]
        pushes.append(GitHubPush(event_id, occurred_at, project, branch))
    return pushes


def load_seen(path: Path) -> set[str]:
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return set()
    except (OSError, json.JSONDecodeError) as exc:
        raise GitHubSyncError("cannot read GitHub sync state") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("seen_event_ids"), list):
        raise GitHubSyncError("GitHub sync state is invalid")
    return {value for value in raw["seen_event_ids"] if isinstance(value, str)}


def save_seen(path: Path, seen: set[str]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = path.with_suffix(path.suffix + ".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"seen_event_ids": sorted(seen)[-5000:]}, handle, separators=(",", ":"))
            handle.write("\n")
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except OSError as exc:
        raise GitHubSyncError("cannot write GitHub sync state") from exc
