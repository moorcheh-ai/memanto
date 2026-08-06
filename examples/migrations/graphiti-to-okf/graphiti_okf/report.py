"""Render the mapping table and run summary from real data.

Generated rather than hand-written so the documented mapping can never drift
away from what :mod:`graphiti_okf.mapping` actually does, and so every count in
it comes from the export being migrated.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from graphiti_okf.mapping import (
    CONFIDENCE_COMMUNITY,
    CONFIDENCE_CURRENT_EDGE,
    CONFIDENCE_ENTITY_NODE,
    CONFIDENCE_EPISODE,
    CONFIDENCE_SUPERSEDED_EDGE,
    MappedMemory,
    kind_breakdown,
    source_record_count,
    type_breakdown,
)

_CONCEPT_ROWS = (
    (
        "`EntityEdge`",
        "`fact` (default), refined to `preference` / `decision` / `goal` / "
        "`commitment` / `instruction` / `relationship` / `event` / `error`",
        "Graphiti's atomic unit of knowledge and the only object carrying "
        "`valid_at`/`invalid_at`. The relation name (`PREFERS`, `DECIDED_ON`, "
        "`WORKS_AT`) is a strong signal for a more specific Memanto primitive "
        "than a bare `fact`.",
    ),
    (
        "`EntityNode`",
        "`context`",
        "A durable subject with a rolled-up summary of everything around it — "
        "background about a recurring participant, not a discrete assertion.",
    ),
    (
        "`EpisodicNode`",
        "`observation`",
        "The raw ingested utterance. Unprocessed testimony rather than derived "
        "knowledge, so `observation` is the honest primitive.",
    ),
    (
        "`CommunityNode`",
        "`learning`",
        "Not observed — Graphiti synthesises it by clustering the graph and "
        "summarising each cluster. That derived quality is what separates "
        "`learning` from `fact`.",
    ),
)

_FIELD_ROWS = (
    ("`fact` / `summary` / `content`", "memory body", "Verbatim, first line reused as the OKF `description`."),
    ("`uuid`", "`resource` / `source_ref`", "Prefixed `graphiti:<kind>:<uuid>` so every memory traces back to one graph object."),
    ("`valid_at`", "`timestamp` → `created_at`", "**Valid time wins over transaction time.** The date the knowledge was true is more useful than the date the pipeline ran."),
    ("`invalid_at`", "body sentence + `invalid_at` frontmatter", "Preserved twice: prose so retrieval can match it, frontmatter so import is lossless."),
    ("`expired_at`", "body sentence + `expired_at` frontmatter", "When Graphiti itself decided the fact was contradicted."),
    ("`created_at`", "`ingested_at` frontmatter", "Transaction time, kept distinct from valid time."),
    ("`name` (relation)", "type heuristic + `relation:<name>` tag", "Drives the refinement from `fact` to a more specific type."),
    ("`source_node_uuid` / `target_node_uuid`", "`Graph relation: A -[REL]-> B` line in the body", "Memanto stores no inter-memory edges, so the triple is flattened into readable text rather than dropped."),
    ("`episodes`", "`graphiti_episodes` count", "How many source episodes support the fact."),
    ("`group_id`", "`graphiti_group_id` frontmatter", "Partition provenance."),
    ("`labels`", "`label:<name>` tags", "Entity typing from Graphiti's ontology."),
    ("`attributes`", "`Attributes:` line in the body", "Custom entity attributes, flattened to text."),
    ("`name_embedding` / `fact_embedding`", "_dropped_", "Model-specific and re-computed by Memanto on ingest; keeping them would bloat the artifact for zero fidelity gain."),
)


def render_mapping_table(export: dict[str, Any], records: list[MappedMemory]) -> str:
    """Render `data/mapping_table.md`."""
    types = type_breakdown(records)
    kinds = kind_breakdown(records)
    superseded = sum(1 for r in records if r.temporal.get("status") == "superseded")
    source_total = source_record_count(export)

    lines = [
        "# Graphiti → Memanto mapping table",
        "",
        f"_Generated {datetime.now(timezone.utc).isoformat()} from "
        f"`{export.get('group_id', 'unknown')}` "
        f"(graphiti-core {export.get('graphiti_version', 'unknown')})._",
        "",
        "## 1. Concept mapping",
        "",
        "| Graphiti concept | Memanto type | Why |",
        "| --- | --- | --- |",
    ]
    lines += [f"| {a} | {b} | {c} |" for a, b, c in _CONCEPT_ROWS]

    lines += [
        "",
        "## 2. Field mapping",
        "",
        "| Graphiti field | Lands in | Notes |",
        "| --- | --- | --- |",
    ]
    lines += [f"| {a} | {b} | {c} |" for a, b, c in _FIELD_ROWS]

    lines += [
        "",
        "## 3. Confidence policy",
        "",
        "Graphiti stores no per-fact confidence score. Rather than invent one, the",
        "adapter derives confidence from the one form of certainty Graphiti *does*",
        "track — temporal standing. A superseded edge is not wrong (it was true once),",
        "so it keeps a non-trivial score, but it must never outrank the fact that",
        "replaced it.",
        "",
        "| Record | Confidence |",
        "| --- | ---: |",
        f"| Entity edge, still valid | {CONFIDENCE_CURRENT_EDGE} |",
        f"| Entity edge, superseded | {CONFIDENCE_SUPERSEDED_EDGE} |",
        f"| Entity node (`context`) | {CONFIDENCE_ENTITY_NODE} |",
        f"| Episode (`observation`) | {CONFIDENCE_EPISODE} |",
        f"| Community (`learning`) | {CONFIDENCE_COMMUNITY} |",
        "",
        "## 4. What this run actually produced",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Graphiti objects in export | {source_total} |",
        f"| Mapped Memanto memories | {len(records)} |",
        f"| Skipped (empty content) | {max(0, source_total - len(records))} |",
        f"| Carrying a closed validity interval | {superseded} |",
        "",
        "### By Graphiti concept",
        "",
        "| Concept | Count |",
        "| --- | ---: |",
    ]
    lines += [f"| {name} | {count} |" for name, count in kinds.items()]

    lines += [
        "",
        "### By Memanto type",
        "",
        "| Type | Count |",
        "| --- | ---: |",
    ]
    lines += [f"| {name} | {count} |" for name, count in types.items()]

    lines += [
        "",
        "## 5. Where the temporal interval survives",
        "",
        "Graphiti's bi-temporality is the reason this adapter exists, so each",
        "interval is written three times at descending levels of structure:",
        "",
        "1. **Prose in the memory body** — `Temporal validity: No longer current. Was",
        "   true from … until ….` Memanto retrieves over text, so an interval that",
        "   lives only in metadata is invisible to search.",
        "2. **OKF frontmatter keys** — `valid_at`, `invalid_at`, `expired_at`,",
        "   `ingested_at`, `graphiti_status`. `memanto migrate okf` routes unknown",
        "   frontmatter into the `[Supporting data]` footer, so import is lossless.",
        "3. **Tags** — `current` / `superseded`, so the distinction stays filterable.",
        "",
    ]
    return "\n".join(lines)


def render_run_summary(export: dict[str, Any], records: list[MappedMemory]) -> str:
    """Short console summary printed by the adapter."""
    types = type_breakdown(records)
    superseded = sum(1 for r in records if r.temporal.get("status") == "superseded")
    parts = [
        f"Source Graphiti objects : {source_record_count(export)}",
        f"Mapped Memanto memories : {len(records)}",
        f"Superseded (temporal)   : {superseded}",
        "Type breakdown          : "
        + (", ".join(f"{k}={v}" for k, v in types.items()) or "—"),
    ]
    return "\n".join(parts)
