"""Offline deterministic backends — no API keys required.

Three architectures under test:

1. ActiveMemoryBackend  — Memanto-style: maintains a compact typed world-model
   per user. When a fact is updated, the old version is replaced. Retrieval is
   O(1) and always-current.

2. AppendLogBackend     — Naive RAG-style: every fact is appended verbatim.
   Retrieval returns the most recent N tokens. Context grows unboundedly;
   stale facts are never purged.

3. SnapshotBackend      — Session-KV style: stores the last value per key
   within a session window. Good for single-session apps; fails when
   preferences evolve across sessions because old sessions bleed through.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from .base import IngestResult, MemoryBackend, RetrieveResult


def _count_tokens(text: str) -> int:
    """Deterministic word-level token approximation (no external deps)."""
    return len(text.split()) if text else 0


# ---------------------------------------------------------------------------
# Backend 1 — Active Memory (Memanto architecture)
# ---------------------------------------------------------------------------

# Patterns that classify an incoming fact into a semantic slot.
# Each tuple: (slot_name, list_of_trigger_phrases)
_SLOT_PATTERNS: list[tuple[str, list[str]]] = [
    ("report_format", [
        "concise executive brief", "bullet point", "detailed launch-risk memo",
        "evidence table", "weekly digest", "narrative prose", "format my reports",
        "format reports",
    ]),
    ("timezone_policy", [
        "utc for all", "use utc", "local timezone", "customer-facing dates",
        "convert to local", "keep utc", "all timestamps",
        "never localise", "shown in the customer",
    ]),
    ("payment_retry", [
        "advisory lock", "outbox event", "exponential backoff",
        "at-most-once", "at-least-once", "idempotency key",
        "failed payments", "payment retry",
    ]),
    ("investor_update_style", [
        "investor update", "lead with revenue", "lead with growth",
        "highlight arr", "churn first", "lead investor",
        "investor meeting", "series b", "lead with arr",
        "new guidance: lead", "path to profitability",
    ]),
    ("financial_data", [
        "arr is $", "arr is", "revenue is $", "revenue is",
        "churn dropped", "mrr is", "valuation", "run rate",
        "arr $",
    ]),
    ("engineering_ticket_style", [
        "engineering ticket", "rollback plan", "impact radius",
        "root cause first", "p0 template", "critical ticket",
        "p0 tickets", "non-p0 tickets",
    ]),
    ("evidence_standard", [
        "speculative roadmap", "observed evidence", "no speculation",
        "cite sources", "data-backed claims", "competitive claims",
        "no speculative",
    ]),
    ("communication_cadence", [
        "daily standup", "weekly review", "async updates only",
        "slack preferred", "email preferred",
    ]),
    ("data_retention", [
        "delete after 30", "retain 90 days", "gdpr delete",
        "anonymise after", "keep indefinitely",
    ]),
]


def _classify_slot(text: str) -> str | None:
    lower = text.lower()
    for slot, phrases in _SLOT_PATTERNS:
        if any(p in lower for p in phrases):
            return slot
    return None


def _slot_matches_query(slot: str, query: str) -> bool:
    query_lower = query.lower()
    slot_keywords: dict[str, list[str]] = {
        "report_format": ["report", "format", "brief", "memo", "summary", "launch-risk"],
        "timezone_policy": ["timezone", "utc", "date", "time", "local", "customer-facing", "invoice"],
        "payment_retry": ["payment", "retry", "lock", "outbox", "idempotency", "double-charge"],
        "investor_update_style": ["investor", "update", "arr", "growth", "board", "metric", "lead"],
        "financial_data": ["arr", "revenue", "mrr", "churn", "valuation", "run rate", "4.2", "financial"],
        "engineering_ticket_style": ["engineering", "ticket", "rollback", "p0", "incident", "critical", "section"],
        "evidence_standard": ["evidence", "speculative", "roadmap", "claims", "sources", "competitive"],
        "communication_cadence": ["standup", "cadence", "slack", "email", "async", "update"],
        "data_retention": ["retention", "delete", "gdpr", "anonymise", "retain"],
    }
    return any(kw in query_lower for kw in slot_keywords.get(slot, []))


class ActiveMemoryBackend(MemoryBackend):
    """Memanto-style active memory: compact typed world-model per user.

    - Ingest: classify each turn into a semantic slot; replace if slot matches.
    - Retrieve: return only the slots relevant to the query (O(1), always current).
    """

    name = "active-memory (Memanto architecture)"

    def __init__(self) -> None:
        self._store: dict[str, dict[str, str]] = defaultdict(dict)

    def reset(self) -> None:
        self._store.clear()

    def ingest(self, user_id: str, content: str) -> IngestResult:
        with self._timer() as t:
            slot = _classify_slot(content)
            if slot:
                self._store[user_id][slot] = content.strip()
                written = _count_tokens(content)
            else:
                # Unclassified: store under auto key (append-once to misc)
                misc_key = f"misc_{len(self._store[user_id])}"
                self._store[user_id][misc_key] = content.strip()
                written = _count_tokens(content)
        return IngestResult(tokens_written=written, latency_ms=t.ms)

    def retrieve(self, user_id: str, query: str) -> RetrieveResult:
        with self._timer() as t:
            user_mem = self._store.get(user_id, {})
            relevant = [
                v for slot, v in user_mem.items()
                if _slot_matches_query(slot, query)
            ]
            # Fall back to all memories if no slot matched
            if not relevant:
                relevant = list(user_mem.values())
            ctx = "\n".join(relevant)
        return RetrieveResult(
            context=ctx,
            tokens_retrieved=_count_tokens(ctx),
            latency_ms=t.ms,
        )


# ---------------------------------------------------------------------------
# Backend 2 — Append-Log (naive RAG)
# ---------------------------------------------------------------------------

class AppendLogBackend(MemoryBackend):
    """Naive append-only log: every fact stored verbatim, retrieved newest-first.

    Simulates a simple vector DB or KV with no active consolidation.
    Context grows unboundedly; stale preferences remain alongside new ones.
    """

    name = "append-log (naive RAG)"
    MAX_TOKENS = 512  # Simulate context-window limit for retrieval

    def __init__(self) -> None:
        self._log: dict[str, list[str]] = defaultdict(list)

    def reset(self) -> None:
        self._log.clear()

    def ingest(self, user_id: str, content: str) -> IngestResult:
        with self._timer() as t:
            self._log[user_id].append(content.strip())
            written = _count_tokens(content)
        return IngestResult(tokens_written=written, latency_ms=t.ms)

    def retrieve(self, user_id: str, query: str) -> RetrieveResult:
        with self._timer() as t:
            entries = self._log.get(user_id, [])
            # Keyword filter: keep entries that share words with query
            query_words = set(re.sub(r"[^\w\s]", "", query.lower()).split())
            scored: list[tuple[int, str]] = []
            for entry in reversed(entries):  # newest first
                entry_words = set(re.sub(r"[^\w\s]", "", entry.lower()).split())
                overlap = len(query_words & entry_words)
                scored.append((overlap, entry))
            scored.sort(key=lambda x: -x[0])

            ctx_parts: list[str] = []
            total_tokens = 0
            for _, entry in scored:
                t_count = _count_tokens(entry)
                if total_tokens + t_count > self.MAX_TOKENS:
                    break
                ctx_parts.append(entry)
                total_tokens += t_count
            ctx = "\n".join(ctx_parts)
        return RetrieveResult(
            context=ctx,
            tokens_retrieved=_count_tokens(ctx),
            latency_ms=t.ms,
        )


# ---------------------------------------------------------------------------
# Backend 3 — Snapshot (session-KV)
# ---------------------------------------------------------------------------

class SnapshotBackend(MemoryBackend):
    """Session-KV snapshot: stores last value per slot per session.

    Models a simple Redis-style key-value store. Works well when preferences
    are stable within a session but degrades when users evolve preferences
    across sessions (old sessions cannot be invalidated).
    """

    name = "snapshot-kv (session-scoped)"

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, str]] = defaultdict(dict)
        self._current_session: dict[str, str] = defaultdict(lambda: "session_0")

    def reset(self) -> None:
        self._sessions.clear()
        self._current_session.clear()

    def new_session(self, user_id: str) -> None:
        """Simulate a new session boundary."""
        idx = int(self._current_session[user_id].split("_")[1]) + 1
        self._current_session[user_id] = f"session_{idx}"

    def ingest(self, user_id: str, content: str) -> IngestResult:
        with self._timer() as t:
            slot = _classify_slot(content) or f"item_{len(self._sessions.get(user_id, {}))}"
            session_key = f"{self._current_session[user_id]}:{slot}"
            self._sessions[user_id][session_key] = content.strip()
            written = _count_tokens(content)
        return IngestResult(tokens_written=written, latency_ms=t.ms)

    def retrieve(self, user_id: str, query: str) -> RetrieveResult:
        with self._timer() as t:
            all_entries = self._sessions.get(user_id, {})
            # Return all entries from all sessions (cross-session bleed)
            ctx_parts = list(all_entries.values())
            ctx = "\n".join(ctx_parts)
        return RetrieveResult(
            context=ctx,
            tokens_retrieved=_count_tokens(ctx),
            latency_ms=t.ms,
        )
