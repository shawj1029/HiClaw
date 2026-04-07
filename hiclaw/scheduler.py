from __future__ import annotations

import time
from datetime import datetime
from zoneinfo import ZoneInfo

from .cron import CronExpression
from .executors import TaskExecutor
from .models import ExecutionResult, Task
from .storage import Storage
from .utils import parse_iso_timestamp, utc_now


class Scheduler:
    def __init__(self, storage: Storage, executor: TaskExecutor, timezone_name: str | None = None) -> None:
        self.storage = storage
        self.executor = executor
        if timezone_name:
            self.timezone_name = timezone_name
        else:
            local_tz = datetime.now().astimezone().tzinfo
            if isinstance(local_tz, ZoneInfo):
                self.timezone_name = local_tz.key
            else:
                self.timezone_name = "UTC"

    def run_forever(self, poll_interval: int = 20) -> None:
        print(f"[HiClaw] Scheduler started. timezone={self.timezone_name}, poll_interval={poll_interval}s")
        while True:
            self.tick()
            time.sleep(max(1, poll_interval))

    def tick(self) -> None:
        now_utc = utc_now()
        tasks = self.storage.load_tasks()
        state = self.storage.load_state()
        task_state = state.setdefault("task_state", {})

        for task in tasks:
            due, slot_key = self._is_due(task, now_utc, task_state.get(task.id, {}))
            if not due or slot_key is None:
                continue

            result = self.executor.execute(task)
            self._record_run(task, slot_key, now_utc, result, task_state)

        self.storage.save_state(state)

    def run_task_now(self, task_id: str) -> ExecutionResult:
        tasks = self.storage.load_tasks()
        task = next((item for item in tasks if item.id == task_id), None)
        if task is None:
            return ExecutionResult(ok=False, error=f"Task not found: {task_id}", code=4)

        now_utc = utc_now()
        state = self.storage.load_state()
        task_state = state.setdefault("task_state", {})
        slot_key = f"manual:{int(now_utc.timestamp())}"
        result = self.executor.execute(task)
        self._record_run(task, slot_key, now_utc, result, task_state)
        self.storage.save_state(state)
        return result

    def _record_run(
        self,
        task: Task,
        slot_key: str,
        now_utc: datetime,
        result: ExecutionResult,
        task_state: dict,
    ) -> None:
        entry = task_state.setdefault(task.id, {})
        entry["last_slot_key"] = slot_key
        entry["last_run_at"] = now_utc.isoformat()

        self.storage.append_run(
            {
                "task_id": task.id,
                "task_name": task.name,
                "timestamp": now_utc.isoformat(),
                "slot_key": slot_key,
                "ok": result.ok,
                "code": result.code,
                "error": result.error,
                "output_preview": result.output[:300],
            }
        )

        status = "OK" if result.ok else "FAIL"
        print(f"[HiClaw] [{status}] {task.name} ({task.id}) @ {now_utc.isoformat()}")
        if result.error:
            print(f"[HiClaw]   error: {result.error}")

    def _is_due(self, task: Task, now_utc: datetime, state: dict) -> tuple[bool, str | None]:
        if not task.enabled:
            return False, None

        schedule = task.schedule
        schedule_type = schedule.get("type")
        last_slot_key = state.get("last_slot_key")
        local_now = now_utc.astimezone(ZoneInfo(self.timezone_name))

        if schedule_type == "every":
            interval = int(schedule["interval_seconds"])
            last_run = parse_iso_timestamp(state.get("last_run_at"))
            if last_run is None:
                last_run = parse_iso_timestamp(task.created_at)
            if last_run is None:
                last_run = now_utc

            due = (now_utc - last_run).total_seconds() >= interval
            slot_key = f"every:{int(now_utc.timestamp()) // interval}"
            if due and slot_key != last_slot_key:
                return True, slot_key
            return False, None

        if schedule_type == "at_times":
            current_hm = local_now.strftime("%H:%M")
            times = schedule.get("times", [])
            if current_hm not in times:
                return False, None

            slot_key = f"at:{local_now.strftime('%Y-%m-%d')}:{current_hm}"
            return (slot_key != last_slot_key), slot_key

        if schedule_type == "cron":
            expr = CronExpression.parse(schedule["expr"])
            floored = local_now.replace(second=0, microsecond=0)
            if not expr.matches(floored):
                return False, None

            slot_key = f"cron:{floored.strftime('%Y-%m-%dT%H:%M')}"
            return (slot_key != last_slot_key), slot_key

        return False, None
