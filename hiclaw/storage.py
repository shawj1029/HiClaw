from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Task


class Storage:
    def __init__(self, base_dir: str | Path | None = None) -> None:
        if base_dir is None:
            base_dir = Path.home() / ".hiclaw"
        self.base_dir = Path(base_dir).expanduser().resolve()
        self.tasks_path = self.base_dir / "tasks.json"
        self.state_path = self.base_dir / "state.json"
        self.history_path = self.base_dir / "history.json"

    def init(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        if not self.tasks_path.exists():
            self._write_json(self.tasks_path, {"tasks": []})
        if not self.state_path.exists():
            self._write_json(self.state_path, {"task_state": {}})
        if not self.history_path.exists():
            self._write_json(self.history_path, {"runs": []})

    def load_tasks(self) -> list[Task]:
        self.init()
        payload = self._read_json(self.tasks_path, {"tasks": []})
        return [Task.from_dict(item) for item in payload.get("tasks", [])]

    def save_tasks(self, tasks: list[Task]) -> None:
        self._write_json(self.tasks_path, {"tasks": [task.to_dict() for task in tasks]})

    def load_state(self) -> dict[str, Any]:
        self.init()
        return self._read_json(self.state_path, {"task_state": {}})

    def save_state(self, state: dict[str, Any]) -> None:
        self._write_json(self.state_path, state)

    def append_run(self, record: dict[str, Any], max_items: int = 500) -> None:
        payload = self._read_json(self.history_path, {"runs": []})
        runs = payload.get("runs", [])
        runs.append(record)
        payload["runs"] = runs[-max_items:]
        self._write_json(self.history_path, payload)

    def _read_json(self, path: Path, default: dict[str, Any]) -> dict[str, Any]:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        tmp_path.replace(path)
