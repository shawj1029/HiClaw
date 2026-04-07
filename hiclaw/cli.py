from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from .cron import CronExpression, CronError
from .daemon import DaemonManager
from .executors import ClaudeClient, TaskExecutor, WebClaudeAutomator
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
    auth_sub.add_parser("open-web", help="Open Claude web page in browser")
    web_login_parser = auth_sub.add_parser("web-login", help="Open persistent browser and complete Claude web login")
    web_login_parser.add_argument("--wait-seconds", type=int, default=300)

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

    task_remove = task_sub.add_parser("remove", help="Remove a task by ID or name")
    task_remove.add_argument("task")

    run_parser = subparsers.add_parser("run", help="Run scheduler loop")
    run_parser.add_argument("--poll-interval", type=int, default=20)
    run_parser.add_argument("--timezone", default=None)

    start_parser = subparsers.add_parser("start", help="Start scheduler in background daemon mode")
    start_parser.add_argument("--poll-interval", type=int, default=20)
    start_parser.add_argument("--timezone", default=None)

    subparsers.add_parser("isalive", help="Show background daemon status")

    kill_parser = subparsers.add_parser("kill", help="Stop background daemon(s)")
    kill_parser.add_argument("target", nargs="?", help="Daemon ID or PID")
    kill_parser.add_argument("--all", action="store_true", help="Stop all daemons")

    autostart_parser = subparsers.add_parser("autostart", help="Manage reboot autostart via crontab")
    autostart_sub = autostart_parser.add_subparsers(dest="autostart_command", required=True)
    autostart_sub.add_parser("status", help="Show autostart entries for current storage")
    autostart_install = autostart_sub.add_parser("install", help="Install @reboot autostart entry")
    autostart_install.add_argument("--poll-interval", type=int, default=20)
    autostart_install.add_argument("--timezone", default=None)
    autostart_sub.add_parser("remove", help="Remove @reboot autostart entry")

    once_parser = subparsers.add_parser("once", help="Run one task immediately by ID or name")
    once_parser.add_argument("task")
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


def _resolve_task(tasks: list[Task], key: str) -> tuple[Task | None, str | None]:
    exact_id = next((task for task in tasks if task.id == key), None)
    if exact_id is not None:
        return exact_id, None

    name_matches = [task for task in tasks if task.name == key]
    if len(name_matches) == 1:
        return name_matches[0], None
    if len(name_matches) > 1:
        ids = ", ".join(task.id for task in name_matches)
        return None, f"Multiple tasks share name '{key}'. Use task ID instead: {ids}"

    return None, f"Task not found: {key}"


def _cmd_init(storage: Storage) -> int:
    storage.init()
    print(f"Initialized HiClaw storage: {storage.base_dir}")
    return 0


def _cmd_auth(args: argparse.Namespace, storage: Storage) -> int:
    client = ClaudeClient()
    if args.auth_command == "status":
        status = client.auth_status()
        print(json.dumps(status.payload, indent=2, ensure_ascii=False))
        return 0 if status.logged_in else 1

    if args.auth_command == "login":
        return client.login()

    if args.auth_command == "open-web":
        ok = client.open_web("https://claude.ai")
        if ok:
            print("Claude web opened.")
            return 0
        print("Failed to open browser.", file=sys.stderr)
        return 1

    if args.auth_command == "web-login":
        automator = WebClaudeAutomator(storage.base_dir / "browser-profile")
        result = automator.login_interactive(wait_seconds=args.wait_seconds)
        if result.ok:
            print(result.output)
            return 0
        if result.error:
            print(result.error, file=sys.stderr)
        return 1

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
        target, error = _resolve_task(tasks, args.task)
        if target is None:
            print(error, file=sys.stderr)
            return 1

        remaining = [task for task in tasks if task.id != target.id]
        storage.save_tasks(remaining)
        print(f"Task removed: {target.id} ({target.name})")
        return 0

    return 1


def _cmd_run(args: argparse.Namespace, storage: Storage) -> int:
    executor = TaskExecutor(web_automator=WebClaudeAutomator(storage.base_dir / "browser-profile"))
    scheduler = Scheduler(storage=storage, executor=executor, timezone_name=args.timezone)
    scheduler.run_forever(poll_interval=args.poll_interval)
    return 0


def _cmd_start(args: argparse.Namespace, storage: Storage) -> int:
    manager = DaemonManager(storage.base_dir)
    try:
        entry = manager.start(poll_interval=args.poll_interval, timezone_name=args.timezone)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"HiClaw started: id={entry.id} pid={entry.pid} log={entry.log_path}")
    return 0


def _cmd_isalive(storage: Storage) -> int:
    manager = DaemonManager(storage.base_dir)
    statuses = manager.list()
    if not statuses:
        print("No daemon records.")
        return 1

    alive_count = 0
    for entry, alive in statuses:
        state = "alive" if alive else "dead"
        if alive:
            alive_count += 1
        print(
            f"{entry.id} | pid={entry.pid} | {state} | started_at={entry.started_at} "
            f"| poll={entry.poll_interval}s | timezone={entry.timezone} | log={entry.log_path}"
        )
    return 0 if alive_count > 0 else 1


def _cmd_kill(args: argparse.Namespace, storage: Storage) -> int:
    manager = DaemonManager(storage.base_dir)
    try:
        killed = manager.kill(target=args.target, kill_all=args.all)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not killed:
        print("No running daemon to kill.")
        return 1

    for entry in killed:
        print(f"Killed daemon: id={entry.id} pid={entry.pid}")
    return 0


def _cmd_autostart(args: argparse.Namespace, storage: Storage) -> int:
    manager = DaemonManager(storage.base_dir)

    if args.autostart_command == "status":
        try:
            lines = manager.autostart_status()
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        if not lines:
            print("Autostart is not installed for this storage.")
            return 1
        for line in lines:
            print(line)
        return 0

    if args.autostart_command == "install":
        try:
            line = manager.autostart_install(poll_interval=args.poll_interval, timezone_name=args.timezone)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print("Autostart installed:")
        print(line)
        return 0

    if args.autostart_command == "remove":
        try:
            removed = manager.autostart_remove()
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"Autostart entries removed: {removed}")
        return 0

    return 1


def _cmd_once(args: argparse.Namespace, storage: Storage) -> int:
    tasks = storage.load_tasks()
    target, error = _resolve_task(tasks, args.task)
    if target is None:
        print(error, file=sys.stderr)
        return 1

    executor = TaskExecutor(web_automator=WebClaudeAutomator(storage.base_dir / "browser-profile"))
    scheduler = Scheduler(storage=storage, executor=executor, timezone_name=args.timezone)
    result = scheduler.run_task_now(target.id)
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
        return _cmd_auth(args, storage)

    if args.command == "task":
        return _cmd_task(args, storage)

    if args.command == "run":
        return _cmd_run(args, storage)

    if args.command == "start":
        return _cmd_start(args, storage)

    if args.command == "isalive":
        return _cmd_isalive(storage)

    if args.command == "kill":
        return _cmd_kill(args, storage)

    if args.command == "autostart":
        return _cmd_autostart(args, storage)

    if args.command == "once":
        return _cmd_once(args, storage)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
