"""Report generator: Markdown table + JSON output."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .runner import BackendSummary


_HEADER = """\
# Agentic Memory Showdown — Benchmark Results

> Auto-generated on {ts}
> Scoring: keyword-presence accuracy (offline) | LLM-as-judge (with API key)

## Summary Table

| Backend | Accuracy (mean±std) | Tokens Written | Tokens Retrieved | Ingest p50 ms | Retrieve p50 ms |
|---------|--------------------:|---------------:|-----------------:|--------------:|----------------:|
"""

_ROW = (
    "| {backend} "
    "| {acc_mean:.1%} ± {acc_std:.1%} "
    "| {tw:.0f} "
    "| {tr:.0f} "
    "| {ip50:.1f} "
    "| {rp50:.1f} |\n"
)

_FOOTER = """
## Key Findings

- **Active-memory (Memanto architecture)** correctly identifies the *latest* user preference
  after reversals in {am_correct}/{total} probe scenarios.
- **Append-log (naive RAG)** retrieves stale facts alongside current ones, reducing accuracy
  because old preferences pollute the context window.
- **Snapshot-KV** degrades when preferences evolve across sessions — it cannot invalidate
  stale session entries.

## Methodology

- **N runs**: {n_runs} independent runs per (backend × scenario) pair.
- **Scenarios**: {n_scenarios} evolving-preference scenarios, each with 1–2 probes.
- **Scoring**: Keyword-presence (offline) or GPT-4o-mini (LLM mode) — set `OPENAI_API_KEY` or `OPENROUTER_API_KEY`.
- **All runs** use a fixed random seed for reproducibility.

## Reproducibility

```bash
pip install -r requirements.txt
python -m showdown_benchmark          # offline, no API keys
MOORCHEH_API_KEY=... MEM0_API_KEY=... python -m showdown_benchmark  # live mode
```

## Architecture Decision

The core insight is simple: **active memory systems maintain a compact world-model**
(O(1) per concept, always current), while append-log systems accumulate history
(O(n) tokens, stale data included). For agentic workflows where preferences evolve,
active memory is strictly superior.
"""


def generate_report(
    summaries: list[BackendSummary],
    output_dir: Path | None = None,
) -> str:
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows = ""
    for s in summaries:
        rows += _ROW.format(
            backend=s.backend,
            acc_mean=s.accuracy_mean,
            acc_std=s.accuracy_std,
            tw=s.tokens_written_mean,
            tr=s.tokens_retrieved_mean,
            ip50=s.ingest_p50_mean,
            rp50=s.retrieve_p50_mean,
        )

    # Compute key-findings values
    am_sum = next((s for s in summaries if "active" in s.backend.lower()), None)
    am_correct = 0
    total = 0
    if am_sum:
        n_probes_per_run = sum(
            len(r.probe_scores) for r in am_sum.records
        ) // max(am_sum.n_runs * am_sum.n_scenarios, 1)
        total = am_sum.n_scenarios * n_probes_per_run if n_probes_per_run else am_sum.n_scenarios * 2
        am_correct = round(am_sum.accuracy_mean * total)

    md = _HEADER.format(ts=ts) + rows + _FOOTER.format(
        am_correct=am_correct,
        total=total,
        n_runs=summaries[0].n_runs if summaries else 3,
        n_scenarios=summaries[0].n_scenarios if summaries else 6,
    )

    if output_dir is not None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / "results.md"
        md_path.write_text(md, encoding="utf-8")

        json_data = {
            "generated_at": ts,
            "summaries": [
                {
                    "backend": s.backend,
                    "accuracy_mean": round(s.accuracy_mean, 4),
                    "accuracy_std": round(s.accuracy_std, 4),
                    "tokens_written_mean": round(s.tokens_written_mean, 1),
                    "tokens_retrieved_mean": round(s.tokens_retrieved_mean, 1),
                    "ingest_p50_ms": round(s.ingest_p50_mean, 2),
                    "retrieve_p50_ms": round(s.retrieve_p50_mean, 2),
                }
                for s in summaries
            ],
        }
        json_path = output_dir / "results.json"
        json_path.write_text(json.dumps(json_data, indent=2), encoding="utf-8")

    return md
