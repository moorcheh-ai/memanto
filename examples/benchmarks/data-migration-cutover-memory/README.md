# Data Migration Cutover Memory Benchmark

This benchmark evaluates how an agentic memory layer handles a production data
migration cutover where facts change over several sessions. The same synthetic
dataset is ingested by every backend, then scored against golden probes for
current-state recall, evidence coverage, retrieved token footprint, p95 latency,
stale-conflict rate, and sensitive-value leakage.

The default implementation is intentionally offline and stdlib-only so reviewers
can reproduce the results without API keys, network access, or an LLM judge.

## Scenario

The dataset models a billing warehouse migration across five sessions:

- initial discovery decisions,
- dry-run changes,
- security review notes,
- final readiness updates,
- post-cutover state.

It includes superseded decisions such as the cutover window and rollback owner,
current operational facts such as dual-write shutdown criteria, and one raw
security note containing a fake credential that must not appear in retrieval
output.

## Backends Compared

| Backend | What it models |
| --- | --- |
| `memanto_active_digest` | A Memanto-style active companion memory that stores typed current-state digests, collapses superseded facts, and redacts sensitive raw values. |
| `passive_append_only` | A passive dedicated-memory baseline that keeps every raw observation and retrieves lexically without contradiction resolution. |
| `recent_window` | A short-context baseline that only keeps the latest raw observations. |

The `MemoryBackend` contract in `run_benchmark.py` is deliberately small:
`ingest(events)` and `retrieve(probe, top_k)`. To run this against a live
Memanto namespace or another memory framework, implement the same methods while
reusing the dataset and `score_probe` function unchanged.

## Metrics

- `retrieval_accuracy`: weighted golden evidence plus required answer terms,
  with penalties for stale evidence and sensitive leaks.
- `evidence_coverage`: fraction of expected evidence IDs retrieved per probe.
- `stale_conflict_rate`: fraction of probes that retrieved superseded evidence.
- `sensitive_leak_rate`: fraction of sensitive probes that exposed forbidden
  credential terms.
- `source_transcript_tokens`: total source tokens ingested from the same dataset.
- `stored_memory_tokens`: backend memory footprint after ingestion.
- `retrieved_tokens_total`: total tokens returned across all probes.
- `p95_read_latency_seconds` and `p95_write_latency_seconds`: local benchmark
  timing around each backend operation.

The judge is deterministic golden matching. No hidden prompts, private runtime
metadata, or session/system instructions are collected.

## Reproduce

From the repository root:

```bash
python examples/benchmarks/data-migration-cutover-memory/run_benchmark.py \
  --output examples/benchmarks/data-migration-cutover-memory/results/sample_results.json \
  --markdown examples/benchmarks/data-migration-cutover-memory/results/sample_results.md
```

Run the tests:

```bash
python -m unittest discover \
  -s examples/benchmarks/data-migration-cutover-memory \
  -p "test_*.py"
```

The generated reports are committed under `results/` as a reference run.

## Sample Result

The reference run shows the active digest backend preserving current facts while
using fewer stored and retrieved tokens than the append-only baseline. The
append-only baseline keeps useful audit evidence, but it also returns obsolete
decisions and leaks the fake credential in the sensitive probe. The recent
window baseline is compact but forgets older facts that remain operationally
current.

See:

- `results/sample_results.json`
- `results/sample_results.md`

## Live Backend Adapter Notes

For a live Memanto run, the active backend can map each event into typed
`remember` calls and use `recall` for probe queries. The same source dataset,
golden evidence IDs, `top_k`, and scoring code should remain fixed. A competing
framework adapter should use the same event order and retrieval limit, with its
own memory configuration documented beside the generated results.
