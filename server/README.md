# DevLoop server

Private FastAPI sync service backed by SQLite. It stores only the allow-listed typed event fields described in the architecture; unknown fields are rejected and there is no arbitrary telemetry/blob column.

## Requirements

- Python 3.11 or 3.12
- [`uv`](https://docs.astral.sh/uv/)
- A random bearer token of at least 32 characters

## Install and run

```bash
cd server
uv sync --dev
export DEVLOOP_API_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export DEVLOOP_DATABASE_PATH="$HOME/.local/share/devloop/devloop.sqlite3"
# Only localhost, loopback IPs, or literal Tailscale IPs are accepted.
export DEVLOOP_BIND_HOST="127.0.0.1"
export DEVLOOP_BIND_PORT="8765"
uv run uvicorn devloop_server.app:create_app --factory \
  --host "$DEVLOOP_BIND_HOST" --port "$DEVLOOP_BIND_PORT" --no-server-header
```

For Tailscale access, set `DEVLOOP_BIND_HOST` to this machine's literal Tailscale IPv4 (`100.64.0.0/10`) or Tailscale IPv6 address. Put TLS in front of the service when traffic is not protected end-to-end by the tailnet. The server deliberately refuses wildcard, LAN, DNS-name, and public binds.

Keep the token in an environment secret/keychain, never in source or an app binary. The SQLite parent directory is created with private permissions. Back up the SQLite database using SQLite-aware tooling while the service is running.

## API

All `/v1/*` routes require an `Authorization` header containing the Bearer scheme and configured token. `GET /health` is unauthenticated and returns only database health.

- `POST /v1/events/batch` — body `{"events": [...]}`; 1–500 events. Duplicate UUIDs are ignored atomically.
- `POST /v1/milestones` — create a typed manual milestone.
- `GET /v1/dashboard?date=2026-03-10&timezone=America%2FNew_York` — aggregate rings, XP, streak, and sanitized recent labels.

Timestamps must be ISO-8601 UTC timestamps (`Z` or an explicit zero offset), and event duration is limited to 0–900 seconds. Active time is counted only from editor/terminal heartbeats and AI activity. Test/build runtimes, Git events, and manual milestones do not add active time or time-based XP; their results can still earn output points. The dashboard uses IANA timezones and handles local/DST calendar boundaries. Request bodies are capped at 1,000,000 bytes while streaming, including requests without a `Content-Length` header.

Scoring constants in the first release are intentionally bounded: time goals are 30–120 minutes, output goals 10–100 points, weekly goals 3–6 days, and daily XP tops out at 200. Goals blend 25% of prior behavior with the initial healthy defaults rather than chasing unbounded activity.

## Test

```bash
cd server
uv sync --dev
uv run pytest
uv run pytest --cov=devloop_server --cov-report=term-missing
```

Schema setup is transactional and idempotent. Startup refuses a database created by a newer schema version rather than modifying it.
