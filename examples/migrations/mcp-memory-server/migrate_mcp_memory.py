#!/usr/bin/env python3
"""Convert the official MCP Memory Server JSONL graph into an OKF bundle.

The converter is intentionally dependency-free and offline.  It emits one
human-readable OKF Markdown document per MCP entity, preserves observations
and relations as readable links, and embeds the exact source records so the
graph can be reconstructed without loss.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import shutil
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote


class MigrationError(ValueError):
    """Raised when an MCP Memory source graph is invalid."""


_MEMANTO_TYPES = {
    "artifact",
    "commitment",
    "context",
    "decision",
    "error",
    "event",
    "fact",
    "goal",
    "instruction",
    "learning",
    "observation",
    "preference",
    "relationship",
}
_MCP_TYPE_TO_MEMANTO = {
    "agent": "artifact",
    "artifact": "artifact",
    "bounty": "goal",
    "component": "artifact",
    "decision": "decision",
    "error": "error",
    "event": "event",
    "fact": "fact",
    "goal": "goal",
    "instruction": "instruction",
    "learning": "learning",
    "organization": "relationship",
    "person": "relationship",
    "preference": "preference",
    "project": "artifact",
    "requirement": "instruction",
    "tool": "artifact",
}


@dataclass(frozen=True)
class EntityRecord:
    line: int
    raw: dict[str, Any]
    name: str
    entity_type: str
    observations: tuple[str, ...]


@dataclass(frozen=True)
class RelationRecord:
    line: int
    raw: dict[str, Any]
    source: str
    target: str
    relation_type: str


@dataclass(frozen=True)
class KnowledgeGraph:
    entities: tuple[EntityRecord, ...]
    relations: tuple[RelationRecord, ...]
    source_sha256: str
    source_bytes: bytes


def _required_string(record: dict[str, Any], key: str, line: int) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise MigrationError(f"line {line}: {key!r} must be a non-empty string")
    return value


def load_mcp_graph(path: str | Path) -> KnowledgeGraph:
    """Load and strictly validate the current MCP Memory JSONL schema."""
    source_path = Path(path)
    try:
        source_bytes = source_path.read_bytes()
    except OSError as exc:
        raise MigrationError(f"cannot read MCP Memory source: {source_path}") from exc
    try:
        source_text = source_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise MigrationError("MCP Memory source must be UTF-8 JSONL") from exc

    entities: list[EntityRecord] = []
    relations: list[RelationRecord] = []
    entity_names: set[str] = set()
    relation_keys: set[tuple[str, str, str]] = set()

    for line_number, raw_line in enumerate(source_text.splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise MigrationError(
                f"line {line_number}: invalid JSON ({exc.msg})"
            ) from exc
        if not isinstance(record, dict):
            raise MigrationError(f"line {line_number}: record must be an object")

        record_type = record.get("type")
        if record_type == "entity":
            name = _required_string(record, "name", line_number)
            entity_type = _required_string(record, "entityType", line_number)
            observations = record.get("observations")
            if not isinstance(observations, list) or not all(
                isinstance(item, str) for item in observations
            ):
                raise MigrationError(
                    f"line {line_number}: observations must be an array of strings"
                )
            if name in entity_names:
                raise MigrationError(
                    f"line {line_number}: duplicate entity name {name!r}"
                )
            entity_names.add(name)
            entities.append(
                EntityRecord(
                    line=line_number,
                    raw=record,
                    name=name,
                    entity_type=entity_type,
                    observations=tuple(observations),
                )
            )
        elif record_type == "relation":
            source = _required_string(record, "from", line_number)
            target = _required_string(record, "to", line_number)
            relation_type = _required_string(record, "relationType", line_number)
            key = (source, target, relation_type)
            if key in relation_keys:
                raise MigrationError(f"line {line_number}: duplicate relation {key!r}")
            relation_keys.add(key)
            relations.append(
                RelationRecord(
                    line=line_number,
                    raw=record,
                    source=source,
                    target=target,
                    relation_type=relation_type,
                )
            )
        else:
            raise MigrationError(
                f"line {line_number}: unsupported record type {record_type!r}"
            )

    if not entities:
        raise MigrationError("source graph contains no entities")

    for relation in relations:
        missing = {
            endpoint
            for endpoint in (relation.source, relation.target)
            if endpoint not in entity_names
        }
        if missing:
            names = ", ".join(sorted(repr(item) for item in missing))
            raise MigrationError(
                f"line {relation.line}: relation references missing entities: {names}"
            )

    return KnowledgeGraph(
        entities=tuple(entities),
        relations=tuple(relations),
        source_sha256=hashlib.sha256(source_bytes).hexdigest(),
        source_bytes=source_bytes,
    )


def _slug_base(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
    return slug[:64].rstrip("-") or "entity"


def build_entity_slugs(entities: tuple[EntityRecord, ...]) -> dict[str, str]:
    """Build stable, collision-proof filenames for entity documents."""
    used: set[str] = set()
    result: dict[str, str] = {}
    for entity in entities:
        base = _slug_base(entity.name)
        slug = base
        if slug in used:
            digest = hashlib.sha256(entity.name.encode("utf-8")).hexdigest()[:8]
            slug = f"{base[:55].rstrip('-')}-{digest}"
        counter = 2
        candidate = slug
        while candidate in used:
            candidate = f"{slug[:58].rstrip('-')}-{counter}"
            counter += 1
        used.add(candidate)
        result[entity.name] = candidate
    return result


def _yaml_scalar(value: Any) -> str:
    # JSON scalars and arrays are valid YAML and avoid adding a YAML dependency.
    return json.dumps(value, ensure_ascii=False)


def _markdown_line(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ").strip()


def _memanto_type(entity_type: str) -> str:
    normalized = entity_type.strip().casefold()
    if normalized in _MEMANTO_TYPES:
        return normalized
    return _MCP_TYPE_TO_MEMANTO.get(normalized, "observation")


def _source_fence(payload: str) -> str:
    """Return a CommonMark fence longer than any backtick run in the JSON."""
    longest = max((len(run) for run in re.findall(r"`+", payload)), default=0)
    return "`" * max(3, longest + 1)


def _source_payload(
    entity: EntityRecord,
    outgoing: list[RelationRecord],
    *,
    source_bytes: bytes | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "entity": {"line": entity.line, "record": entity.raw},
        "outgoing_relations": [
            {"line": relation.line, "record": relation.raw} for relation in outgoing
        ],
    }
    if source_bytes is not None:
        payload["source_file"] = {
            "encoding": "base64",
            "sha256": hashlib.sha256(source_bytes).hexdigest(),
            "bytes": base64.b64encode(source_bytes).decode("ascii"),
        }
    return payload


def _entity_document(
    entity: EntityRecord,
    outgoing: list[RelationRecord],
    incoming: list[RelationRecord],
    slugs: dict[str, str],
    *,
    source_bytes: bytes | None = None,
) -> str:
    description = (
        entity.observations[0]
        if entity.observations
        else f"MCP Memory entity of type {entity.entity_type}."
    )
    tags = [
        "mcp-memory",
        "mcp-entity",
        f"entity-type-{_slug_base(entity.entity_type)}",
    ]
    resource = "memory://knowledge-graph/entities/" + quote(entity.name, safe="")
    frontmatter = [
        "---",
        f"type: {_yaml_scalar('MCP ' + entity.entity_type)}",
        f"title: {_yaml_scalar(entity.name)}",
        f"description: {_yaml_scalar(_markdown_line(description)[:200])}",
        f"resource: {_yaml_scalar(resource)}",
        f"tags: {_yaml_scalar(tags)}",
        "x_memanto:",
        f"  type: {_yaml_scalar(_memanto_type(entity.entity_type))}",
        '  source: "mcp-memory-server"',
        "  confidence: 1.0",
        "mcp_memory:",
        "  schema_version: 1",
        f"  original_line: {entity.line}",
        f"  entity_name: {_yaml_scalar(entity.name)}",
        f"  entity_type: {_yaml_scalar(entity.entity_type)}",
        f"  observation_count: {len(entity.observations)}",
        f"  outgoing_relation_count: {len(outgoing)}",
        f"  incoming_relation_count: {len(incoming)}",
        "---",
        "",
    ]
    body = [
        f"# {entity.name}",
        "",
        "## Entity",
        "",
        f"- **Type:** `{entity.entity_type}`",
        f"- **Source line:** {entity.line}",
        "",
        "## Observations",
        "",
    ]
    if entity.observations:
        body.extend(
            f"{index}. {_markdown_line(observation)}"
            for index, observation in enumerate(entity.observations, start=1)
        )
    else:
        body.append("_No observations were stored for this entity._")

    body.extend(["", "## Relationships", "", "### Outgoing", ""])
    if outgoing:
        for relation in outgoing:
            target_path = f"{slugs[relation.target]}.md"
            body.append(
                f"- `{relation.relation_type}` → [{relation.target}]({target_path})"
            )
    else:
        body.append("_None._")

    body.extend(["", "### Incoming", ""])
    if incoming:
        for relation in incoming:
            source_path = f"{slugs[relation.source]}.md"
            body.append(
                f"- [{relation.source}]({source_path}) → `{relation.relation_type}`"
            )
    else:
        body.append("_None._")

    payload = json.dumps(
        _source_payload(entity, outgoing, source_bytes=source_bytes),
        ensure_ascii=False,
        indent=2,
    )
    fence = _source_fence(payload)
    body.extend(
        [
            "",
            "## Lossless MCP source",
            "",
            "The block below preserves the exact entity record and all of its "
            "outgoing relation records for reconstruction.",
            "",
            f"{fence}json mcp-memory-source",
            payload,
            fence,
            "",
        ]
    )
    return "\n".join(frontmatter + body)


def _root_index(graph: KnowledgeGraph) -> str:
    return "\n".join(
        [
            "---",
            "type: index",
            'title: "MCP Memory Server migration bundle"',
            "---",
            "",
            "# MCP Memory Server → OKF",
            "",
            "This bundle was generated from the official MCP Memory Server JSONL "
            "knowledge graph.",
            "",
            "- [Importable memories](memories/index.md)",
            "- [Migration report](metrics/migration-report.json)",
            "- [Savings report](metrics/savings-report.json)",
            "- [Mapping table](metrics/mapping-table.md)",
            "- [Original source](source/memory.jsonl)",
            "",
            f"Source SHA-256: `{graph.source_sha256}`",
            "",
        ]
    )


def _memory_index(entities: tuple[EntityRecord, ...], slugs: dict[str, str]) -> str:
    lines = [
        "---",
        "type: index",
        'title: "MCP Memory entities"',
        "---",
        "",
        "# Entities",
        "",
    ]
    lines.extend(
        f"- [{entity.name}](entities/{slugs[entity.name]}.md) — `{entity.entity_type}`"
        for entity in entities
    )
    lines.append("")
    return "\n".join(lines)


def _mapping_table() -> str:
    return """# MCP Memory Server → Memanto OKF mapping

| MCP Memory concept | OKF representation | Memanto import behavior |
| --- | --- | --- |
| Entity name | `title` and H1 | Becomes the memory title |
| Entity type | Free-form OKF `type`, exact `mcp_memory.entity_type`, and `x_memanto.type` | Deterministically maps known semantic types; unknown types become `observation` without losing the source type |
| Observations | Numbered `## Observations` section | Imported as searchable memory content |
| Outgoing relation | Typed Markdown link in `## Relationships` | Link and relation label remain searchable |
| Incoming relation | Backlink in `## Relationships` | Graph neighborhood remains human-browsable |
| Exact source record | `json mcp-memory-source` fenced block | Survives import/export as memory content |
| Exact source file bytes | One base64 + SHA-256 manifest in the first entity block | Preserves whitespace, line endings, UTF-8 BOM, blank lines, and final-newline state |
| Source URI | `memory://knowledge-graph/entities/<name>` | Becomes `source_ref` |
| Provenance | `mcp-memory` tags and namespaced frontmatter | Preserved in tags/supporting data |

The original JSONL is also copied into `source/memory.jsonl`.  Import is scoped
to `memories/`, so the source and metrics directories are not re-ingested.
"""


def _prepare_output(path: Path, force: bool) -> None:
    resolved = path.resolve()
    if resolved == Path(resolved.anchor):
        raise MigrationError("refusing to use a filesystem root as output")
    if path.exists():
        if not force:
            raise MigrationError(
                f"output already exists: {path} (pass --force to replace it)"
            )
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    path.mkdir(parents=True)


def _savings_report(graph: KnowledgeGraph, memories_dir: Path) -> dict[str, Any]:
    source_bytes = len(graph.source_bytes)
    importable_okf_bytes = sum(
        path.stat().st_size
        for path in sorted(memories_dir.rglob("*"))
        if path.is_file()
    )
    delta_bytes = importable_okf_bytes - source_bytes
    delta_percent = round((delta_bytes / source_bytes) * 100, 2)
    return {
        "schema_version": 1,
        "applicability": "not_applicable",
        "reason": (
            "The MCP Memory Server is a local JSONL store with no provider "
            "billing, token, or latency baseline, and Memanto's direct OKF "
            "import path does not emit a provider savings report. No synthetic "
            "savings are claimed."
        ),
        "claims": {
            "cost_savings": None,
            "token_savings": None,
            "latency_savings": None,
        },
        "measured_storage": {
            "source_jsonl_bytes": source_bytes,
            "importable_okf_bytes": importable_okf_bytes,
            "delta_bytes": delta_bytes,
            "delta_percent": delta_percent,
            "interpretation": (
                "The OKF representation is larger because it adds readable "
                "Markdown structure, typed links, backlinks, metadata, and "
                "lossless reconstruction blocks. This is portability overhead, "
                "not a storage-savings claim."
            ),
        },
    }


def write_okf_bundle(
    graph: KnowledgeGraph, output: str | Path, *, force: bool = False
) -> dict[str, Any]:
    output_path = Path(output)
    _prepare_output(output_path, force)

    entities_dir = output_path / "memories" / "entities"
    metrics_dir = output_path / "metrics"
    source_dir = output_path / "source"
    entities_dir.mkdir(parents=True)
    metrics_dir.mkdir()
    source_dir.mkdir()

    slugs = build_entity_slugs(graph.entities)
    for index, entity in enumerate(graph.entities):
        outgoing = [
            relation for relation in graph.relations if relation.source == entity.name
        ]
        incoming = [
            relation for relation in graph.relations if relation.target == entity.name
        ]
        document = _entity_document(
            entity,
            outgoing,
            incoming,
            slugs,
            source_bytes=graph.source_bytes if index == 0 else None,
        )
        (entities_dir / f"{slugs[entity.name]}.md").write_text(
            document, encoding="utf-8"
        )

    (output_path / "index.md").write_text(_root_index(graph), encoding="utf-8")
    (output_path / "memories" / "index.md").write_text(
        _memory_index(graph.entities, slugs), encoding="utf-8"
    )
    (metrics_dir / "mapping-table.md").write_text(_mapping_table(), encoding="utf-8")
    (source_dir / "memory.jsonl").write_bytes(graph.source_bytes)

    entity_types = Counter(entity.entity_type for entity in graph.entities)
    memanto_types = Counter(
        _memanto_type(entity.entity_type) for entity in graph.entities
    )
    relation_types = Counter(relation.relation_type for relation in graph.relations)
    report: dict[str, Any] = {
        "schema_version": 1,
        "source_format": "official-mcp-memory-server-jsonl",
        "source_sha256": graph.source_sha256,
        "source_records": len(graph.entities) + len(graph.relations),
        "source_entities": len(graph.entities),
        "source_relations": len(graph.relations),
        "mapped_okf_memories": len(graph.entities),
        "entity_type_breakdown": dict(sorted(entity_types.items())),
        "memanto_type_breakdown": dict(sorted(memanto_types.items())),
        "relation_type_breakdown": dict(sorted(relation_types.items())),
        "lossless_source_copy": "source/memory.jsonl",
        "import_path": "memories",
    }
    (metrics_dir / "migration-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    savings_report = _savings_report(graph, output_path / "memories")
    (metrics_dir / "savings-report.json").write_text(
        json.dumps(savings_report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def migrate(
    source: str | Path, output: str | Path, *, force: bool = False
) -> dict[str, Any]:
    return write_okf_bundle(load_mcp_graph(source), output, force=force)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert MCP Memory Server JSONL to an OKF bundle."
    )
    parser.add_argument("--input", required=True, help="Path to memory.jsonl")
    parser.add_argument("--output", required=True, help="Output OKF directory")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace the exact output path if it already exists",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = migrate(args.input, args.output, force=args.force)
    except MigrationError as exc:
        print(f"error: {exc}")
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
