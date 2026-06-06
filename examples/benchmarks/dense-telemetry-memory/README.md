# Dense Telemetry Memory Benchmark

Submission for issue [#639](https://github.com/moorcheh-ai/memanto/issues/639), **Scenario A: The Context-Overhead & Latency Sprint**.

This benchmark stress-tests agent memory on **dense, shifting technical logs** — ICU vitals streams, lab panels, medication titrations, device alarms, and care-team handoffs over seven clinical shifts. The same patient state evolves: hypoxic vitals become stable, a contraindicated antibiotic is replaced after allergy reconciliation, respiratory support escalates then weans, and disposition moves from ICU to ward to home discharge.

Unlike preference-drift or coding-agent audit benchmarks, this scenario models **data-intensive production telemetry** where append-only graph dumps inflate context with superseded vitals and stale orders, while recent-window logs forget durable allergies and baseline diagnoses.

## Experimental Design

| Variable | Value |
| --- | --- |
| Host environment | Documented at runtime (`python_version`, `platform`) |
| LLM backend | None — deterministic golden-set scoring |
| Dataset | 16 synthetic ICU telemetry events across 7 shifts, 9 evaluation queries |
| Baselines | `append_only_log`, `windowed_recent_log`, `active_telemetry_digest` |
| Isolation | Identical events and queries run through all backends in one process |

## Metrics

| Metric | Definition |
| --- | --- |
| **Retrieval accuracy** | Golden-set match: all `must_have` terms present, no `must_not_have` stale terms |
| **Avg retrieved tokens** | Mean whitespace-delimited tokens injected per query |
| **Total ingestion tokens** | Tokens if every event text were dumped into context each turn |
| **p95 latency (ms)** | 95th percentile retrieval time per backend |
| **Stale conflict rate** | Fraction of queries that surface superseded clinical facts |
| **Signal/noise ratio** | Useful signal tokens ÷ total retrieved tokens |
| **Cross-session degradation** | Accuracy curve as sessions accumulate (shift-01 → shift-07) |

## Run

```bash
python examples/benchmarks/dense-telemetry-memory/run_benchmark.py
```

Generate committed sample reports:

```bash
python examples/benchmarks/dense-telemetry-memory/run_benchmark.py \
  --output examples/benchmarks/dense-telemetry-memory/results/sample_results.json \
  --markdown examples/benchmarks/dense-telemetry-memory/results/sample_results.md
```

Run tests:

```bash
python -m unittest examples.benchmarks.dense-telemetry-memory.test_benchmark -q
```

## Backends Compared

| Backend | Models | Strengths | Weaknesses |
| --- | --- | --- | --- |
| `append_only_log` | Mem0/Zep-style graph dump | High recall | Token bloat, stale vitals, contraindicated meds leak through |
| `windowed_recent_log` | Sliding context window | Low footprint | Forgets durable allergies, baseline dx, attending |
| `active_telemetry_digest` | Memanto-style typed digest | Current facts, allergy-safe meds, compact scoped retrieval | Requires active supersession at write time |

## Prerequisites

No API keys required. The benchmark is fully offline and uses only the Python standard library.

To run against live Memanto retrieval, configure a Moorcheh API key per the [main README](https://github.com/moorcheh-ai/memanto/blob/main/README.md) and adapt the `active_telemetry_digest` backend to call `memanto.recall()`.

## Why This Scenario Matters

Production monitoring agents ingest **orders of magnitude more telemetry than conversational preference notes**. A memory layer that dumps every vitals packet into context creates immediate post-ingestion latency and token inflation. This benchmark quantifies that tradeoff and shows how an active companion digest wins on accuracy, stale suppression, and signal-to-noise while keeping retrieval latency flat.
