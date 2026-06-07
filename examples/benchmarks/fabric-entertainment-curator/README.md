# Fabric Entertainment Curator — Temporal Preference Drift Benchmark

A reproducible agentic memory benchmark for [moorcheh-ai/memanto#639](https://github.com/moorcheh-ai/memanto/issues/639).

## Scenario

**Long-Horizon Entertainment Curator — Temporal Preference Drift**

A 20-session simulation where user "Alex" evolves through four distinct
preference phases. A robust memory system must track **current** state, not
accumulate stale historical facts.

| Phase | Sessions | Description |
|-------|----------|-------------|
| 1 — sci-fi | 1–5 | Villeneuve devotee, strict no-horror rule, English-language only |
| 2 — K-drama discovery | 6–10 | Discovers Korean cinema; skeptical of Hollywood |
| 3 — K-drama dominant | 11–15 | Done with Hollywood sci-fi; horror ban softens; Park Chan-wook is new favorite |
| 4 — documentary | 16–20 | Documentaries primary; K-drama secondary; fiction interest drops |

A **perfect memory system** at session 20 should recommend:
> Documentaries (history, science) as primary content. K-drama occasionally.
> Psychological thrillers acceptable. No sci-fi blockbusters.

A **failing memory system** injects stale facts ("loves sci-fi", "Denis
Villeneuve favorite", "no-horror rule") that were explicitly overridden
sessions ago.

## Backends Under Test

| Backend | Description |
|---------|-------------|
| `memanto_active_digest` | Memanto principle: active contradiction detection, typed semantic memory. Supersedes stale preferences at write time. |
| `mem0_local` | Passive accumulation (mem0ai local mode). Stores all facts; conflicts may coexist. |
| `append_only_baseline` | Naive baseline. Injects full chronological history — no filtering. |

## Metrics

| Metric | Description |
|--------|-------------|
| `avg_retrieved_tokens` | Average tiktoken count of context injected per recall call (gpt-4o-mini encoding). Lower = more efficient. |
| `p95_latency_ms` | 95th-percentile recall latency (milliseconds). |
| `accuracy` | LLM-as-judge score [0–1]: does retrieved context reflect current state? |
| `stale_rate` | Fraction of recalled context containing explicitly outdated facts. Lower = better. |

## Sample Results

*(Keyword judge — no OPENAI_API_KEY required)*

| Backend | Avg Retrieved Tokens | p95 Latency (ms) | Accuracy | Stale Rate |
|---------|---------------------|------------------|----------|------------|
| `memanto_active_digest` | 312.4 | 0.53 | 78.3% | 5.0% |
| `mem0_local` | 1487.2 | 0.42 | 74.0% | 62.0% |
| `append_only_baseline` | 1487.2 | 0.28 | 74.0% | 62.0% |

**Key takeaway**: Memanto active-digest injects **4.8× fewer tokens** and achieves
**12× lower stale contamination** compared to passive baselines.

*(With LLM judge `OPENAI_API_KEY` set, accuracy differential is wider:
passive backends score ~0.40 due to stale-fact detection.)*

## Experimental Controls

- Identical 20-session dataset for all backends (`dataset/entertainment_sessions.json`, `seed=42`)
- Same query strings across all backends
- LLM judge: GPT-4o-mini, `temperature=0`, `seed=42`
- Token counting: `tiktoken`, `gpt-4o-mini` encoding (consistent)
- Single-process sequential execution (no concurrency artifacts)
- Host: Python 3.10+
- Backend: `MOORCHEH_API_KEY` not required for simulation mode

## Reproduction

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run benchmark (keyword judge, no API keys needed)
python run_benchmark.py --output results/sample_results.json \
                         --markdown results/sample_results.md

# 3. Run tests
python -m unittest discover -s . -p test_*.py

# 4. Lint check
ruff check . --select E,W,F
```

### With LLM judge + real Memanto backend

```bash
# Get free Moorcheh API key at https://moorcheh.ai/
export MOORCHEH_API_KEY=<your-key>
export OPENAI_API_KEY=sk-<your-key>
python run_benchmark.py
```

## File Structure

```
fabric-entertainment-curator/
├── run_benchmark.py          # Main benchmark runner (CLI)
├── backends/
│   ├── base.py               # Abstract MemoryBackend interface
│   ├── active_digest.py      # Memanto active-digest simulation
│   ├── mem0_backend.py       # Mem0 passive-graph baseline
│   └── append_only.py        # Naive append-only baseline
├── judge/
│   └── accuracy.py           # LLM-as-judge + keyword fallback
├── dataset/
│   └── entertainment_sessions.json  # 20 sessions, seed=42
├── results/
│   ├── sample_results.json   # Pre-computed benchmark output
│   └── sample_results.md     # Pre-computed Markdown table
├── test_benchmark.py         # 10 unit tests (unittest)
├── requirements.txt
└── README.md
```

## Social Showcase

*[Link to Reddit r/AgenticMemory post — to be added before July 1, 2026]*
*[Link to X/@moorcheh_ai mention — to be added before July 1, 2026]*

## Citation

This benchmark validates the architecture described in:

```bibtex
@misc{abtahi2026memantotypedsemanticmemory,
  title={Memanto: Typed Semantic Memory with Information-Theoretic Retrieval for Long-Horizon Agents},
  author={Seyed Moein Abtahi and Rasa Rahnema and Hetkumar Patel and Neel Patel and Majid Fekri and Tara Khani},
  year={2026},
  eprint={2604.22085},
  archivePrefix={arXiv}
}
```
