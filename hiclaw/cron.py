from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


class CronError(ValueError):
    pass


def _parse_range(token: str, minimum: int, maximum: int, allow_sunday_7: bool = False) -> set[int]:
    if token == "*":
        return set(range(minimum, maximum + 1))

    results: set[int] = set()
    for part in token.split(","):
        if "/" in part:
            base, step_str = part.split("/", 1)
            if not step_str.isdigit() or int(step_str) <= 0:
                raise CronError(f"Invalid step '{part}'")
            step = int(step_str)
        else:
            base = part
            step = 1

        if base == "*":
            start, end = minimum, maximum
        elif "-" in base:
            left, right = base.split("-", 1)
            start = int(left)
            end = int(right)
        else:
            start = int(base)
            end = int(base)

        if allow_sunday_7:
            start = 0 if start == 7 else start
            end = 0 if end == 7 else end

        if start < minimum or end > maximum or start > end:
            raise CronError(f"Out-of-range cron field '{part}'")

        for value in range(start, end + 1, step):
            results.add(value)

    return results


@dataclass
class CronExpression:
    minute: set[int]
    hour: set[int]
    day_of_month: set[int]
    month: set[int]
    day_of_week: set[int]
    day_of_month_any: bool
    day_of_week_any: bool

    @classmethod
    def parse(cls, expression: str) -> "CronExpression":
        fields = expression.split()
        if len(fields) != 5:
            raise CronError("Cron must have 5 fields: minute hour day month weekday")

        minute_str, hour_str, dom_str, month_str, dow_str = fields

        minute = _parse_range(minute_str, 0, 59)
        hour = _parse_range(hour_str, 0, 23)
        day_of_month = _parse_range(dom_str, 1, 31)
        month = _parse_range(month_str, 1, 12)
        day_of_week = _parse_range(dow_str, 0, 6, allow_sunday_7=True)

        return cls(
            minute=minute,
            hour=hour,
            day_of_month=day_of_month,
            month=month,
            day_of_week=day_of_week,
            day_of_month_any=(dom_str == "*"),
            day_of_week_any=(dow_str == "*"),
        )

    def matches(self, dt: datetime) -> bool:
        if dt.minute not in self.minute:
            return False
        if dt.hour not in self.hour:
            return False
        if dt.month not in self.month:
            return False

        dom_match = dt.day in self.day_of_month
        cron_dow = (dt.weekday() + 1) % 7
        dow_match = cron_dow in self.day_of_week

        if self.day_of_month_any and self.day_of_week_any:
            return True
        if self.day_of_month_any:
            return dow_match
        if self.day_of_week_any:
            return dom_match
        return dom_match or dow_match
