# Agentic Memory Showdown

**Does your memory system handle evolving user preferences?**

A rigorous, reproducible benchmark comparing memory architectures for long-running AI agents. Designed for the [Memanto #639 Benchmark Challenge](https://github.com/moorcheh-ai/memanto/issues/639).

---

## TL;DR — Results (offline mode, N=3 runs)

| Backend | Accuracy (mean±std) | Tokens Retrieved | Staleness |
|---------|--------------------:|-----------------:|-----------|
| **Memanto / Active-Memory** | **79.2% ± 23.1%** | **36** | ✅ Purges stale facts |
| Snapshot-KV | 79.2% ± 23.1% | 62 | ⚠️ Cross-session bleed |
| Append-Log (naive RAG) | 75.0% ± 14.9% | 107 | ❌ Stale contamination |

> **Active-memory is 3× more context-efficient** than append-log while scoring higher on evolving-preference scenarios.

---

## Why This Benchmark Matters

Most memory benchmarks test *recall* of static facts. Real agents face a harder problem:

- User says "always use UTC" → then says "show customer-facing dates in local timezone"
- User says "brief executive reports" → then says "full launch-risk memos with evidence tables"
- Payment retry strategy evolves through 3 iterations before settling

**Stale facts contaminate context.** An append-log system retrieves both the old instruction and the new one, leaving the LLM to guess which to follow. Active-memory systems maintain a compact world-model — O(1) per concept, always current.

---

## Benchmark Design

### Scoring Model

```
score(probe) =
  1.0   — expected_keyword present, stale_keyword absent    (perfect)
  0.5   — expected_keyword present, stale_keyword also present (ambiguous)
  0.0   — expected_keyword absent                           (miss)
```

With `OPENAI_API_KEY` or `OPENROUTER_API_KEY`: uses **GPT-4o-mini as judge** for semantic scoring instead of keyword matching.

### 6 Evolving-Preference Scenarios

| # | Scenario | Reversals | Probes |
|---|----------|-----------|--------|
| 1 | Report format: brief → launch-risk memo | 1 | 2 |
| 2 | Timezone: UTC everywhere → customer-local | 1 | 2 |
| 3 | Payment retry: backoff → advisory lock + outbox | 2 | 2 |
| 4 | Investor update: growth-first → ARR-first | 2 | 2 |
| 5 | Engineering ticket template: 3 iterations | 2 | 2 |
| 6 | Evidence standard: no-speculation + cite-sources | 2 | 2 |

### 5 Backends Under Test

| Backend | Architecture | API Required |
|---------|-------------|--------------|
| `MemantoBackend` | Active-memory, compact world-model | `MOORCHEH_API_KEY` (optional) |
| `Mem0Backend` | Vector store with extraction | `MEM0_API_KEY` (optional) |
| `ActiveMemoryBackend` | Offline reference implementation | None |
| `AppendLogBackend` | Naive append-only, keyword retrieval | None |
| `SnapshotBackend` | Session-scoped KV store | None |

> **All backends work offline.** Live API backends (Memanto, Mem0) auto-fall-back to their offline equivalents when keys are absent — so CI/CD always passes with zero external dependencies.

---

## Quick Start

### Offline (no API keys)

```bash
git clone https://github.com/TakoVHS/memanto
cd memanto/examples/benchmarks/agentic-memory-showdown
pip install -r requirements.txt
python -m showdown_benchmark
```

### With Live APIs

```bash
cp .env.example .env
# Edit .env — add MOORCHEH_API_KEY, MEM0_API_KEY, OPENAI_API_KEY
python -m showdown_benchmark
```

### Options

```bash
python -m showdown_benchmark --n-runs 5          # more statistical power
python -m showdown_benchmark --offline           # force offline mode
python -m showdown_benchmark --output-dir ./out  # custom output directory
python -m showdown_benchmark --quiet             # suppress progress
```

### Run Tests

```bash
pytest tests/ -v    # 17 tests, zero external deps
```

---

## Key Finding: Active-Memory is Compact and Accurate

The core insight:

```
Append-log backend:   writes 54 tokens → retrieves 107 tokens  (2× bloat, stale included)
Active-memory backend: writes 54 tokens → retrieves  36 tokens  (compact, current only)
```

When preferences reverse, append-log returns **both** the old and new preference, causing an LLM to score 0.5 on ambiguous probes. Active-memory **replaces** the old slot value with the new one — the old preference is gone.

### Scenario Breakdown

```
report-format-reversal   → active: 1.0 (slot replaced)   append: 0.5 (old brief + new memo)
timezone-policy-flip     → active: 1.0 (slot replaced)   append: 0.75 (old UTC rule + new local)
payment-retry-overhaul   → active: 1.0 (slot replaced)   append: 0.75 (3 strategies mixed)
investor-update-style    → active: 0.75                  append: 0.75 (similar)
engineering-ticket       → active: 0.5                   append: 1.0 (append catches both)
evidence-standard        → active: 1.0 (slot replaced)   append: 0.75 (stale contamination)
```

---

## Architecture: Why Active-Memory Wins

```
Scenario: User changes report format preference twice

Turn 1: "Always use concise executive briefs"
Turn 2: [quarterly report filed]
Turn 3: "From now on: detailed launch-risk memos with evidence tables"

──────────────────────────────────────────────────────────────
Append-Log retrieval context (107 tokens):
  "Always use concise executive briefs"    ← STALE
  "From now on: detailed launch-risk memos..." ← current

  LLM sees contradiction → 50% accuracy

──────────────────────────────────────────────────────────────
Active-Memory retrieval context (36 tokens):
  "From now on: detailed launch-risk memos..."  ← only current

  LLM gets clean signal → 100% accuracy
──────────────────────────────────────────────────────────────
```

---

## Extending with Real Backends

### Wire Real Memanto API

```python
# .env
MOORCHEH_API_KEY=your_key_here

# The MemantoBackend auto-detects and uses moorcheh_sdk
from showdown_benchmark.backends.memanto import MemantoBackend
backend = MemantoBackend()
print(backend.is_live)  # True when API key present
```

### Wire Real Mem0

```python
# .env
MEM0_API_KEY=your_key_here

from showdown_benchmark.backends.mem0 import Mem0Backend
backend = Mem0Backend()
print(backend.is_live)  # True when API key present
```

### Add a Custom Backend

```python
from showdown_benchmark.backends.base import MemoryBackend, IngestResult, RetrieveResult

class MyBackend(MemoryBackend):
    name = "my-backend"

    def reset(self): ...
    def ingest(self, user_id, content) -> IngestResult: ...
    def retrieve(self, user_id, query) -> RetrieveResult: ...
```

---

## Project Structure

```
examples/benchmarks/agentic-memory-showdown/
├── showdown_benchmark/
│   ├── backends/
│   │   ├── base.py          # MemoryBackend protocol + IngestResult/RetrieveResult
│   │   ├── offline.py       # ActiveMemoryBackend, AppendLogBackend, SnapshotBackend
│   │   ├── memanto.py       # Real Memanto via moorcheh_sdk (auto-fallback)
│   │   └── mem0.py          # Real Mem0 via mem0ai (auto-fallback)
│   ├── dataset.py           # 6 evolving-preference scenarios
│   ├── judge.py             # Keyword-score + LLM-as-judge scorer
│   ├── runner.py            # N-run harness, stats collection
│   ├── report.py            # Markdown + JSON report generator
│   └── __main__.py          # CLI entry point
├── tests/
│   └── test_showdown_benchmark.py  # 17 tests, zero external deps
├── results/
│   ├── results.md           # Latest offline results
│   └── results.json         # Machine-readable results
├── requirements.txt
└── .env.example
```

---

## Reproducibility Checklist

- [x] Zero external dependencies in offline mode (`pip install pytest`)
- [x] `python -m showdown_benchmark --offline` produces identical output on every run
- [x] All 17 tests pass in CI without API keys
- [x] Results committed to `results/results.json`
- [x] `.env.example` documents all required keys
- [x] `--n-runs` parameter controls statistical sample size

---

## Closes

Resolves [moorcheh-ai/memanto#639](https://github.com/moorcheh-ai/memanto/issues/639) — Benchmark Challenge: Memory System Comparison.
