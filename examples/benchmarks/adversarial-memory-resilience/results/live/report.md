# Adversarial memory resilience benchmark

All values come from live backends over identical seeded workloads.
Marker matching is deterministic; no LLM judge is used.

| Backend | Accuracy | MRR | Stale exposure | Poison exposure | Foreign exposure | Retrieved tokens | p95 retrieval (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| mem0 | 0.729 | 0.472 | 0.667 | 0.167 | 0.000 | 90.2 | 0.0465 |
| memanto | 0.944 | 0.551 | 0.750 | 0.229 | 0.000 | 91.0 | 0.4486 |

## Paired effects (memanto minus mem0)

| Metric | Mean delta | 95% bootstrap CI |
|---|---:|---:|
| hit | 0.215278 | [0.138889, 0.291667] |
| reciprocal_rank | 0.078819 | [0.017821, 0.138429] |
| stale_exposure | 0.083333 | [0.041667, 0.131944] |
| poison_exposure | 0.062500 | [0.013889, 0.118056] |
| foreign_exposure | 0.000000 | [0.000000, 0.000000] |
| retrieved_tokens | 0.791667 | [0.138889, 1.520833] |
| mean_retrieval_latency_seconds | 0.318327 | [0.305866, 0.332310] |

Lower is better for stale, poison, foreign exposure, retrieved tokens, and latency. Higher is better for hit rate and reciprocal rank.
The latency effect is the paired mean retrieval-latency delta; backend p95 write and retrieval latencies are reported separately above and in summary.json.
