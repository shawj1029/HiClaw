from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hiclaw.daemon import DaemonEntry, DaemonManager


class DaemonManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.manager = DaemonManager(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_resolve_by_id(self) -> None:
        entries = [
            DaemonEntry(id="abc12345", pid=101, started_at="x", poll_interval=20, timezone="local", log_path="/tmp/a"),
        ]
        resolved = self.manager._resolve_target(entries, "abc12345")
        self.assertEqual(resolved.pid, 101)

    def test_resolve_by_pid(self) -> None:
        entries = [
            DaemonEntry(id="abc12345", pid=101, started_at="x", poll_interval=20, timezone="local", log_path="/tmp/a"),
        ]
        resolved = self.manager._resolve_target(entries, "101")
        self.assertEqual(resolved.id, "abc12345")

    def test_resolve_multiple_without_target(self) -> None:
        entries = [
            DaemonEntry(id="a1", pid=101, started_at="x", poll_interval=20, timezone="local", log_path="/tmp/a"),
            DaemonEntry(id="b2", pid=202, started_at="x", poll_interval=20, timezone="local", log_path="/tmp/b"),
        ]
        with self.assertRaises(ValueError):
            self.manager._resolve_target(entries, None)

    def test_resolve_not_found(self) -> None:
        entries = [
            DaemonEntry(id="abc12345", pid=101, started_at="x", poll_interval=20, timezone="local", log_path="/tmp/a"),
        ]
        with self.assertRaises(ValueError):
            self.manager._resolve_target(entries, "zzz")

    def test_cleanup_log_deletes_file(self) -> None:
        log_path = Path(self.tmp.name) / "test.log"
        log_path.write_text("x\n", encoding="utf-8")
        self.assertTrue(log_path.exists())
        self.manager._cleanup_log(str(log_path))
        self.assertFalse(log_path.exists())

    def test_cmd_tokens_match(self) -> None:
        expected = ["/usr/bin/python3", "-m", "hiclaw", "run"]
        self.assertTrue(self.manager._cmd_tokens_match(expected, expected))
        self.assertTrue(self.manager._cmd_tokens_match(["env", *expected], expected))
        self.assertTrue(self.manager._cmd_tokens_match(expected[1:], expected[1:]))
        self.assertFalse(self.manager._cmd_tokens_match(["python3", "-m", "other"], expected))

    def test_is_entry_alive_false_when_start_time_mismatch(self) -> None:
        entry = DaemonEntry(
            id="a1",
            pid=123,
            started_at="x",
            poll_interval=20,
            timezone="local",
            log_path="/tmp/a.log",
            pid_start_time="111",
            pid_cmd_tokens=["python3", "-m", "hiclaw", "run"],
        )
        with (
            patch.object(self.manager, "_is_pid_alive", return_value=True),
            patch.object(self.manager, "_read_pid_start_time", return_value="222"),
            patch.object(self.manager, "_read_process_cmd_tokens", return_value=["python3", "-m", "hiclaw", "run"]),
        ):
            self.assertFalse(self.manager._is_entry_alive(entry))

    def test_is_entry_alive_false_when_cmd_mismatch(self) -> None:
        entry = DaemonEntry(
            id="a1",
            pid=123,
            started_at="x",
            poll_interval=20,
            timezone="local",
            log_path="/tmp/a.log",
            pid_start_time="111",
            pid_cmd_tokens=["python3", "-m", "hiclaw", "run"],
        )
        with (
            patch.object(self.manager, "_is_pid_alive", return_value=True),
            patch.object(self.manager, "_read_pid_start_time", return_value="111"),
            patch.object(self.manager, "_read_process_cmd_tokens", return_value=["python3", "-m", "other"]),
        ):
            self.assertFalse(self.manager._is_entry_alive(entry))


if __name__ == "__main__":
    unittest.main()
