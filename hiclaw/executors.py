from __future__ import annotations

import json
import re
import shutil
import subprocess
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import ExecutionResult, Task


@dataclass
class AuthStatus:
    logged_in: bool
    payload: dict[str, Any]


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


class WebClaudeAutomator:
    LOGIN_URL = "https://claude.ai/login"
    CHAT_URL = "https://claude.ai/new"
    COMPOSER_SELECTORS = [
        "textarea[placeholder*='Message']",
        "textarea[data-testid='chat-input']",
        "div[contenteditable='true'][role='textbox']",
        "div[contenteditable='true']",
    ]
    SEND_SELECTORS = [
        "button[aria-label*='Send']",
        "button[data-testid='send-button']",
        "button:has-text('Send')",
    ]

    def __init__(self, profile_dir: str | Path | None = None) -> None:
        if profile_dir is None:
            profile_dir = Path.home() / ".hiclaw" / "browser-profile"
        self.profile_dir = Path(profile_dir).expanduser().resolve()

    def login_interactive(self, wait_seconds: int = 300) -> ExecutionResult:
        playwright = self._load_playwright()
        if isinstance(playwright, ExecutionResult):
            return playwright

        sync_playwright, playwright_timeout_error = playwright

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=False,
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(self.CHAT_URL, wait_until="domcontentloaded", timeout=30_000)

                if self._find_composer(page) is not None:
                    return ExecutionResult(ok=True, output="Web session already authenticated.")

                print("[HiClaw] Please complete Claude web login in the opened browser window...")
                page.goto(self.LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
                if not self._wait_for_composer(page, wait_seconds * 1000, playwright_timeout_error):
                    return ExecutionResult(
                        ok=False,
                        code=3,
                        auth_required=True,
                        error="Web login not completed in time.",
                    )

                return ExecutionResult(ok=True, output="Web login completed and profile saved.")
            finally:
                context.close()

    def send(self, model: str, message: str, headless: bool = True) -> ExecutionResult:
        playwright = self._load_playwright()
        if isinstance(playwright, ExecutionResult):
            return playwright

        sync_playwright, _playwright_timeout_error = playwright

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=headless,
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(self.CHAT_URL, wait_until="domcontentloaded", timeout=45_000)

                composer = self._find_composer(page)
                if composer is None:
                    return ExecutionResult(
                        ok=False,
                        code=3,
                        auth_required=True,
                        error="Claude web session is not logged in. Run: hiclaw auth web-login",
                    )

                self._choose_model(page, model)
                composer = self._find_composer(page)
                if composer is None:
                    return ExecutionResult(ok=False, code=2, error="Cannot locate message input on Claude web.")

                self._fill_message(page, composer, message)
                sent = self._click_send(page)
                if not sent:
                    composer.click(timeout=2_000)
                    page.keyboard.press("Enter")

                return ExecutionResult(ok=True, output="Message submitted via Claude web.")
            except Exception as exc:  # noqa: BLE001
                return ExecutionResult(ok=False, code=2, error=f"Web send failed: {exc}")
            finally:
                context.close()

    def _load_playwright(self) -> tuple[Any, type] | ExecutionResult:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError:
            return ExecutionResult(
                ok=False,
                code=2,
                error=(
                    "playwright is not installed. Install with:\n"
                    "  python3 -m pip install playwright\n"
                    "  python3 -m playwright install chromium"
                ),
            )

        return sync_playwright, PlaywrightTimeoutError

    def _find_composer(self, page: Any) -> Any | None:
        for selector in self.COMPOSER_SELECTORS:
            try:
                locator = page.locator(selector).first
                if locator.count() > 0 and locator.is_visible():
                    return locator
            except Exception:  # noqa: BLE001
                continue
        return None

    def _wait_for_composer(self, page: Any, timeout_ms: int, timeout_error: type) -> bool:
        for selector in self.COMPOSER_SELECTORS:
            try:
                page.wait_for_selector(selector, timeout=timeout_ms, state="visible")
                return True
            except timeout_error:
                continue
            except Exception:  # noqa: BLE001
                continue
        return False

    def _choose_model(self, page: Any, model: str) -> None:
        if not model:
            return

        lowered = model.lower()
        picker_selectors = [
            "button[aria-haspopup='menu']",
            "button[aria-label*='Model']",
            "button:has-text('Claude')",
        ]
        for selector in picker_selectors:
            try:
                page.locator(selector).first.click(timeout=1_500)
                break
            except Exception:  # noqa: BLE001
                continue

        option_patterns = [
            re.compile(re.escape(model), re.IGNORECASE),
            re.compile(re.escape(lowered.replace("claude-", "").replace("claude ", "")), re.IGNORECASE),
        ]
        for pattern in option_patterns:
            try:
                page.get_by_role("option", name=pattern).first.click(timeout=1_500)
                return
            except Exception:  # noqa: BLE001
                pass
            try:
                page.get_by_text(pattern).first.click(timeout=1_500)
                return
            except Exception:  # noqa: BLE001
                pass

    def _fill_message(self, page: Any, composer: Any, message: str) -> None:
        try:
            tag = composer.evaluate("el => el.tagName.toLowerCase()")
        except Exception:  # noqa: BLE001
            tag = ""

        if tag == "textarea":
            composer.fill(message)
            return

        composer.click(timeout=2_000)
        page.keyboard.type(message)

    def _click_send(self, page: Any) -> bool:
        for selector in self.SEND_SELECTORS:
            try:
                btn = page.locator(selector).first
                if btn.count() > 0 and btn.is_enabled() and btn.is_visible():
                    btn.click(timeout=2_000)
                    return True
            except Exception:  # noqa: BLE001
                continue
        return False


class TaskExecutor:
    def __init__(
        self,
        claude_client: ClaudeClient | None = None,
        web_automator: WebClaudeAutomator | None = None,
    ) -> None:
        self.claude = claude_client or ClaudeClient()
        self.web = web_automator or WebClaudeAutomator()

    def execute(self, task: Task) -> ExecutionResult:
        mode = task.executor.lower()
        if mode not in {"auto", "cli", "web"}:
            return ExecutionResult(ok=False, error=f"Unsupported executor: {task.executor}", code=2)

        if mode == "web":
            return self.web.send(model=task.model, message=task.message, headless=True)

        status = self.claude.auth_status()
        if status.logged_in:
            return self.claude.send(model=task.model, message=task.message)

        if mode == "cli":
            return ExecutionResult(
                ok=False,
                auth_required=True,
                code=3,
                error="Claude CLI not logged in. Run: hiclaw auth login",
            )

        web_result = self.web.send(model=task.model, message=task.message, headless=True)
        if web_result.ok:
            return web_result

        if web_result.auth_required:
            return ExecutionResult(
                ok=False,
                auth_required=True,
                code=3,
                error=(
                    "Claude is not logged in via CLI or web. "
                    "Run: hiclaw auth login or hiclaw auth web-login"
                ),
            )

        return web_result
