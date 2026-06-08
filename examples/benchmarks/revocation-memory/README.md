# Access Revocation Memory Benchmark

This benchmark tests a production failure mode that ordinary recall demos miss:
an agent remembers an authorization, retention rule, or contact preference and
continues surfacing it after it has been revoked.

It runs the same five-session operations history through:

- `memanto`: the real Memanto SDK and Moorcheh retrieval backend.
- `mem0`: the real Mem0 framework with a local FastEmbed model.
- `fixture`: a deterministic current-state digest for smoke tests only.

The fixture is explicitly marked `smoke_fixture` in every report. It is not a
substitute for live framework results.

## Scenario

The dataset evolves three high-risk facts:

1. Production access is revoked and replaced with staging-only access.
2. Customer export retention changes from 30 days to deletion within 24 hours.
3. SMS escalation is revoked in favor of PagerDuty.

It also adds a two-human production approval rule, secret-handling policy, and
an access-review owner. Six golden probes score current-fact recall and stale
fact leakage.

Every report embeds a SHA-256 fingerprint of the canonical dataset so reviewers
can detect changed inputs and distinguish committed smoke output from live runs.

## Metrics

- Retrieval accuracy: fraction of required current facts present.
- Stale leak rate: fraction of probes that retrieve any forbidden old fact.
- Ingested and retrieved tokens: deterministic word-and-punctuation token proxy.
- Write and read p95 latency: wall-clock seconds around framework calls.

The token proxy is intentionally provider-independent and is documented in the
JSON environment metadata. It measures comparative memory footprint, not an LLM
provider's billable token count.

## Run

Smoke test without credentials:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
python examples/benchmarks/revocation-memory/benchmark.py \
  --backend fixture \
  --output examples/benchmarks/revocation-memory/results/fixture-results.json
```

Live Memanto run:

```bash
export MOORCHEH_API_KEY="..."
python examples/benchmarks/revocation-memory/benchmark.py \
  --backend memanto \
  --settle-seconds 0.3 \
  --output examples/benchmarks/revocation-memory/results/memanto-results.json
```

Live Mem0 run:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
pip install -r examples/benchmarks/revocation-memory/requirements.txt
python examples/benchmarks/revocation-memory/benchmark.py \
  --backend mem0 \
  --output examples/benchmarks/revocation-memory/results/mem0-results.json
```

The Mem0 adapter uses direct import (`infer=False`) so both frameworks receive
the same curated facts and no external LLM key is required. This isolates
retrieval behavior and makes any stale fact leakage visible instead of asking
an extraction model to resolve contradictions before storage. Each live run
uses a unique agent/user namespace to prevent historical bleed.

## Validate

```bash
python -m unittest \
  examples/benchmarks/revocation-memory/test_benchmark.py -v
python -m py_compile \
  examples/benchmarks/revocation-memory/benchmark.py \
  examples/benchmarks/revocation-memory/test_benchmark.py

python examples/benchmarks/revocation-memory/benchmark.py \
  --validate-report \
  examples/benchmarks/revocation-memory/results/fixture-results.json
```

Report validation checks the dataset fingerprint, backend/mode pairing, probe
membership, and required summary fields. In particular, a fixture report cannot
be relabeled as a live framework result.

## Interpretation

A high-quality memory system should retrieve the current rule and avoid the
superseded rule. Accuracy alone is insufficient: a response containing both
"delete within 24 hours" and "retain for 30 days" earns the current-fact hit but
also records a stale leak. This makes contradictions visible rather than hiding
them inside a single aggregate score.
