"""
Hindsight document-transfer ZIP → OKF bundle adapter (Path B, #1609).

Parses archives produced by Hindsight's async export API
(``POST .../document-transfer/export``) — ``manifest.json``, per-document
JSON under ``documents/``, and optional ``observations.json`` — and writes an
OKF v0.2 bundle consumable by ``memanto migrate okf``.

Schema reference: vectorize-io/hindsight ``hindsight_api/engine/transfer/schema.py``
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from memanto.app.services.okf_export_service import OkfExportService

# Hindsight ``fact_type`` → Memanto memory type (None = auto-classify on import).
HINDSIGHT_FACT_TYPE_MAP: dict[str, str | None] = {
    "world": "fact",
    "experience": "event",
    "opinion": "preference",
    "observation": "observation",
    "belief": "fact",
    "relationship": "relationship",
    "goal": "goal",
    "plan": "goal",
    "task": "commitment",
    "decision": "decision",
}


@dataclass(frozen=True)
class HindsightArchive:
    manifest: dict[str, Any]
    documents: list[dict[str, Any]]
    observations: list[dict[str, Any]]


def parse_hindsight_archive(source: str | Path | bytes) -> HindsightArchive:
    """Load a Hindsight transfer ZIP from a path or raw bytes."""
    if isinstance(source, bytes):
        payload = source
    else:
        payload = Path(source).read_bytes()

    try:
        zf_ctx = zipfile.ZipFile(io.BytesIO(payload), "r")
    except zipfile.BadZipFile as exc:
        raise ValueError("Invalid Hindsight archive: not a valid ZIP file") from exc

    with zf_ctx as zf:
        names = set(zf.namelist())
        if "manifest.json" not in names:
            raise ValueError("Invalid Hindsight archive: manifest.json is missing")

        manifest = json.loads(zf.read("manifest.json"))
        doc_names = sorted(
            n for n in names if n.startswith("documents/") and n.endswith(".json")
        )
        documents = [json.loads(zf.read(name)) for name in doc_names]

        observations: list[dict[str, Any]] = []
        if "observations.json" in names:
            observations = json.loads(zf.read("observations.json"))

    return HindsightArchive(
        manifest=manifest, documents=documents, observations=observations
    )


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None
    return None


def _memory_from_fact(
    fact: dict[str, Any],
    *,
    document_id: str,
    fact_index: int,
    document_tags: list[str],
) -> dict[str, Any]:
    text = (fact.get("text") or "").strip()
    fact_type = (fact.get("fact_type") or "").strip().lower()
    mem_type = HINDSIGHT_FACT_TYPE_MAP.get(fact_type)

    tags = sorted({*(document_tags or []), *(fact.get("tags") or [])})
    if fact_type and fact_type not in tags:
        tags.append(f"hindsight:{fact_type}")

    entities = fact.get("entities") or []
    causal = fact.get("causal_relations") or []
    context = fact.get("context")

    body_parts = [text]
    if context:
        body_parts.append(f"\n_Context: {context}_")
    if entities:
        body_parts.append("\n**Entities:** " + ", ".join(entities))
    if causal:
        edges = ", ".join(
            f"{edge.get('relation_type')}→fact#{edge.get('target_fact_index')}"
            for edge in causal
        )
        body_parts.append(f"\n**Causal links:** {edges}")

    created_at = (
        _parse_dt(fact.get("mentioned_at"))
        or _parse_dt(fact.get("occurred_start"))
        or _parse_dt(fact.get("event_date"))
        or _parse_dt(fact.get("created_at"))
    )

    return {
        "id": f"{document_id}:fact:{fact_index}",
        "title": text[:80] + ("..." if len(text) > 80 else ""),
        "content": "".join(body_parts),
        "type": mem_type,
        "tags": tags,
        "confidence": 0.85,
        "source": "hindsight",
        "source_ref": f"{document_id}#{fact_index}",
        "provenance": "imported",
        "created_at": created_at,
    }


def hindsight_to_memories_by_type(archive: HindsightArchive) -> dict[str, list[dict[str, Any]]]:
    """Convert parsed Hindsight facts/observations into Memanto memory buckets."""
    buckets: dict[str, list[dict[str, Any]]] = {}

    def _add(mem_type: str | None, memory: dict[str, Any]) -> None:
        key = mem_type or "fact"
        buckets.setdefault(key, []).append(memory)

    for document in archive.documents:
        doc_id = document.get("id") or "unknown"
        doc_tags = document.get("tags") or []
        for index, fact in enumerate(document.get("facts") or []):
            memory = _memory_from_fact(
                fact, document_id=doc_id, fact_index=index, document_tags=doc_tags
            )
            _add(memory.get("type"), memory)

    for index, observation in enumerate(archive.observations):
        text = (observation.get("text") or "").strip()
        if not text:
            continue
        tags = list(observation.get("tags") or [])
        tags.append("hindsight:observation")
        memory = {
            "id": f"observation:{index}",
            "title": text[:80] + ("..." if len(text) > 80 else ""),
            "content": text,
            "type": "observation",
            "tags": tags,
            "confidence": 0.9,
            "source": "hindsight",
            "source_ref": f"observation:{index}",
            "provenance": "imported",
            "created_at": _parse_dt(observation.get("mentioned_at"))
            or _parse_dt(observation.get("event_date")),
        }
        _add("observation", memory)

    return buckets


def migration_summary(archive: HindsightArchive, memories_by_type: dict[str, list]) -> dict[str, Any]:
    """Summary table for PR / BountyHub claim."""
    source_facts = sum(len(doc.get("facts") or []) for doc in archive.documents)
    mapped = sum(len(rows) for rows in memories_by_type.values())
    return {
        "source_bank_id": archive.manifest.get("source_bank_id"),
        "schema_version": archive.manifest.get("schema_version"),
        "archive_type": archive.manifest.get("archive_type"),
        "source_documents": len(archive.documents),
        "source_facts": source_facts,
        "source_observations": len(archive.observations),
        "mapped_memories": mapped,
        "per_type": {k: len(v) for k, v in sorted(memories_by_type.items())},
    }


def export_hindsight_to_okf(
    source: str | Path | bytes,
    output_dir: str | Path,
    *,
    agent_id: str = "hindsight-migrated",
) -> dict[str, Any]:
    """Parse a Hindsight ZIP and write an OKF bundle directory."""
    archive = parse_hindsight_archive(source)
    memories_by_type = hindsight_to_memories_by_type(archive)

    svc = OkfExportService(exports_dir=Path(output_dir).parent)
    okf_result = svc.write_okf_bundle(
        agent_id,
        memories_by_type,
        output_dir=Path(output_dir),
        split="file",
    )

    summary = migration_summary(archive, memories_by_type)
    return {**okf_result, "migration_summary": summary}
