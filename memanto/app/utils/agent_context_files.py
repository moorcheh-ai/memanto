"""Select generated local context documents belonging to one agent."""

import re
from pathlib import Path

from memanto.app.utils.validation import validate_safe_id

_DATE_PATTERN = r"[0-9]{4}-[0-9]{2}-[0-9]{2}"


def get_agent_context_files(
    data_dir: Path, agent_id: str
) -> tuple[list[Path], list[Path]]:
    """Return daily summaries and session logs with an exact agent boundary.

    Prefix matching alone includes other agents whose names start with the
    requested name. Daily summaries have a fixed date suffix. Session names
    are ambiguous because both agent and session ids allow underscores and
    dates, so their generated first-line owner must also match exactly.
    Custom filenames and session files without an owner header are omitted.
    """
    validate_safe_id(agent_id, "agent_id")
    prefix = re.escape(agent_id)
    summary_name = re.compile(rf"{prefix}_{_DATE_PATTERN}\.md")
    session_name = re.compile(rf"{prefix}_{_DATE_PATTERN}_[A-Za-z0-9_-]+_summary\.md")
    summaries = [
        path
        for path in sorted((data_dir / "summaries").glob(f"{agent_id}_*.md"))
        if summary_name.fullmatch(path.name)
        and path.is_file()
        and not path.is_symlink()
    ]

    expected_header = f"# Session Summary for {agent_id}".encode("ascii")
    valid_headers = {
        expected_header,
        expected_header + b"\n",
        expected_header + b"\r\n",
    }
    sessions = []
    for path in sorted((data_dir / "sessions").glob(f"{agent_id}_*_summary.md")):
        if (
            not session_name.fullmatch(path.name)
            or path.is_symlink()
            or not path.is_file()
        ):
            continue
        try:
            with path.open("rb") as source:
                header = source.readline(len(expected_header) + 2)
        except OSError:
            continue
        if header in valid_headers:
            sessions.append(path)

    return summaries, sessions
