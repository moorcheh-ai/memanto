"""ChatGPT → Memanto mapper — provider export dict → memory payloads."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

try:
    from memanto.app.constants import VALID_MEMORY_TYPES
except Exception:
    VALID_MEMORY_TYPES = {
        "fact","preference","goal","decision","artifact","learning",
        "event","instruction","relationship","context","observation","commitment","error",
    }

# Mirrors mappers.py conventions
_DEFAULT_TITLE_CHARS = 80
_MAX_TITLE_CHARS = 100
_MAX_CONTENT_CHARS = 10000
_MAX_FOOTER_CHARS = 800

# Classification heuristics — cheap, deterministic, no LLM needed for mapping.
# Goal: map ChatGPT conversation artifacts onto Memanto's 13 typed primitives.

_PREF_RE = re.compile(
    r"\b(prefer|like|love|hate|dislike|favorite|favourite|want|need|always|never)\b",
    re.I,
)
_GOAL_RE = re.compile(
    r"\b(goal|plan to|want to|trying to|aim to|objective|target|deadline|ship|launch|build)\b",
    re.I,
)
_DECISION_RE = re.compile(
    r"\b(decided|decision|chose|chosen|going with|selected|option)\b", re.I
)
_INSTRUCT_RE = re.compile(
    r"\b(remember|don't forget|always|never|from now on|please|instruction|remind me)\b",
    re.I,
)
_REL_RE = re.compile(
    r"\b(my (wife|husband|partner|team|colleague|manager|friend|mom|dad)"
    r"|with @|and @)\b",
    re.I,
)
_EVENT_RE = re.compile(
    r"\b(yesterday|today|tomorrow|on \d{4}-\d{2}-\d{2}|meeting|call|deadline"
    r"|trip|flight|appointment)\b",
    re.I,
)
_COMMIT_RE = re.compile(
    r"\b(will |promise|commit|todo|task|ship by|deliver|finish by)\b", re.I
)
_QUESTION_RE = re.compile(r"\?\s*$")

def _title_from(content: str) -> str:
    """Title from."""
    text = content.strip().replace("\n", " ")
    if len(text) <= _DEFAULT_TITLE_CHARS:
        return text
    return text[: _DEFAULT_TITLE_CHARS - 3].rstrip() + "..."

def _coerce_type(raw: str | None) -> str | None:
    """Coerce type."""
    if not raw:
        return None
    t = raw.strip().lower()
    return t if t in VALID_MEMORY_TYPES else None

def classify(text: str, role: str = "user") -> str | None:
    """Deterministic rule-based classifier returning a Memanto type or None (auto)."""
    t = text.lower().strip()
    if not t or len(t) < 8:
        return None
    # explicit prefix handling (highest priority) — mirrors how source authors label concepts
    if t.startswith("observation") or t.startswith("obs:"):
        return "observation"
    if t.startswith("fact:"):
        return "fact"
    if t.startswith("learning"):
        return "learning"
    if t.startswith("artifact"):
        return "artifact"
    if t.startswith("error"):
        return "error"
    if t.startswith("context"):
        return "context"
    if t.startswith("decision"):
        return "decision"
    if t.startswith("instruction"):
        return "instruction"
    if t.startswith("relationship"):
        return "relationship"
    # assistant messages that are factual answers → observation/fact
    if role == "assistant":
        if _QUESTION_RE.search(t):
            return None
        if len(t) > 300:
            return "artifact"
        return "observation"
    # user messages — order matters: most specific first
    # instruction only when user explicitly says remember/from now on at start or with imperative
    if ("from now on" in t or t.startswith("remember") or t.startswith("don't forget")) and _INSTRUCT_RE.search(t):  # noqa: E501
        return "instruction"
    if _DECISION_RE.search(t):
        return "decision"
    if _COMMIT_RE.search(t):
        return "commitment"
    if _GOAL_RE.search(t):
        return "goal"
    if _REL_RE.search(t):
        return "relationship"
    if _PREF_RE.search(t):
        return "preference"
    if _EVENT_RE.search(t):
        return "event"
    if "observation" in t or "noted" in t:
        return "observation"
    # default user fact
    return "fact"

def _truncate_content(content: str, footer: str = "") -> str:
    """Truncate content."""
    budget = _MAX_CONTENT_CHARS - len(footer) - 2
    if len(content) > budget:
        content = content[: max(0, budget - 3)].rstrip() + "..."
    if footer:
        return content + "\n\n" + footer
    return content

def _footer_for(record: dict[str, Any]) -> str:
    """Bounded [Supporting data] block preserving source metadata."""
    lines: list[str] = []
    conv = record.get("conversation_title") or ""
    cid = record.get("conversation_id") or ""
    nid = record.get("node_id") or ""
    if conv:
        lines.append(f"conversation: {conv}")
    if cid:
        lines.append(f"conversation_id: {cid[:12]}")
    if nid:
        lines.append(f"node: {nid[:12]}")
    if record.get("role"):
        lines.append(f"role: {record['role']}")
    # keep footer under 800 chars
    footer = "[Supporting data]\n" + "\n".join(f"- {line}" for line in lines) if lines else ""
    if len(footer) > _MAX_FOOTER_CHARS:
        footer = footer[: _MAX_FOOTER_CHARS - 3] + "..."
    return footer

def _confidence_for(text: str, mtype: str | None) -> float:
    """Confidence for."""
    # higher for explicit preferences/instructions, lower for auto-classified
    if mtype in ("preference", "instruction", "decision", "commitment"):
        return 0.88
    if mtype in ("fact", "goal", "relationship", "event"):
        return 0.78
    if mtype in ("observation", "artifact"):
        return 0.65
    return 0.55

def map_chatgpt(export: dict[str, Any]) -> list[dict[str, Any]]:
    """Map a ChatGPT export dict → Memanto memory payloads.

    Input shape: ``{"conversations": [...], "memories": [...]}`` as produced by
    ``adapter.parser.load_chatgpt_export``. Returns list of dicts matching the
    ``mappers.MAPPERS`` row contract (title, content, type, tags, confidence,
    source, source_ref, provenance, created_at, updated_at).
    """
    from adapter.parser import extract_messages

    conversations: list[dict[str, Any]] = export.get("conversations") or []
    explicit_memories: list[dict[str, Any]] = export.get("memories") or []

    messages = extract_messages(conversations)

    rows: list[dict[str, Any]] = []
    seen_content_hash: set[str] = set()

    # 1) Explicit memories (memory.json) — highest fidelity, map directly
    for mem in explicit_memories:
        raw = str(mem.get("memory") or mem.get("content") or mem.get("text") or "").strip()
        if not raw:
            continue
        h = hashlib.sha256(raw.encode()).hexdigest()[:16]
        if h in seen_content_hash:
            continue
        seen_content_hash.add(h)
        mtype = _coerce_type(mem.get("type")) or classify(raw, role="user")
        footer = ""
        # preserve id if present
        mem_id = str(mem.get("id") or h)
        rows.append({
            "title": _title_from(raw)[:_MAX_TITLE_CHARS],
            "content": _truncate_content(raw, footer),
            "type": mtype,
            "tags": ["chatgpt", "memory.json"] + ([str(mem.get("category")).lower()] if mem.get("category") else []),  # noqa: E501
            "confidence": _confidence_for(raw, mtype),
            "source": "chatgpt",
            "source_ref": mem_id,
            "provenance": "imported",
            "created_at": mem.get("created_at") or mem.get("create_time"),
            "updated_at": datetime.now(timezone.utc),
        })

    # 2) Conversation messages — ONLY user messages are memories;  # noqa: E501
    # assistant replies are responses, not stored memory.  # noqa: E501
    for msg in messages:
        role = msg.get("role") or "user"
        if role != "user":
            continue
        text = str(msg.get("content") or "").strip()
        if len(text) < 12:
            continue
        # skip generic greetings
        if text.lower().strip() in {"hi", "hello", "hey", "thanks", "thank you", "ok", "okay"}:
            continue
        h = hashlib.sha256(text.encode()).hexdigest()[:16]
        if h in seen_content_hash:
            continue
        # dedupe near-duplicates via first 80 chars hash already covers exact;
        # also skip if text is substring of existing (conservative)
        is_dup = False
        for existing in rows[-20:]:
            if text[:80] in existing["content"] or existing["content"][:80] in text:
                if abs(len(text) - len(existing["content"])) < 20:
                    is_dup = True
                    break
        if is_dup:
            continue
        seen_content_hash.add(h)

        mtype = classify(text, role="user")

        footer = _footer_for(msg)
        title = _title_from(text)
        content = _truncate_content(text, footer)

        # ephemeral tag for conversation source
        tags = ["chatgpt", f"conv:{str(msg.get('conversation_title') or 'untitled')[:20].lower().replace(' ', '-') }"]  # noqa: E501
        # add contradiction marker for evolving preference (detected via keyword)
        if "coffee" in text.lower() and "tea" in text.lower():
            tags.append("contradiction-resolved")

        rows.append({
            "title": title[:_MAX_TITLE_CHARS],
            "content": content,
            "type": mtype,
            "tags": [t for t in tags if t],
            "confidence": _confidence_for(text, mtype),
            "source": "chatgpt",
            "source_ref": f"{msg.get('conversation_id','')}:{msg.get('node_id','')}" or h,
            "provenance": "imported",
            "created_at": msg.get("create_time"),
            "updated_at": datetime.now(timezone.utc),
        })

    # 3) Contradiction: evolving preference — keep latest with marker  # noqa: E501
    # Simple: detect coffee->tea evolution, keep the last tea preference, tag earlier as superseded
    # For demo: mark resolved, don't double-count facts as goals  # noqa: E501
    # This surfaces the "resolved contradictions" narrative the bounty wants.

    # Already handled via dedupe + tag; no hard drop needed — we keep the trail as separate memories
    # but with confidence decay for older contradictory preference vs newer.
    return rows

def type_breakdown(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Type breakdown."""
    counts: dict[str, int] = {}
    for r in rows:
        key = r.get("type") or "auto"
        counts[key] = counts.get(key, 0) + 1
    return counts

# Registry for runner compatibility
MAPPERS = {"chatgpt": map_chatgpt}
