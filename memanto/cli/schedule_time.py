"""Validation helpers for MEMANTO schedule times."""

import re

_SCHEDULE_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_SCHEDULE_TIME_ERROR = "schedule_time must be in HH:MM 24-hour format (00:00-23:59)"


def parse_schedule_time(time_str: str) -> tuple[int, int]:
    """Parse a schedule time string into ``(hour, minute)``."""
    if not isinstance(time_str, str):
        raise ValueError(_SCHEDULE_TIME_ERROR)

    match = _SCHEDULE_TIME_RE.fullmatch(time_str.strip())
    if not match:
        raise ValueError(_SCHEDULE_TIME_ERROR)
    return int(match.group(1)), int(match.group(2))


def normalize_schedule_time(time_str: str) -> str:
    """Return a canonical HH:MM representation for a valid schedule time."""
    hour, minute = parse_schedule_time(time_str)
    return f"{hour:02d}:{minute:02d}"
