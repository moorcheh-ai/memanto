"""Read generated session logs without confusing agent-name prefixes."""

import logging
from pathlib import Path

from memanto.app.utils.validation import validate_safe_id

logger = logging.getLogger(__name__)


def read_session_summaries(sessions_dir: Path, agent_id: str, date: str) -> list[str]:
    """Load only logs whose generated owner header matches the requested agent.

    Agent and session IDs both allow underscores. A filename glob alone can
    therefore mistake another agent's name for this agent's date/session suffix.
    The first line is written by SessionService, before any memory content, and
    supplies an unambiguous owner. Omit logs without that binding; never infer
    ownership from a matching prefix or from text later in the memory body.
    """
    validate_safe_id(agent_id, "agent_id")
    validate_safe_id(date, "date")
    expected_header = f"# Session Summary for {agent_id}"
    contents = []
    for path in sorted(sessions_dir.glob(f"{agent_id}_{date}_*_summary.md")):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            with path.open(encoding="utf-8") as source:
                # Bound the ownership read and use the same open file for its
                # content. Text mode also accepts the writer's CRLF on Windows.
                header = source.readline(len(expected_header) + 2)
                if header not in (expected_header, expected_header + "\n"):
                    continue
                contents.append(header + source.read())
        except (OSError, UnicodeError):
            logger.warning("Could not read session summary %s", path)
    return contents
