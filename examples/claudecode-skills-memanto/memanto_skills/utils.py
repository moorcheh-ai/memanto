"""
Shared formatting helpers.
"""

from __future__ import annotations

from typing import Any


def format_context_block(
    memories: list[dict[str, Any]],
    skill_name: str = "",
) -> str:
    """
    Format a list of Memanto memories into a compact markdown block.

    The block is designed to be prepended to a skill's SKILL.md content
    (or injected into the system prompt) so Claude Code absorbs past
    engineering decisions before executing the skill.

    Returns an empty string when *memories* is empty so callers can
    guard with a simple truthiness check.
    """
    if not memories:
        return ""

    header = (
        f"## Your Engineering Profile"
        + (f" (for `/{skill_name}`)" if skill_name else "")
        + "\n\n"
        + "_These memories were retrieved from your Memanto engineering profile "
        "and must be honoured throughout this skill execution. "
        "Do not repeat instructions the user has already given. "
        "Do not ask questions already answered here._\n"
    )

    lines: list[str] = [header]
    for i, mem in enumerate(memories, 1):
        mtype = mem.get("type", "memory")
        title = mem.get("title", "").strip()
        content = mem.get("content", "").strip()
        confidence = mem.get("confidence", "")
        tags: list[str] = mem.get("tags", [])

        # Strip the internal source tag to keep the output clean
        display_tags = [t for t in tags if not t.startswith("skill:") and t != "claudecode-skills-memanto"]

        badge = f"**[{mtype}]**"
        if confidence is not None and confidence != "":
            try:
                badge += f" _(confidence: {float(confidence):.0%})_"
            except (TypeError, ValueError):
                pass

        tag_str = f" · tags: {', '.join(display_tags)}" if display_tags else ""
        lines.append(f"{i}. {badge}{tag_str}")
        if title:
            lines.append(f"   **{title}**")
        if content:
            lines.append(f"   {content}")
        lines.append("")  # blank line between entries

    return "\n".join(lines)
