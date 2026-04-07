from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from hiclaw.models import ExecutionResult, Task
from hiclaw.scheduler import Scheduler
from hiclaw.storage import Storage


class FakeExecutor:
    def execute(self, task: Task) -> ExecutionResult:
        return ExecutionResult(ok=True, output=f"ok:{task.id}")


class SchedulerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(self.tmp.name)
        self.storage.init()
        self.scheduler = Scheduler(storage=self.storage, executor=FakeExecutor(), timezone_name="UTC")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_every_due(self) -> None:
        task = Task(
            id="t1",
            name="every",
            executor="auto",
            model="sonnet",
            message="hello",
            schedule={"type": "every", "interval_seconds": 60},
            created_at="2026-04-06T00:00:00+00:00",
        )
        due, slot = self.scheduler._is_due(task, datetime(2026, 4, 6, 0, 2, tzinfo=timezone.utc), {})
        self.assertTrue(due)
        self.assertIsNotNone(slot)

    def test_at_times_dedup(self) -> None:
        task = Task(
            id="t2",
            name="at",
            executor="auto",
            model="sonnet",
            message="hello",
            schedule={"type": "at_times", "times": ["09:00"]},
            created_at="2026-04-06T00:00:00+00:00",
        )
        now = datetime(2026, 4, 6, 9, 0, tzinfo=timezone.utc)
        due, slot = self.scheduler._is_due(task, now, {})
        self.assertTrue(due)
        self.assertEqual(slot, "at:2026-04-06:09:00")

        due2, _ = self.scheduler._is_due(task, now, {"last_slot_key": slot})
        self.assertFalse(due2)

    def test_compact_log_file_keeps_last_action(self) -> None:
        log_path = Path(self.tmp.name) / "runtime.log"
        log_path.write_text(
            "\n".join(
                [
                    "[HiClaw] Scheduler started.",
                    "[HiClaw] [OK] first (id1) @ t1",
                    "[HiClaw] [FAIL] second (id2) @ t2",
                    "[HiClaw]   error: boom",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        Scheduler._compact_log_file(log_path)
        content = log_path.read_text(encoding="utf-8")
        self.assertIn("log compacted", content)
        self.assertNotIn("[HiClaw] [OK] first", content)
        self.assertIn("[HiClaw] [FAIL] second", content)
        self.assertIn("[HiClaw]   error: boom", content)


if __name__ == "__main__":
    unittest.main()
