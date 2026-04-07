from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


EVERY_PATTERN = re.compile(r"^(?P<value>\d+)(?P<unit>[smhd])$")
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_every(spec: str) -> int:
    match = EVERY_PATTERN.match(spec.strip())
    if not match:
        raise ValueError("Invalid --every format, use <number><s|m|h|d>, e.g. 30m")

    value = int(match.group("value"))
    unit = match.group("unit")

    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return value * multipliers[unit]


def parse_at_times(spec: str) -> list[str]:
    values = [v.strip() for v in spec.split(",") if v.strip()]
    if not values:
        raise ValueError("--at-times cannot be empty")

    unique: set[str] = set()
    for value in values:
        if not TIME_PATTERN.match(value):
            raise ValueError(f"Invalid time '{value}', expected HH:MM")
        unique.add(value)

    return sorted(unique)


def parse_iso_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def localize(dt: datetime, timezone_name: str) -> datetime:
    return dt.astimezone(ZoneInfo(timezone_name))
