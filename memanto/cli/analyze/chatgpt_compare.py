"""
Compare a ChatGPT account export against Memanto.
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
    # ChatGPT does not run on local agentic memory; read latency over vast history is simulated.
    "chatgpt_read_ms": 600,
    "memanto_read_ms": 90,
    "extraction_usd_per_1m_input_tokens": DEFAULT_INPUT_USD_PER_1M,
    "extraction_usd_per_1m_output_tokens": DEFAULT_OUTPUT_USD_PER_1M,
    "extraction_source_multiplier": DEFAULT_SOURCE_MULTIPLIER,
}


def _human_bytes(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024.0:
            return f"{num:.2f} {unit}"
        num /= 1024.0
    return f"{num:.2f} PB"


def compute_metrics(export: dict[str, Any]) -> dict[str, Any]:
    """Compute deterministic comparison metrics from a ChatGPT export."""
    conversations = export.get("conversations", []) or []
    conv_count = len(conversations)

    total_chars = 0
    message_count = 0

    for conv in conversations:
        mapping = conv.get("mapping") or {}
        for node in mapping.values():
            if not isinstance(node, dict):
                continue
            message = node.get("message")
            if not message:
                continue
            message_count += 1
            content = message.get("content") or {}
            parts = content.get("parts") or []
            for part in parts:
                if isinstance(part, str):
                    total_chars += len(part)

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

    # Reconstructed memories count (one per conversation)
    vector_count = conv_count
    storage_chatgpt_bytes = total_chars  # Raw JSON text representation
    storage_memanto_bytes = vector_count * ASSUMPTIONS["vector_bytes_memanto"]
    storage_saved_bytes = max(0, storage_chatgpt_bytes - storage_memanto_bytes)

    read_ms_chatgpt = ASSUMPTIONS["chatgpt_read_ms"]
    read_ms_memanto = ASSUMPTIONS["memanto_read_ms"]
    latency_speedup = (
        round(read_ms_chatgpt / read_ms_memanto, 1) if read_ms_memanto else 0
    )

    return {
        "volume": {
            "conversations": conv_count,
            "messages": message_count,
            "estimated_content_tokens": content_tokens,
            "estimated_input_tokens": input_tokens,
            "estimated_output_tokens": output_tokens,
            "vector_count": vector_count,
        },
        "ingestion_tax": {
            "chatgpt_input_tokens": input_tokens,
            "chatgpt_output_tokens": output_tokens,
            "chatgpt_input_cost_usd": ingestion["input_cost_usd"],
            "chatgpt_output_cost_usd": ingestion["output_cost_usd"],
            "chatgpt_extraction_cost_usd": ingestion["total_cost_usd"],
            "tokens_saved": input_tokens + output_tokens,
        },
        "storage": {
            "chatgpt_raw": storage_chatgpt_bytes,
            "chatgpt_human": _human_bytes(storage_chatgpt_bytes),
            "memanto_raw": storage_memanto_bytes,
            "memanto_human": _human_bytes(storage_memanto_bytes),
            "saved_raw": storage_saved_bytes,
            "saved_human": _human_bytes(storage_saved_bytes),
            "compression_ratio": ASSUMPTIONS["compression_ratio"],
        },
        "latency": {
            "chatgpt_read_ms": read_ms_chatgpt,
            "memanto_read_ms": read_ms_memanto,
            "speedup_x": latency_speedup,
            "ms_saved_per_query": max(0, read_ms_chatgpt - read_ms_memanto),
        },
    }


def build_llm_prompt(metrics: dict[str, Any]) -> str:
    v = metrics["volume"]
    t = metrics["ingestion_tax"]
    s = metrics["storage"]
    lat = metrics["latency"]

    return (
        "Write a structured technical brief comparing ChatGPT raw history to Memanto.\n\n"
        "=== MEASURED INPUT METRICS ===\n"
        f"- Conversations: {v['conversations']}\n"
        f"- Total Messages: {v['messages']}\n"
        f"- Estimated content tokens: {v['estimated_content_tokens']:,}\n\n"
        "=== PROJECTED MEMANTO IMPACT ===\n"
        f"1. Ingestion/Extraction Cost — ChatGPT raw history ingest is modeled as "
        f"~{t['chatgpt_input_tokens']:,} input tokens + {t['chatgpt_output_tokens']:,} output tokens "
        f"≈ ${t['chatgpt_extraction_cost_usd']} extraction cost. Memanto maps each conversation "
        f"into a single structured memory record, skipping redundant text extraction.\n"
        f"2. Latency — Traversing or querying raw JSON history is ~{lat['chatgpt_read_ms']}ms. "
        f"Memanto exact-match bitwise recall delivers <{lat['memanto_read_ms']}ms read time "
        f"({lat['speedup_x']}x faster).\n"
        f"3. Storage — Raw text stores {s['chatgpt_human']}. Memanto vector/Hamming representation "
        f"stores {s['memanto_human']} (saving {s['saved_human']}).\n\n"
        "Write a concise, professional markdown brief with these sections:\n"
        "## Executive summary (2-3 sentences)\n"
        "## What you could save by migrating (bullet points with numbers)\n"
        "## What could improve in your memory layer (search speed, recall precision)\n"
        "## Migration considerations\n"
        "Use third person and professional tense."
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
    lines.append("# Memanto vs. ChatGPT — Memory Analysis Report")
    lines.append("")
    lines.append(f"_Generated: {generated}_")
    if exported_at:
        lines.append(f"_ChatGPT export: {exported_at}_")
    lines.append("")
    lines.append("## Your ChatGPT footprint (measured)")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| Conversations | {v['conversations']:,} |")
    lines.append(f"| Total Messages | {v['messages']:,} |")
    lines.append(f"| Estimated content tokens | {v['estimated_content_tokens']:,} |")
    lines.append("")
    lines.append("## Projected impact of migrating to Memanto")
    lines.append("")
    lines.append("### 1. Ingestion tax (token savings)")
    lines.append("")
    lines.append("| | ChatGPT | Memanto |")
    lines.append("| --- | --- | --- |")
    lines.append(f"| Ingest/content input tokens (estimated) | {t['chatgpt_input_tokens']:,} | 0 |")
    lines.append(f"| AI extraction output tokens | {t['chatgpt_output_tokens']:,} | 0 |")
    lines.append(f"| **Total extraction cost** | **${t['chatgpt_extraction_cost_usd']}** | **$0.00** |")
    lines.append("")
    lines.append(
        f"**You could save ~{t['tokens_saved']:,} extraction tokens** "
        f"if you migrate — Memanto's structural migration stores mapped conversation history directly."
    )
    lines.append("")
    lines.append("### 2. Latency & indexing")
    lines.append("")
    lines.append("| | ChatGPT | Memanto |")
    lines.append("| --- | --- | --- |")
    lines.append(f"| Read latency | ~{lat['chatgpt_read_ms']}ms | <{lat['memanto_read_ms']}ms |")
    lines.append("| Write availability | parsing delay | 0ms (instant) |")
    lines.append("")
    lines.append(f"**Reads could be ~{lat['speedup_x']}x faster**.")
    lines.append("")
    lines.append("### 3. Storage footprint")
    lines.append("")
    lines.append("| | ChatGPT | Memanto |")
    lines.append("| --- | --- | --- |")
    lines.append(f"| Vector storage | {s['chatgpt_human']} | {s['memanto_human']} |")
    lines.append("")
    lines.append(f"**Storage could be smaller** — freeing {s['saved_human']}.")
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
    lines.append("- **Assumptions used:**")
    for key, value in ASSUMPTIONS.items():
        lines.append(f"  - `{key}` = {value}")
    lines.append("")
    return "\n".join(lines)
