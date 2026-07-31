"""Durable memory extraction from Claude Code conversations.

The extractor applies lightweight, deterministic heuristics to user turns and
assistant summaries. It deliberately favours precision over recall: a memory
is emitted only when there is a clear, reusable signal (preference, decision,
fact, instruction, commitment, relationship, goal, event, observation,
context). Everything else is left in the source archive.

Each extracted memory uses the shape consumed by ``mappers.map_okf`` (and the
OKF loader): ``type``, ``title``, ``description``, ``tags``, ``timestamp``,
``body``, ``x_memanto``, ``extra``, ``source_path``.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from claude_code_adapter.parser import ConversationTurn

# --- Memory classification helpers -----------------------------------------

_PREFERENCE_RE = re.compile(
    r"\b(i|we)\s+(prefer|like|love|want|need|hate|dislike)\b"
    r"|\bmy\s+favorite\b"
    r"|\bplease\s+use\b"
    r"|\buse\s+[a-z0-9_.-]+\s+instead\b",
    re.IGNORECASE,
)

_DECISION_RE = re.compile(
    r"\b(decide|decided|let.s\s+use|going\s+with|go\s+with|choose|chose)\b",
    re.IGNORECASE,
)

_INSTRUCTION_RE = re.compile(
    r"\b(always|never|remember\s+to|make\s+sure\s+to|don.t\s+forget\s+to|"
    r"please\s+always|please\s+never)\b",
    re.IGNORECASE,
)

_COMMITMENT_RE = re.compile(
    r"\b(i|we)\s+(will|need\s+to|must|should|have\s+to)\b"
    r"|\btomorrow\s+(i|we)\b"
    r"|\bnext\s+week\b",
    re.IGNORECASE,
)

_RELATIONSHIP_RE = re.compile(
    r"\bmy\s+(team|colleague|manager|client|customer|partner|boss|friend)\b"
    r"|\bworks\s+with\b"
    r"|\bwe\s+work\s+on\b",
    re.IGNORECASE,
)

_GOAL_RE = re.compile(
    r"\b(goal|objective|aim|target|want\s+to\s+achieve|plan\s+to)\b",
    re.IGNORECASE,
)

_EVENT_RE = re.compile(
    r"\b(meeting|release|launch|deadline|due|call|interview|demo|sprint|"
    r"conference|on\s+\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|"
    r"nov|dec))\b",
    re.IGNORECASE,
)

_OBSERVATION_RE = re.compile(
    r"\b(i|we)\s+(noticed|found|saw|discovered|realized|learned|observed)\b",
    re.IGNORECASE,
)

_CONTEXT_RE = re.compile(
    r"\b(environment|stack|version|operating\s+system|language|framework|"
    r"database|server|port|localhost|node\s+version|python\s+version)\b",
    re.IGNORECASE,
)

# Tag extraction: tech/platform names commonly mentioned by developers.
_TAG_PATTERNS = [
    (r"\bpython\b", "python"),
    (r"\bjavascript\b", "javascript"),
    (r"\btypescript\b", "typescript"),
    (r"\bnode(?:\.js)?\b", "nodejs"),
    (r"\breact\b", "react"),
    (r"\bnext(?:\.js)?\b", "nextjs"),
    (r"\bdocker\b", "docker"),
    (r"\bkubernetes\b", "kubernetes"),
    (r"\bgolang\b|\bgo\s+language\b", "golang"),
    (r"\brust\b", "rust"),
    (r"\bpostgres(?:ql)?\b", "postgresql"),
    (r"\bmysql\b", "mysql"),
    (r"\bsqlite\b", "sqlite"),
    (r"\bmongodb\b", "mongodb"),
    (r"\bredis\b", "redis"),
    (r"\baws\b", "aws"),
    (r"\bazure\b", "azure"),
    (r"\bgcp\b|\bgoogle\s+cloud\b", "gcp"),
    (r"\bgit\b", "git"),
    (r"\bgithub\b", "github"),
    (r"\bclaude\b", "claude"),
    (r"\bopenai\b", "openai"),
    (r"\bllm\b|\blarge\s+language\s+model\b", "llm"),
    (r"\bapi\b", "api"),
    (r"\bfastapi\b", "fastapi"),
    (r"\bflask\b", "flask"),
    (r"\bdjango\b", "django"),
    (r"\bgraphql\b", "graphql"),
    (r"\bterraform\b", "terraform"),
    (r"\bnginx\b", "nginx"),
    (r"\bwindows\b", "windows"),
    (r"\bmac(?:os)?\b", "macos"),
    (r"\blinux\b", "linux"),
]


def _clean_text(text: str) -> str:
    """Normalise whitespace/newlines for classification and titles."""
    return re.sub(r"\s+", " ", text).strip()


def _extract_tags(text: str, cwd: str | None = None) -> list[str]:
    tags: list[str] = []
    for pattern, tag in _TAG_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE) and tag not in tags:
            tags.append(tag)
    if cwd:
        # Derive a project tag from the working directory basename.
        project = Path(cwd).name.strip()
        if project and len(project) <= 32:
            slug = re.sub(r"[^a-z0-9-]+", "-", project.lower()).strip("-")
            if slug and slug not in tags:
                tags.append(slug)
    return tags[:8]


def _classify(text: str) -> str:
    """Choose the best Memanto memory type for a user/assistant turn."""
    clean = _clean_text(text)
    if _INSTRUCTION_RE.search(clean):
        return "instruction"
    if _PREFERENCE_RE.search(clean):
        return "preference"
    if _DECISION_RE.search(clean):
        return "decision"
    if _RELATIONSHIP_RE.search(clean):
        return "relationship"
    if _COMMITMENT_RE.search(clean):
        return "commitment"
    if _GOAL_RE.search(clean):
        return "goal"
    if _EVENT_RE.search(clean):
        return "event"
    if _OBSERVATION_RE.search(clean):
        return "observation"
    if _CONTEXT_RE.search(clean):
        return "context"
    return "fact"


def _title_from(text: str, mem_type: str) -> str:
    clean = _clean_text(text)
    if len(clean) <= 80:
        return clean
    return clean[:77].rstrip() + "..."


def _memory_id(turn: ConversationTurn, index: int) -> str:
    """Deterministic id derived from the source message (stable across runs)."""
    seed = turn.message_id or f"{turn.session_id or 'session'}-{index}"
    return f"claude_{uuid.uuid5(uuid.NAMESPACE_URL, seed).hex[:12]}"


def _is_usable_turn(turn: ConversationTurn) -> bool:
    """Skip turns that are too short, tool-only, or meta wrappers."""
    if not turn.text:
        return False
    text = turn.text.strip()
    if len(text) < 12:
        return False
    if text.startswith("<local-command-caveat>"):
        return False
    if text.startswith("<command-name>"):
        return False
    # A turn made entirely of tool annotations is not durable knowledge.
    if re.fullmatch(r"(\[tool: [^\]]+\]\s*)+", text):
        return False
    return True


def _build_okf_entry(
    turn: ConversationTurn,
    index: int,
    source_path: str,
    *,
    confidence: float = 0.85,
) -> dict[str, Any]:
    """Convert one conversation turn into an OKF entry dict."""
    text = turn.text.strip()
    mem_type = _classify(text)
    tags = _extract_tags(text, turn.cwd)
    if turn.git_branch and "branch=" + turn.git_branch not in tags:
        tags.append("branch=" + turn.git_branch[:24])

    timestamp = (turn.timestamp or datetime.now(timezone.utc)).isoformat()
    mem_id = _memory_id(turn, index)

    return {
        "type": mem_type,
        "title": _title_from(text, mem_type),
        "description": _clean_text(text)[:200],
        "tags": tags,
        "timestamp": timestamp,
        "resource": f"{source_path}#{turn.message_id or index}",
        "body": text,
        "x_memanto": {
            "id": mem_id,
            "confidence": confidence,
            "provenance": "imported",
            "source": "claude-code",
            "status": "active",
            "type": mem_type,
        },
        "extra": {
            "session_id": turn.session_id,
            "cwd": turn.cwd,
            "git_branch": turn.git_branch,
            "message_id": turn.message_id,
        },
        "source_path": source_path,
    }


def extract_memories(
    turns: list[ConversationTurn],
    *,
    source_path: str = "claude-code",
    include_assistant: bool = True,
) -> list[dict[str, Any]]:
    """Extract durable OKF memory entries from parsed conversation turns.

    ``include_assistant`` controls whether assistant summaries are considered.
    Assistant text usually restates the user's request; enabling it can surface
    decisions, but may also duplicate user memories.
    """
    memories: list[dict[str, Any]] = []
    for index, turn in enumerate(turns):
        if turn.role == "user":
            if not _is_usable_turn(turn):
                continue
            memories.append(
                _build_okf_entry(turn, index, source_path, confidence=0.9)
            )
        elif include_assistant and turn.role == "assistant":
            if not _is_usable_turn(turn):
                continue
            # Only classify assistant text that reads like a decision/summary,
            # not generic answers. The pattern gate avoids flooding the bundle
            # with every assistant reply.
            if not _DECISION_RE.search(turn.text) and not _GOAL_RE.search(turn.text):
                continue
            memories.append(
                _build_okf_entry(turn, index, source_path, confidence=0.7)
            )
    return memories
