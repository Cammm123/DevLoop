from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .client import APIClient, DeliveryError
from .config import Config, ConfigError
from .events import Event, EventValidationError
from .gitmeta import GitMetadataError, latest_commit_changed_files, snapshot
from .spool import Spool


_NORMAL_RETRY_LIMIT = 10
_EXPLICIT_RETRY_LIMIT = 100


_STDIN_SCHEMAS: dict[str, tuple[set[str], set[str]]] = {
    "heartbeat": ({"type", "duration_seconds"}, {"source", "project", "file", "language", "editor"}),
    "test_result": ({"type", "success", "duration_seconds"}, {"project", "tool", "count"}),
    "build_result": ({"type", "success", "duration_seconds"}, {"project", "tool", "count"}),
    "ai_activity": ({"type", "tool", "duration_seconds"}, {"project"}),
    "milestone": ({"type", "title"}, {"project"}),
}


def _event_from_payload(payload: Any, device_id: str) -> Event:
    if not isinstance(payload, dict) or not isinstance(payload.get("type"), str):
        raise EventValidationError("stdin must be one JSON object with a type")
    event_type = payload["type"]
    if event_type not in _STDIN_SCHEMAS:
        raise EventValidationError("unsupported stdin event type")
    required, optional = _STDIN_SCHEMAS[event_type]
    keys = set(payload)
    if missing := required - keys:
        raise EventValidationError(f"missing stdin fields: {', '.join(sorted(missing))}")
    if unknown := keys - required - optional:
        raise EventValidationError(f"unknown stdin fields: {', '.join(sorted(unknown))}")
    if event_type == "heartbeat":
        source = payload.get("source", "editor")
        if source not in {"editor", "terminal"}:
            raise EventValidationError("heartbeat source must be editor or terminal")
        return Event.create(
            device_id=device_id, source=source, kind="heartbeat",
            duration_seconds=payload["duration_seconds"], project=payload.get("project"),
            entity=payload.get("file"), language=payload.get("language"), tool=payload.get("editor"),
        )
    if event_type in {"test_result", "build_result"}:
        source = "test" if event_type == "test_result" else "build"
        kind = "test_run" if source == "test" else "build"
        return Event.create(
            device_id=device_id, source=source, kind=kind,
            duration_seconds=payload["duration_seconds"], project=payload.get("project"),
            tool=payload.get("tool"), success=payload["success"], magnitude=payload.get("count"),
        )
    if event_type == "ai_activity":
        return Event.create(
            device_id=device_id, source="ai", kind="ai_activity",
            duration_seconds=payload["duration_seconds"], project=payload.get("project"), tool=payload["tool"],
        )
    return Event.create(
        device_id=device_id, source="manual", kind="milestone", duration_seconds=0,
        project=payload.get("project"), label=payload["title"],
    )


def _status(args: argparse.Namespace) -> bool:
    if args.success:
        return True
    if args.failure:
        return False
    raise EventValidationError("exactly one of --success or --failure is required")


def _from_args(args: argparse.Namespace, device_id: str) -> Event:
    common = {"device_id": device_id}
    if args.command == "heartbeat":
        return Event.create(
            **common, source=args.source, kind="heartbeat", duration_seconds=args.duration,
            project=args.project, entity=args.file, language=args.language, tool=args.editor,
        )
    if args.command in {"test-result", "build-result"}:
        source = "test" if args.command == "test-result" else "build"
        return Event.create(
            **common, source=source, kind="test_run" if source == "test" else "build",
            duration_seconds=args.duration, project=args.project, tool=args.tool,
            success=_status(args), magnitude=args.count,
        )
    if args.command == "ai":
        return Event.create(
            **common, source="ai", kind="ai_activity", duration_seconds=args.duration,
            project=args.project, tool=args.tool,
        )
    if args.command == "milestone":
        return Event.create(
            **common, source="manual", kind="milestone", duration_seconds=0,
            project=args.project, label=args.title,
        )
    if args.command in {"git-snapshot", "git-commit"}:
        metadata = snapshot(args.repo)
        if args.command == "git-snapshot":
            kind, magnitude = "git_snapshot", metadata.changed_files
        else:
            kind, magnitude = "commit", latest_commit_changed_files(args.repo)
        return Event.create(
            **common, source="git", kind=kind, duration_seconds=0,
            project=metadata.project, branch=metadata.branch, magnitude=magnitude,
        )
    if args.command == "stdin":
        try:
            payload = json.load(sys.stdin)
        except (json.JSONDecodeError, UnicodeError) as exc:
            raise EventValidationError("stdin is not valid JSON") from exc
        return _event_from_payload(payload, device_id)
    raise EventValidationError("unknown command")


def _add_result_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser], name: str) -> None:
    parser = sub.add_parser(name)
    status = parser.add_mutually_exclusive_group(required=True)
    status.add_argument("--success", action="store_true")
    status.add_argument("--failure", action="store_true")
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--project")
    parser.add_argument("--tool")
    parser.add_argument("--count", type=int)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="devloop", description="Privacy-preserving coding activity collector")
    parser.add_argument("--config", type=Path, help="TOML configuration path")
    sub = parser.add_subparsers(dest="command", required=True)

    heartbeat = sub.add_parser("heartbeat")
    heartbeat.add_argument("--duration", type=float, required=True)
    heartbeat.add_argument("--source", choices=("editor", "terminal"), default="editor")
    heartbeat.add_argument("--project")
    heartbeat.add_argument("--file")
    heartbeat.add_argument("--language")
    heartbeat.add_argument("--editor")

    for name in ("git-snapshot", "git-commit"):
        git_parser = sub.add_parser(name)
        git_parser.add_argument("--repo", type=Path, default=Path.cwd())

    _add_result_parser(sub, "test-result")
    _add_result_parser(sub, "build-result")

    ai = sub.add_parser("ai")
    ai.add_argument("--tool", required=True)
    ai.add_argument("--duration", type=float, required=True)
    ai.add_argument("--project")

    milestone = sub.add_parser("milestone")
    milestone.add_argument("--title", required=True)
    milestone.add_argument("--project")
    sub.add_parser("stdin", help="read one fixed-schema integration event from standard input")
    sub.add_parser("retry", help="retry queued events")
    return parser


def _retry(spool: Spool, client: APIClient) -> int:
    delivered, remaining, invalid = spool.retry(client.send, limit=_EXPLICIT_RETRY_LIMIT)
    print(json.dumps({"delivered": delivered, "remaining": remaining, "invalid_dropped": invalid}))
    return 0 if remaining == 0 else 1


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        config = Config.load(args.config)
        client, spool = APIClient(config), Spool(config.spool_file)
        if args.command == "retry":
            return _retry(spool, client)
        event = _from_args(args, config.device_id())
        # Deliver the fresh event first. If connectivity is down, queue it without
        # generating a second burst of doomed retry requests.
        try:
            client.send(event)
        except DeliveryError as exc:
            if exc.transient:
                spool.append(event)
                state = "queued"
            else:
                print(json.dumps({"status": "rejected", "event_id": event.id}))
                return 1
        else:
            state = "sent"
            # Keep normal command latency and request volume bounded.
            spool.retry(client.send, limit=_NORMAL_RETRY_LIMIT)
        print(json.dumps({"status": state, "event_id": event.id}))
        return 0
    except (ConfigError, EventValidationError, GitMetadataError) as exc:
        print(f"devloop: {exc}", file=sys.stderr)
        return 2
    except OSError:
        # Filesystem errors can contain sensitive paths; keep diagnostics generic.
        print("devloop: local storage operation failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
