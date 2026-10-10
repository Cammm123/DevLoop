from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitMetadataError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GitMetadata:
    project: str
    branch: str
    commit_count: int
    changed_files: int


def _git(repo: Path, *args: str) -> bytes:
    # Every command is a constant metadata query. No shell, diffs, remotes, config,
    # blobs, file contents, commit messages, or user identity are requested.
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args], check=True, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitMetadataError("unable to read Git metadata") from exc
    return completed.stdout


def _branch(repo: Path) -> str:
    try:
        value = _git(repo, "symbolic-ref", "--quiet", "--short", "HEAD").decode("utf-8", "replace").strip()
    except GitMetadataError:
        return "detached"
    return value or "detached"


def _commit_count(repo: Path) -> int:
    try:
        return int(_git(repo, "rev-list", "--count", "HEAD").strip() or b"0")
    except GitMetadataError:
        # An unborn repository has no HEAD.
        return 0
    except ValueError as exc:
        raise GitMetadataError("invalid Git metadata") from exc


def _status_count(repo: Path) -> int:
    # -z makes unusual filenames safe. Rename/copy records have a second path.
    fields = _git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=normal").split(b"\0")
    count = index = 0
    while index < len(fields) and fields[index]:
        record = fields[index]
        count += 1
        status = record[:2]
        index += 2 if b"R" in status or b"C" in status else 1
    return count


def snapshot(repo: Path) -> GitMetadata:
    resolved = repo.expanduser().resolve()
    top = Path(_git(resolved, "rev-parse", "--show-toplevel").decode("utf-8", "replace").strip())
    return GitMetadata(top.name, _branch(resolved), _commit_count(resolved), _status_count(resolved))


def latest_commit_changed_files(repo: Path) -> int:
    # Only count NUL-delimited names; names themselves are discarded immediately.
    raw = _git(repo.expanduser().resolve(), "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", "-z", "HEAD")
    return sum(bool(item) for item in raw.split(b"\0"))
