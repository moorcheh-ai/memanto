"""Shared validation for daily schedule times."""

import re

SCHEDULE_TIME_RE = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d")
