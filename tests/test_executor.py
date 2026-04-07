import unittest
from unittest.mock import patch

from hiclaw.executors import AuthStatus, ClaudeClient, TaskExecutor
from hiclaw.models import ExecutionResult, Task


class FakeClaudeClient:
    def __init__(self, logged_in: bool, send_ok: bool = True) -> None:
        self.logged_in = logged_in
        self.send_ok = send_ok

    def auth_status(self) -> AuthStatus:
        return AuthStatus(logged_in=self.logged_in, payload={"loggedIn": self.logged_in})

    def send(self, model: str, message: str, timeout_seconds: int = 300) -> ExecutionResult:
        if self.send_ok:
            return ExecutionResult(ok=True, output=f"cli:{model}:{message}")
        return ExecutionResult(ok=False, code=2, error="cli send failed")


class FakeWebAutomator:
    def __init__(self, result: ExecutionResult) -> None:
        self.result = result

    def send(self, model: str, message: str, headless: bool = True) -> ExecutionResult:
        return self.result


class ExecutorTest(unittest.TestCase):
    def test_auto_prefers_cli_when_logged_in(self) -> None:
        task = Task(
            id="1",
            name="t",
            executor="auto",
            model="sonnet",
            message="hello",
            schedule={"type": "every", "interval_seconds": 60},
        )
        executor = TaskExecutor(
            claude_client=FakeClaudeClient(logged_in=True),
            web_automator=FakeWebAutomator(ExecutionResult(ok=False, error="should not use")),
        )
        result = executor.execute(task)
        self.assertTrue(result.ok)
        self.assertIn("cli:sonnet:hello", result.output)

    def test_auto_falls_back_to_web(self) -> None:
        task = Task(
            id="2",
            name="t",
            executor="auto",
            model="sonnet",
            message="hello",
            schedule={"type": "every", "interval_seconds": 60},
        )
        executor = TaskExecutor(
            claude_client=FakeClaudeClient(logged_in=False),
            web_automator=FakeWebAutomator(ExecutionResult(ok=True, output="web sent")),
        )
        result = executor.execute(task)
        self.assertTrue(result.ok)
        self.assertEqual(result.output, "web sent")

    def test_cli_mode_requires_cli_login(self) -> None:
        task = Task(
            id="3",
            name="t",
            executor="cli",
            model="sonnet",
            message="hello",
            schedule={"type": "every", "interval_seconds": 60},
        )
        executor = TaskExecutor(
            claude_client=FakeClaudeClient(logged_in=False),
            web_automator=FakeWebAutomator(ExecutionResult(ok=True, output="web sent")),
        )
        result = executor.execute(task)
        self.assertFalse(result.ok)
        self.assertTrue(result.auth_required)

    def test_web_mode_uses_web(self) -> None:
        task = Task(
            id="4",
            name="t",
            executor="web",
            model="sonnet",
            message="hello",
            schedule={"type": "every", "interval_seconds": 60},
        )
        executor = TaskExecutor(
            claude_client=FakeClaudeClient(logged_in=True),
            web_automator=FakeWebAutomator(ExecutionResult(ok=True, output="web sent")),
        )
        result = executor.execute(task)
        self.assertTrue(result.ok)
        self.assertEqual(result.output, "web sent")


class ClaudeClientOpenWebTest(unittest.TestCase):
    def test_open_web_wsl_uses_cmd_success(self) -> None:
        client = ClaudeClient()
        with (
            patch.object(client, "_is_wsl", return_value=True),
            patch("hiclaw.executors.shutil.which", return_value="/mnt/c/Windows/System32/cmd.exe"),
            patch("hiclaw.executors.subprocess.run") as mock_run,
            patch("hiclaw.executors.webbrowser.open") as mock_open,
        ):
            mock_run.return_value.returncode = 0
            ok = client.open_web("https://claude.ai")

        self.assertTrue(ok)
        self.assertEqual(mock_run.call_count, 1)
        mock_open.assert_not_called()

    def test_open_web_wsl_fallbacks_to_webbrowser(self) -> None:
        client = ClaudeClient()
        with (
            patch.object(client, "_is_wsl", return_value=True),
            patch("hiclaw.executors.shutil.which", return_value="/mnt/c/Windows/System32/cmd.exe"),
            patch("hiclaw.executors.subprocess.run") as mock_run,
            patch("hiclaw.executors.webbrowser.open", return_value=True) as mock_open,
        ):
            mock_run.return_value.returncode = 1
            ok = client.open_web("https://claude.ai")

        self.assertTrue(ok)
        self.assertEqual(mock_run.call_count, 1)
        mock_open.assert_called_once()

    def test_open_web_non_wsl_uses_webbrowser(self) -> None:
        client = ClaudeClient()
        with (
            patch.object(client, "_is_wsl", return_value=False),
            patch("hiclaw.executors.webbrowser.open", return_value=True) as mock_open,
        ):
            ok = client.open_web("https://claude.ai")

        self.assertTrue(ok)
        mock_open.assert_called_once()


if __name__ == "__main__":
    unittest.main()
