"""
Temporal Query Helpers

Utility functions to make temporal queries easier for agents.
"""

from datetime import datetime, timedelta, timezone
from typing import Any


def parse_iso_timestamp(ts_str: str) -> datetime:
    """
    Parse an ISO formatted timestamp string into an aware UTC datetime object.
    Handles missing timezones by assuming UTC.
    """
    if not ts_str:
        raise ValueError("Empty timestamp string")

    ts_str = ts_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(ts_str)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def format_local_time(ts) -> str:
    """
    Format a timestamp (string or datetime) into a highly-readable local time string.
    Example: 'Mar 11, 2026 03:00 PM'
    """
    if not ts:
        return ""

    try:
        if isinstance(ts, str):
            clean_ts = ts.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_ts)
        elif isinstance(ts, datetime):
            dt = ts
        else:
            return str(ts)

        # If the timestamp is naive (no timezone info), assume it's UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        # Convert to local time
        local_dt = dt.astimezone()
        return local_dt.strftime("%b %d, %Y %I:%M %p")
    except Exception:
        return str(ts)


def format_current_local_time() -> str:
    """
    Get the current time in a highly-readable local time string.
    """
    return datetime.now().astimezone().strftime("%b %d, %Y %I:%M %p")


def get_today_range() -> tuple[str, str]:
    """Get ISO timestamps for today (start and end)"""
    today = datetime.now(timezone.utc).date()
    start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    end = datetime.combine(today, datetime.max.time(), tzinfo=timezone.utc)
    return start.isoformat().replace("+00:00", "Z"), end.isoformat().replace(
        "+00:00", "Z"
    )


def get_yesterday_range() -> tuple[str, str]:
    """Get ISO timestamps for yesterday (start and end)"""
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    start = datetime.combine(yesterday, datetime.min.time(), tzinfo=timezone.utc)
    end = datetime.combine(yesterday, datetime.max.time(), tzinfo=timezone.utc)
    return start.isoformat().replace("+00:00", "Z"), end.isoformat().replace(
        "+00:00", "Z"
    )


def get_last_n_days(days: int) -> str:
    """Get ISO timestamp for N days ago (start of day)"""
    past = datetime.now(timezone.utc) - timedelta(days=days)
    start = datetime.combine(past.date(), datetime.min.time(), tzinfo=timezone.utc)
    return start.isoformat().replace("+00:00", "Z")


def get_last_n_hours(hours: int) -> str:
    """Get ISO timestamp for N hours ago"""
    past = datetime.now(timezone.utc) - timedelta(hours=hours)
    return past.isoformat().replace("+00:00", "Z")


def get_this_week_range() -> tuple[str, str]:
    """Get ISO timestamps for current week (Monday to Sunday)"""
    today = datetime.now(timezone.utc)
    monday = today - timedelta(days=today.weekday())
    start = datetime.combine(monday.date(), datetime.min.time(), tzinfo=timezone.utc)
    end = datetime.now(timezone.utc)
    return start.isoformat().replace("+00:00", "Z"), end.isoformat().replace(
        "+00:00", "Z"
    )


def get_this_month_range() -> tuple[str, str]:
    """Get ISO timestamps for current month (1st to today)"""
    today = datetime.now(timezone.utc)
    first_day = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return first_day.isoformat().replace("+00:00", "Z"), today.isoformat().replace(
        "+00:00", "Z"
    )


def parse_relative_time(relative: str) -> str | None:
    """
    Parse relative time strings to ISO timestamps

    Supports:
    - "today", "yesterday"
    - "last 7 days", "last 24 hours"
    - "this week", "this month"

    Examples:
        parse_relative_time("today") -> "2025-12-27T00:00:00Z"
        parse_relative_time("last 7 days") -> "2025-12-20T00:00:00Z"
    """
    relative = relative.lower().strip()

    if relative == "today":
        start, _ = get_today_range()
        return start

    if relative == "yesterday":
        start, _ = get_yesterday_range()
        return start

    if relative == "this week":
        start, _ = get_this_week_range()
        return start

    if relative == "this month":
        start, _ = get_this_month_range()
        return start

    # Parse "last N days/hours"
    if relative.startswith("last "):
        parts = relative.split()
        if len(parts) == 3:
            try:
                number = int(parts[1])
                unit = parts[2]

                if unit in ["day", "days"]:
                    return get_last_n_days(number)
                elif unit in ["hour", "hours"]:
                    return get_last_n_hours(number)
            except ValueError:
                pass

    return None


def build_temporal_query(
    base_url: str,
    agent_id: str,
    query: str,
    relative_time: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """
    Build a complete temporal recall request payload.

    Args:
        base_url: MEMANTO server URL (e.g., "http://localhost:8000")
        agent_id: Agent identifier
        query: Search query
        relative_time: Human-readable time (e.g., "last 7 days", "today")
        created_after: ISO timestamp (overrides relative_time)
        created_before: ISO timestamp
        limit: Maximum results

    Returns:
        Dict containing:
        - method: HTTP method ("POST")
        - url: recall endpoint URL
        - json: request body for /api/v2/agents/{agent_id}/recall

    Examples:
        >>> build_temporal_query(
        ...     "http://localhost:8000",
        ...     "claude_dev",
        ...     "decisions",
        ...     relative_time="last 7 days"
        ... )
        {
          "method": "POST",
          "url": "http://localhost:8000/api/v2/agents/claude_dev/recall",
          "json": {
            "query": "decisions",
            "created_after": "2025-12-20T00:00:00Z",
            "limit": 10
          }
        }
    """
    # Parse relative time if provided and no absolute time given
    if relative_time and not created_after:
        created_after = parse_relative_time(relative_time)

    body: dict[str, Any] = {"query": query, "limit": limit}
    if created_after:
        body["created_after"] = created_after
    if created_before:
        body["created_before"] = created_before

    return {
        "method": "POST",
        "url": f"{base_url}/api/v2/agents/{agent_id}/recall",
        "json": body,
    }


# Quick access functions for common queries
def query_today(
    base_url: str, agent_id: str, query: str = "context", limit: int = 20
) -> dict[str, Any]:
    """Get memories from today"""
    return build_temporal_query(
        base_url, agent_id, query, relative_time="today", limit=limit
    )


def query_recent(
    base_url: str, agent_id: str, days: int = 7, query: str = "recent", limit: int = 20
) -> dict[str, Any]:
    """Get memories from last N days"""
    return build_temporal_query(
        base_url, agent_id, query, relative_time=f"last {days} days", limit=limit
    )


def query_this_week(
    base_url: str, agent_id: str, query: str = "week", limit: int = 30
) -> dict[str, Any]:
    """Get memories from this week"""
    return build_temporal_query(
        base_url, agent_id, query, relative_time="this week", limit=limit
    )
