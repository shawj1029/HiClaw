# HiClaw

HiClaw is a cross-platform CLI scheduler (WSL/macOS) that sends scheduled messages with Claude.

## Features

- Auth helpers
  - `hiclaw auth status`
  - `hiclaw auth login` (Claude Code CLI login)
  - `hiclaw auth web-login` (Playwright persistent browser login for claude.ai)
  - `hiclaw auth verify`
- Scheduler triggers
  - interval (`--every`, e.g. `30m`)
  - cron (`--cron`, 5-field)
  - daily fixed times (`--at-times`, e.g. `09:00,14:30`)
- Executors
  - `cli`: send via `claude -p`
  - `web`: send via claude.ai browser automation (Playwright)
  - `auto`: try `cli` first, fallback to `web`

## Install

```bash
cd HiClaw
python3 -m pip install -e .
```

If you want web executor:

```bash
python3 -m pip install -e '.[web]'
python3 -m playwright install chromium
```

## Quick Start (CLI executor)

```bash
hiclaw init
hiclaw auth status
hiclaw auth login
hiclaw auth verify --model sonnet

hiclaw task add \
  --name morning_ping \
  --model sonnet \
  --executor auto \
  --message "Reply exactly with: HICLAW_OK" \
  --cron "0 9 * * 1-5"

hiclaw run --poll-interval 20
```

## Quick Start (Web executor)

```bash
hiclaw init
hiclaw auth web-login --wait-seconds 300

hiclaw task add \
  --name web_ping \
  --model sonnet \
  --executor web \
  --message "Reply exactly with: WEB_OK" \
  --every 1h

hiclaw once <task-id>
```

Web session is persisted under `<storage-dir>/browser-profile` (default `~/.hiclaw/browser-profile`).

## Command Reference

```bash
hiclaw --help
hiclaw auth --help
hiclaw task --help
```

## Storage

Default directory: `~/.hiclaw`

- `tasks.json`: task definitions
- `state.json`: scheduling de-dup state
- `history.json`: recent run history
- `browser-profile/`: persistent browser session for web executor

Use custom path:

```bash
hiclaw --storage-dir /tmp/hiclaw-data task list
```

## Stability Validation (2026-04-07)

Validated in local environment:

- Unit tests: `python3 -m unittest discover -s tests -v` (13/13 pass)
- Real auth status check: success
- Real one-shot task send via `claude -p`: success
- Real auth verify (`hiclaw auth verify`): success

## Caveats

- Web automation selectors may break when claude.ai UI changes.
- For unattended scheduling, keep at least one auth path valid (`cli` or `web`).
- In WSL, `auth web-login` requires usable GUI/browser environment.

## License

MIT. See [LICENSE](./LICENSE).
