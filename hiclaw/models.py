from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Task:
    id: str
    name: str
    executor: str
    model: str
    message: str
    schedule: dict[str, Any]
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "executor": self.executor,
            "model": self.model,
            "message": self.message,
            "schedule": self.schedule,
            "enabled": self.enabled,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Task":
        return cls(
            id=payload["id"],
            name=payload["name"],
            executor=payload.get("executor", "auto"),
            model=payload["model"],
            message=payload["message"],
            schedule=payload["schedule"],
            enabled=payload.get("enabled", True),
            created_at=payload.get("created_at", datetime.now(timezone.utc).isoformat()),
        )


@dataclass
class ExecutionResult:
    ok: bool
    output: str = ""
    error: str = ""
    code: int = 0
    auth_required: bool = False
