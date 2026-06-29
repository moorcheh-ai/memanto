"""
Memory Export Service

Generates a structured memory.md file with all 13 memory types
organized into sections, ready for agent consumption.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from memanto.app.utils.validation import validate_safe_id

# Memory type metadata: (label, emoji, description)
MEMORY_TYPE_META = {
    "fact": (
        "Facts",
        "Verified information, project status, and established truths.",
    ),
    "preference": (
        "Preferences",
        "User and entity preferences for personalization.",
    ),
    "instruction": (
        "Instructions",
        "Standing rules, constraints, and guidelines to always follow.",
    ),
    "decision": (
        "Decisions",
        "Architectural choices, approach selections, and their rationale.",
    ),
    "event": (
        "Events",
        "Important conversations, milestones, and temporal occurrences.",
    ),
    "goal": (
        "Goals",
        "Objectives, targets, and milestones to track progress.",
    ),
    "commitment": (
        "Commitments",
        "Promises, obligations, and TODOs that need follow-through.",
    ),
    "observation": (
        "Observations",
        "Patterns noticed, behavioral notes, and recurring themes.",
    ),
    "learning": (
        "Learnings",
        "Knowledge acquired from experience, corrections, and insights.",
    ),
    "relationship": (
        "Relationships",
        "Entity connections, team context, and collaboration patterns.",
    ),
    "context": (
        "Context",
        "Session summaries, status updates, and conversation state.",
    ),
    "artifact": (
        "Artifacts",
        "Tool outputs, files, reports, and external references.",
    ),
    "error": (
        "Errors",
        "Failure records, bugs, and lessons learned from mistakes.",
    ),
}

# Canonical ordering
MEMORY_TYPE_ORDER = [
    "instruction",
    "fact",
    "decision",
    "goal",
    "commitment",
    "preference",
    "relationship",
    "context",
    "event",
    "learning",
    "observation",
    "artifact",
    "error",
]


class MemoryExportService:
    """Formats and writes a structured memory.md for an agent."""

    def __init__(self, exports_dir: Path | None = None):
        self.exports_dir = exports_dir or (Path.home() / ".memanto" / "exports")

    # Public API
    def format_memory_md(
        self,
        agent_id: str,
        memories_by_type: dict[str, list[dict[str, Any]]],
        generated_at: str | None = None,
    ) -> str:
        """
        Build the full Markdown string.

        Args:
            agent_id: Agent identifier.
            memories_by_type: Dict mapping memory type -> list of memory dicts.
            generated_at: Timestamp for the header (defaults to now).

        Returns:
            Formatted Markdown string.
        """
        generated_at = generated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        total = sum(len(mems) for mems in memories_by_type.values())
        type_counts = {t: len(mems) for t, mems in memories_by_type.items() if mems}

        lines: list[str] = []

        # Header
        lines.append(f"# Memory — {agent_id}")
        lines.append("")
        lines.append(f"> Generated: {generated_at}  ")
        lines.append(f"> Total memories: **{total}**  ")

        if type_counts:
            summary_parts = [f"{t}: {c}" for t, c in type_counts.items()]
            lines.append(f"> Breakdown: {', '.join(summary_parts)}")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Sections in canonical order
        for mem_type in MEMORY_TYPE_ORDER:
            label, description = MEMORY_TYPE_META[mem_type]
            memories = memories_by_type.get(mem_type, [])

            lines.append(f"## {label}")
            lines.append("")
            lines.append(f"*{description}*")
            lines.append("")

            if not memories:
                lines.append("*No memories of this type.*")
                lines.append("")
                lines.append("---")
                lines.append("")
                continue

            for mem in memories:
                title = mem.get("title") or "Untitled"
                content = (mem.get("content") or "").strip()
                confidence = mem.get("confidence")
                tags = mem.get("tags", [])
                created_at = mem.get("created_at", "")
                status = mem.get("status", "")

                lines.append(f"### {title}")
                lines.append("")
                if content:
                    lines.append(content)
                    lines.append("")

                # Metadata line
                meta_parts: list[str] = []
                if confidence is not None:
                    meta_parts.append(f"Confidence: {confidence}")
                if status:
                    meta_parts.append(f"Status: {status}")
                if created_at:
                    meta_parts.append(f"Created: {str(created_at)[:19]}")
                if tags:
                    tag_str = (
                        ", ".join(f"`{t}`" for t in tags)
                        if isinstance(tags, list)
                        else str(tags)
                    )
                    meta_parts.append(f"Tags: {tag_str}")

                if meta_parts:
                    lines.append(f"*{' | '.join(meta_parts)}*")
                    lines.append("")

            lines.append("---")
            lines.append("")

        # Footer
        lines.append("*End of memory export.*")
        lines.append("")

        return "\n".join(lines)

    def write_memory_md(
        self,
        agent_id: str,
        memories_by_type: dict[str, list[dict[str, Any]]],
        output_path: Path | None = None,
    ) -> Path:
        """
        Generate and write memory.md to disk.

        Args:
            agent_id: Agent identifier.
            memories_by_type: Dict mapping memory type -> list of memory dicts.
            output_path: Custom output path. Defaults to
                ``~/.memanto/exports/{agent_id}_memory.md``.

        Returns:
            Absolute Path to the written file.
        """
        if output_path is None:
            validate_safe_id(agent_id, "agent_id")
            self.exports_dir.mkdir(parents=True, exist_ok=True)
            output_path = self.exports_dir / f"{agent_id}_memory.md"
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

        content = self.format_memory_md(agent_id, memories_by_type)
        output_path.write_text(content, encoding="utf-8")
        return output_path.resolve()
