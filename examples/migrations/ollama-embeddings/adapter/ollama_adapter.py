"""
Ollama Embeddings Migration Adapter for Memanto.

This module connects to an Ollama instance, discovers available embedding models,
exports conversation/context data, and transforms it into a provider-style export
JSON consumable by `memanto migrate --file` and into Open Knowledge Format (OKF)
bundles for portable, vendor-neutral memory ownership.

Architecture:
    Ollama API (localhost:11434)
        │
        ├── Model discovery  ──  /api/tags  ──  available embedding models
        ├── Context export   ──  /api/chat  ──  extracted memories as JSON
        └── Embedding verif  ──  /api/embeddings  ──  compatibility check
                │
        ┌───────┴────────┐
        ▼                ▼
    Export JSON      OKF Bundle
    (memanto         (portable
     migrate         markdown
     --file)         knowledge)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_OLLAMA_BASE = "http://localhost:11434"
REQUEST_TIMEOUT_S = 30.0
DEFAULT_EMBEDDING_DIM = 768

# Memanto memory types that the adapter can map to
MEMANTO_MEMORY_TYPES = {
    "fact",
    "preference",
    "goal",
    "commitment",
    "relationship",
    "event",
    "decision",
    "observation",
    "artifact",
}

# OKF field names that are known/standard
OKF_KNOWN_FIELDS = {
    "type", "title", "description", "resource", "tags", "timestamp", "x_memanto"
}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _make_client(base_url: str = DEFAULT_OLLAMA_BASE, timeout: float = REQUEST_TIMEOUT_S) -> httpx.Client:
    """Create an httpx client pointing at the Ollama REST API."""
    return httpx.Client(
        base_url=base_url.rstrip("/"),
        timeout=timeout,
        headers={"Content-Type": "application/json"},
    )


def _title_from(content: str, max_chars: int = 80) -> str:
    """Derive a title from content when none is provided."""
    text = content.strip().replace("\n", " ")
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 3].rstrip() + "..."


# ---------------------------------------------------------------------------
# Model Discovery
# ---------------------------------------------------------------------------

def discover_models(base_url: str = DEFAULT_OLLAMA_BASE) -> dict[str, Any]:
    """Discover all available Ollama models and their embedding capabilities.

    Returns:
        Dict with keys:
        - ``all_models``: list of all installed model dicts (from /api/tags)
        - ``embedding_models``: subset that can generate embeddings
        - ``chat_models``: models suitable for chat/completion
        - ``count``: total model count
    """
    with _make_client(base_url) as client:
        resp = client.get("/api/tags")
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Ollama /api/tags failed ({resp.status_code}): {resp.text[:500]}"
            )
        data = resp.json() if resp.content else {}

    all_models = data.get("models", []) if isinstance(data, dict) else []
    embedding_models = []

    for model in all_models:
        name = model.get("name", "")
        details = model.get("details", {})
        family = (details.get("family") or "").lower()

        # Models commonly used for embeddings: nomic, bge, e5, snowflake,
        # mxbai, all-minilm, or any model with "embed" in the name.
        is_embed = (
            "embed" in name.lower()
            or "nomic" in name.lower()
            or "bge" in name.lower()
            or "e5" in name.lower()
            or "snowflake" in name.lower()
            or "mxbai" in name.lower()
            or "all-minilm" in name.lower()
            or family in {"bert", "nomic-bert"}
        )
        if is_embed:
            embedding_models.append(model)

    chat_models = [m for m in all_models if m not in embedding_models]

    return {
        "all_models": all_models,
        "embedding_models": embedding_models,
        "chat_models": chat_models,
        "count": len(all_models),
    }


# ---------------------------------------------------------------------------
# Embedding Verification
# ---------------------------------------------------------------------------

def verify_embedding_compatibility(
    model: str,
    base_url: str = DEFAULT_OLLAMA_BASE,
    dimensions: int | None = None,
) -> dict[str, Any]:
    """Verify that an Ollama model produces properly-dimensioned embeddings.

    Sends a test prompt to ``/api/embeddings`` and reports the vector length,
    so you can confirm compatibility before running a full migration.

    Args:
        model: Ollama model name (e.g. ``nomic-embed-text``).
        base_url: Ollama API base URL.
        dimensions: Expected vector dimensions (auto-detected if None).

    Returns:
        Dict with ``model``, ``dimensions``, ``compatible``, ``took_ms``,
        ``raw_length``, and any ``error``.
    """
    result: dict[str, Any] = {
        "model": model,
        "dimensions": dimensions,
        "compatible": False,
        "took_ms": 0,
        "raw_length": 0,
    }

    with _make_client(base_url) as client:
        try:
            payload = {
                "model": model,
                "prompt": "Memanto memory migration compatibility test.",
            }
            resp = client.post("/api/embeddings", json=payload)
            if resp.status_code >= 400:
                result["error"] = f"HTTP {resp.status_code}: {resp.text[:300]}"
                return result

            data = resp.json() if resp.content else {}
            embedding = data.get("embedding", [])
            result["raw_length"] = len(embedding)

            if dimensions is None:
                result["dimensions"] = len(embedding)
            if result["dimensions"] and result["dimensions"] > 0:
                result["compatible"] = (
                    result["raw_length"] == result["dimensions"]
                    if dimensions is not None
                    else True
                )

        except Exception as exc:
            result["error"] = str(exc)

    return result


# ---------------------------------------------------------------------------
# Context / Memory Export from Ollama
# ---------------------------------------------------------------------------

def export_ollama_memories(
    model: str,
    contexts: list[str],
    base_url: str = DEFAULT_OLLAMA_BASE,
    agent_id: str = "ollama-agent",
    chat_model: str | None = None,
) -> dict[str, Any]:
    """Extract structured memories from Ollama chat context.

    Feeds each context string through an Ollama chat model with a system prompt
    that instructs it to output a JSON array of extracted memory records. Each
    record includes title, content, type, tags, and confidence.

    Args:
        model: Embedding model name (for the export metadata).
        contexts: List of context strings to process.
        base_url: Ollama API base URL.
        agent_id: Identifier for the exporting agent.
        chat_model: LLM to use for extraction (defaults to ``model``).

    Returns:
        A provider-style export dict compatible with ``memanto migrate --file``.
    """
    chat_model = chat_model or model
    memories: list[dict[str, Any]] = []
    migrated_at = _now_utc()

    system_prompt = (
        "You are a memory extraction system. Given a conversation or context "
        "string, extract all factual memories, preferences, decisions, and "
        "observations as a JSON array. Each memory must have: "
        'type (one of: fact, preference, decision, observation, event, goal, '
        'commitment, relationship), '
        "title (short summary), "
        "content (full detail), "
        "tags (list of strings), "
        "confidence (0.0-1.0). "
        "Return ONLY valid JSON array, no preamble or explanation."
    )

    with _make_client(base_url) as client:
        for idx, context in enumerate(contexts):
            try:
                resp = client.post(
                    "/api/chat",
                    json={
                        "model": chat_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": context},
                        ],
                        "format": "json",
                    },
                )
                if resp.status_code >= 400:
                    memories.append(
                        {
                            "title": f"Raw context #{idx + 1}",
                            "content": context,
                            "type": "artifact",
                            "tags": ["ollama-raw", f"batch-{idx}"],
                            "confidence": 0.5,
                            "source": "ollama-raw",
                            "source_ref": f"ollama-raw-{idx}",
                            "export_scope": {"agent_id": agent_id},
                        }
                    )
                    continue

                data = resp.json()
                message = data.get("message", {})
                raw_output = message.get("content", "")

                # Try parsing structured JSON; fall back to raw context
                try:
                    extracted = json.loads(raw_output)
                    if isinstance(extracted, list):
                        for mem in extracted:
                            if isinstance(mem, dict) and mem.get("content"):
                                mem.setdefault("source", "ollama")
                                mem.setdefault("source_ref", f"ollama-{idx}-{len(memories)}")
                                mem.setdefault("export_scope", {"agent_id": agent_id})
                                memories.append(mem)
                    elif isinstance(extracted, dict):
                        extracted.setdefault("source", "ollama")
                        extracted.setdefault("source_ref", f"ollama-{idx}")
                        extracted.setdefault("export_scope", {"agent_id": agent_id})
                        if extracted.get("content"):
                            memories.append(extracted)
                except (json.JSONDecodeError, TypeError):
                    # Fall back: treat the raw output as artifact content
                    if raw_output.strip():
                        memories.append(
                            {
                                "title": _title_from(raw_output),
                                "content": raw_output.strip(),
                                "type": "artifact",
                                "tags": ["ollama-extracted", f"batch-{idx}"],
                                "confidence": 0.7,
                                "source": "ollama",
                                "source_ref": f"ollama-extract-{idx}",
                                "export_scope": {"agent_id": agent_id},
                            }
                        )
                    elif context.strip():
                        memories.append(
                            {
                                "title": _title_from(context),
                                "content": context.strip(),
                                "type": "artifact",
                                "tags": ["ollama-raw", f"batch-{idx}"],
                                "confidence": 0.5,
                                "source": "ollama-raw",
                                "source_ref": f"ollama-raw-{idx}",
                                "export_scope": {"agent_id": agent_id},
                            }
                        )

            except Exception as exc:
                # On failure, preserve the raw context
                if context.strip():
                    memories.append(
                        {
                            "title": _title_from(context),
                            "content": context.strip(),
                            "type": "artifact",
                            "tags": ["ollama-fallback"],
                            "confidence": 0.3,
                            "source": "ollama-fallback",
                            "source_ref": f"ollama-fallback-{idx}",
                            "export_scope": {"agent_id": agent_id},
                            "extraction_error": str(exc),
                        }
                    )

    return {
        "exported_at": migrated_at.isoformat(),
        "provider": "ollama",
        "model": model,
        "embedding_model": model,
        "chat_model": chat_model,
        "api_base": base_url,
        "summary": {
            "model_count": 1,
            "memory_count": len(memories),
            "context_count": len(contexts),
        },
        "memories": memories,
        "notes": {
            "extraction": (
                "Memories extracted from Ollama conversations via the chat API. "
                "Embedding compatibility verified via /api/embeddings."
            ),
            "compatibility": (
                "This export is consumable by `memanto migrate --file <this.json>` "
                "using the 'ollama' provider mapper."
            ),
        },
    }


# ---------------------------------------------------------------------------
# Mapper: Ollama export -> Memanto memory payloads
# ---------------------------------------------------------------------------

def map_ollama(export: dict[str, Any]) -> list[dict[str, Any]]:
    """Map an Ollama export to Memanto memory payloads.

    Follows the same contract as ``mappers.map_mem0`` / ``map_letta`` etc.
    — each returned dict is accepted by ``SdkClient.batch_remember``.

    Falls back to raw context preservation when structured extraction fails.
    """
    rows: list[dict[str, Any]] = []
    migrated_at = _now_utc()

    for mem in export.get("memories", []) or []:
        if not isinstance(mem, dict):
            continue
        content = (mem.get("content") or mem.get("text") or "").strip()
        if not content:
            continue

        memory_type = mem.get("type", "").strip().lower() or None
        if memory_type and memory_type not in MEMANTO_MEMORY_TYPES:
            memory_type = None  # Let Memanto auto-classify

        tags = [str(t) for t in (mem.get("tags") or []) if t]

        confidence = mem.get("confidence")
        if confidence is None or not isinstance(confidence, (int, float)):
            confidence = 0.8
        confidence = float(confidence)
        confidence = min(1.0, max(0.0, confidence))

        created_at = mem.get("created_at") or mem.get("timestamp")
        if isinstance(created_at, str):
            try:
                if created_at.endswith("Z"):
                    created_at = created_at[:-1] + "+00:00"
                created_at = datetime.fromisoformat(created_at)
            except (ValueError, TypeError):
                created_at = None

        title = (mem.get("title") or "").strip() or _title_from(content)

        rows.append(
            {
                "title": title,
                "content": content,
                "type": memory_type,
                "tags": tags,
                "confidence": confidence,
                "source": "ollama",
                "source_ref": (
                    str(mem.get("source_ref"))
                    if mem.get("source_ref")
                    else None
                ),
                "provenance": "imported",
                "created_at": created_at,
                "updated_at": migrated_at,
            }
        )

    return rows


# ---------------------------------------------------------------------------
# OKF Bundle Builder
# ---------------------------------------------------------------------------

def build_okf_bundle(
    export: dict[str, Any],
    output_dir: Path,
    *,
    split: str = "auto",
    threshold: int = 50,
) -> dict[str, Any]:
    """Build an OKF (Open Knowledge Format) bundle from an Ollama export.

    Produces a directory of markdown files with YAML frontmatter conforming to
    the OKF spec. The bundle is human-readable, git-friendly, and importable
    via ``memanto migrate okf ./bundle``.

    Args:
        export: An export dict from ``export_ollama_memories``.
        output_dir: Where to write the bundle.
        split: Bundle layout strategy:
               ``"file"`` — one .md file per memory
               ``"type"`` — one .md file per memory type (stacked)
               ``"auto"`` — file per memory for small types, stacked for large
        threshold: Max number of files per type before switching to stacked
                   (only relevant for ``split="auto"``).

    Returns:
        Dict with ``output_path``, ``total_memories``, ``per_type_counts``, ``sections``.
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    memories_dir = output_dir / "memories"
    memories_dir.mkdir(parents=True, exist_ok=True)

    # Group memories by type
    by_type: dict[str, list[dict[str, Any]]] = {}
    for mem in export.get("memories", []) or []:
        mtype = mem.get("type") or "unclassified"
        by_type.setdefault(mtype, []).append(mem)

    total = 0
    per_type_counts: dict[str, int] = {}

    # Write an index
    index_path = output_dir / "index.md"
    _write_okf_index(index_path, export, by_type)

    mem_index_lines = ["# Memories", ""]
    for mtype in sorted(by_type):
        count = len(by_type[mtype])
        per_type_counts[mtype] = count
        mem_index_lines.append(f"- [{mtype.capitalize()} ({count})]({mtype}/index.md)")
    mem_index_lines.append("")
    (memories_dir / "index.md").write_text("\n".join(mem_index_lines), encoding="utf-8")

    for mtype, mems in sorted(by_type.items()):
        type_dir = memories_dir / mtype
        type_dir.mkdir(parents=True, exist_ok=True)

        use_stacked = False
        if split == "type":
            use_stacked = True
        elif split == "auto" and len(mems) > threshold:
            use_stacked = True

        if use_stacked:
            _write_stacked_okf(type_dir / f"{mtype}.md", mtype, mems)
        else:
            _write_file_per_okf(type_dir, mtype, mems)

        # Type-level index
        type_index = type_dir / "index.md"
        type_index_lines = [f"# {mtype.capitalize()}", "", f"**Count:** {len(mems)}", ""]
        if use_stacked:
            type_index_lines.append(f"- [{mtype.capitalize()} memories]({mtype}.md)")
        else:
            for mem in mems:
                title = (mem.get("title") or "untitled").strip()
                slug = _slugify(title)
                type_index_lines.append(f"- [{title}]({slug}.md)")
        type_index_lines.append("")
        type_index.write_text("\n".join(type_index_lines), encoding="utf-8")

        total += len(mems)

    # Metrics section
    metrics_dir = output_dir / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    _write_okf_metrics(metrics_dir / "overview.md", export, per_type_counts)

    return {
        "output_path": str(output_dir),
        "total_memories": total,
        "per_type_counts": per_type_counts,
        "sections": ["memories", "metrics"],
    }


def _slugify(text: str) -> str:
    """Create a filesystem-safe slug from text."""
    import re

    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")[:100]


def _write_okf_index(
    path: Path, export: dict[str, Any], by_type: dict[str, list[dict[str, Any]]]
) -> None:
    """Write the top-level OKF bundle index."""
    lines = [
        "---",
        "type: index",
        f'title: "Ollama Memory Export - {export.get("exported_at", "unknown")}"',
        f"description: \"OKF bundle exported from Ollama using model '{export.get('model', 'unknown')}'\"",
        f"tags: [ollama, migration, memanto]",
        f"timestamp: {export.get('exported_at', _now_utc().isoformat())}",
        "---",
        "",
        "# Ollama Memory Export",
        "",
        f"**Embedding Model:** {export.get('model', 'unknown')}",
        f"**Chat Model:** {export.get('chat_model', 'unknown')}",
        f"**Export Time:** {export.get('exported_at', 'unknown')}",
        f"**Total Memories:** {export.get('summary', {}).get('memory_count', 0)}",
        "",
        "## Memory Types",
        "",
    ]
    for mtype, mems in sorted(by_type.items()):
        lines.append(f"- **{mtype.capitalize()}:** {len(mems)} memories")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_stacked_okf(
    path: Path, mtype: str, mems: list[dict[str, Any]]
) -> None:
    """Write multiple memories into a single stacked OKF .md file."""
    # Use the OKF entry delimiter from Memanto's export service
    ENTRY_DELIMITER = "\n\n<!-- okf-entry -->\n\n"

    chunks: list[str] = []
    for mem in mems:
        chunk = _mem_to_okf_markdown(mem, mtype)
        chunks.append(chunk)

    path.write_text(ENTRY_DELIMITER.join(chunks), encoding="utf-8")


def _write_file_per_okf(
    type_dir: Path, mtype: str, mems: list[dict[str, Any]]
) -> None:
    """Write one .md file per memory."""
    for mem in mems:
        title = (mem.get("title") or "untitled").strip()
        slug = _slugify(title)
        content = _mem_to_okf_markdown(mem, mtype)
        (type_dir / f"{slug}.md").write_text(content, encoding="utf-8")


def _mem_to_okf_markdown(mem: dict[str, Any], mtype: str) -> str:
    """Convert a single memory dict into OKF markdown with YAML frontmatter."""
    import yaml

    title = (mem.get("title") or "Untitled Memory").strip()
    content = (mem.get("content") or "").strip()
    tags = [str(t) for t in (mem.get("tags") or []) if t]
    confidence = mem.get("confidence", 0.8)

    frontmatter: dict[str, Any] = {
        "type": mtype,
        "title": title,
        "description": content[:200] if len(content) > 200 else content,
        "tags": tags,
        "timestamp": mem.get("created_at") or _now_utc().isoformat(),
        "x_memanto": {
            "type": mtype,
            "confidence": confidence,
            "source": "ollama",
            "source_ref": mem.get("source_ref"),
        },
    }

    # Preserve extra fields in frontmatter
    for key, value in mem.items():
        if (
            key
            not in {
                "title", "content", "tags", "confidence", "type",
                "created_at", "source_ref", "export_scope", "source",
            }
            and value is not None
        ):
            frontmatter[key] = value

    yaml_block = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True).strip()
    return f"---\n{yaml_block}\n---\n\n{content}\n"


def _write_okf_metrics(
    path: Path,
    export: dict[str, Any],
    per_type_counts: dict[str, int],
) -> None:
    """Write an OKF metrics overview file."""
    summary = export.get("summary", {})
    total = sum(per_type_counts.values())

    lines = [
        "---",
        "type: metrics",
        'title: "Migration Metrics"',
        f"description: \"Aggregate metrics for the Ollama → Memanto migration\"",
        f"timestamp: {export.get('exported_at', _now_utc().isoformat())}",
        "---",
        "",
        "# Migration Metrics",
        "",
        "## Summary",
        "",
        f"- **Source:** Ollama ({export.get('model', 'unknown')})",
        f"- **Total Memories Exported:** {total}",
        f"- **Context Strings Processed:** {summary.get('context_count', 0)}",
        f"- **Embedding Model:** {export.get('embedding_model', 'unknown')}",
        f"- **Chat Model:** {export.get('chat_model', 'unknown')}",
        "",
        "## Per-Type Breakdown",
        "",
    ]
    for mtype, count in sorted(per_type_counts.items()):
        pct = (count / total * 100) if total > 0 else 0
        lines.append(f"- **{mtype.capitalize()}:** {count} ({pct:.1f}%)")

    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Convenience: full migration pipeline
# ---------------------------------------------------------------------------

def run_full_migration(
    model: str,
    contexts: list[str],
    output_dir: Path,
    *,
    base_url: str = DEFAULT_OLLAMA_BASE,
    chat_model: str | None = None,
    agent_id: str = "ollama-agent",
    verify_embedding: bool = True,
) -> dict[str, Any]:
    """Run the complete migration pipeline: discover → verify → export → build OKF.

    Args:
        model: Ollama embedding model name.
        contexts: List of context strings to process.
        output_dir: Directory for output files.
        base_url: Ollama API base URL.
        chat_model: LLM for memory extraction (defaults to model).
        agent_id: Identifier for the exporting agent.
        verify_embedding: Run embedding compatibility check first.

    Returns:
        Dict with ``export``, ``okf_bundle``, ``model_info``, ``embedding_verify``, and
        ``export_path`` pointing at the JSON file ready for ``memanto migrate --file``.
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    result: dict[str, Any] = {}

    # 1. Discover models
    result["model_info"] = discover_models(base_url)

    # 2. Verify embedding compatibility
    if verify_embedding:
        result["embedding_verify"] = verify_embedding_compatibility(model, base_url)

    # 3. Export
    export = export_ollama_memories(
        model=model,
        contexts=contexts,
        base_url=base_url,
        agent_id=agent_id,
        chat_model=chat_model,
    )
    result["export"] = export

    # Write export JSON
    export_path = output_dir / "ollama_export.json"
    export_path.write_text(
        json.dumps(export, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    result["export_path"] = str(export_path)

    # 4. Build OKF bundle
    okf_dir = output_dir / "okf_bundle"
    okf_result = build_okf_bundle(export, okf_dir)
    result["okf_bundle"] = okf_result

    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    """CLI entry point for the Ollama migration adapter."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Ollama Embeddings → Memanto Migration Adapter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_migration.py --model nomic-embed-text --context "User likes dark mode"
  python run_migration.py --model all-minilm --context-file contexts.txt
  python run_migration.py --dry-run  # discover models + verify only
        """,
    )
    parser.add_argument(
        "--model",
        default="nomic-embed-text",
        help="Ollama embedding model name (default: nomic-embed-text)",
    )
    parser.add_argument(
        "--chat-model",
        default=None,
        help="Ollama chat model for extraction (default: same as --model)",
    )
    parser.add_argument(
        "--context",
        action="append",
        default=[],
        help="Context string to extract memories from (repeatable)",
    )
    parser.add_argument(
        "--context-file",
        default=None,
        help="File with context strings (one per line)",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_OLLAMA_BASE,
        help=f"Ollama API base URL (default: {DEFAULT_OLLAMA_BASE})",
    )
    parser.add_argument(
        "--output-dir",
        default="./ollama_migration_output",
        help="Output directory (default: ./ollama_migration_output)",
    )
    parser.add_argument(
        "--agent-id",
        default="ollama-agent",
        help="Export agent identifier",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover models and verify embeddings only (no export)",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip embedding compatibility check",
    )
    parser.add_argument(
        "--split",
        default="auto",
        choices=["auto", "file", "type"],
        help="OKF bundle layout strategy (default: auto)",
    )

    args = parser.parse_args()

    if args.dry_run:
        print("=== Ollama Model Discovery ===")
        model_info = discover_models(args.base_url)
        print(f"  Total models: {model_info['count']}")
        print(f"  Embedding models: {len(model_info['embedding_models'])}")
        for m in model_info["embedding_models"]:
            print(f"    - {m.get('name', '?')}")
        print(f"  Chat models: {len(model_info['chat_models'])}")
        for m in model_info["chat_models"][:5]:
            print(f"    - {m.get('name', '?')}")

        print(f"\n=== Embedding Verification for '{args.model}' ===")
        verify = verify_embedding_compatibility(args.model, args.base_url)
        if verify.get("error"):
            print(f"  ERROR: {verify['error']}")
        else:
            print(f"  Dimensions: {verify['dimensions']}")
            print(f"  Compatible: {verify['compatible']}")
            print(f"  Raw Length: {verify['raw_length']}")
        return

    contexts = list(args.context)
    if args.context_file:
        contexts.extend(
            Path(args.context_file).read_text(encoding="utf-8").strip().split("\n")
        )
    contexts = [c.strip() for c in contexts if c.strip()]

    if not contexts:
        print(
            "No contexts provided. Use --context or --context-file to supply "
            "conversation/memory text to extract from."
        )
        print("Running in demo mode with sample contexts...")
        contexts = [
            "User prefers dark mode on all applications. Uses Python for data science.",
            "The team decided to use PostgreSQL for the production database. "
            "Redis is used for caching.",
            "Project Alpha deadline is August 15th. The client requested weekly "
            "progress reports.",
        ]

    output_dir = Path(args.output_dir)
    result = run_full_migration(
        model=args.model,
        contexts=contexts,
        output_dir=output_dir,
        base_url=args.base_url,
        chat_model=args.chat_model,
        agent_id=args.agent_id,
        verify_embedding=not args.skip_verify,
    )

    print(f"\n=== Migration Complete ===")
    print(f"  Export JSON:  {result['export_path']}")
    print(f"  OKF Bundle:   {result['okf_bundle']['output_path']}")
    print(f"  Memories:     {result['okf_bundle']['total_memories']}")
    print(f"  Per Type:     {result['okf_bundle']['per_type_counts']}")
    print(f"\n  To import into Memanto:")
    print(f"    memanto migrate --file {result['export_path']}")
    print(f"  Or from OKF bundle:")
    print(f"    memanto migrate okf {result['okf_bundle']['output_path']}")
    print()


if __name__ == "__main__":
    main()
