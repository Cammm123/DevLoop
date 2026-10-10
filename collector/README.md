# DevLoop Collector

A Python 3.11 CLI for macOS and Linux that sends only the coding-activity metadata allowed by DevLoop. Events have generated UUIDs, a stable opaque device ID, UTC time, a clamped active duration, and a fixed typed schema. Failed requests are retained as private JSONL and retried with the same UUID.

## Install and configure

```sh
cd collector
uv sync --dev
uv run devloop --help
```

The default config is `~/.config/devloop/config.toml` (or `$XDG_CONFIG_HOME/devloop/config.toml):

```toml
[collector]
api_url = "https://devloop.example.internal"
token = "replace-with-private-token"
timeout_seconds = 5
# device_id_file = "~/.local/state/devloop/device_id"
# spool_file = "~/.local/state/devloop/spool.jsonl"
```

Environment overrides are `DEVLOOP_API_URL`, `DEVLOOP_TOKEN`, `DEVLOOP_TIMEOUT_SECONDS`, `DEVLOOP_DEVICE_ID_FILE`, and `DEVLOOP_SPOOL_FILE`. These values configure transport/local storage and are never added to events. Prefer a mode-0600 config file or a secret manager. Device and spool files are created mode 0600.

`api_url` is the API origin; the collector posts a one-event batch to `<api_url>/v1/events/batch` with an optional bearer token. HTTPS is required except for loopback and literal Tailscale addresses (`100.64.0.0/10` or `fd7a:115c:a1e0::/48`). Embedded credentials, queries, and fragments are rejected. Duplicate UUIDs are accepted idempotently by the server.

## Commands

```sh
devloop heartbeat --duration 45 --project myapp --file src/main.py --language Python --editor "VS Code"
devloop git-snapshot --repo "$PWD"
devloop git-commit --repo "$PWD"
devloop test-result --success --duration 13 --project myapp --tool pytest --count 42
devloop build-result --failure --duration 80 --project myapp --tool xcodebuild
devloop ai --tool Claude --duration 120 --project myapp
devloop milestone --title "Finished offline sync" --project myapp
devloop github-sync --username Cammm123
devloop retry
```

### GitHub account tracking

`github-sync` imports public `PushEvent` metadata for one GitHub account. It retains only the event ID for deduplication, timestamp, repository basename, branch, and a conservative magnitude of one commit per push. GitHub's public feed redacts per-push commit counts, so a push containing multiple commits still counts as one. Commit messages, authors, diffs, files, and source code are never retained. Repeated runs are idempotent through both a private mode-0600 cursor file and deterministic event UUIDs.

Set `GITHUB_TOKEN` only if authenticated GitHub access is needed; never place it in the DevLoop config or command line. A timer may safely invoke the command every 15 minutes.

Durations are clamped to 0–900 seconds. A supplied project or filename path is reduced to its basename. Control characters are removed, text is bounded, URL/remote-like values are rejected, and unknown fields are rejected. Git commands query only repository root name, branch, counts, status metadata, and changed-file names solely long enough to count them. They never request diffs, blobs, commit messages, identities, configuration, or remotes.

## Fixed-schema stdin integration

`devloop stdin` reads exactly one JSON object and rejects unknown keys/types. Supported `type` values and fields are:

- `heartbeat`: required `duration_seconds`; optional `source` (`editor` or `terminal`), `project`, `file`, `language`, `editor`
- `test_result` / `build_result`: required `success`, `duration_seconds`; optional `project`, `tool`, `count`
- `ai_activity`: required `tool`, `duration_seconds`; optional `project`
- `milestone`: required `title`; optional `project`

```sh
printf '%s\n' '{"type":"heartbeat","duration_seconds":30,"project":"web","file":"app.ts","language":"TypeScript","editor":"VS Code"}' | devloop stdin
```

Do not pipe WakaTime logs or editor buffers into this command.

## VS Code and WakaTime-compatible direction

A VS Code extension can call `devloop stdin` from document-focus/edit timers, after applying its own idle detection. Pass only the workspace-folder name, `path.basename(document.fileName)`, language ID, editor name, and active interval. Never pass document text, diagnostics, terminal data, environment values, or the full path.

For a WakaTime-style integration, configure the editor callback/plugin to invoke this CLI alongside its heartbeat timer. Build the fixed `heartbeat` object from WakaTime-compatible metadata fields (`project`, basename-only entity, language, editor, active duration); do **not** scrape `.wakatime.log`, intercept API payloads, or forward plugin arguments wholesale. This is interface-compatible direction, not a claim that this CLI accepts arbitrary WakaTime payloads.

## Shell timing hooks without command capture

The safe pattern is to mark activity at prompt boundaries. The hook stores only a timestamp and sends only elapsed seconds; it does not inspect history, `$BASH_COMMAND`, command arguments, stdout, or stderr.

**Bash** (`~/.bashrc`):

```sh
__devloop_prompt_time=$(date +%s)
__devloop_prompt_heartbeat() {
  local now elapsed
  now=$(date +%s)
  elapsed=$(( now - __devloop_prompt_time ))
  __devloop_prompt_time=$now
  (( elapsed > 0 )) && devloop heartbeat --source terminal --duration "$elapsed" >/dev/null 2>&1
}
PROMPT_COMMAND="__devloop_prompt_heartbeat${PROMPT_COMMAND:+;$PROMPT_COMMAND}"
```

**Zsh** (`~/.zshrc`):

```sh
typeset -gi __devloop_prompt_time=$(date +%s)
__devloop_prompt_heartbeat() {
  local -i now=$(date +%s)
  local -i elapsed=$(( now - __devloop_prompt_time ))
  __devloop_prompt_time=$now
  (( elapsed > 0 )) && devloop heartbeat --source terminal --duration "$elapsed" >/dev/null 2>&1
}
autoload -Uz add-zsh-hook
add-zsh-hook precmd __devloop_prompt_heartbeat
```

Long intervals are safely clamped. For stronger idle detection, have a timer invoke a heartbeat only while keyboard/editor activity is known; never attach command text.

## Privacy boundary

The collector has no fields or CLI options for source contents/diffs, terminal command text/output, AI prompts/responses, environment values, credentials, or repository remotes. The API response body is ignored. The local retry spool accepts only validated event objects. Retries are bounded (10 records opportunistically, 100 for explicit `devloop retry`) and stop at the first transient connectivity failure. Malformed records and permanently rejected 4xx records are dropped; transient failures retain the original queued UUID and all unattempted records.

Run tests with `uv run pytest`.
