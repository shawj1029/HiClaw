import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
