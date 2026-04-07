# HiClaw

HiClaw is a cross-platform CLI scheduler (WSL/macOS) that can send scheduled messages through Claude Code.

## Current Scope (v0.1)

- Claude authentication workflow:
  - `hiclaw auth status`
  - `hiclaw auth login`
  - `hiclaw auth open-web`
  - `hiclaw auth verify`
- Task scheduler with three trigger styles:
  - interval (`--every`)
  - cron (`--cron`)
  - daily fixed times (`--at-times`)
- Task operations:
  - add/list/remove
  - run one task immediately (`once`)
  - run daemon loop (`run`)
- Executors:
  - `auto` (same as `cli` in v0.1)
  - `cli` (uses `claude -p`)
  - `web` placeholder (planned in next phase)

## Install

```bash
cd HiClaw
python3 -m pip install -e .
```

## Quick Start

```bash
# 1) Initialize local storage (~/.hiclaw by default)
hiclaw init

# 2) Check login status
hiclaw auth status

# 3) If needed, login
hiclaw auth login

# 4) Verify end-to-end auth + send ability
hiclaw auth verify --model sonnet

# 5) Add a schedule task
hiclaw task add \
  --name morning_ping \
  --model sonnet \
  --executor auto \
  --message "Reply exactly with: HICLAW_OK" \
  --cron "0 9 * * 1-5"

# 6) Run scheduler loop
hiclaw run --poll-interval 20
```

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

Use custom path:

```bash
hiclaw --storage-dir /tmp/hiclaw-data task list
```

## Stability Validation (2026-04-07)

Validated in local environment:

- Unit tests: `python3 -m unittest discover -s tests -v` (9/9 pass)
- Real auth status check: success
- Real one-shot task send via `claude -p`: success

## Roadmap

- Web executor to open Claude web and automate model/message send (Playwright mode)
- Better task controls (enable/disable/update)
- Retry policy and backoff
- Structured logs and export

## Notes

- `web` executor is intentionally not enabled in v0.1 yet.
- For unattended scheduling, keep Claude auth session valid.

## License

MIT. See [LICENSE](./LICENSE).
