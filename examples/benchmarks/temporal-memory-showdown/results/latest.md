# Temporal Memory Showdown Results

Generated: `2026-06-12T21:27:29.456574+00:00`

## Primary showdown

The primary comparison is Memanto against Mem0's default agentic (`infer=True`) pipeline. `mem0-direct` is retained as a vector-only ablation.

- Memanto coverage advantage: **+27.8 percentage points** (paired bootstrap 95% CI +9.3 to +48.1 points).
- Full ingestion was **30,285.9x faster** (0.096s vs 2912.082s).
- Query p95 was **4.7% lower** (0.0983s vs 0.1032s).
- Memanto used **0 extraction LLM tokens** vs **134,690** native Ollama tokens.
- Stale-value leakage remains visible in both systems and is reported rather than filtered from the audit.

## Headline metrics

| Backend | Coverage | Strict accuracy | Stale leak rate | Retrieved tokens | Query p95 | Ingest p95 | LLM tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| memanto-on-prem | 97.2% | 0.0% | 100.0% | 1779 | 0.0983s | 0.0049s | 0 |
| mem0-direct | 98.6% | 0.0% | 100.0% | 1783 | 0.1038s | 0.1463s | 0 |
| mem0-agentic | 69.4% | 11.1% | 88.9% | 1793 | 0.1032s | 93.1412s | 134690 |

## Per-query audit

### memanto-on-prem

| Query | Category | Coverage | Stale leak | Retrieved tokens |
| --- | --- | ---: | ---: | ---: |
| Q01 | current-state | 100.0% | yes | 103 |
| Q02 | current-state | 100.0% | yes | 110 |
| Q03 | current-state | 100.0% | yes | 90 |
| Q04 | current-state | 100.0% | yes | 85 |
| Q05 | current-state | 100.0% | yes | 102 |
| Q06 | current-state | 100.0% | yes | 97 |
| Q07 | current-state | 100.0% | yes | 101 |
| Q08 | current-state | 100.0% | yes | 113 |
| Q09 | current-state | 100.0% | yes | 97 |
| Q10 | current-state | 100.0% | yes | 95 |
| Q11 | current-state | 100.0% | yes | 96 |
| Q12 | historical | 100.0% | yes | 100 |
| Q13 | historical | 100.0% | yes | 103 |
| Q14 | historical | 100.0% | yes | 100 |
| Q15 | historical | 100.0% | yes | 103 |
| Q16 | multi-hop | 100.0% | yes | 90 |
| Q17 | multi-hop | 50.0% | yes | 106 |
| Q18 | multi-hop | 100.0% | yes | 88 |

### mem0-direct

| Query | Category | Coverage | Stale leak | Retrieved tokens |
| --- | --- | ---: | ---: | ---: |
| Q01 | current-state | 100.0% | yes | 97 |
| Q02 | current-state | 100.0% | yes | 103 |
| Q03 | current-state | 100.0% | yes | 90 |
| Q04 | current-state | 100.0% | yes | 86 |
| Q05 | current-state | 100.0% | yes | 107 |
| Q06 | current-state | 100.0% | yes | 104 |
| Q07 | current-state | 100.0% | yes | 101 |
| Q08 | current-state | 100.0% | yes | 115 |
| Q09 | current-state | 100.0% | yes | 95 |
| Q10 | current-state | 100.0% | yes | 95 |
| Q11 | current-state | 100.0% | yes | 94 |
| Q12 | historical | 100.0% | yes | 107 |
| Q13 | historical | 100.0% | yes | 96 |
| Q14 | historical | 100.0% | yes | 101 |
| Q15 | historical | 100.0% | yes | 103 |
| Q16 | multi-hop | 100.0% | yes | 90 |
| Q17 | multi-hop | 75.0% | yes | 111 |
| Q18 | multi-hop | 100.0% | yes | 88 |

### mem0-agentic

| Query | Category | Coverage | Stale leak | Retrieved tokens |
| --- | --- | ---: | ---: | ---: |
| Q01 | current-state | 0.0% | yes | 98 |
| Q02 | current-state | 100.0% | yes | 115 |
| Q03 | current-state | 100.0% | yes | 91 |
| Q04 | current-state | 100.0% | yes | 90 |
| Q05 | current-state | 100.0% | yes | 116 |
| Q06 | current-state | 0.0% | yes | 94 |
| Q07 | current-state | 0.0% | yes | 110 |
| Q08 | current-state | 100.0% | yes | 98 |
| Q09 | current-state | 100.0% | yes | 94 |
| Q10 | current-state | 0.0% | yes | 113 |
| Q11 | current-state | 100.0% | yes | 84 |
| Q12 | historical | 100.0% | no | 103 |
| Q13 | historical | 100.0% | yes | 95 |
| Q14 | historical | 100.0% | yes | 95 |
| Q15 | historical | 100.0% | no | 98 |
| Q16 | multi-hop | 33.3% | yes | 89 |
| Q17 | multi-hop | 50.0% | yes | 119 |
| Q18 | multi-hop | 66.7% | yes | 91 |

## Method notes

- Both systems receive the same 32 records in the same order.
- Both systems answer the same 18 queries with the same `top_k`.
- Accuracy is deterministic concept coverage, not an LLM judge.
- Strict accuracy requires full concept coverage and no stale-value match.
- Stale leak rate measures whether superseded values appear in retrieved context.
- Token counts use `cl100k_base` only as a fixed cross-system accounting unit.
- Latency excludes one warm-up pass and includes all configured repeated queries.
- Mem0 agentic LLM tokens are native Ollama `prompt_eval_count` and `eval_count`.
