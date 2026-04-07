from __future__ import annotations

import json
import shutil
import subprocess
import webbrowser
from dataclasses import dataclass

from .models import ExecutionResult, Task


@dataclass
class AuthStatus:
    logged_in: bool
    payload: dict


class ClaudeClient:
    def __init__(self, executable: str = "claude") -> None:
        self.executable = executable

    def is_installed(self) -> bool:
        return shutil.which(self.executable) is not None

    def auth_status(self) -> AuthStatus:
        if not self.is_installed():
            return AuthStatus(logged_in=False, payload={"error": "claude CLI not found"})

        proc = subprocess.run(
            [self.executable, "auth", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if proc.returncode != 0:
            return AuthStatus(logged_in=False, payload={"error": proc.stderr.strip() or proc.stdout.strip()})

        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return AuthStatus(logged_in=False, payload={"error": "invalid auth status response", "raw": proc.stdout})

        return AuthStatus(logged_in=bool(payload.get("loggedIn")), payload=payload)

    def login(self) -> int:
        proc = subprocess.run([self.executable, "auth", "login"], check=False)
        return proc.returncode

    def open_web(self, url: str = "https://claude.ai") -> bool:
        return webbrowser.open(url)

    def send(self, model: str, message: str, timeout_seconds: int = 300) -> ExecutionResult:
        proc = subprocess.run(
            [
                self.executable,
                "-p",
                message,
                "--model",
                model,
                "--output-format",
                "text",
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )

        output = proc.stdout.strip()
        error = proc.stderr.strip()
        return ExecutionResult(ok=(proc.returncode == 0), output=output, error=error, code=proc.returncode)


class TaskExecutor:
    def __init__(self, claude_client: ClaudeClient | None = None) -> None:
        self.claude = claude_client or ClaudeClient()

    def execute(self, task: Task) -> ExecutionResult:
        mode = task.executor.lower()
        if mode not in {"auto", "cli", "web"}:
            return ExecutionResult(ok=False, error=f"Unsupported executor: {task.executor}", code=2)

        if mode == "web":
            return ExecutionResult(
                ok=False,
                error=(
                    "web executor is not enabled in v0.1. Use 'auto' or 'cli'. "
                    "For login bootstrap, run: hiclaw auth login"
                ),
                code=2,
            )

        status = self.claude.auth_status()
        if not status.logged_in:
            return ExecutionResult(
                ok=False,
                auth_required=True,
                code=3,
                error="Claude not logged in. Run: hiclaw auth login",
            )

        return self.claude.send(model=task.model, message=task.message)
