"""
Compare a Letta archival memory export against Memanto.

Two layers:
  1. Deterministic metrics computed locally from the export JSON.
  2. A narrative written by Memanto's own LLM (Moorcheh ``answer`` endpoint),
     grounded strictly in the computed metrics.
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
    # Letta archival recall uses embedding search over passages.
    "letta_read_ms": 450,
    "memanto_read_ms": 90,
    "extraction_usd_per_1m_input_tokens": DEFAULT_INPUT_USD_PER_1M,
    "extraction_usd_per_1m_output_tokens": DEFAULT_OUTPUT_USD_PER_1M,
    # Export lacks raw source conversations; scale stored passage text.
    "extraction_source_multiplier": DEFAULT_SOURCE_MULTIPLIER,
}


def _human_bytes(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024.0:
            return f"{num:.2f} {unit}"
        num /= 1024.0
    return f"{num:.2f} PB"


def _passage_text(passage: dict[str, Any]) -> str:
    return (
        passage.get("text")
        or passage.get("content")
        or passage.get("memory")
        or passage.get("title")
        or ""
    )


def _agent_count(export: dict[str, Any], summary: dict[str, Any]) -> int:
    if summary.get("agent_count") is not None:
        return int(summary["agent_count"])
    agents = export.get("agents", []) or []
    if agents:
        return len(agents)
    if export.get("agent_id"):
        return 1
    return 0


def compute_metrics(export: dict[str, Any]) -> dict[str, Any]:
    """Compute deterministic comparison metrics from a Letta export."""
    summary = export.get("summary", {}) or {}
    passages = export.get("passages", []) or []

    agent_count = _agent_count(export, summary)
    passage_count = int(summary.get("passage_count") or len(passages))

    total_chars = sum(len(_passage_text(passage)) for passage in passages)

    cpt = ASSUMPTIONS["chars_per_token"]
    content_tokens = total_chars // cpt if cpt else 0
    output_tokens = content_tokens
    multiplier = float(ASSUMPTIONS["extraction_source_multiplier"])
    input_tokens = int(content_tokens * multiplier)
    ingestion = estimate_ingestion_cost(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        assumptions=ASSUMPTIONS,
    )

    vector_count = passage_count
    storage_letta_bytes = vector_count * ASSUMPTIONS["vector_bytes_float32"]
    storage_memanto_bytes = vector_count * ASSUMPTIONS["vector_bytes_memanto"]
    storage_saved_bytes = storage_letta_bytes - storage_memanto_bytes

    read_ms_letta = ASSUMPTIONS["letta_read_ms"]
    read_ms_memanto = ASSUMPTIONS["memanto_read_ms"]
    latency_speedup = (
        round(read_ms_letta / read_ms_memanto, 1) if read_ms_memanto else 0
    )

    return {
        "volume": {
            "agents": agent_count,
            "passages": passage_count,
            "total_content_chars": total_chars,
            "estimated_content_tokens": content_tokens,
            "estimated_input_tokens": input_tokens,
            "estimated_output_tokens": output_tokens,
            "vector_count": vector_count,
        },
        "ingestion_tax": {
            "letta_input_tokens": ingestion["input_tokens"],
            "letta_output_tokens": ingestion["output_tokens"],
            "letta_total_tokens": ingestion["total_extraction_tokens"],
            "letta_input_cost_usd": ingestion["input_cost_usd"],
            "letta_output_cost_usd": ingestion["output_cost_usd"],
            "letta_extraction_cost_usd": ingestion["total_cost_usd"],
            "memanto_extraction_tokens": 0,
            "memanto_extraction_cost_usd": 0.0,
            "tokens_saved": ingestion["tokens_saved"],
        },
        "storage": {
            "letta_bytes": storage_letta_bytes,
            "memanto_bytes": storage_memanto_bytes,
            "bytes_saved": storage_saved_bytes,
            "letta_human": _human_bytes(storage_letta_bytes),
            "memanto_human": _human_bytes(storage_memanto_bytes),
            "saved_human": _human_bytes(storage_saved_bytes),
            "compression_ratio": ASSUMPTIONS["compression_ratio"],
        },
        "latency": {
            "letta_read_ms": read_ms_letta,
            "memanto_read_ms": read_ms_memanto,
            "speedup_x": latency_speedup,
            "ms_saved_per_query": read_ms_letta - read_ms_memanto,
        },
    }


def build_llm_prompt(metrics: dict[str, Any]) -> str:
    """Self-contained instruction + data for the Moorcheh answer endpoint."""
    v = metrics["volume"]
    t = metrics["ingestion_tax"]
    s = metrics["storage"]
    lat = metrics["latency"]

    return (
        "You are a senior infrastructure analyst writing a migration brief that "
        "compares a user's existing Letta deployment against Memanto "
        "(powered by the Moorcheh engine). Use ONLY the measured data below. "
        "Do NOT invent benchmark scores or numbers that are not provided.\n\n"
        "=== MEASURED LETTA FOOTPRINT ===\n"
        f"- Agents: {v['agents']}\n"
        f"- Archival passages: {v['passages']}\n"
        f"- Estimated content tokens: {v['estimated_content_tokens']:,}\n\n"
        "=== PROJECTED MEMANTO IMPACT (if you migrate) ===\n"
        f"1. Ingestion tax — Today Letta ingest is modeled as "
        f"~{t['letta_input_tokens']:,} ingest/content input tokens "
        f"(@ ${ASSUMPTIONS['extraction_usd_per_1m_input_tokens']}/1M; estimated "
        f"× {ASSUMPTIONS['extraction_source_multiplier']} from stored text) + "
        f"{t['letta_output_tokens']:,} AI extraction output tokens "
        f"(@ ${ASSUMPTIONS['extraction_usd_per_1m_output_tokens']}/1M) ≈ "
        f"${t['letta_extraction_cost_usd']} total. With Memanto, typed "
        f"primitives could bypass that step → 0 tokens, $0.\n"
        f"2. Latency — Letta archival recall is ~{lat['letta_read_ms']}ms read "
        f"with embedding search over passages. Memanto could deliver "
        f"<{lat['memanto_read_ms']}ms read and 0ms write (instantly searchable) — "
        f"about {lat['speedup_x']}x faster per query.\n"
        f"3. Storage — Letta currently stores Float32 passage vectors "
        f"({s['letta_human']} across {v['vector_count']} vectors). Memanto "
        f"could use {s['compression_ratio']}x binary compression ({s['memanto_human']}), "
        f"freeing {s['saved_human']}, on serverless infra that scales to zero when "
        f"idle.\n"
        "4. Retrieval model — Letta uses probabilistic Approximate Nearest "
        "Neighbor (ANN) search over archival passages; Memanto would use "
        "deterministic exact-match recall (bitwise Hamming distance on CPU), "
        "which can reduce vector-induced mis-retrieval.\n\n"
        "VOICE & TENSE (required):\n"
        "- Present tense for what the user HAS in Letta today (measured facts).\n"
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

    lines: list[str] = []
    lines.append("# Memanto vs. Letta — Memory Analysis Report")
    lines.append("")
    lines.append(f"_Generated: {generated}_")
    if exported_at:
        lines.append(f"_Letta export: {exported_at}_")
    lines.append("")
    lines.append("## Your Letta footprint (measured)")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| Agents | {v['agents']:,} |")
    lines.append(f"| Archival passages | {v['passages']:,} |")
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
    lines.append("| | Letta | Memanto |")
    lines.append("| --- | --- | --- |")
    lines.append(
        f"| Ingest/content input tokens (estimated) | {t['letta_input_tokens']:,} | 0 |"
    )
    lines.append(f"| AI extraction output tokens | {t['letta_output_tokens']:,} | 0 |")
    lines.append(
        f"| Input cost (@ ${ASSUMPTIONS['extraction_usd_per_1m_input_tokens']}/1M) | "
        f"${t['letta_input_cost_usd']} | $0.00 |"
    )
    lines.append(
        f"| Output cost (@ ${ASSUMPTIONS['extraction_usd_per_1m_output_tokens']}/1M) | "
        f"${t['letta_output_cost_usd']} | $0.00 |"
    )
    lines.append(
        f"| **Total extraction cost** | "
        f"**${t['letta_extraction_cost_usd']}** | **$0.00** |"
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
    lines.append("| | Letta | Memanto |")
    lines.append("| --- | --- | --- |")
    lines.append(
        f"| Read latency | ~{lat['letta_read_ms']}ms | <{lat['memanto_read_ms']}ms |"
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
    lines.append("| | Letta | Memanto |")
    lines.append("| --- | --- | --- |")
    lines.append(f"| Vector storage | {s['letta_human']} | {s['memanto_human']} |")
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
