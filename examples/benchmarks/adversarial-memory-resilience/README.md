# Adversarial memory resilience benchmark

This suite compares live **Memanto** and **Mem0** under a production-shaped
incident-response workload. It asks a narrower and harder question than a
standard relevance benchmark:

> Can an agent retrieve the current fact without also surfacing stale states,
> untrusted prompt-injection payloads, or another tenant's data—and what does
> that cost in tokens and latency?

The same deterministic event stream is sent to both systems. No LLM judge is
used: opaque markers make every score independently auditable.

## What is measured

| Metric | Direction | Definition |
|---|---:|---|
| Retrieval accuracy | higher | Expected current marker appears in top-k |
| Mean reciprocal rank | higher | Rank-sensitive current-state retrieval |
| Stale exposure | lower | Any superseded marker appears in top-k |
| Poison exposure | lower | Any untrusted instruction marker appears in top-k |
| Foreign exposure | lower | Any marker from a different tenant appears in top-k |
| Tokens ingested/retrieved | lower | Deterministic lexical token approximation |
| p95 write/retrieval latency | lower | Wall-clock seconds around backend calls |

The report also gives paired 95% bootstrap confidence intervals for every
probe-level difference. Pairing by seed and probe removes workload variance.
The comparison's `mean_retrieval_latency_seconds` value is the paired mean of
the per-probe retrieval-latency differences; it is intentionally distinct from
the backend-level p95 write and retrieval latencies in `summary.json`.

## Experimental controls

- Three fixed seeds by default: `7,19,43`.
- Three tenants, each stored under a distinct Memanto agent and Mem0 user ID.
- Four independent incidents per tenant.
- Four state revisions: `INVESTIGATING`, `MITIGATING`, `MONITORING`, and
  `RESOLVED`.
- Two benign distractors and one explicitly untrusted prompt-injection record
  per tenant per revision.
- Identical event order, probe text, top-k, embedding model, and host for both
  backends.
- Mem0 inference is disabled so the comparison measures memory retrieval, not
  an unrelated extraction LLM. It uses local Qdrant and
  `all-MiniLM-L6-v2` through FastEmbed.
- Memanto uses its public SDK and isolated benchmark namespaces.

No provider is favored in scoring. A poison record is not counted as a
failure merely because it was stored; it counts only if an ordinary current
status query retrieves it into the agent context. Foreign exposure is a
tenant-isolation invariant rather than a semantic relevance judgment.

## Run it

Python 3.10–3.12 is supported.

```bash
cd examples/benchmarks/adversarial-memory-resilience
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Put a free Moorcheh key in `MOORCHEH_API_KEY`, then run:

```bash
python run_benchmark.py
```

For a small validation run:

```bash
python run_benchmark.py \
  --seeds 7 \
  --tenants 2 \
  --incidents 1 \
  --revisions 2 \
  --top-k 3 \
  --output-dir results/smoke
```

After adapter initialization succeeds, the benchmark deletes temporary cloud
namespaces and local Qdrant state even when execution fails. Initialization also
attempts best-effort cleanup of any resources it created before an error. Use
`--keep-backend-state` only for debugging.

## Artifacts

Every run writes:

- `config.json` — all experiment controls.
- `environment.json` — OS, Python, processor, and exact package versions.
- `dataset.jsonl` — the complete generated source workload.
- `traces.jsonl` — one auditable row per backend, seed, and probe.
- `summary.json` and `summary.csv` — required aggregate metrics.
- `comparison.json` — paired mean effects and 95% bootstrap intervals; its
  retrieval-latency effect is explicitly named and is not a p95 statistic.
- `report.md` — a human-readable results table.

The source workload never contains secrets or real user data. API keys are
read only from the process environment and are never written to an artifact.

## Published live run

The checked-in [`results/live`](results/live) run was executed against the
production Memanto service and local Mem0 on three seeds, three isolated
tenants, four incidents per tenant, and four revisions. It contains 288
retrieval traces (144 per backend) and 396 source workload records.

| Backend | Accuracy | MRR | Stale exposure | Poison exposure | Foreign exposure | p95 retrieval |
|---|---:|---:|---:|---:|---:|---:|
| Memanto | 0.944 | 0.551 | 0.750 | 0.229 | 0.000 | 0.449 s |
| Mem0 | 0.729 | 0.472 | 0.667 | 0.167 | 0.000 | 0.047 s |

Memanto improved hit rate by 0.215 (95% paired-bootstrap CI 0.139 to
0.292), but returned more stale and prompt-injection-marked context and had
higher retrieval latency on this workload. Both systems maintained complete
tenant isolation. See [`report.md`](results/live/report.md) and the raw traces
for the full audit trail. All nine temporary cloud namespaces were deleted
after the run.

## Validate the implementation

```bash
python -m pytest -q tests
ruff check adversarial_memory tests run_benchmark.py
ruff format --check adversarial_memory tests run_benchmark.py
```

Unit tests cover deterministic generation, temporal checkpoints, marker
scoring, exposure classes, percentile math, paired bootstrap alignment,
runner lifecycle, and metric aggregation. A live smoke test is still
recommended for changed credentials or SDK versions because behavior cannot be
proven by mocks.

## Interpreting results

Accuracy alone is insufficient. A backend can find the current state while
also injecting three obsolete states and an attacker-controlled instruction
into the model context. Read accuracy together with exposure rates and
retrieved tokens.

Confidence intervals are descriptive for this fixed synthetic workload. They
quantify run-level uncertainty but do not claim universal performance across
all languages, domains, prompts, or hardware.
