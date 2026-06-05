from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Protocol

from .dataset import IncidentQuery, IncidentRecord


TOKEN_RE = re.compile(r"[A-Za-z0-9_.-]+")


@dataclass(frozen=True)
class MemoryHit:
    """A recalled memory snippet with provenance metadata."""

    text: str
    source_key: str
    session: int

    @property
    def tokens(self) -> int:
        """Return an approximate token count for the recalled text."""

        return len(TOKEN_RE.findall(self.text))


class MemoryBackend(Protocol):
    """Minimal backend contract required by the benchmark runner."""

    name: str

    def ingest(self, records: Iterable[IncidentRecord]) -> None:
        """Store benchmark incident records in the backend."""

        ...

    def recall(self, query: IncidentQuery) -> list[MemoryHit]:
        """Return memory snippets relevant to a benchmark query."""

        ...


def token_count(text: str) -> int:
    """Return the benchmark's simple lexical token count."""

    return len(TOKEN_RE.findall(text))


def _query_terms(query: IncidentQuery) -> set[str]:
    """Derive coarse retrieval terms from a benchmark query."""

    terms = {query.service}
    prompt = query.prompt.lower()
    for term in ("owner", "runbook", "status", "customer", "rollback", "escalation"):
        if term in prompt:
            terms.add(term)
    return terms


class MemantoTypedDigestBackend:
    """A Memanto-style backend that keeps current typed facts by key."""

    name = "memanto_typed_digest"

    def __init__(self) -> None:
        """Create an empty typed digest memory."""

        self.current_by_key: dict[str, IncidentRecord] = {}
        self.history: list[IncidentRecord] = []

    def ingest(self, records: Iterable[IncidentRecord]) -> None:
        """Store each record while applying supersession keys."""

        for record in records:
            self.history.append(record)
            for old_key in record.supersedes:
                self.current_by_key.pop(old_key, None)
            self.current_by_key[record.key] = record

    def recall(self, query: IncidentQuery) -> list[MemoryHit]:
        """Recall the strongest current typed facts for a query."""

        terms = _query_terms(query)
        scored: list[tuple[int, IncidentRecord]] = []
        for record in self.current_by_key.values():
            text = f"{record.kind} {record.service} {record.text}".lower()
            score = sum(1 for term in terms if term in text)
            if score:
                recency_bonus = record.session
                scored.append((score * 100 + recency_bonus, record))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            MemoryHit(
                text=(
                    f"[{record.service}:{record.kind}:session-{record.session}] "
                    f"{record.text}"
                ),
                source_key=record.key,
                session=record.session,
            )
            for _, record in scored[:2]
        ]


class AppendOnlyLogBackend:
    """A baseline backend that retains every historical incident record."""

    name = "append_only_log"

    def __init__(self) -> None:
        """Create an empty append-only memory."""

        self.records: list[IncidentRecord] = []

    def ingest(self, records: Iterable[IncidentRecord]) -> None:
        """Append all incident records without supersession."""

        self.records.extend(records)

    def recall(self, query: IncidentQuery) -> list[MemoryHit]:
        """Recall matching historical and current records for a query."""

        terms = _query_terms(query)
        matches: list[tuple[int, IncidentRecord]] = []
        for record in self.records:
            text = f"{record.kind} {record.service} {record.text}".lower()
            score = sum(1 for term in terms if term in text)
            if score:
                # Append-only systems often retain old and new matches together.
                matches.append((score * 100 + record.session, record))
        matches.sort(key=lambda item: item[0], reverse=True)
        return [
            MemoryHit(
                text=(
                    f"[{record.service}:{record.kind}:session-{record.session}] "
                    f"{record.text}"
                ),
                source_key=record.key,
                session=record.session,
            )
            for _, record in matches[:5]
        ]
