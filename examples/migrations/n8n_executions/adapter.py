"""Convert selected n8n execution outputs into a deterministic OKF bundle.

The adapter consumes the response from n8n's ``GET /api/v1/executions`` API
with ``includeData=true``, a JSON array of full execution objects, a single
execution object, or a directory containing any combination of those shapes.

Only fields explicitly listed in the mapping file are copied. This allow-list
is intentional: n8n execution data often includes credentials, personal data,
and intermediate payloads that should not become long-lived agent memory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from memanto.app.constants import VALID_MEMORY_TYPES
from memanto.app.services.okf_export_service import OkfExportService
from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle

_TEMPLATE_FIELD_RE = re.compile(r"\{([^{}]+)\}")
_INDEX_TIMESTAMP_RE = re.compile(r"(?m)^timestamp: .+$")
_METRICS_GENERATED_RE = re.compile(r"(?m)^\*Visualizations auto-generated at .+\*$")
_MISSING = object()
_OWNERSHIP_MARKER = ".n8n-executions-okf.json"
_OWNERSHIP_VALUE = {"generator": "n8n-executions-okf", "version": 1}


class MappingError(ValueError):
    """Raised when an n8n export or mapping is structurally invalid."""


def _sha256_bytes(value: bytes) -> str:
    """Return a lowercase SHA-256 digest."""
    return hashlib.sha256(value).hexdigest()


def _canonical_json(value: Any) -> str:
    """Serialize a value deterministically for hashes and inline payloads."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _read_json(path: Path) -> Any:
    """Load JSON and report the source path on malformed input."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MappingError(f"Invalid JSON in {path}: {exc}") from exc


def load_mapping(path: str | Path) -> dict[str, Any]:
    """Load and validate a version-1 YAML mapping."""
    mapping_path = Path(path)
    try:
        raw = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise MappingError(f"Invalid YAML in {mapping_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise MappingError("Mapping must be a YAML object")
    if raw.get("version") != 1:
        raise MappingError("Mapping version must be 1")

    mappings = raw.get("mappings")
    if not isinstance(mappings, list) or not mappings:
        raise MappingError("Mapping must contain a non-empty 'mappings' list")

    for index, item in enumerate(mappings):
        label = f"mappings[{index}]"
        if not isinstance(item, dict):
            raise MappingError(f"{label} must be an object")
        for required in ("node", "memory_type", "title", "fields"):
            if not item.get(required):
                raise MappingError(f"{label}.{required} is required")
        if item["memory_type"] not in VALID_MEMORY_TYPES:
            raise MappingError(
                f"{label}.memory_type must be one of "
                f"{', '.join(sorted(VALID_MEMORY_TYPES))}"
            )
        if not isinstance(item["fields"], list):
            raise MappingError(f"{label}.fields must be a list")
        for field_index, field in enumerate(item["fields"]):
            if (
                not isinstance(field, dict)
                or not field.get("label")
                or not field.get("path")
            ):
                raise MappingError(
                    f"{label}.fields[{field_index}] requires label and path"
                )
    return raw


def _normalise_payload(payload: Any, source: str) -> list[dict[str, Any]]:
    """Normalise supported n8n export shapes to execution objects."""
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        # The public API envelope has a top-level ``data`` list. A full
        # execution has a ``data`` object containing ``resultData``.
        if isinstance(payload.get("data"), list):
            records = payload["data"]
        elif any(key in payload for key in ("id", "workflowId", "resultData")):
            records = [payload]
        else:
            raise MappingError(
                f"{source} is neither an n8n execution nor an API response"
            )
    else:
        raise MappingError(f"{source} must contain a JSON object or array")

    executions: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise MappingError(f"{source} execution {index} is not an object")
        executions.append(record)
    return executions


def load_executions(
    path: str | Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load executions plus deterministic hashes of every source file."""
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"n8n export not found: {source}")

    files = (
        sorted(source.glob("*.json"), key=lambda item: item.name.casefold())
        if source.is_dir()
        else [source]
    )
    if not files:
        raise MappingError(f"No JSON files found in {source}")

    executions: list[dict[str, Any]] = []
    hashes: list[dict[str, Any]] = []
    for file_path in files:
        raw = file_path.read_bytes()
        payload = _read_json(file_path)
        executions.extend(_normalise_payload(payload, str(file_path)))
        hashes.append(
            {
                "file": file_path.name,
                "sha256": _sha256_bytes(raw),
                "size_bytes": len(raw),
            }
        )

    # Stable order even if n8n returns newest-first or files are rearranged.
    executions.sort(
        key=lambda item: (
            str(item.get("startedAt") or item.get("stoppedAt") or ""),
            str(item.get("id") or ""),
        )
    )
    return executions, hashes


def _get_path(value: Any, path: str, default: Any = _MISSING) -> Any:
    """Resolve a conservative dotted path through dictionaries and lists."""
    current = value
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        if isinstance(current, list) and part.isdigit():
            index = int(part)
            if index < len(current):
                current = current[index]
                continue
        if default is not _MISSING:
            return default
        raise MappingError(f"Required path '{path}' is missing")
    return current


def _render_template(template: str, item: dict[str, Any]) -> str:
    """Expand conservative dotted-path placeholders from one node item."""

    def replace(match: re.Match[str]) -> str:
        """Render one template match without evaluating arbitrary expressions."""
        path = match.group(1).strip()
        value = _get_path(item, path)
        if isinstance(value, (dict, list)):
            return _canonical_json(value)
        return str(value)

    return _TEMPLATE_FIELD_RE.sub(replace, template)


def _as_markdown(value: Any) -> str:
    """Render an allow-listed scalar or structured value on one Markdown line."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (dict, list)):
        return f"`{_canonical_json(value)}`"
    return str(value).replace("\n", " ")


def _iter_node_items(
    execution: dict[str, Any], node_name: str
) -> Iterable[tuple[int, int, int, dict[str, Any]]]:
    """Yield source coordinates and JSON items for a named n8n node."""
    data = execution.get("data")
    if not isinstance(data, dict):
        return
    result_data = data.get("resultData")
    if not isinstance(result_data, dict):
        return
    run_data = result_data.get("runData")
    if not isinstance(run_data, dict):
        return
    runs = run_data.get(node_name)
    if not isinstance(runs, list):
        return

    for run_index, run in enumerate(runs):
        if not isinstance(run, dict):
            continue
        run_outputs = _get_path(run, "data.main", default=[])
        if not isinstance(run_outputs, list):
            continue
        for output_index, output in enumerate(run_outputs):
            if not isinstance(output, list):
                continue
            for item_index, wrapped in enumerate(output):
                item = wrapped.get("json") if isinstance(wrapped, dict) else None
                if isinstance(item, dict):
                    yield run_index, output_index, item_index, item


def _workflow_identity(execution: dict[str, Any]) -> tuple[str, str]:
    """Resolve a stable workflow ID plus its human-readable name."""
    workflow_data = execution.get("workflowData")
    workflow_data = workflow_data if isinstance(workflow_data, dict) else {}
    workflow_id = str(
        execution.get("workflowId") or workflow_data.get("id") or "unknown-workflow"
    )
    workflow_name = str(workflow_data.get("name") or workflow_id)
    return workflow_id, workflow_name


def _stable_memory_id(
    workflow_id: str,
    execution_id: str,
    node_name: str,
    run_index: int,
    output_index: int,
    item_index: int,
) -> str:
    """Derive a deterministic memory ID from the complete n8n coordinate."""
    coordinate = "\x1f".join(
        (
            workflow_id,
            execution_id,
            node_name,
            str(run_index),
            str(output_index),
            str(item_index),
        )
    )
    return f"n8n-{_sha256_bytes(coordinate.encode('utf-8'))[:24]}"


def _resource_url(
    base_url: str | None, workflow_id: str, execution_id: str
) -> str | None:
    """Build a human-navigable execution URL when a base URL is configured."""
    if not base_url:
        return None
    return f"{base_url.rstrip('/')}/workflow/{workflow_id}/executions/{execution_id}"


def _confidence(config: dict[str, Any], item: dict[str, Any]) -> float:
    """Resolve and clamp provenance confidence to Memanto's accepted range."""
    if config.get("confidence_path"):
        raw = _get_path(item, str(config["confidence_path"]))
        scale = float(config.get("confidence_scale", 1))
        if not scale:
            raise MappingError("confidence_scale cannot be zero")
        value = float(raw) / scale
    else:
        value = float(config.get("confidence", 0.8))
    return max(0.0, min(value, 1.0))


def _build_content(
    mapping: dict[str, Any],
    item: dict[str, Any],
    *,
    workflow_id: str,
    workflow_name: str,
    execution_id: str,
    execution_status: str,
    node_name: str,
    run_index: int,
    output_index: int,
    item_index: int,
) -> str:
    """Build readable allow-listed Markdown with complete n8n provenance."""
    heading = str(mapping.get("content_heading") or mapping["memory_type"]).title()
    lines = [f"# {heading}", ""]
    for field in mapping["fields"]:
        value = _get_path(item, str(field["path"]), default=_MISSING)
        if value is _MISSING:
            if field.get("required", True):
                raise MappingError(
                    f"Required field '{field['path']}' is missing in "
                    f"execution {execution_id}, node {node_name}"
                )
            continue
        lines.append(f"- **{field['label']}**: {_as_markdown(value)}")

    lines.extend(
        [
            "",
            "## n8n provenance",
            "",
            f"- **Workflow**: {workflow_name} (`{workflow_id}`)",
            f"- **Execution**: `{execution_id}`",
            f"- **Node**: {node_name}",
            f"- **Position**: run {run_index}, output {output_index}, item {item_index}",
            f"- **Execution status**: {execution_status}",
        ]
    )
    return "\n".join(lines).strip()


def build_memories(
    executions: list[dict[str, Any]], mapping: dict[str, Any]
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Map selected outputs to Memanto memory dictionaries."""
    source_config = mapping.get("source")
    source_config = source_config if isinstance(source_config, dict) else {}
    base_url = source_config.get("execution_base_url")

    memories_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skipped: Counter[str] = Counter()
    source_rows: list[dict[str, Any]] = []

    for execution in executions:
        execution_id = str(execution.get("id") or "")
        if not execution_id:
            skipped["execution_missing_id"] += 1
            continue
        workflow_id, workflow_name = _workflow_identity(execution)
        expected_workflow = source_config.get("workflow_name")
        if expected_workflow and workflow_name != expected_workflow:
            skipped["workflow_filtered"] += 1
            continue
        timestamp = execution.get("stoppedAt") or execution.get("startedAt")
        status = str(execution.get("status") or "unknown")

        for node_mapping in mapping["mappings"]:
            node_name = str(node_mapping["node"])
            node_items = list(_iter_node_items(execution, node_name))
            if not node_items:
                skipped[f"node_without_items:{node_name}"] += 1
                continue

            for run_index, output_index, item_index, item in node_items:
                try:
                    title = _render_template(str(node_mapping["title"]), item)
                    tags = [
                        _render_template(str(tag), item)
                        for tag in (node_mapping.get("tags") or [])
                    ]
                    content = _build_content(
                        node_mapping,
                        item,
                        workflow_id=workflow_id,
                        workflow_name=workflow_name,
                        execution_id=execution_id,
                        execution_status=status,
                        node_name=node_name,
                        run_index=run_index,
                        output_index=output_index,
                        item_index=item_index,
                    )
                    confidence = _confidence(node_mapping, item)
                except (MappingError, TypeError, ValueError) as exc:
                    raise MappingError(
                        f"Could not map execution {execution_id}, node {node_name}, "
                        f"run {run_index}, output {output_index}, item {item_index}: "
                        f"{exc}"
                    ) from exc

                memory_id = _stable_memory_id(
                    workflow_id,
                    execution_id,
                    node_name,
                    run_index,
                    output_index,
                    item_index,
                )
                memory_type = str(node_mapping["memory_type"])
                source_ref = _resource_url(base_url, workflow_id, execution_id)
                memory = {
                    "id": memory_id,
                    "title": title,
                    "content": content,
                    "tags": list(dict.fromkeys(tags)),
                    "confidence": confidence,
                    "provenance": "n8n_execution",
                    # Memanto constrains source to the actor class
                    # (user/agent/tool/system). n8n is the originating tool;
                    # its identity remains in provenance, tags, the resource
                    # URL, and the readable body.
                    "source": "tool",
                    "status": "active",
                    "created_at": timestamp,
                    "source_ref": source_ref,
                }
                memories_by_type[memory_type].append(memory)
                source_rows.append(
                    {
                        "memory_id": memory_id,
                        "memory_type": memory_type,
                        "workflow_id": workflow_id,
                        "execution_id": execution_id,
                        "node": node_name,
                        "run": run_index,
                        "output": output_index,
                        "item": item_index,
                    }
                )

    for memories in memories_by_type.values():
        memories.sort(key=lambda row: (str(row.get("created_at") or ""), row["id"]))
    source_rows.sort(key=lambda row: row["memory_id"])
    memory_fingerprints = sorted(
        (
            {
                "memory_id": memory["id"],
                "sha256": _memory_fingerprint_from_source(memory_type, memory),
            }
            for memory_type, memories in memories_by_type.items()
            for memory in memories
        ),
        key=lambda row: row["memory_id"],
    )
    return dict(memories_by_type), {
        "skipped": dict(sorted(skipped.items())),
        "source_rows": source_rows,
        "memory_fingerprints": memory_fingerprints,
    }


def _generated_at(executions: list[dict[str, Any]]) -> str:
    """Use the latest source timestamp instead of a wall-clock timestamp."""
    timestamps = [
        str(execution.get("stoppedAt") or execution.get("startedAt"))
        for execution in executions
        if execution.get("stoppedAt") or execution.get("startedAt")
    ]
    return max(timestamps, default="1970-01-01T00:00:00Z")


def _normalise_bundle_timestamps(bundle: Path, timestamp: str) -> None:
    """Replace wall-clock display timestamps so repeated runs are byte-stable."""
    for index_path in sorted(bundle.rglob("index.md")):
        original = index_path.read_text(encoding="utf-8")
        updated = _INDEX_TIMESTAMP_RE.sub(f"timestamp: {timestamp}", original)
        index_path.write_bytes(updated.replace("\r\n", "\n").encode("utf-8"))

    overview_path = bundle / "metrics" / "overview.md"
    if overview_path.exists():
        original = overview_path.read_text(encoding="utf-8")
        updated = _METRICS_GENERATED_RE.sub(
            f"*Visualizations generated from source snapshot {timestamp}*",
            original,
        )
        overview_path.write_bytes(updated.replace("\r\n", "\n").encode("utf-8"))


def _normalise_bundle_newlines(bundle: Path) -> None:
    """Normalize generated text artifacts to deterministic UTF-8/LF files."""
    for path in sorted(bundle.rglob("*")):
        if path.is_file() and path.suffix in {".md", ".json"}:
            text = path.read_text(encoding="utf-8")
            normalized = text.replace("\r\n", "\n").replace("\r", "\n")
            if path.suffix == ".md":
                normalized = "\n".join(
                    line.rstrip() for line in normalized.splitlines()
                )
                normalized = normalized.rstrip("\n") + "\n"
            path.write_bytes(normalized.encode("utf-8"))


def _bundle_hashes(bundle: Path) -> list[dict[str, str]]:
    """Hash every committed bundle artifact except self-referential reports."""
    rows: list[dict[str, str]] = []
    for path in sorted(bundle.rglob("*")):
        if path.is_file() and path.name not in {
            "migration-manifest.json",
            "round-trip-report.json",
        }:
            rows.append(
                {
                    "file": path.relative_to(bundle).as_posix(),
                    "sha256": _sha256_bytes(path.read_bytes()),
                }
            )
    return rows


def _memory_fingerprint_payload(
    *,
    memory_id: str,
    memory_type: str,
    title: str,
    content: str,
    tags: list[Any],
    confidence: Any,
    provenance: Any,
    source: Any,
    status: Any,
    created_at: Any,
    source_ref: Any,
) -> dict[str, Any]:
    """Build the exact privacy-preserving semantic payload used for fidelity."""
    return {
        "id": memory_id,
        "type": memory_type,
        "title": title,
        "content": content,
        "tags": tags,
        "confidence": confidence,
        "provenance": provenance,
        "source": source,
        "status": status,
        "created_at": created_at,
        "source_ref": source_ref,
    }


def _memory_fingerprint_from_source(memory_type: str, memory: dict[str, Any]) -> str:
    """Hash every selected semantic field before OKF serialization."""
    payload = _memory_fingerprint_payload(
        memory_id=str(memory["id"]),
        memory_type=memory_type,
        title=str(memory["title"]),
        content=str(memory["content"]),
        tags=list(memory.get("tags") or []),
        confidence=memory.get("confidence"),
        provenance=memory.get("provenance"),
        source=memory.get("source"),
        status=memory.get("status"),
        created_at=memory.get("created_at"),
        source_ref=memory.get("source_ref"),
    )
    return _sha256_bytes(_canonical_json(payload).encode("utf-8"))


def _memory_fingerprint_from_loaded(memory: dict[str, Any]) -> dict[str, str]:
    """Hash the same semantic fields after loading the OKF document."""
    x_memanto = memory.get("x_memanto")
    x_memanto = x_memanto if isinstance(x_memanto, dict) else {}
    memory_id = str(x_memanto.get("id") or "")
    payload = _memory_fingerprint_payload(
        memory_id=memory_id,
        memory_type=str(memory.get("type") or x_memanto.get("type") or ""),
        title=str(memory.get("title") or ""),
        content=str(memory.get("body") or ""),
        tags=list(memory.get("tags") or []),
        confidence=x_memanto.get("confidence"),
        provenance=x_memanto.get("provenance"),
        source=x_memanto.get("source"),
        status=x_memanto.get("status"),
        created_at=memory.get("timestamp"),
        source_ref=memory.get("resource"),
    )
    return {
        "memory_id": memory_id,
        "sha256": _sha256_bytes(_canonical_json(payload).encode("utf-8")),
    }


def _storage_report(
    source_hashes: list[dict[str, Any]], bundle: Path
) -> dict[str, Any]:
    """Measure source JSON bytes against readable OKF Markdown bytes."""
    markdown_files = sorted(bundle.rglob("*.md"))
    source_bytes = sum(int(row["size_bytes"]) for row in source_hashes)
    okf_bytes = sum(path.stat().st_size for path in markdown_files)
    delta_bytes = okf_bytes - source_bytes
    delta_percent = (
        round((delta_bytes / source_bytes) * 100, 2) if source_bytes else None
    )
    return {
        "version": 1,
        "basis": "measured-file-bytes",
        "source": {
            "format": "n8n public API JSON",
            "files": len(source_hashes),
            "bytes": source_bytes,
        },
        "portable_okf_markdown": {
            "files": len(markdown_files),
            "bytes": okf_bytes,
        },
        "delta_bytes": delta_bytes,
        "delta_percent": delta_percent,
        "interpretation": (
            "portability overhead" if delta_bytes >= 0 else "storage reduction"
        ),
        "provider_cost_savings": None,
        "token_savings": None,
        "latency_savings": None,
        "notes": (
            "n8n execution history has no provider billing/token/latency baseline; "
            "unavailable values are null rather than invented."
        ),
    }


def validate_round_trip(bundle: str | Path) -> dict[str, Any]:
    """Validate that OKF can be loaded and mapped back into Memanto rows."""
    root = Path(bundle)
    manifest_path = root / "migration-manifest.json"
    expected_manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists()
        else {}
    )
    expected_rows = expected_manifest.get("source_rows") or []

    loaded = load_okf_bundle(root)
    mapped = map_okf(loaded)
    loaded_ids = {
        str(entry.get("x_memanto", {}).get("id"))
        for entry in loaded["memories"]
        if isinstance(entry.get("x_memanto"), dict)
    }
    expected_ids = {str(row["memory_id"]) for row in expected_rows}
    expected_fingerprints = expected_manifest.get("memory_fingerprints") or []
    actual_fingerprints = sorted(
        (_memory_fingerprint_from_loaded(entry) for entry in loaded["memories"]),
        key=lambda row: row["memory_id"],
    )
    semantic_fingerprints_preserved = actual_fingerprints == expected_fingerprints

    issues: list[str] = []
    if len(loaded["memories"]) != len(expected_rows):
        issues.append(
            f"OKF count {len(loaded['memories'])} != source count {len(expected_rows)}"
        )
    if loaded_ids != expected_ids:
        issues.append("Stable memory IDs changed during OKF load")
    if len(mapped) != len(loaded["memories"]):
        issues.append("Some OKF entries could not map back to Memanto rows")
    if any(not row.get("content") or not row.get("title") for row in mapped):
        issues.append("A round-tripped memory lost its title or content")
    if not semantic_fingerprints_preserved:
        issues.append("A selected semantic field changed during the OKF round trip")

    return {
        "valid": not issues,
        "source_count": len(expected_rows),
        "okf_count": len(loaded["memories"]),
        "memanto_count": len(mapped),
        "stable_ids_preserved": loaded_ids == expected_ids,
        "semantic_fingerprints_preserved": semantic_fingerprints_preserved,
        "issues": issues,
    }


def _write_json(path: Path, value: Any) -> None:
    """Write deterministic UTF-8 JSON without platform newline translation."""
    path.write_bytes(
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
    )


def _atomic_publish(staged_bundle: Path, output: Path, stage_root: Path) -> None:
    """Replace a validated generated bundle with rollback on swap failure."""
    previous = stage_root / "previous-output"
    moved_previous = False
    try:
        if output.exists():
            os.replace(output, previous)
            moved_previous = True
        os.replace(staged_bundle, output)
    except Exception:
        if moved_previous and previous.exists() and not output.exists():
            os.replace(previous, output)
        raise
    finally:
        if stage_root.exists():
            shutil.rmtree(stage_root)


def _assert_replaceable_output(output: Path) -> None:
    """Refuse to replace a directory not owned by this adapter."""
    if not output.exists():
        return
    if not output.is_dir():
        raise MappingError(f"Output exists and is not a directory: {output}")
    marker_path = output / _OWNERSHIP_MARKER
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise MappingError(
            f"Refusing to replace unowned output directory: {output}"
        ) from exc
    if marker != _OWNERSHIP_VALUE:
        raise MappingError(f"Refusing to replace unowned output directory: {output}")


def convert_n8n_executions(
    input_path: str | Path,
    mapping_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    """Convert an n8n export to OKF and atomically replace ``output_path``."""
    executions, source_hashes = load_executions(input_path)
    mapping = load_mapping(mapping_path)
    memories_by_type, stats = build_memories(executions, mapping)
    if not any(memories_by_type.values()):
        skipped = (
            ", ".join(f"{key}={value}" for key, value in stats["skipped"].items())
            or "none"
        )
        raise MappingError(
            f"No memories were produced by the configured mappings; skipped={skipped}"
        )

    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    _assert_replaceable_output(output)
    stage_root = Path(
        tempfile.mkdtemp(prefix=f".{output.name}-", dir=str(output.parent))
    )
    staged_bundle = stage_root / "bundle"
    generated_at = _generated_at(executions)

    try:
        service = OkfExportService(exports_dir=stage_root / "exports")
        result = service.write_okf_bundle(
            "n8n-executions",
            memories_by_type,
            output_dir=staged_bundle,
            split="file",
        )
        _normalise_bundle_timestamps(staged_bundle, generated_at)
        _normalise_bundle_newlines(staged_bundle)
        _write_json(staged_bundle / _OWNERSHIP_MARKER, _OWNERSHIP_VALUE)

        mapping_bytes = Path(mapping_path).read_bytes()
        manifest = {
            "format": "okf",
            "migration": "n8n-executions",
            "mapping_version": mapping["version"],
            "mapping_sha256": _sha256_bytes(mapping_bytes),
            "generated_at": generated_at,
            "source_execution_count": len(executions),
            "source_files": source_hashes,
            "memory_count": result["total_memories"],
            "memory_counts_by_type": result["per_type_counts"],
            "skipped": stats["skipped"],
            "source_rows": stats["source_rows"],
            "memory_fingerprints": stats["memory_fingerprints"],
        }
        _write_json(staged_bundle / "migration-manifest.json", manifest)

        report = validate_round_trip(staged_bundle)
        _write_json(staged_bundle / "round-trip-report.json", report)
        if not report["valid"]:
            raise MappingError(
                "Round-trip validation failed: " + "; ".join(report["issues"])
            )

        (staged_bundle / "metrics").mkdir(parents=True, exist_ok=True)
        _write_json(
            staged_bundle / "metrics" / "savings-report.json",
            _storage_report(source_hashes, staged_bundle),
        )
        manifest["bundle_files"] = _bundle_hashes(staged_bundle)
        _write_json(staged_bundle / "migration-manifest.json", manifest)
        _atomic_publish(staged_bundle, output, stage_root)
    except Exception:
        if stage_root.exists():
            shutil.rmtree(stage_root)
        raise

    return {
        "output_path": str(output),
        "memory_count": sum(len(rows) for rows in memories_by_type.values()),
        "memory_counts_by_type": {
            key: len(rows) for key, rows in memories_by_type.items()
        },
        "round_trip": validate_round_trip(output),
    }


def _parser() -> argparse.ArgumentParser:
    """Build the adapter command-line parser."""
    parser = argparse.ArgumentParser(
        description="Convert selected n8n execution outputs to an OKF bundle."
    )
    parser.add_argument("input", help="n8n execution JSON file or directory")
    parser.add_argument(
        "--mapping",
        default=str(Path(__file__).with_name("mapping.yaml")),
        help="version-1 YAML mapping (default: mapping.yaml beside this script)",
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).with_name("sample-okf")),
        help="destination OKF bundle",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate an existing --output bundle without converting",
    )
    return parser


def main() -> int:
    """Run conversion or validation and return a process exit code."""
    args = _parser().parse_args()
    result = (
        validate_round_trip(args.output)
        if args.validate_only
        else convert_n8n_executions(args.input, args.mapping, args.output)
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("valid", result.get("round_trip", {}).get("valid")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
