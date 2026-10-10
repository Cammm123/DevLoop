# DevLoop Architecture

## Goal

DevLoop is a private, self-hosted coding-fitness system for Mac and Linux machines. It records activity metadata, computes sustainable progress metrics, and presents Time, Output, and Consistency rings in a native iPhone app and WidgetKit widgets.

## Privacy boundary

Allowed telemetry:

- UTC timestamp and active duration
- generated event/device identifiers
- source tool and event type
- project name, filename, language, and editor name
- Git branch, commit counts, changed-file counts, test/build status
- AI tool name and active duration
- manually completed milestone title

Explicitly forbidden:

- source-code contents or diffs
- terminal command text or output
- AI prompts or responses
- environment variables, credentials, repository remotes, or file contents

Collectors must construct typed events and reject arbitrary metadata keys. The iPhone receives only aggregate statistics and recent sanitized event labels.

## Topology

```text
Mac/Linux editor plugins ─┐
Git/test/build hooks ─────┼─> DevLoop collector ─HTTPS/Tailscale─> Private API + SQLite
AI-tool activity ─────────┘                                      ├─> iPhone app
                                                                └─> WidgetKit shared cache
```

The API binds to the private Tailscale interface or loopback and requires a bearer token. Tokens live in environment/keychain configuration and are never compiled into the app or committed.

## Components

- `server/`: FastAPI service, SQLite persistence, scoring and dashboard aggregation.
- `collector/`: Cross-platform Python CLI, idle-aware heartbeats, local retry spool, Git/test/build/manual event commands.
- `ios/`: SwiftUI iPhone app and WidgetKit extension generated with XcodeGen.
- `shared/`: JSON examples and API contract fixtures.

## Event contract

Each event contains:

- `id`: UUID supplied by the collector for idempotency
- `occurred_at`: ISO-8601 UTC timestamp
- `device_id`: stable opaque local identifier
- `source`: `editor`, `terminal`, `git`, `test`, `build`, `ai`, or `manual`
- `kind`: typed action such as `heartbeat`, `commit`, `test_run`, `build`, or `milestone`
- `duration_seconds`: active duration, clamped to 0...900 seconds per event
- optional sanitized `project`, `entity`, `language`, `tool`, `branch`
- optional `success`, `magnitude`, and milestone `label`

Duplicate IDs are ignored safely.

## Dashboard contract

`GET /v1/dashboard` returns the original aggregate fields (`rings`, active
seconds, output points, event count, streak, and sanitized recent-event labels)
for compatibility, plus the native iOS `DashboardSnapshot` fields. The rich
snapshot contains Time/Output/Consistency metrics, a 14-calendar-day trend,
28-day language and project distributions, adaptive goals, cumulative XP and
level progress, daily summary counts, deterministic quests, and achievements
backed by actual event timestamps. Dashboard responses never include device
identifiers, branches, source/command/prompt contents, or other raw payloads.

## Initial scoring

- **Time ring:** active seconds divided by an adaptive time goal derived from the trailing 28 active days, initially 60 minutes.
- **Output ring:** weighted Git commits, successful tests/builds, meaningful editor activity, and manual milestones divided by an adaptive output goal.
- **Consistency ring:** active days in the trailing seven-day window divided by an adaptive weekly target, initially five.
- **XP:** a bounded blend of active minutes and output points. It cannot be increased by keeping an idle editor open.
- **Streak:** consecutive local calendar days that meet a minimum meaningful-activity threshold.

Goals adapt gradually and stay within healthy bounds. DevLoop does not encourage unlimited coding time.

## Installation path

The iOS project is generated and built on a Mac. Each fork must replace the checked-in example bundle identifiers, Apple team, Keychain service, and App Group with values it owns. The first private install uses Xcode automatic signing and a connected, unlocked iPhone with Developer Mode enabled. After installation, the app operates independently and reaches the API over Tailscale. TestFlight can be added later for wireless distribution.
