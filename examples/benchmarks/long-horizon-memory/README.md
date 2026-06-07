# Long-Horizon Agent Memory Benchmark

Submission for [issue #639](https://github.com/moorcheh-ai/memanto/issues/639).

This benchmark compares live Memanto and Mem0 retrieval as mutable operational
state grows from 8 to 48 sessions. It is designed to answer a production
question that a four-session demo cannot:

> How quickly does a memory backend lose current-state accuracy, accumulate
> stale contradictions, or inflate context as history grows?

The benchmark does not use a simulated "Memanto-style" implementation. The
competitive run calls the real Memanto `SdkClient` and the real Mem0 `Memory`
API against the same event stream.

## Experiment

Each run contains eight mutable facts:

- production region
- payment rail
- primary database
- retention policy
- incident channel
- release window
- on-call owner
- checkout feature gate

Every eight-session epoch updates each fact once. The key order and unrelated
distractor notes vary by seed. Values never repeat, so stale retrieval is
unambiguous.

At sessions 8, 16, 24, 32, and 48, the runner asks one probe per fact. Every
stored update includes a machine-readable canonical marker:

```text
CANONICAL[production_region=eu-west-1]
```

This gives the benchmark deterministic golden scoring without an LLM judge.
The scorer separates retrieval quality from context cleanliness:

1. Is the current value the first returned result?
2. Does the current value appear anywhere in top-k?
3. Does top-k also contain a superseded value for the same fact?

Top-1 current-state accuracy is the primary accuracy metric. The benchmark also
reports clean-context recall (`strict_accuracy` in the JSON artifacts), which
is true only when the current value appears and no stale contradiction appears
anywhere in top-k. Keeping these metrics separate avoids turning a correct
first result into an accuracy failure solely because a lower-ranked diagnostic
result is stale.

## Fairness controls

- Both backends receive byte-identical event content in the same order.
- Mem0 uses `infer=False`, so neither side gets an LLM extraction advantage.
- Backend write and read order is deterministically shuffled per operation to
  reduce systematic first-run network bias.
- Every live call is timed with `time.perf_counter()`.
- Context tokens use the same `cl100k_base` tokenizer for both systems.
- The default run uses three seeds and paired probes.
- The report includes a paired bootstrap confidence interval, not only means.
- Agent and collection IDs are unique per seed to prevent cross-run leakage.
- Raw traces preserve every query, returned item, rank, score, and latency.
- Transient Memanto transport failures are retried up to five times with
  exponential backoff. Writes use deterministic per-event IDs so an ambiguous
  network response cannot create duplicate benchmark memories. Retry waits are
  included in wall-clock latency.

## Metrics

| Metric | Meaning |
|---|---|
| Top-1 accuracy | First result contains the current canonical value |
| Top-k current recall | Current value appears anywhere in top-k |
| Stale-context rate | At least one superseded value appears in top-k |
| Clean-context recall | Current value recalled with no stale contradiction |
| Mean reciprocal rank | Rank quality of the current value |
| Retrieved tokens | Mean and total normalized context footprint |
| Ingested tokens | Total input footprint sent to each memory backend |
| Signal-to-noise | Tokens from current-value records divided by all returned tokens |
| Read p50/p95/p99 | Semantic retrieval wall-clock latency |
| Write p50/p95/p99 | Memory ingestion wall-clock latency |

The report also breaks out accuracy, stale context, and token footprint by
checkpoint to expose long-horizon degradation.

## Reference live run

The repository includes the complete live run captured on June 7, 2026 at
`reference-results/20260607T014457127413Z/`. It contains all 240 retrieval
traces (120 paired probes), 288 write traces, the environment manifest, and
machine-readable summaries.

| Backend | Top-1 accuracy | Top-k recall | Stale context | Mean tokens | Read p95 | Write p95 |
|---|---:|---:|---:|---:|---:|---:|
| Memanto | 40.8% | 97.5% | 80.0% | 319.6 | 1,136.5 ms | 1,429.2 ms |
| Mem0 | 31.7% | 96.7% | 80.0% | 323.3 | 22.7 ms | 25.0 ms |

The paired Top-1 difference was **+9.2 percentage points** for Memanto
(95% bootstrap CI `[0.0, 18.3]`, n=120). Memanto also retrieved 442 fewer
tokens across all probes and had higher mean reciprocal rank (0.624 vs 0.575).

The result is deliberately not presented as a universal win. Both systems
returned stale state in 80% of all top-5 contexts, and local Mem0 was roughly
50x faster than the hosted Memanto path in this run. The useful finding is
narrower: under identical append-only events, Memanto ranked the current state
first more often and used slightly less context, while paying a substantial
network-latency cost.

This run completed before the free Moorcheh account reached its documented
API-request limit. The benchmark logic, dataset, and scoring are the same as
the submitted code; the later resilience change adds deterministic write IDs,
transient transport retries, and Git source metadata. It does not alter the
stored event text, queries, golden labels, or scoring. The original artifacts
are preserved unchanged rather than relabeled as a later run.

## Setup

Use Python 3.10 through 3.12.

```bash
cd examples/benchmarks/long-horizon-memory
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set:

```bash
export MOORCHEH_API_KEY="..."
```

`MOORCHEH_API_KEY` powers Memanto and is never written to artifacts. Mem0 runs
locally with FastEmbed's `sentence-transformers/all-MiniLM-L6-v2` weights,
registered under the `benchmark/all-MiniLM-L6-v2` direct-download alias, and an
isolated Qdrant store. Its first run downloads approximately 90 MB of model
data. Because Mem0 uses `infer=False`, its LLM client is initialized with a
sentinel key and never makes a generation request.

The runner uses `certifi` as the default CA bundle when `SSL_CERT_FILE` is not
already configured. TLS verification remains enabled.
FastEmbed's reusable model files default to the ignored `work/fastembed-cache`
directory; set `FASTEMBED_CACHE_PATH` to override it.
Mem0 telemetry is disabled, and its config and history databases stay under the
benchmark's ignored `work/` directory instead of the user's home directory.

## Run

Full paired run:

```bash
python run_benchmark.py \
  --backends memanto mem0 \
  --seeds 7,19,43 \
  --sessions 48 \
  --checkpoints 8,16,24,32,48 \
  --top-k 5
```

Fast smoke run:

```bash
python run_benchmark.py \
  --backends memanto mem0 \
  --seeds 7 \
  --sessions 16 \
  --checkpoints 8,16
```

The command prints the generated report and writes an isolated result directory:

```text
results/<UTC run id>/
  config.json
  environment.json
  raw_traces.jsonl
  write_traces.jsonl
  summary.json
  summary.csv
  report.md
```

The committed reference artifacts use the same file layout under
`reference-results/<UTC run id>/`.

By default, the runner deletes both temporary local Memanto agent metadata and
the hosted namespace created for each seed, plus its isolated local Qdrant
state. It never reuses or deletes a pre-existing namespace or local directory.
Pass `--keep-backend-state` only when debugging a live run.

## Tests

The unit tests never call external services:

```bash
python -m unittest discover -s tests -v
```

They verify dataset determinism, marker parsing, stale-conflict scoring,
bootstrap repeatability, paired artifact generation, and a control experiment
where a current-state backend must beat an append-only backend.

## Interpretation limits

- This benchmark evaluates memory ingestion and retrieval, not final response
  generation.
- Canonical markers make scoring reproducible but are easier than unconstrained
  natural-language fact extraction.
- Mem0 uses a local 384-dimensional FastEmbed model, while Memanto uses
  Moorcheh's hosted retrieval path. The environment manifest records this
  architectural difference rather than hiding it.
- Network measurements should be repeated from more than one region before
  making broad latency claims.
- A single run is evidence, not a universal ranking. Publish raw traces and
  confidence intervals with every claimed result.
