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
- Daemon controls
  - `hiclaw start`: run scheduler in background
  - `hiclaw isalive`: inspect daemon status
  - `hiclaw kill [ID|PID]` / `hiclaw kill --all`
  - `hiclaw autostart install|status|remove` (via `crontab @reboot`)

## Install

Download from GitHub:

```bash
git clone git@github.com:shawj1029/HiClaw.git
cd HiClaw
```

Install:

```bash
python3 -m pip install -e .
```

If you want web executor:

```bash
python3 -m pip install -e '.[web]'
python3 -m playwright install chromium
```

## Most Common Use Case

```bash
# 1) initialize storage (only needs to run once after install)
hiclaw init

# 2) create one simple daily task: wake_up at 4:00 AM using haiku
hiclaw task add \
  --name wake_up \
  --model haiku \
  --executor auto \
  --message "only return 1." \
  --cron "0 4 * * *"

# 3) run in background with 60s polling
hiclaw start --poll-interval 60

# 4) confirm daemon is alive
hiclaw isalive
```

Optional autostart on reboot:

```bash
hiclaw autostart install --poll-interval 60
hiclaw autostart status
```

If you want to remove the task:

```bash
hiclaw task remove wake_up
```

If you want to stop the background scheduler:

```bash
hiclaw kill --all
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

## Simple Always-On Mode

```bash
# 1) start in background
hiclaw start --poll-interval 20

# 2) check daemon
hiclaw isalive

# 3) stop one daemon by id/pid
hiclaw kill <daemon-id-or-pid>

# 4) stop all daemons
hiclaw kill --all
```

Enable reboot autostart:

```bash
hiclaw autostart install --poll-interval 20
hiclaw autostart status
hiclaw autostart remove
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

`hiclaw once` and `hiclaw task remove` both accept task ID or exact task name.
If multiple tasks share the same name, HiClaw will ask you to use ID.

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
- `runtime/daemons.json`: background daemon registry
- `runtime/hiclaw-run-<daemon-id>.log`: per-daemon background log

Use custom path:

```bash
hiclaw --storage-dir /tmp/hiclaw-data task list
```

## Stability Validation (2026-04-07)

Validated in local environment:

- Unit tests: `python3 -m unittest discover -s tests -v` (29/29 pass)
- Real auth status check: success
- Real one-shot task send via `claude -p`: success
- Real auth verify (`hiclaw auth verify`): success

## Caveats

- Web automation selectors may break when claude.ai UI changes.
- For unattended scheduling, keep at least one auth path valid (`cli` or `web`).
- In WSL, `auth web-login` requires usable GUI/browser environment.
- `autostart` depends on `crontab` availability; if missing, use manual startup scripts.

## Log Policy

- Daemon mode writes to `runtime/hiclaw-run-<daemon-id>.log`.
- While daemon is running, log is compacted every hour and keeps only the latest action record.
- `hiclaw kill` / `hiclaw kill --all` performs normal shutdown and deletes the corresponding daemon log.
- If daemon exits abnormally, log file is intentionally preserved for diagnosis.

## License

MIT. See [LICENSE](./LICENSE).
