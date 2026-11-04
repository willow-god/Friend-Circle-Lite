"""Minimal five-field cron expression support.

Only the standard numeric syntax is supported: ``*``, lists, ranges, and step
values (for example ``*/15`` or ``1-5``). This is enough for scheduling the
daily email digest without adding a third-party dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


class CronSyntaxError(ValueError):
    """Raised when a cron expression cannot be parsed."""


@dataclass(frozen=True, slots=True)
class CronExpression:
    """A parsed five-field cron expression."""

    minutes: frozenset[int]
    hours: frozenset[int]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]
    day_is_wildcard: bool = False
    weekday_is_wildcard: bool = False

    @classmethod
    def parse(cls, expression: str) -> "CronExpression":
        fields = str(expression or "").split()
        if len(fields) != 5:
            raise CronSyntaxError(f"cron 表达式需要 5 个字段，实际为 {len(fields)} 个: {expression!r}")

        minutes = _parse_field(fields[0], 0, 59)
        hours = _parse_field(fields[1], 0, 23)
        days = _parse_field(fields[2], 1, 31)
        months = _parse_field(fields[3], 1, 12)
        weekdays = frozenset(value % 7 for value in _parse_field(fields[4], 0, 7))
        return cls(
            minutes=frozenset(minutes),
            hours=frozenset(hours),
            days=frozenset(days),
            months=frozenset(months),
            weekdays=weekdays,
            day_is_wildcard=fields[2] == "*",
            weekday_is_wildcard=fields[4] == "*",
        )

    def matches(self, moment: datetime) -> bool:
        if moment.minute not in self.minutes:
            return False
        if moment.hour not in self.hours:
            return False
        if moment.month not in self.months:
            return False

        day_matches = moment.day in self.days
        # Cron uses Sunday=0, while datetime.weekday() uses Monday=0.
        weekday_matches = ((moment.weekday() + 1) % 7) in self.weekdays

        # When both day fields are restricted, standard cron matches either one.
        if self.day_is_wildcard or self.weekday_is_wildcard:
            return day_matches and weekday_matches
        return day_matches or weekday_matches

    def latest_occurrence(self, now: datetime, lookback_days: int = 400) -> datetime | None:
        """Return the most recent matching minute at or before ``now``."""
        moment = now.replace(second=0, microsecond=0)
        earliest = moment - timedelta(days=lookback_days)
        while moment >= earliest:
            if self.matches(moment):
                return moment
            moment -= timedelta(minutes=1)
        return None


def _parse_field(field: str, minimum: int, maximum: int) -> set[int]:
    values: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            raise CronSyntaxError(f"cron 字段包含空项: {field!r}")

        base, step = _split_step(part)
        if base == "*":
            start, end = minimum, maximum
        elif "-" in base:
            start_text, end_text = base.split("-", 1)
            start = _parse_int(start_text, minimum, maximum)
            end = _parse_int(end_text, minimum, maximum)
            if end < start:
                raise CronSyntaxError(f"cron 范围起点大于终点: {part!r}")
        else:
            start = end = _parse_int(base, minimum, maximum)

        values.update(range(start, end + 1, step))
    return values


def _split_step(part: str) -> tuple[str, int]:
    if "/" not in part:
        return part, 1
    base, step_text = part.split("/", 1)
    try:
        step = int(step_text)
    except ValueError as exc:
        raise CronSyntaxError(f"cron 步长无效: {part!r}") from exc
    if step <= 0:
        raise CronSyntaxError(f"cron 步长必须大于 0: {part!r}")
    return base, step


def _parse_int(value: str, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise CronSyntaxError(f"cron 数值无效: {value!r}") from exc
    if not minimum <= number <= maximum:
        raise CronSyntaxError(f"cron 数值 {number} 超出范围 {minimum}-{maximum}")
    return number
