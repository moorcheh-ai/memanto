"""The Engineering Profile — recalled memories shaped for prompt injection.

Memanto returns a list of memory dicts from ``recall``. ``MemoryProfile`` wraps
that list and renders a compact, token-frugal context block that Claude Code
injects via a hook's ``additionalContext``. The block is deterministic and
grouped by memory type so hard rules (instructions) read before softer ones
(preferences).
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Any

# Render order: hard constraints first, context last. Mirrors how a senior
# engineer would brief a teammate — rules before nice-to-knows. Covers all of
# Memanto's valid memory types; anything unrecognised renders after these with
# a capitalised fallback label.
_TYPE_ORDER = [
    "instruction",
    "decision",
    "commitment",
    "preference",
    "error",
    "learning",
    "fact",
    "observation",
    "relationship",
    "artifact",
    "event",
    "context",
    "goal",
]

_TYPE_LABEL = {
    "instruction": "Rules (always honour)",
    "decision": "Decisions made",
    "commitment": "Commitments",
    "preference": "Preferences",
    "error": "Known failure modes",
    "learning": "Lessons learned",
    "fact": "Codebase facts",
    "observation": "Observed patterns",
    "relationship": "Relationships",
    "artifact": "Artifacts",
    "event": "Events",
    "context": "Background",
    "goal": "Goals",
}


@dataclass
class MemoryProfile:
    """A set of recalled memories, ready to format as an injectable block."""

    memories: list[dict[str, Any]]

    def __bool__(self) -> bool:
        return bool(self.memories)

    def __len__(self) -> int:
        return len(self.memories)

    @classmethod
    def from_recall(
        cls,
        result: dict[str, Any] | None,
        min_similarity: float | None = None,
    ) -> MemoryProfile:
        """Build a profile from a Memanto ``recall`` response.

        Applies an optional similarity floor. Memanto exposes the score as
        either ``score`` or ``similarity_score`` depending on the endpoint, so
        we coalesce both.
        """
        raw_memories = (result or {}).get("memories", []) or []
        memories = [m for m in raw_memories if isinstance(m, dict)]
        if min_similarity is not None:
            memories = [m for m in memories if _score(m) >= min_similarity]
        return cls(memories=memories)

    def format_context_block(self, skill_name: str | None = None) -> str:
        """Render the profile as a Markdown block for prompt injection.

        Returns an empty string when there is nothing to inject, so callers can
        cheaply skip injection (``if block:``).
        """
        if not self.memories:
            return ""

        grouped: dict[str, list[dict[str, Any]]] = {}
        for mem in self.memories:
            mtype = mem.get("type")
            key = mtype.lower() if isinstance(mtype, str) and mtype else "context"
            grouped.setdefault(key, []).append(mem)

        # Escape skill_name everywhere it appears in the injected block. The
        # block is fed back into the model as system context, so a crafted
        # value containing ``"`` or ``>`` would otherwise break attribute
        # boundaries or close the wrapper early and reshape the prompt.
        safe_skill = html.escape(skill_name, quote=True) if skill_name else ""
        header_skill = f" for /{safe_skill}" if safe_skill else ""
        lines = [
            f'<engineering-profile source="memanto"{_skill_attr(safe_skill)}>',
            f"Relevant engineering memory{header_skill} "
            "(carried over from previous skill sessions — honour it, "
            "do not re-ask the user):",
        ]

        ordered_types = [t for t in _TYPE_ORDER if t in grouped]
        ordered_types += [t for t in grouped if t not in _TYPE_ORDER]

        for mtype in ordered_types:
            label = _TYPE_LABEL.get(mtype, mtype.capitalize())
            lines.append(f"\n{label}:")
            for mem in grouped[mtype]:
                lines.append(f"  - {_render_memory(mem)}")

        lines.append("</engineering-profile>")
        return "\n".join(lines)

    def to_plain_list(self) -> list[str]:
        """Flat list of memory contents (for CLI/profile display)."""
        return [_render_memory(m) for m in self.memories]


def _render_memory(mem: dict[str, Any]) -> str:
    content = (mem.get("content") or mem.get("title") or "").strip()
    confidence = mem.get("confidence")
    if isinstance(confidence, (int, float)) and confidence < 0.6:
        return f"{content} (tentative)"
    return content


def _score(mem: dict[str, Any]) -> float:
    raw = mem.get("score")
    if raw is None:
        raw = mem.get("similarity_score")
    try:
        return float(raw) if raw is not None else 1.0
    except (TypeError, ValueError):
        return 1.0


def _skill_attr(skill_name: str | None) -> str:
    """Render the ``skill="..."`` attribute. Caller must pass an HTML-escaped value."""
    return f' skill="{skill_name}"' if skill_name else ""
