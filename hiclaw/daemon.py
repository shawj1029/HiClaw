from __future__ import annotations

import contextlib
import fcntl
import json
import os
import shlex
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


AUTOSTART_MARKER = "# hiclaw-autostart"


@dataclass
class DaemonEntry:
    id: str
    pid: int
    started_at: str
    poll_interval: int
    timezone: str
    log_path: str
    pid_start_time: str | None = None
    pid_cmd_tokens: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "pid": self.pid,
            "started_at": self.started_at,
            "poll_interval": self.poll_interval,
            "timezone": self.timezone,
            "log_path": self.log_path,
            "pid_start_time": self.pid_start_time,
            "pid_cmd_tokens": self.pid_cmd_tokens,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DaemonEntry":
        pid_cmd_tokens = payload.get("pid_cmd_tokens")
        if isinstance(pid_cmd_tokens, list):
            pid_cmd_tokens = [str(token) for token in pid_cmd_tokens]
        else:
            pid_cmd_tokens = None
        return cls(
            id=str(payload["id"]),
            pid=int(payload["pid"]),
            started_at=str(payload["started_at"]),
            poll_interval=int(payload["poll_interval"]),
            timezone=str(payload["timezone"]),
            log_path=str(payload["log_path"]),
            pid_start_time=(str(payload["pid_start_time"]) if payload.get("pid_start_time") else None),
            pid_cmd_tokens=pid_cmd_tokens,
        )


class DaemonManager:
    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir).expanduser().resolve()
        self.runtime_dir = self.base_dir / "runtime"
        self.registry_path = self.runtime_dir / "daemons.json"
        self.lock_path = self.runtime_dir / "daemons.lock"

    def start(self, poll_interval: int, timezone_name: str | None = None) -> DaemonEntry:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        with self._registry_lock():
            entries = self._filter_alive(self._load_entries())

            daemon_id = uuid.uuid4().hex[:8]
            log_path = self.runtime_dir / f"hiclaw-run-{daemon_id}.log"
            cmd = [
                sys.executable,
                "-m",
                "hiclaw",
                "--storage-dir",
                str(self.base_dir),
                "run",
                "--poll-interval",
                str(poll_interval),
            ]
            if timezone_name:
                cmd.extend(["--timezone", timezone_name])

            env = os.environ.copy()
            env["HICLAW_DAEMON_MODE"] = "1"
            env["HICLAW_DAEMON_LOG_PATH"] = str(log_path)
            env["HICLAW_LOG_COMPACT_SECONDS"] = "3600"

            with log_path.open("ab") as handle:
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=handle,
                    stderr=handle,
                    env=env,
                    start_new_session=True,
                    close_fds=True,
                )

            # Give subprocess a short window to fail fast on startup errors.
            time.sleep(0.2)
            if proc.poll() is not None:
                raise RuntimeError(f"Failed to start daemon, exit code={proc.returncode}. Check: {log_path}")

            entry = DaemonEntry(
                id=daemon_id,
                pid=proc.pid,
                started_at=datetime.now(timezone.utc).isoformat(),
                poll_interval=poll_interval,
                timezone=timezone_name or "local",
                log_path=str(log_path),
                pid_start_time=self._read_pid_start_time(proc.pid),
                pid_cmd_tokens=self._read_process_cmd_tokens(proc.pid) or cmd,
            )
            entries.append(entry)
            self._save_entries(entries)
            return entry

    def list(self) -> list[tuple[DaemonEntry, bool]]:
        with self._registry_lock():
            entries = self._filter_alive(self._load_entries())
            return [(entry, True) for entry in entries]

    def kill(self, target: str | None = None, kill_all: bool = False) -> list[DaemonEntry]:
        with self._registry_lock():
            entries = self._filter_alive(self._load_entries())

            if not entries:
                self._save_entries([])
                return []

            if kill_all:
                targets = entries
            else:
                target_entry = self._resolve_target(entries, target)
                targets = [target_entry]

            killed: list[DaemonEntry] = []
            kill_pids = {entry.pid for entry in targets}
            for entry in targets:
                if self._terminate_pid(entry.pid):
                    self._cleanup_log(entry.log_path)
                    killed.append(entry)

            remaining = [entry for entry in entries if entry.pid not in kill_pids and self._is_entry_alive(entry)]
            self._save_entries(remaining)
            return killed

    def autostart_install(self, poll_interval: int, timezone_name: str | None = None) -> str:
        line = self._build_autostart_line(poll_interval, timezone_name)
        current = self._read_crontab_lines()
        filtered = [ln for ln in current if AUTOSTART_MARKER not in ln or str(self.base_dir) not in ln]
        filtered.append(line)
        self._write_crontab_lines(filtered)
        return line

    def autostart_remove(self) -> int:
        current = self._read_crontab_lines()
        filtered = [ln for ln in current if AUTOSTART_MARKER not in ln or str(self.base_dir) not in ln]
        removed = len(current) - len(filtered)
        self._write_crontab_lines(filtered)
        return removed

    def autostart_status(self) -> list[str]:
        lines = self._read_crontab_lines()
        return [ln for ln in lines if AUTOSTART_MARKER in ln and str(self.base_dir) in ln]

    def _resolve_target(self, entries: list[DaemonEntry], target: str | None) -> DaemonEntry:
        if target is None:
            if len(entries) == 1:
                return entries[0]
            ids = ", ".join(f"{entry.id}(pid={entry.pid})" for entry in entries)
            raise ValueError(f"Multiple daemons running. Specify ID/PID or use --all: {ids}")

        by_id = [entry for entry in entries if entry.id == target]
        if len(by_id) == 1:
            return by_id[0]

        if target.isdigit():
            pid = int(target)
            by_pid = [entry for entry in entries if entry.pid == pid]
            if len(by_pid) == 1:
                return by_pid[0]

        raise ValueError(f"Daemon not found: {target}")

    def _load_entries(self) -> list[DaemonEntry]:
        if not self.registry_path.exists():
            return []
        with self.registry_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        raw_entries = payload.get("daemons", [])
        return [DaemonEntry.from_dict(item) for item in raw_entries]

    def _save_entries(self, entries: list[DaemonEntry]) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        payload = {"daemons": [entry.to_dict() for entry in entries]}
        tmp = self.registry_path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        tmp.replace(self.registry_path)

    def _filter_alive(self, entries: list[DaemonEntry]) -> list[DaemonEntry]:
        cleaned = [entry for entry in entries if self._is_entry_alive(entry)]
        self._save_entries(cleaned)
        return cleaned

    def _is_pid_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def _is_entry_alive(self, entry: DaemonEntry) -> bool:
        if not self._is_pid_alive(entry.pid):
            return False

        if entry.pid_start_time:
            current_start_time = self._read_pid_start_time(entry.pid)
            if current_start_time != entry.pid_start_time:
                return False

        if entry.pid_cmd_tokens:
            actual_tokens = self._read_process_cmd_tokens(entry.pid)
            if actual_tokens and not self._cmd_tokens_match(actual_tokens, entry.pid_cmd_tokens):
                return False

        return True

    def _terminate_pid(self, pid: int, timeout_seconds: float = 5.0) -> bool:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return False

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self._is_pid_alive(pid):
                return True
            time.sleep(0.1)

        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            return True

        return not self._is_pid_alive(pid)

    def _build_autostart_line(self, poll_interval: int, timezone_name: str | None) -> str:
        py = shlex.quote(sys.executable)
        storage = shlex.quote(str(self.base_dir))
        cmd = f"{py} -m hiclaw --storage-dir {storage} start --poll-interval {poll_interval}"
        if timezone_name:
            cmd += f" --timezone {shlex.quote(timezone_name)}"
        return f"@reboot {cmd} >/dev/null 2>&1 {AUTOSTART_MARKER} {shlex.quote(str(self.base_dir))}"

    def _cleanup_log(self, log_path: str) -> None:
        path = Path(log_path)
        try:
            if path.exists():
                path.unlink()
        except OSError:
            # Keep log on deletion failure; this should not block daemon shutdown.
            pass

    @contextlib.contextmanager
    def _registry_lock(self) -> Any:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _read_pid_start_time(self, pid: int) -> str | None:
        stat_path = Path(f"/proc/{pid}/stat")
        if stat_path.exists():
            try:
                content = stat_path.read_text(encoding="utf-8")
                parts = content.split()
                if len(parts) >= 22:
                    return parts[21]
            except OSError:
                return None

        proc = subprocess.run(
            ["ps", "-p", str(pid), "-o", "lstart="],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return None
        return proc.stdout.strip() or None

    def _read_process_cmd_tokens(self, pid: int) -> list[str] | None:
        cmdline_path = Path(f"/proc/{pid}/cmdline")
        if cmdline_path.exists():
            try:
                raw = cmdline_path.read_bytes()
                tokens = [chunk.decode("utf-8", errors="replace") for chunk in raw.split(b"\x00") if chunk]
                return tokens or None
            except OSError:
                return None

        proc = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return None
        line = proc.stdout.strip()
        if not line:
            return None
        try:
            return shlex.split(line)
        except ValueError:
            return line.split()

    def _cmd_tokens_match(self, actual: list[str], expected: list[str]) -> bool:
        if actual == expected:
            return True
        if len(actual) >= len(expected) and actual[-len(expected) :] == expected:
            return True
        if len(expected) > 1 and len(actual) >= len(expected) - 1 and actual[-(len(expected) - 1) :] == expected[1:]:
            return True
        return False

    def _read_crontab_lines(self) -> list[str]:
        try:
            proc = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=False)
        except FileNotFoundError as exc:
            raise RuntimeError("crontab command not found. Install cron or use manual startup scripts.") from exc
        if proc.returncode != 0:
            return []

        lines = [line.rstrip("\n") for line in proc.stdout.splitlines()]
        return [line for line in lines if line.strip()]

    def _write_crontab_lines(self, lines: list[str]) -> None:
        body = "\n".join(lines) + ("\n" if lines else "")
        try:
            proc = subprocess.run(["crontab", "-"], input=body, text=True, capture_output=True, check=False)
        except FileNotFoundError as exc:
            raise RuntimeError("crontab command not found. Install cron or use manual startup scripts.") from exc
        if proc.returncode != 0:
            stderr = proc.stderr.strip() or proc.stdout.strip()
            raise RuntimeError(f"Failed to write crontab: {stderr}")
