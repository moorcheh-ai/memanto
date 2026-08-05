# Temporal Memory Showdown

A live, reproducible benchmark of actual Memanto On-Prem and actual Mem0 OSS.
It tests a long-running research mission whose facts change across ten sessions.
The benchmark is designed to answer two separate questions:

1. How do the retrieval layers compare when both store the same raw memories?
2. What changes when Mem0's normal LLM extraction and reconciliation pipeline is enabled?

No backend is simulated. No LLM judges the results.

## Systems under test

| Backend | Storage path | Ingestion mode |
| --- | --- | --- |
| `memanto-on-prem` | Memanto `SdkClient` -> Moorcheh On-Prem | Typed `remember()` calls |
| `mem0-direct` | Mem0 2.0.5 -> local Qdrant | `infer=False`, raw memory |
| `mem0-agentic` | Mem0 2.0.5 -> local Qdrant | `infer=True`, Ollama extraction |

All three use `nomic-embed-text` through the same Ollama service. The agentic
Mem0 run uses `qwen2.5:1.5b`; its native Ollama input and output token counters
are captured without estimating them.

## Dataset

The synthetic Asteria mission contains 32 records across ten sessions. It has
eleven explicit state changes, including:

- crop: Genovese basil -> dwarf radish
- launch: August 14 -> September 2
- commander: Elena Park -> Priya Nair
- channel: Slack -> Matrix
- nutrient protocol: N-17 / pH 6.2 -> N-21 / pH 5.9
- landing site: Malapert Ridge -> Shackleton rim
- vendor: Helios / PO-81 -> Nova / PO-96
- valve procedure: V1 -> V3

The 18 golden queries cover current state, history, and multi-hop briefs.
Every answer is scored with required and forbidden concept groups. This makes
the result deterministic and exposes stale-value leakage directly.

## Metrics

- deterministic required-concept coverage
- exact query accuracy
- stale-value leak rate
- source and retrieved context tokens (`cl100k_base` accounting unit)
- native Ollama extraction tokens for agentic Mem0
- ingestion total, p50, and p95 latency
- time until the final update becomes searchable
- query mean, p50, and p95 latency after warm-up
- client process RSS delta
- paired bootstrap 95% confidence interval for coverage differences

## Reproduce

Prerequisites: Python 3.10+, Docker with Compose, and enough disk space for
`nomic-embed-text` plus `qwen2.5:1.5b`.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
pip install -r examples/benchmarks/temporal-memory-showdown/requirements.txt
```

Configure Moorcheh to use the same local Ollama models:

```bash
python - <<'PY'
from moorcheh.user_config import (
    EmbeddingConfig,
    LlmConfig,
    save_runtime_config,
)

save_runtime_config(
    EmbeddingConfig(provider="ollama", model="nomic-embed-text"),
    LlmConfig(provider="ollama", model="qwen2.5:1.5b"),
)
PY

python -m moorcheh up \
  --bundled-ollama \
  --embedding-provider ollama \
  --embedding-model nomic-embed-text
```

Run all systems:

```bash
python examples/benchmarks/temporal-memory-showdown/run_benchmark.py \
  --backends memanto,mem0-direct,mem0-agentic \
  --repeats 5
```

The runner writes machine-readable JSON and an audit-friendly Markdown table to
`results/latest.json` and `results/latest.md`.

Run only deterministic unit tests:

```bash
pytest examples/benchmarks/temporal-memory-showdown/tests -q
```

## Verified live result

The committed result was produced by
[GitHub Actions run 27441595257](https://github.com/2077196405-commits/memanto/actions/runs/27441595257)
on June 12, 2026, using a four-core Ubuntu runner:

| Metric | Memanto On-Prem | Mem0 agentic |
| --- | ---: | ---: |
| Golden concept coverage | 97.2% | 69.4% |
| Total ingestion time | 0.096s | 2912.082s |
| Query p95 | 0.0983s | 0.1032s |
| Retrieved context tokens | 1779 | 1793 |
| Extraction LLM tokens | 0 | 134,690 |

The paired coverage advantage is 27.8 percentage points, with a bootstrap 95%
confidence interval of 9.3 to 48.1 points. Memanto completed ingestion about
30,286 times faster while avoiding all extraction-model tokens.

`mem0-direct` reached 98.6% coverage, but it deliberately disables Mem0's
normal extraction and reconciliation (`infer=False`). It is included as a
vector-only ablation, not the primary agentic competitor.

The run also exposed a limitation worth keeping visible: raw top-five context
from every backend can contain superseded values. The report therefore
separates required-concept coverage from strict contradiction-free accuracy
instead of hiding stale-value leakage.

## Experimental controls

- same records, order, queries, and `top_k=5`
- same embedding model and Ollama service
- fresh Memanto agent and fresh Mem0 collection per run
- one warm-up query pass before measured latency samples
- first measured pass used for accuracy and context-token totals
- no answer-generation model and no LLM-as-a-judge
- fixed bootstrap seed and fixed tokenizer accounting unit

## Interpretation limits

The benchmark measures retrieval context, not final answer quality. Memanto's
server runs in Docker while Mem0's Qdrant runs in the Python process, so client
RSS is reported but is not treated as a total-system memory comparison.
`cl100k_base` is a stable cross-system accounting unit, not the native embedding
tokenizer. Exact internal LLM tokens are reported only where Ollama exposes
them.
