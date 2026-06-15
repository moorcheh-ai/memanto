"""
Compare a Mem0 account export against Memanto.

Two layers:
  1. Deterministic metrics computed locally from the export JSON (trustworthy,
     reproducible). These drive every number in the report.
  2. A narrative written by Memanto's own LLM (Moorcheh ``answer`` endpoint),
     grounded strictly in the computed metrics.

Benchmark percentages are intentionally NOT used — only defensible
architectural differences and numbers derived from the user's real data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from memanto.cli.analyze.ingestion_cost import (
    DEFAULT_INPUT_USD_PER_1M,
    DEFAULT_OUTPUT_USD_PER_1M,
    DEFAULT_SOURCE_MULTIPLIER,
    estimate_ingestion_cost,
)

ASSUMPTIONS: dict[str, Any] = {
    "chars_per_token": 4,
    "vector_bytes_float32": 4096,
    "vector_bytes_memanto": 128,
    "compression_ratio": 32,
    # Observed Mem0 read latency envelope (~470–527 ms); single midpoint used.
    "mem0_read_ms": 499,
    "memanto_read_ms": 90,
    "extraction_usd_per_1m_input_tokens": DEFAULT_INPUT_USD_PER_1M,
    "extraction_usd_per_1m_output_tokens": DEFAULT_OUTPUT_USD_PER_1M,
    # Mem0 export has no raw source text; scale stored memory text to estimate
    # ingest/content input (original chats/docs are larger than distilled facts).
    "extraction_source_multiplier": DEFAULT_SOURCE_MULTIPLIER,
}


def _human_bytes(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024.0:
            return f"{num:.2f} {unit}"
        num /= 1024.0
    return f"{num:.2f} PB"


def _memory_text(memory: dict[str, Any]) -> str:
    return (
        memory.get("memory")
        or memory.get("content")
        or memory.get("text")
        or memory.get("title")
        or ""
    )


def _entity_type_counts(entities: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entity in entities:
        entity_type = str(entity.get("type") or "unknown").lower()
        counts[entity_type] = counts.get(entity_type, 0) + 1
    return counts


def compute_metrics(export: dict[str, Any]) -> dict[str, Any]:
    """Compute deterministic comparison metrics from a Mem0 export."""
    summary = export.get("summary", {}) or {}
    entities = export.get("entities", []) or []
    memories = export.get("memories", []) or []

    entity_count = int(summary.get("entity_count") or len(entities))
    scope_count = int(summary.get("scope_count") or 0)
    memory_count = int(summary.get("memory_count") or len(memories))
    entity_types = _entity_type_counts(entities)

    total_chars = sum(len(_memory_text(memory)) for memory in memories)

    cpt = ASSUMPTIONS["chars_per_token"]
    content_tokens = total_chars // cpt if cpt else 0

    # Output: stored memory text ≈ AI extraction model output (best proxy).
    output_tokens = content_tokens
    multiplier = float(ASSUMPTIONS["extraction_source_multiplier"])
    # Input: estimated source content ingested (embedding / ingest pipeline).
    input_tokens = int(content_tokens * multiplier)
    ingestion = estimate_ingestion_cost(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        assumptions=ASSUMPTIONS,
    )

    vector_count = memory_count
    storage_mem0_bytes = vector_count * ASSUMPTIONS["vector_bytes_float32"]
    storage_memanto_bytes = vector_count * ASSUMPTIONS["vector_bytes_memanto"]
    storage_saved_bytes = storage_mem0_bytes - storage_memanto_bytes

    read_ms_mem0 = ASSUMPTIONS["mem0_read_ms"]
    read_ms_memanto = ASSUMPTIONS["memanto_read_ms"]
    latency_speedup = round(read_ms_mem0 / read_ms_memanto, 1) if read_ms_memanto else 0

    return {
        "volume": {
            "entities": entity_count,
            "scopes": scope_count,
            "memories": memory_count,
            "entity_types": entity_types,
            "total_content_chars": total_chars,
            "estimated_content_tokens": content_tokens,
            "estimated_input_tokens": input_tokens,
            "estimated_output_tokens": output_tokens,
            "vector_count": vector_count,
        },
        "ingestion_tax": {
            "mem0_input_tokens": ingestion["input_tokens"],
            "mem0_output_tokens": ingestion["output_tokens"],
            "mem0_total_tokens": ingestion["total_extraction_tokens"],
            "mem0_input_cost_usd": ingestion["input_cost_usd"],
            "mem0_output_cost_usd": ingestion["output_cost_usd"],
            "mem0_extraction_cost_usd": ingestion["total_cost_usd"],
            "memanto_extraction_tokens": 0,
            "memanto_extraction_cost_usd": 0.0,
            "tokens_saved": ingestion["tokens_saved"],
        },
        "storage": {
            "mem0_bytes": storage_mem0_bytes,
            "memanto_bytes": storage_memanto_bytes,
            "bytes_saved": storage_saved_bytes,
            "mem0_human": _human_bytes(storage_mem0_bytes),
            "memanto_human": _human_bytes(storage_memanto_bytes),
            "saved_human": _human_bytes(storage_saved_bytes),
            "compression_ratio": ASSUMPTIONS["compression_ratio"],
        },
        "latency": {
            "mem0_read_ms": read_ms_mem0,
            "memanto_read_ms": read_ms_memanto,
            "speedup_x": latency_speedup,
            "ms_saved_per_query": read_ms_mem0 - read_ms_memanto,
        },
    }


def build_llm_prompt(metrics: dict[str, Any]) -> str:
    """Self-contained instruction + data for the Moorcheh answer endpoint."""
    v = metrics["volume"]
    t = metrics["ingestion_tax"]
    s = metrics["storage"]
    lat = metrics["latency"]
    type_lines = ", ".join(
        f"{name}: {count}" for name, count in sorted(v["entity_types"].items())
    )

    return (
        "You are a senior infrastructure analyst writing a migration brief that "
        "compares a user's existing Mem0 deployment against Memanto "
        "(powered by the Moorcheh engine). Use ONLY the measured data below. "
        "Do NOT invent benchmark scores or numbers that are not provided.\n\n"
        "=== MEASURED MEM0 FOOTPRINT ===\n"
        f"- Entities: {v['entities']}\n"
        f"- Entity types: {type_lines or 'n/a'}\n"
        f"- Export scopes: {v['scopes']}\n"
        f"- Memories: {v['memories']}\n"
        f"- Estimated content tokens: {v['estimated_content_tokens']:,}\n\n"
        "=== PROJECTED MEMANTO IMPACT (if you migrate) ===\n"
        f"1. Ingestion tax — Today Mem0 ingest is modeled as "
        f"~{t['mem0_input_tokens']:,} ingest/content input tokens "
        f"(@ ${ASSUMPTIONS['extraction_usd_per_1m_input_tokens']}/1M; estimated "
        f"× {ASSUMPTIONS['extraction_source_multiplier']} from stored text) + "
        f"{t['mem0_output_tokens']:,} AI extraction output tokens "
        f"(@ ${ASSUMPTIONS['extraction_usd_per_1m_output_tokens']}/1M) ≈ "
        f"${t['mem0_extraction_cost_usd']} total. With Memanto, typed "
        f"primitives could bypass that step → 0 tokens, $0.\n"
        f"2. Latency — Mem0 is ~{lat['mem0_read_ms']}ms read with indexing "
        f"before new memories are searchable. Memanto could deliver "
        f"<{lat['memanto_read_ms']}ms read and 0ms write (instantly searchable) — "
        f"about {lat['speedup_x']}x faster per query.\n"
        f"3. Storage — Mem0 currently stores Float32 vectors "
        f"({s['mem0_human']} across {v['vector_count']} vectors). Memanto "
        f"could use {s['compression_ratio']}x binary compression ({s['memanto_human']}), "
        f"freeing {s['saved_human']}, on serverless infra that scales to zero when "
        f"idle.\n"
        "4. Retrieval model — Mem0 uses probabilistic Approximate Nearest "
        "Neighbor (ANN) search; Memanto would use deterministic exact-match recall "
        "(bitwise Hamming distance on CPU), which can reduce vector-induced "
        "mis-retrieval.\n\n"
        "VOICE & TENSE (required):\n"
        "- Present tense for what the user HAS in Mem0 today (measured facts).\n"
        "- Future or conditional tense for Memanto benefits (can save, would save, "
        "could improve, if you migrate). Do NOT write as if they already use Memanto.\n\n"
        "Write a concise, professional markdown brief with these sections:\n"
        "## Executive summary (2-3 sentences)\n"
        "## What you could save by migrating (bullet token, storage, latency wins "
        "using the numbers above)\n"
        "## What could improve in your memory layer (precision, instant writes, typed "
        "primitives, serverless cost)\n"
        "## Migration considerations (honest trade-offs and next steps)\n"
        "Keep it grounded and specific to the numbers. Do not add benchmark "
        "percentages."
    )


def build_report_markdown(
    *,
    metrics: dict[str, Any],
    narrative: str,
    export_path: str,
    llm_model: str,
    llm_method: str,
    exported_at: str | None,
) -> str:
    v = metrics["volume"]
    t = metrics["ingestion_tax"]
    s = metrics["storage"]
    lat = metrics["latency"]
    generated = datetime.now(timezone.utc).isoformat()
    type_lines = ", ".join(
        f"{name}: {count}" for name, count in sorted(v["entity_types"].items())
    )

    lines: list[str] = []
    lines.append("# Memanto vs. Mem0 — Memory Analysis Report")
    lines.append("")
    lines.append(f"_Generated: {generated}_")
    if exported_at:
        lines.append(f"_Mem0 export: {exported_at}_")
    lines.append("")
    lines.append("## Your Mem0 footprint (measured)")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| Entities | {v['entities']:,} |")
    lines.append(f"| Entity types | {type_lines or 'n/a'} |")
    lines.append(f"| Export scopes | {v['scopes']:,} |")
    lines.append(f"| Memories | {v['memories']:,} |")
    lines.append(f"| Estimated content tokens | {v['estimated_content_tokens']:,} |")
    lines.append(
        f"| Est. ingest/content input tokens | {v['estimated_input_tokens']:,} |"
    )
    lines.append(
        f"| Est. AI extraction output tokens | {v['estimated_output_tokens']:,} |"
    )
    lines.append("")
    lines.append("## Projected impact of migrating to Memanto")
    lines.append("")
    lines.append("### 1. Ingestion tax (token savings)")
    lines.append("")
    lines.append("| | Mem0 | Memanto |")
    lines.append("| --- | --- | --- |")
    lines.append(
        f"| Ingest/content input tokens (estimated) | {t['mem0_input_tokens']:,} | 0 |"
    )
    lines.append(f"| AI extraction output tokens | {t['mem0_output_tokens']:,} | 0 |")
    lines.append(
        f"| Input cost (@ ${ASSUMPTIONS['extraction_usd_per_1m_input_tokens']}/1M) | "
        f"${t['mem0_input_cost_usd']} | $0.00 |"
    )
    lines.append(
        f"| Output cost (@ ${ASSUMPTIONS['extraction_usd_per_1m_output_tokens']}/1M) | "
        f"${t['mem0_output_cost_usd']} | $0.00 |"
    )
    lines.append(
        f"| **Total extraction cost** | "
        f"**${t['mem0_extraction_cost_usd']}** | **$0.00** |"
    )
    lines.append("")
    lines.append(
        f"**You could save ~{t['tokens_saved']:,} extraction tokens** "
        f"(input + output) at ingest if you migrate — Memanto's typed primitives "
        "would skip the extraction LLM entirely."
    )
    lines.append("")
    lines.append("### 2. Latency & indexing")
    lines.append("")
    lines.append("| | Mem0 | Memanto |")
    lines.append("| --- | --- | --- |")
    lines.append(
        f"| Read latency | ~{lat['mem0_read_ms']}ms | <{lat['memanto_read_ms']}ms |"
    )
    lines.append("| Write availability | indexing delay | 0ms (instant) |")
    lines.append("")
    lines.append(
        f"**Reads could be ~{lat['speedup_x']}x faster** (~{lat['ms_saved_per_query']}ms "
        "saved per query), and new memories would be searchable the moment they are "
        "written."
    )
    lines.append("")
    lines.append("### 3. Storage footprint")
    lines.append("")
    lines.append("| | Mem0 | Memanto |")
    lines.append("| --- | --- | --- |")
    lines.append(f"| Vector storage | {s['mem0_human']} | {s['memanto_human']} |")
    lines.append("")
    lines.append(
        f"**Storage could be ~{s['compression_ratio']}x smaller** — you would free "
        f"{s['saved_human']} and could run on serverless infrastructure that scales "
        "to zero when idle."
    )
    lines.append("")
    lines.append("## Analysis")
    lines.append("")
    lines.append(narrative.strip() if narrative else "_(LLM narrative unavailable.)_")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Method & assumptions")
    lines.append("")
    lines.append(f"- **LLM:** {llm_model}")
    lines.append(f"- **How compared:** {llm_method}")
    lines.append(f"- **Source export:** `{export_path}`")
    lines.append(
        "- **Metrics:** computed locally from the export; benchmark percentages "
        "deliberately excluded."
    )
    lines.append("- **Assumptions used:**")
    for key, value in ASSUMPTIONS.items():
        lines.append(f"  - `{key}` = {value}")
    lines.append("")
    return "\n".join(lines)
