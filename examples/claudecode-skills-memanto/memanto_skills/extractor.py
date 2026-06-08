"""
Engineering insight extractor.

After a skill completes, the agent produces a conversation summary.
This module decides *what* to extract from that summary and *what memory
type* to tag it with, using simple heuristics that work without an LLM.

Callers can also pass structured entries directly to bypass heuristics.
"""

from __future__ import annotations

import re
from typing import Any


# ---------------------------------------------------------------------------
# Memory-type heuristics — ordered from most-specific to least
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[str, list[str]]] = [
    # (memory_type, list-of-keyword-fragments)
    ("decision",     ["decided", "chose", "will use", "going with", "picked", "selected", "we'll use", "we chose"]),
    ("instruction",  ["always", "never", "must", "should", "do not", "don't", "enforce", "rule:", "convention:"]),
    ("preference",   ["prefer", "like", "dislike", "want", "favour", "favor", "instead of"]),
    ("artifact",     ["created", "generated", "scaffold", "wrote", "added file", "created file"]),
    ("goal",         ["goal", "aim", "objective", "target", "want to achieve", "trying to"]),
    ("error",        ["bug", "error", "broken", "failed", "mistake", "regression", "issue"]),
    ("fact",         ["is ", "are ", "has ", "have ", "exists", "defined as", "means", "stands for"]),
    ("context",      ["context", "background", "project is", "codebase", "repo", "this project"]),
    ("learning",     []),  # catch-all
]


def infer_memory_type(text: str) -> str:
    """
    Heuristically infer the best Memanto memory type for *text*.

    Falls back to ``"learning"`` when nothing more specific matches.
    """
    lower = text.lower()
    for memory_type, keywords in _PATTERNS:
        if any(kw in lower for kw in keywords):
            return memory_type
    return "learning"


# ---------------------------------------------------------------------------
# Skill → memory-type mapping
# Used when the *skill name* itself is a strong signal.
# ---------------------------------------------------------------------------

_SKILL_TYPE_MAP: dict[str, str] = {
    "tdd":                          "decision",
    "grill-with-docs":              "decision",
    "grill-me":                     "decision",
    "improve-codebase-architecture": "decision",
    "setup-matt-pocock-skills":     "instruction",
    "diagnose":                     "learning",
    "to-prd":                       "artifact",
    "to-issues":                    "artifact",
    "triage":                       "context",
    "zoom-out":                     "context",
    "prototype":                    "artifact",
    "handoff":                      "context",
    "caveman":                      "preference",
    "write-a-skill":                "instruction",
}


def default_type_for_skill(skill_name: str) -> str:
    """Return the default memory type for *skill_name*, or ``"learning"``."""
    return _SKILL_TYPE_MAP.get(skill_name.lower(), "learning")


# ---------------------------------------------------------------------------
# Sentence splitter — split a multi-fact summary into atomic memories
# ---------------------------------------------------------------------------

_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def split_into_sentences(text: str, max_sentences: int = 5) -> list[str]:
    """
    Split *text* into individual sentences, capped at *max_sentences*.

    Used to break a paragraph-form skill summary into atomic memories.
    Each memory should be a single, independently retrievable fact.
    """
    sentences = [s.strip() for s in _SPLIT_RE.split(text.strip()) if s.strip()]
    return sentences[:max_sentences]


# ---------------------------------------------------------------------------
# Batch extraction helper
# ---------------------------------------------------------------------------

def extract_memories_from_summary(
    skill_name: str,
    summary: str,
    split_sentences: bool = False,
    confidence: float = 0.85,
    extra_tags: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Turn a free-text *summary* into a list of memory-entry dicts.

    Each dict has the keys expected by :meth:`MemantoSkillsClient.store_from_skill`:
    ``summary``, ``memory_type``, ``confidence``, ``extra_tags``.

    Args:
        skill_name:      The invoking skill (used for type defaults).
        summary:         Free-text summary from the skill run.
        split_sentences: If True, split *summary* into individual sentences
                         and create one memory per sentence.
        confidence:      Default confidence for all extracted memories.
        extra_tags:      Additional tags to attach to every extracted memory.
    """
    if split_sentences:
        fragments = split_into_sentences(summary)
    else:
        fragments = [summary]

    entries: list[dict[str, Any]] = []
    for fragment in fragments:
        if not fragment:
            continue
        memory_type = infer_memory_type(fragment) if split_sentences else default_type_for_skill(skill_name)
        entries.append({
            "summary":     fragment,
            "memory_type": memory_type,
            "confidence":  confidence,
            "extra_tags":  extra_tags,
        })
    return entries
