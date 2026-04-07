import unittest

from hiclaw.cli import _resolve_task
from hiclaw.models import Task


class CliResolveTaskTest(unittest.TestCase):
    def test_resolve_by_id(self) -> None:
        tasks = [
            Task(id="a1", name="smoke", executor="auto", model="sonnet", message="x", schedule={"type": "every", "interval_seconds": 60}),
        ]
        task, error = _resolve_task(tasks, "a1")
        self.assertIsNotNone(task)
        self.assertIsNone(error)
        assert task is not None
        self.assertEqual(task.name, "smoke")

    def test_resolve_by_name(self) -> None:
        tasks = [
            Task(id="a1", name="smoke", executor="auto", model="sonnet", message="x", schedule={"type": "every", "interval_seconds": 60}),
        ]
        task, error = _resolve_task(tasks, "smoke")
        self.assertIsNotNone(task)
        self.assertIsNone(error)
        assert task is not None
        self.assertEqual(task.id, "a1")

    def test_resolve_name_ambiguous(self) -> None:
        tasks = [
            Task(id="a1", name="smoke", executor="auto", model="sonnet", message="x", schedule={"type": "every", "interval_seconds": 60}),
            Task(id="b2", name="smoke", executor="auto", model="sonnet", message="y", schedule={"type": "every", "interval_seconds": 60}),
        ]
        task, error = _resolve_task(tasks, "smoke")
        self.assertIsNone(task)
        self.assertIsNotNone(error)
        assert error is not None
        self.assertIn("Multiple tasks share name", error)

    def test_resolve_missing(self) -> None:
        tasks = []
        task, error = _resolve_task(tasks, "unknown")
        self.assertIsNone(task)
        self.assertEqual(error, "Task not found: unknown")


if __name__ == "__main__":
    unittest.main()
