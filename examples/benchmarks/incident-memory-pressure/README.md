# Incident Memory Pressure Benchmark

This benchmark is a reproducible submission for
`moorcheh-ai/memanto#639`, the Great Agentic Memory Showdown.

It tests an agent-memory scenario that is different from the existing
preference-drift benchmark: long-running incident response memory. The same
incident timeline is fed into two backends:

- `memanto_typed_digest`: a Memanto-style typed memory backend that keeps
  current facts, provenance, recency, and supersession keys.
- `append_only_log`: a graph/log-style baseline that recalls matching historical
  snippets without suppressing stale state.

The workload stresses the production tradeoff called out in the bounty:
retrieval accuracy versus resource footprint.

## Scenario

The dataset follows an SRE assistant across 18 incident updates for three
services: payments, search, and notifications. The facts include:

- stale runbooks replaced by safer runbooks
- rollback decisions that must stay retrievable
- customer-facing status wording that changes over time
- service owners and escalation targets that rotate
- mitigation records that should not pollute current action answers

Queries ask the memory layer for the current action, owner, status wording, or
runbook. A correct backend should surface the current fact and avoid injecting
stale superseded facts.

## Metrics

The runner emits JSON and Markdown with:

- `tokens_ingested`: total input tokens seen by the backend
- `tokens_retrieved`: total context tokens returned across the query suite
- `p95_latency_ms`: p95 retrieval latency
- `retrieval_accuracy`: expected facts present and stale facts absent
- `stale_suppression`: percentage of stale fragments kept out of context
- `signal_to_noise`: expected fact tokens divided by retrieved context tokens

## Run

From the repository root:

```bash
python examples/benchmarks/incident-memory-pressure/run_benchmark.py --format markdown
python examples/benchmarks/incident-memory-pressure/run_benchmark.py --format json
python examples/benchmarks/incident-memory-pressure/tests/test_incident_memory_pressure.py
```

The benchmark has no required third-party dependencies. `requirements.txt`
exists only to make that explicit for automated reviewers.

## Sample result

The committed sample output in `results/sample_results.md` is generated from
the deterministic offline dataset. The Memanto-style backend is expected to use
fewer retrieved tokens and suppress stale facts more aggressively, while the
append-only baseline retains more historical context and therefore returns more
noise.

## Live backend extension

The benchmark intentionally keeps the default run credential-free. To attach a
live Memanto, Mem0, Zep, or Hindsight backend, implement the small `MemoryBackend`
protocol in `incident_memory_pressure/backends.py`:

```python
class MemoryBackend(Protocol):
    name: str

    def ingest(self, records: Iterable[IncidentRecord]) -> None: ...
    def recall(self, query: IncidentQuery) -> list[MemoryHit]: ...
```

The dataset, scoring, JSON output, and Markdown report remain unchanged, so a
live adapter can be compared under the same evaluation contract.
