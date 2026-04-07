from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from .cron import CronExpression, CronError
from .executors import ClaudeClient, TaskExecutor
from .models import Task
from .scheduler import Scheduler
from .storage import Storage
from .utils import parse_at_times, parse_every


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hiclaw", description="HiClaw - scheduled Claude message runner")
    parser.add_argument("--storage-dir", default=None, help="Data directory (default: ~/.hiclaw)")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Initialize storage files")

    auth_parser = subparsers.add_parser("auth", help="Authentication helpers")
    auth_sub = auth_parser.add_subparsers(dest="auth_command", required=True)
    auth_sub.add_parser("status", help="Show Claude auth status")
    auth_sub.add_parser("login", help="Run 'claude auth login'")

    verify_parser = auth_sub.add_parser("verify", help="Verify auth by sending a small test prompt")
    verify_parser.add_argument("--model", default="sonnet")

    task_parser = subparsers.add_parser("task", help="Task management")
    task_sub = task_parser.add_subparsers(dest="task_command", required=True)

    task_add = task_sub.add_parser("add", help="Add a scheduled task")
    task_add.add_argument("--name", required=True)
    task_add.add_argument("--model", required=True)
    task_add.add_argument("--executor", choices=["auto", "cli", "web"], default="auto")
    msg_group = task_add.add_mutually_exclusive_group(required=True)
    msg_group.add_argument("--message")
    msg_group.add_argument("--message-file")

    sched_group = task_add.add_mutually_exclusive_group(required=True)
    sched_group.add_argument("--every", help="Interval format: 30m, 2h, 1d")
    sched_group.add_argument("--cron", help="5-field cron expression")
    sched_group.add_argument("--at-times", help="Comma-separated HH:MM list, e.g. 09:00,14:30")

    task_sub.add_parser("list", help="List tasks")

    task_remove = task_sub.add_parser("remove", help="Remove a task")
    task_remove.add_argument("id")

    run_parser = subparsers.add_parser("run", help="Run scheduler loop")
    run_parser.add_argument("--poll-interval", type=int, default=20)
    run_parser.add_argument("--timezone", default=None)

    once_parser = subparsers.add_parser("once", help="Run one task immediately")
    once_parser.add_argument("id")
    once_parser.add_argument("--timezone", default=None)

    return parser


def _get_storage(storage_dir: str | None) -> Storage:
    storage = Storage(storage_dir)
    storage.init()
    return storage


def _read_message(args: argparse.Namespace) -> str:
    if args.message is not None:
        return args.message
    path = Path(args.message_file)
    return path.read_text(encoding="utf-8")


def _build_schedule(args: argparse.Namespace) -> dict:
    if args.every:
        return {"type": "every", "interval_seconds": parse_every(args.every)}

    if args.cron:
        try:
            CronExpression.parse(args.cron)
        except CronError as exc:
            raise ValueError(str(exc)) from exc
        return {"type": "cron", "expr": args.cron}

    if args.at_times:
        return {"type": "at_times", "times": parse_at_times(args.at_times)}

    raise ValueError("One schedule must be provided")


def _cmd_init(storage: Storage) -> int:
    storage.init()
    print(f"Initialized HiClaw storage: {storage.base_dir}")
    return 0


def _cmd_auth(args: argparse.Namespace) -> int:
    client = ClaudeClient()
    if args.auth_command == "status":
        status = client.auth_status()
        print(json.dumps(status.payload, indent=2, ensure_ascii=False))
        return 0 if status.logged_in else 1

    if args.auth_command == "login":
        return client.login()

    if args.auth_command == "verify":
        status = client.auth_status()
        if not status.logged_in:
            print("Claude not logged in. Run: hiclaw auth login", file=sys.stderr)
            return 1

        result = client.send(model=args.model, message="Reply exactly with: HICLAW_OK")
        if result.ok:
            print("Auth verify success.")
            print(result.output)
            return 0

        print("Auth verify failed.", file=sys.stderr)
        if result.error:
            print(result.error, file=sys.stderr)
        return 1

    return 1


def _cmd_task(args: argparse.Namespace, storage: Storage) -> int:
    tasks = storage.load_tasks()

    if args.task_command == "list":
        if not tasks:
            print("No tasks.")
            return 0

        for task in tasks:
            print(
                f"{task.id} | {task.name} | executor={task.executor} | model={task.model} | schedule={task.schedule} | enabled={task.enabled}"
            )
        return 0

    if args.task_command == "add":
        try:
            schedule = _build_schedule(args)
            message = _read_message(args)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

        task = Task(
            id=uuid.uuid4().hex[:12],
            name=args.name,
            executor=args.executor,
            model=args.model,
            message=message,
            schedule=schedule,
        )
        tasks.append(task)
        storage.save_tasks(tasks)
        print(f"Task created: {task.id}")
        return 0

    if args.task_command == "remove":
        old_len = len(tasks)
        tasks = [task for task in tasks if task.id != args.id]
        if len(tasks) == old_len:
            print(f"Task not found: {args.id}", file=sys.stderr)
            return 1
        storage.save_tasks(tasks)
        print(f"Task removed: {args.id}")
        return 0

    return 1


def _cmd_run(args: argparse.Namespace, storage: Storage) -> int:
    scheduler = Scheduler(storage=storage, executor=TaskExecutor(), timezone_name=args.timezone)
    scheduler.run_forever(poll_interval=args.poll_interval)
    return 0


def _cmd_once(args: argparse.Namespace, storage: Storage) -> int:
    scheduler = Scheduler(storage=storage, executor=TaskExecutor(), timezone_name=args.timezone)
    result = scheduler.run_task_now(args.id)
    if result.ok:
        print("Task executed successfully.")
        if result.output:
            print(result.output)
        return 0

    print("Task execution failed.", file=sys.stderr)
    if result.error:
        print(result.error, file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    storage = _get_storage(args.storage_dir)

    if args.command == "init":
        return _cmd_init(storage)

    if args.command == "auth":
        return _cmd_auth(args)

    if args.command == "task":
        return _cmd_task(args, storage)

    if args.command == "run":
        return _cmd_run(args, storage)

    if args.command == "once":
        return _cmd_once(args, storage)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
