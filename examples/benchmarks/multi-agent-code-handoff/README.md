# Multi-Agent Codebase Handoff Benchmark

This benchmark evaluates how a shared, active memory layer handles a realistic
multi-agent software release handoff compared with a per-agent append-only log
baseline.

The workload models a team of specialized coding agents shipping an imports API:

- planner
- implementer
- reviewer
- qa-agent
- docs-agent
- release-manager

Facts intentionally change over time. The benchmark asks each agent for the
current state of facts that were often created or corrected by another agent.
This stresses the multi-agent memory sharing problem: the best memory layer must
surface the latest cross-agent fact without bloating the prompt with stale logs.

## What It Measures

The output includes:

- retrieval accuracy using golden dataset matching
- cross-agent retrieval accuracy
- total ingested tokens
- total retrieved tokens
- p95 retrieval latency
- stale conflict rate
- signal-to-noise ratio for retrieved context

## Backends

The default benchmark is dependency-free and deterministic:

- `shared_active_digest`: an offline control that mirrors Memanto's intended
  active shared memory behavior, typed facts, latest-state supersession, and
  compact retrieval.
- `shared_append_log`: a shared transcript baseline with cross-agent access but
  no active supersession, so stale facts remain in retrieved context.
- `per_agent_append_log`: a siloed append-only log baseline where each agent
  mainly searches its own transcript, causing missed handoffs and stale
  contradictions.

The harness isolates benchmark design from service availability. A real Memanto
or competitor adapter can replace either backend as long as it implements the
same `ingest(event)` and `retrieve(question)` interface in `run_benchmark.py`.

## Scientific Controls

- Backend LLM: none by default. The run is offline and uses golden exact-match
  scoring rather than LLM-as-a-judge.
- Dataset: `dataset/codebase_handoff.json`
- Prompt/system instructions: none. Retrieval queries are the exact `query`
  strings in the dataset.
- Engine toggles:
  - `shared_active_digest`: global shared namespace, one active fact per key,
    latest event supersedes older values, max 1 fact retrieved.
  - `shared_append_log`: global shared namespace, append-only transcript, no
    supersession, max 6 log entries retrieved.
  - `per_agent_append_log`: per-agent silo, append-only transcript, no
    supersession, max 6 log entries retrieved.
- Host environment: captured in each JSON result under `host_environment`.

## Run

```bash
python run_benchmark.py \
  --output results/latest.json \
  --markdown results/latest.md
```

Run tests:

```bash
python -m unittest discover -s . -p "test_*.py"
```

No external packages are required.

## Expected Result

The shared active digest should retrieve fewer tokens, avoid stale conflicts,
and score higher on cross-agent handoff questions. This is the production
tension the bounty asks for: accuracy versus resource footprint under changing
state.
