"""Distill a finished skill session into typed engineering memories.

This is the heart of the "active extraction" guideline: instead of regex-only
keyword matching, we lead with **Memanto's backend LLM** to read the session
summary and emit structured memories. We degrade gracefully to a lightweight
heuristic only if the LLM path yields nothing parseable, so a lifecycle hook
never silently no-ops.

Why ``answer()`` for extraction?
    ``SdkClient.answer`` routes to Memanto's backend LLM
    (``moorcheh.answer.generate``) and accepts an arbitrary ``question`` plus a
    ``header_prompt``. We turn that LLM into an extraction engine: the header
    frames it as a distiller, the question carries the session summary, and we
    ask for a strict JSON array of typed memories. The agent's existing
    memories are also retrieved as context, which helps the LLM avoid emitting
    near-duplicates of what is already stored.
"""

from __future__ import annotations

import json
import re
from typing import Any

from memanto.app.constants import VALID_MEMORY_TYPES
from memanto.app.utils.validation import InputLimits

# Sourced from the SDK so this never drifts if Memanto adds a 14th type.
VALID_TYPES = set(VALID_MEMORY_TYPES)

# Cap how much of a transcript we hand to the LLM. The bounty asks us to pass
# an "interaction summary"; we keep the most recent slice, which is where
# decisions usually land, and stay well under model context limits.
_MAX_SUMMARY_CHARS = 6000

EXTRACTION_HEADER = (
    "You are an engineering-memory distiller for a developer's coding agent. "
    "You read a summary of a finished coding session and extract only the "
    "DURABLE engineering signals worth remembering across future sessions: "
    "architectural decisions, hard rules/conventions, coding preferences, "
    "stable codebase facts, root-cause learnings, and explicit goals. "
    "Ignore ephemeral chatter, greetings, and one-off task details. "
    "Each item must stand alone without the surrounding conversation."
)

# The footer deliberately steers the LLM toward the 8 types that durable
# engineering signals actually land in; ``_coerce_memory`` still accepts any
# of the SDK's valid types if the model picks one outside this list.
EXTRACTION_FOOTER = (
    "Respond with ONLY a JSON array (no prose, no code fences). Each element: "
    '{"type": <one of: decision, instruction, preference, fact, learning, '
    'error, goal, context>, "title": <<=80 chars>, "content": <one atomic '
    'self-contained statement>, "confidence": <0.0-1.0>}. '
    "Return [] if nothing durable was established."
)


def build_extraction_question(skill_name: str | None, summary: str) -> str:
    """Compose the question handed to the backend LLM."""
    summary = (summary or "").strip()[:_MAX_SUMMARY_CHARS]
    skill_line = (
        f"The session used the /{skill_name} skill.\n" if skill_name else ""
    )
    return (
        f"{skill_line}"
        "Extract the durable engineering memories from this session summary.\n\n"
        "=== SESSION SUMMARY ===\n"
        f"{summary}\n"
        "=== END SUMMARY ==="
    )


def parse_llm_memories(answer_text: str) -> list[dict[str, Any]]:
    """Parse the LLM's JSON-array answer into validated memory dicts.

    Tolerant of code fences and leading/trailing prose: we locate the first
    JSON array in the text. Invalid items are dropped rather than raising, so
    a partially-malformed answer still yields usable memories.
    """
    if not answer_text:
        return []

    payload = _extract_json_array(answer_text)
    if payload is None:
        return []

    try:
        raw = json.loads(payload)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(raw, list):
        return []

    out: list[dict[str, Any]] = []
    for item in raw:
        mem = _coerce_memory(item)
        if mem is not None:
            out.append(mem)
    return out


def heuristic_memories(summary: str) -> list[dict[str, Any]]:
    """Lightweight fallback used only when the LLM path yields nothing.

    Splits the summary into sentences and classifies each by keyword. Kept
    deliberately conservative — it exists so the hook degrades gracefully when
    the network/LLM is unavailable, not to compete with the LLM path.
    """
    summary = (summary or "").strip()
    if not summary:
        return []

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sentence in _split_sentences(summary):
        s = _ROLE_PREFIX_RE.sub("", sentence).strip()
        if len(s) < 12:
            continue
        mtype = _classify(s)
        if mtype is None:
            continue
        key = s.lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "type": mtype,
                "title": s[:80],
                "content": s,
                "confidence": 0.6,
            }
        )
        if len(out) >= 12:
            break
    return out


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #

_FENCE_RE = re.compile(r"```(?:json)?", re.IGNORECASE)


def _extract_json_array(text: str) -> str | None:
    cleaned = _FENCE_RE.sub("", text).strip()
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return None
    return cleaned[start : end + 1]


def _coerce_memory(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    content = str(item.get("content") or "").strip()
    if not content:
        return None

    mtype = str(item.get("type") or "learning").strip().lower()
    if mtype not in VALID_TYPES:
        mtype = "learning"

    title = str(item.get("title") or content).strip()[:80]

    confidence = item.get("confidence", 0.85)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.85
    confidence = min(max(confidence, 0.0), 1.0)

    return {
        "type": mtype,
        "title": title,
        "content": content[: InputLimits.MAX_TEXT_LENGTH],
        "confidence": confidence,
    }


# Strip dialogue-format role prefixes ("user:", "assistant:", "human:", "claude:")
# that appear in raw transcript strings. Heuristic classification should see
# the content only, not the speaker label.
_ROLE_PREFIX_RE = re.compile(
    r"^\s*(?:user|assistant|human|claude|system)\s*:\s*", re.IGNORECASE
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?\n])\s+")

# Ordered most-specific first; first match wins.
_HEURISTIC_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("instruction", ("always", "never", "must ", "should ", "do not", "don't", "enforce", "convention")),
    ("decision", ("decided", "chose", "will use", "going with", "we use", "picked", "selected", "switched to")),
    ("preference", ("prefer", "favour", "favor", "instead of", "rather than", "like to")),
    ("error", ("bug", "root cause", "regression", "failed because", "broke")),
    ("goal", ("goal is", "aim to", "objective", "we want to")),
]


def _classify(sentence: str) -> str | None:
    lower = sentence.lower()
    for mtype, keywords in _HEURISTIC_RULES:
        if any(kw in lower for kw in keywords):
            return mtype
    return None


def _split_sentences(text: str) -> list[str]:
    # Treat bullet markers as sentence boundaries too.
    normalized = re.sub(r"^\s*[-*•]\s*", "", text, flags=re.MULTILINE)
    return _SENTENCE_SPLIT_RE.split(normalized)
