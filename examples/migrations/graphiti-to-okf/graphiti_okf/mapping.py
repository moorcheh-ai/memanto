"""Graphiti graph objects -> Memanto memory records.

This module is the whole adapter. It is deliberately pure: it takes the raw
export dict produced by ``scripts/export_graphiti.py`` and returns
``MappedMemory`` records. Serialising those records into something the shipped
CLI can eat lives in :mod:`okf_writer` and :mod:`provider_json`.

Why the mapping looks the way it does
-------------------------------------
Graphiti is bi-temporal. Every ``EntityEdge`` carries two independent time
axes:

* ``created_at`` / ``expired_at`` — *transaction time*: when Graphiti itself
  learned the fact, and when it decided the fact had been contradicted.
* ``valid_at`` / ``invalid_at`` — *valid time*: when the fact was true out in
  the world, independent of when anyone told the system.

Flattening that into a single ``created_at`` is the failure mode this adapter
exists to avoid: it is exactly the information that answers "what did I use to
prefer, and when did I change my mind?". So the interval is preserved three
times over, at descending levels of structure:

1. as a natural-language sentence in the memory body, so Memanto's retrieval
   can actually match on it;
2. as OKF frontmatter keys, which ``memanto migrate okf`` funnels into the
   ``[Supporting data]`` footer, so the import is lossless;
3. as tags (``current`` / ``superseded``), so it is filterable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Memanto's 13 primitives (memanto.app.constants.VALID_MEMORY_TYPES).
VALID_MEMORY_TYPES = frozenset(
    {
        "fact",
        "preference",
        "goal",
        "decision",
        "artifact",
        "learning",
        "event",
        "instruction",
        "relationship",
        "context",
        "observation",
        "commitment",
        "error",
    }
)

SOURCE_NAME = "graphiti"

# Default Memanto type per Graphiti concept. Entity edges are refined further
# by _RELATION_RULES below; the other three are structural, so they map 1:1.
DEFAULT_TYPE_BY_KIND = {
    "entity_edge": "fact",
    "entity_node": "context",
    "episode": "observation",
    "community": "learning",
}

# An EntityEdge is Graphiti's atomic unit of knowledge, but "fact" is only its
# floor. The relation name (PREFERS, DECIDED_ON, WORKS_AT...) is a strong,
# cheap signal for a more specific Memanto primitive. First match wins, so the
# order encodes precedence: intent beats mere association.
_RELATION_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "preference",
        (
            "prefer",
            "favor",
            "favour",
            "like",
            "dislike",
            "enjoy",
            "hate",
            "love",
            "want",
        ),
    ),
    (
        "decision",
        ("decid", "chose", "choose", "chosen", "select", "adopt", "switch", "settle"),
    ),
    ("goal", ("goal", "aim", "plan", "intend", "target", "aspir", "roadmap")),
    ("commitment", ("commit", "promis", "agree", "owe", "deadline", "due", "sla")),
    (
        "instruction",
        ("instruct", "rule", "policy", "must", "should", "always", "never", "require"),
    ),
    ("error", ("error", "fail", "bug", "broke", "regress", "incident", "outage")),
    (
        "relationship",
        (
            "works_at",
            "works_with",
            "employed",
            "manages",
            "reports_to",
            "member_of",
            "belongs_to",
            "owns",
            "colleague",
            "friend",
            "married",
            "parent",
            "teammate",
        ),
    ),
    (
        "event",
        ("attend", "happen", "occur", "launch", "ship", "releas", "visit", "joined"),
    ),
)

# Graphiti stores no per-fact confidence score. Rather than invent one, we
# derive it from the one form of certainty Graphiti *does* track: temporal
# standing. A superseded edge is not wrong -- it was true once -- so it keeps a
# non-trivial score, but it must never outrank the fact that replaced it.
CONFIDENCE_CURRENT_EDGE = 0.9
CONFIDENCE_SUPERSEDED_EDGE = 0.5
CONFIDENCE_ENTITY_NODE = 0.8
CONFIDENCE_EPISODE = 0.7
CONFIDENCE_COMMUNITY = 0.6

_MAX_TITLE_CHARS = 80


@dataclass
class MappedMemory:
    """One Memanto-shaped memory, plus the Graphiti provenance behind it."""

    title: str
    content: str
    type: str
    tags: list[str]
    confidence: float
    source_ref: str
    created_at: datetime | None
    graphiti_kind: str
    temporal: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.type not in VALID_MEMORY_TYPES:
            raise ValueError(
                f"{self.type!r} is not one of Memanto's 13 memory types; "
                "an unmapped type would be silently auto-classified on import."
            )


def _parse_dt(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp out of a Graphiti export field."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _title_from(text: str) -> str:
    flat = " ".join(text.split())
    if len(flat) <= _MAX_TITLE_CHARS:
        return flat
    return flat[: _MAX_TITLE_CHARS - 3].rstrip() + "..."


def classify_edge(name: str, fact: str) -> str:
    """Pick a Memanto type for an EntityEdge.

    The relation name is checked first because it is the author's own label for
    the relationship and carries far less noise than the rendered fact
    sentence; the fact text is only a fallback.
    """
    for haystack in (name or "", fact or ""):
        lowered = haystack.lower()
        if not lowered:
            continue
        for memory_type, needles in _RELATION_RULES:
            if any(needle in lowered for needle in needles):
                return memory_type
    return DEFAULT_TYPE_BY_KIND["entity_edge"]


def temporal_status(
    valid_at: datetime | None,
    invalid_at: datetime | None,
    expired_at: datetime | None,
) -> str:
    """``superseded`` once Graphiti has closed the interval, else ``current``."""
    return "superseded" if (invalid_at or expired_at) else "current"


def describe_validity(
    *,
    status: str,
    valid_at: datetime | None,
    invalid_at: datetime | None,
    expired_at: datetime | None,
    created_at: datetime | None,
) -> str:
    """Render Graphiti's bi-temporal interval as a retrievable English sentence.

    Memanto retrieves over memory *text*, so an interval that only exists in
    frontmatter is invisible to search. This sentence is what makes
    "what did I believe before I changed my mind" answerable after migration.
    """
    if status == "superseded":
        parts = ["No longer current."]
        if valid_at:
            parts.append(f"Was true from {_iso(valid_at)}")
            parts[-1] += f" until {_iso(invalid_at)}." if invalid_at else " onwards."
        elif invalid_at:
            parts.append(f"Ceased to be true on {_iso(invalid_at)}.")
        if expired_at:
            parts.append(f"Superseded in the graph on {_iso(expired_at)}.")
        return "Temporal validity: " + " ".join(parts)

    if valid_at:
        return (
            f"Temporal validity: currently true, in effect since {_iso(valid_at)} "
            "and not contradicted as of export."
        )
    if created_at:
        return (
            "Temporal validity: currently true; no explicit start date recorded, "
            f"first observed {_iso(created_at)}."
        )
    return "Temporal validity: currently true; no dates recorded."


def _entity_name_lookup(export: dict[str, Any]) -> dict[str, str]:
    return {
        node.get("uuid"): node.get("name") or "?"
        for node in export.get("entity_nodes") or []
        if node.get("uuid")
    }


def map_entity_edge(edge: dict[str, Any], names: dict[str, str]) -> MappedMemory | None:
    """Map one EntityEdge -- the carrier of Graphiti's temporal facts."""
    fact = (edge.get("fact") or "").strip()
    if not fact:
        return None

    relation = (edge.get("name") or "").strip()
    created_at = _parse_dt(edge.get("created_at"))
    valid_at = _parse_dt(edge.get("valid_at"))
    invalid_at = _parse_dt(edge.get("invalid_at"))
    expired_at = _parse_dt(edge.get("expired_at"))
    status = temporal_status(valid_at, invalid_at, expired_at)

    source = names.get(edge.get("source_node_uuid") or "", "?")
    target = names.get(edge.get("target_node_uuid") or "", "?")

    body = [fact, ""]
    body.append(
        describe_validity(
            status=status,
            valid_at=valid_at,
            invalid_at=invalid_at,
            expired_at=expired_at,
            created_at=created_at,
        )
    )
    body.append(f"Graph relation: {source} -[{relation or 'RELATES_TO'}]-> {target}")
    episodes = [e for e in (edge.get("episodes") or []) if e]
    if episodes:
        body.append(f"Derived from {len(episodes)} source episode(s).")

    tags = ["graphiti", "graphiti:entity_edge", status]
    if relation:
        tags.append(f"relation:{relation.lower()}")

    return MappedMemory(
        title=_title_from(fact),
        content="\n".join(body).strip(),
        type=classify_edge(relation, fact),
        tags=tags,
        confidence=(
            CONFIDENCE_SUPERSEDED_EDGE
            if status == "superseded"
            else CONFIDENCE_CURRENT_EDGE
        ),
        source_ref=f"graphiti:entity_edge:{edge.get('uuid')}",
        # Prefer valid_at: the date the knowledge was true beats the date the
        # pipeline happened to run.
        created_at=valid_at or created_at,
        graphiti_kind="entity_edge",
        temporal={
            "status": status,
            "valid_at": _iso(valid_at),
            "invalid_at": _iso(invalid_at),
            "expired_at": _iso(expired_at),
            "ingested_at": _iso(created_at),
        },
        extra={
            "graphiti_uuid": edge.get("uuid"),
            "graphiti_relation": relation,
            "graphiti_source_entity": source,
            "graphiti_target_entity": target,
            "graphiti_episodes": len(episodes),
            "graphiti_group_id": edge.get("group_id"),
        },
    )


def map_entity_node(node: dict[str, Any]) -> MappedMemory | None:
    """Map one EntityNode -> ``context``.

    An entity node is a durable subject with a rolled-up summary of everything
    around it. That is background about a recurring participant, not a discrete
    assertion, which is what ``context`` is for.
    """
    name = (node.get("name") or "").strip()
    if not name:
        return None
    summary = (node.get("summary") or "").strip()
    created_at = _parse_dt(node.get("created_at"))

    body = [f"{name}: {summary}" if summary else name]
    labels = [str(x) for x in (node.get("labels") or []) if x and x != "Entity"]
    if labels:
        body.append(f"Entity types: {', '.join(labels)}")
    attributes = node.get("attributes") or {}
    if attributes:
        rendered = "; ".join(f"{k}={v}" for k, v in attributes.items())
        body.append(f"Attributes: {rendered}")

    return MappedMemory(
        title=_title_from(name),
        content="\n\n".join(body).strip(),
        type=DEFAULT_TYPE_BY_KIND["entity_node"],
        tags=["graphiti", "graphiti:entity_node", *(f"label:{x.lower()}" for x in labels)],
        confidence=CONFIDENCE_ENTITY_NODE,
        source_ref=f"graphiti:entity_node:{node.get('uuid')}",
        created_at=created_at,
        graphiti_kind="entity_node",
        extra={
            "graphiti_uuid": node.get("uuid"),
            "graphiti_labels": ", ".join(labels) if labels else None,
            "graphiti_group_id": node.get("group_id"),
        },
    )


def map_episode(episode: dict[str, Any]) -> MappedMemory | None:
    """Map one EpisodicNode -> ``observation``.

    Episodes are the raw ingested utterances. They are unprocessed testimony
    rather than derived knowledge, so ``observation`` is the honest primitive.
    """
    content = (episode.get("content") or "").strip()
    if not content:
        return None
    name = (episode.get("name") or "").strip() or "episode"
    valid_at = _parse_dt(episode.get("valid_at"))
    created_at = _parse_dt(episode.get("created_at"))
    description = (episode.get("source_description") or "").strip()

    body = [content, ""]
    body.append(f"Recorded as episode '{name}'" + (f" ({description})." if description else "."))
    if valid_at:
        body.append(f"Occurred at {_iso(valid_at)}.")

    return MappedMemory(
        title=_title_from(f"{name}: {content}"),
        content="\n".join(body).strip(),
        type=DEFAULT_TYPE_BY_KIND["episode"],
        tags=["graphiti", "graphiti:episode", f"episode:{name.lower()}"],
        confidence=CONFIDENCE_EPISODE,
        source_ref=f"graphiti:episode:{episode.get('uuid')}",
        created_at=valid_at or created_at,
        graphiti_kind="episode",
        temporal={"status": "current", "valid_at": _iso(valid_at)},
        extra={
            "graphiti_uuid": episode.get("uuid"),
            "graphiti_episode_name": name,
            "graphiti_episode_source": episode.get("source"),
            "graphiti_source_description": description or None,
            "graphiti_group_id": episode.get("group_id"),
        },
    )


def map_community(node: dict[str, Any]) -> MappedMemory | None:
    """Map one CommunityNode -> ``learning``.

    Communities are not observed; Graphiti synthesises them by clustering the
    graph and summarising each cluster. That derived-insight quality is what
    separates ``learning`` from ``fact``.
    """
    name = (node.get("name") or "").strip()
    summary = (node.get("summary") or "").strip()
    if not (name or summary):
        return None

    body = [summary or name, "", "Synthesised by Graphiti community detection over clustered entities."]

    return MappedMemory(
        title=_title_from(name or summary),
        content="\n".join(body).strip(),
        type=DEFAULT_TYPE_BY_KIND["community"],
        tags=["graphiti", "graphiti:community"],
        confidence=CONFIDENCE_COMMUNITY,
        source_ref=f"graphiti:community:{node.get('uuid')}",
        created_at=_parse_dt(node.get("created_at")),
        graphiti_kind="community",
        extra={
            "graphiti_uuid": node.get("uuid"),
            "graphiti_group_id": node.get("group_id"),
        },
    )


def map_export(export: dict[str, Any]) -> list[MappedMemory]:
    """Map a whole raw Graphiti export into Memanto memory records.

    Ordering is entity edges first: they are the highest-value records, and
    OKF bundles read top-down.
    """
    names = _entity_name_lookup(export)
    mapped: list[MappedMemory] = []

    for edge in export.get("entity_edges") or []:
        record = map_entity_edge(edge, names)
        if record:
            mapped.append(record)
    for node in export.get("entity_nodes") or []:
        record = map_entity_node(node)
        if record:
            mapped.append(record)
    for episode in export.get("episodes") or []:
        record = map_episode(episode)
        if record:
            mapped.append(record)
    for community in export.get("communities") or []:
        record = map_community(community)
        if record:
            mapped.append(record)

    return mapped


def source_record_count(export: dict[str, Any]) -> int:
    """Total Graphiti objects in the export, for honest skipped-vs-mapped math."""
    return sum(
        len(export.get(key) or [])
        for key in ("entity_edges", "entity_nodes", "episodes", "communities")
    )


def type_breakdown(records: list[MappedMemory]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.type] = counts.get(record.type, 0) + 1
    return dict(sorted(counts.items()))


def kind_breakdown(records: list[MappedMemory]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.graphiti_kind] = counts.get(record.graphiti_kind, 0) + 1
    return dict(sorted(counts.items()))
