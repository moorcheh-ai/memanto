"""
LangGraph Memory Nodes - Read/Write from Memanto backend.

Provides two core nodes for a LangGraph StateGraph:
- recall_memories: Pre-node that recalls relevant memories and injects into state
- store_memories: Post-node that extracts signals and stores to Memanto

These nodes operate on a GraphState TypedDict that carries conversation
context alongside memory data.
"""

from __future__ import annotations

import re
from typing import Any

from memory_backend import LocalBackend, MemoryBackend, get_backend

# ---------------------------------------------------------------------------
# Extraction patterns: (regex, memory_type, confidence)
# ---------------------------------------------------------------------------
_PATTERNS = [
    (re.compile(r"(?:always|never|must|shall|should)\s+.{10,}", re.I), "instruction", 0.90),
    (re.compile(r"(?:decided|decision|chose|chosen|agreed|resolved)\s+(?:to|on|that)\s+.{10,}", re.I), "decision", 0.85),
    (re.compile(r"(?:prefer|preference|favour|favor|like better|standard is)\s+.{10,}", re.I), "preference", 0.75),
    (re.compile(r"(?:pattern|convention|approach|strategy|architecture|paradigm)\s*(?:is|are|:)\s+.{10,}", re.I), "decision", 0.80),
    (re.compile(r"(?:use|using|adopt|follow)\s+(?:the\s+)?(?:pattern|convention|style|approach|library|framework)\s+.{5,}", re.I), "preference", 0.70),
    (re.compile(r"(?:TODO|FIXME|HACK|NOTE|IMPORTANT|WARNING)[:\s].{5,}"), "context", 0.60),
    (re.compile(r"(?:test|testing|spec)\s+(?:first|driven|strategy|approach)\s+.{5,}", re.I), "instruction", 0.80),
    (re.compile(r"(?:file|module|directory|folder)\s+(?:structure|organization|layout|naming)\s*[:=]\s*.{5,}", re.I), "decision", 0.75),
    (re.compile(r"(?:naming|variable|function|class)\s+(?:convention|style|pattern)\s*[:=]\s*.{5,}", re.I), "preference", 0.70),
    (re.compile(r"(?:error|exception|failure|bug)\s+(?:handling|strategy|pattern)\s*[:=]\s*.{5,}", re.I), "instruction", 0.80),
]

# Tag categories for LangGraph workflow stages
_STAGE_TAG_MAP = {
    "research": ["research", "information-gathering"],
    "planning": ["planning", "architecture"],
    "implementation": ["implementation", "coding"],
    "review": ["review", "quality"],
    "testing": ["testing", "validation"],
}


# ---------------------------------------------------------------------------
# Signal extraction
# ---------------------------------------------------------------------------

def extract_signals(text: str, stage: str | None = None) -> list[dict[str, Any]]:
    """Extract engineering signals from LLM I/O text."""
    signals = []
    seen = set()
    for pat, mem_type, confidence in _PATTERNS:
        for match in pat.finditer(text):
            content = match.group(0).strip()
            key = content.lower()[:80]
            if key in seen:
                continue
            seen.add(key)
            tags = list(_STAGE_TAG_MAP.get(stage or "", []))
            signals.append({
                "type": mem_type,
                "title": content[:100],
                "content": content,
                "confidence": confidence,
                "tags": tags,
                "source": f"langgraph:{stage}" if stage else "langgraph",
                "provenance": "observed",
            })
    return signals


def extract_from_file_references(text: str, stage: str | None = None) -> list[dict[str, Any]]:
    """Extract file-path-based context memories."""
    signals = []
    ext_pat = re.compile(r"[\w./-]+\.(?:py|ts|js|go|rs|rb|java|md|yaml|yml|json|toml)")
    files = ext_pat.findall(text)
    if files:
        unique_files = list(dict.fromkeys(files))[:5]
        tags = list(_STAGE_TAG_MAP.get(stage or "", []))
        file_list = ", ".join(unique_files)
        signals.append({
            "type": "context",
            "title": f"Files referenced in {stage or 'langgraph'} session",
            "content": f"Files touched: {file_list}",
            "confidence": 0.60,
            "tags": tags + ["file-references"],
            "source": f"langgraph:{stage}" if stage else "langgraph",
            "provenance": "observed",
        })
    return signals


# ---------------------------------------------------------------------------
# Memory formatting
# ---------------------------------------------------------------------------

def format_memory_context(memories: list[dict[str, Any]], max_chars: int = 2000) -> str:
    """Format recalled memories into a concise context block for LLM injection."""
    if not memories:
        return ""

    lines = ["## Memory Context (from Memanto)"]
    lines.append("The following are your established decisions, instructions, and preferences from previous sessions. Honor them.")
    lines.append("")

    for m in memories:
        mtype = m.get("type", "context").upper()
        content = m.get("content", "")
        confidence = m.get("confidence", 0.8)
        tags = m.get("tags", [])
        if len(content) > 200:
            content = content[:197] + "..."
        tag_str = f" [{', '.join(tags)}]" if tags else ""
        lines.append(f"- [{mtype}] {content}{tag_str} (confidence: {confidence:.0%})")

    result = "\n".join(lines)
    if len(result) > max_chars:
        result = result[: max_chars - 3] + "..."
    return result


# ---------------------------------------------------------------------------
# LangGraph Node Functions
# ---------------------------------------------------------------------------

def recall_memories(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph pre-node: recall relevant memories and inject into state.

    Reads from state:
        - messages: list of conversation messages
        - session_id: optional session identifier for cross-session recall
        - backend: optional MemoryBackend instance (uses default if not set)
        - stage: optional workflow stage tag

    Writes to state:
        - memory_context: formatted string of recalled memories for LLM injection
        - recalled_memories: raw list of recalled memory dicts
    """
    backend: MemoryBackend = state.get("backend") or get_backend()
    messages = state.get("messages", [])
    session_id = state.get("session_id", "default")
    stage = state.get("stage")

    # Build a recall query from the latest user message
    query_parts = []
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                query_parts.append(content[:200])
            elif isinstance(content, list):
                # Handle structured message content
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        query_parts.append(block.get("text", "")[:200])

    # Also include session_id as a query hint for cross-session recall
    if session_id and session_id != "default":
        query_parts.append(session_id)

    query = " ".join(query_parts) if query_parts else "general context"

    # Recall memories relevant to the query
    memories = backend.recall(query=query, limit=5)

    # If we have a stage, also recall stage-specific memories
    if stage:
        stage_tags = _STAGE_TAG_MAP.get(stage, [])
        stage_memories = backend.recall(query=stage, limit=3, tags=stage_tags)
        seen_ids = {m.get("id") for m in memories}
        for m in stage_memories:
            if m.get("id") not in seen_ids:
                memories.append(m)
                seen_ids.add(m.get("id"))

    context = format_memory_context(memories)

    return {
        **state,
        "memory_context": context,
        "recalled_memories": memories,
    }


def store_memories(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph post-node: extract signals and store to Memanto.

    Reads from state:
        - messages: list of conversation messages
        - session_id: optional session identifier
        - backend: optional MemoryBackend instance (uses default if not set)
        - stage: optional workflow stage tag

    Writes to state:
        - stored_memory_ids: list of IDs for newly stored memories
    """
    backend: MemoryBackend = state.get("backend") or get_backend()
    messages = state.get("messages", [])
    session_id = state.get("session_id", "default")
    stage = state.get("stage")

    # Gather all text content from messages for signal extraction
    all_text_parts = []
    for msg in messages:
        if isinstance(msg, dict):
            content = msg.get("content", "")
            if isinstance(content, str):
                all_text_parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        all_text_parts.append(block.get("text", ""))

    full_text = "\n\n".join(all_text_parts)

    # Extract signals
    signals = extract_signals(full_text, stage)
    signals.extend(extract_from_file_references(full_text, stage))

    # Add session metadata to each signal
    for signal in signals:
        if session_id and session_id != "default":
            signal.setdefault("tags", [])
            if f"session:{session_id}" not in signal["tags"]:
                signal["tags"].append(f"session:{session_id}")

    # Store signals
    stored_ids = []
    for signal in signals:
        try:
            mid = backend.store(signal)
            stored_ids.append(mid)
        except Exception:
            pass

    return {
        **state,
        "stored_memory_ids": stored_ids,
    }
