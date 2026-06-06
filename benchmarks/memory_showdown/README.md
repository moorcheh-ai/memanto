# The Great Agentic Memory Showdown

**Submission for [Issue #639](https://github.com/moorcheh-ai/memanto/issues/639) — $100 bounty**

A rigorous, reproducible benchmark that pits Memanto against Mem0 (and an optional Cathedral baseline) on the core challenge of 2026 agent infrastructure: tracking user preferences that **evolve and contradict** across sessions, while minimising token overhead.

---

## Scenario: The Shifting Persona & Temporal Tracking Test

> *"Build an agent where user preferences dynamically mutate or contradict over multiple distinct sessions. Measure preference retention accuracy over a long duration."*
> — Issue #639, Scenario B

An AI agent serves as a personal **entertainment curator**. The user's preferences shift across four write sessions:

| Session | Change |
|---------|--------|
| 1 | Loves action blockbusters + classic rock. Hates romance. |
| 2 | Discovers arthouse cinema. Blockbusters become secondary. |
| 3 | **Reversal**: burned out on action entirely. Pivots to psychological thrillers + jazz. |
| 4 | **New constraint**: foreign-language films only. Favourite directors named. |

After all writes, four probe questions test whether the system surfaces the **current** preferences and suppresses the outdated ones.

---

## Metrics

| Metric | What it measures |
|--------|-----------------|
| **Preference accuracy** | LLM-as-judge score 0–3 per probe (0=wrong prefs served, 3=perfectly current) |
| **Context tokens** | Prompt tokens attributable to injected memory context |
| **Total tokens** | Full token cost per LLM call (prompt + completion) |
| **Write latency p50/p95** | Wall-clock ms to store one preference fact |
| **Read latency p50/p95** | Wall-clock ms for semantic retrieval |

---

## Setup

```bash
pip install -r requirements.txt

export OPENAI_API_KEY=sk-...           # required for all frameworks
export MOORCHEH_API_KEY=...            # get free key at moorcheh.ai  (enables memanto)
export CATHEDRAL_API_KEY=...           # optional (enables cathedral baseline)
```

---

## Run

```bash
# Run all available frameworks
python benchmark.py

# Run specific frameworks
python benchmark.py --framework mem0 memanto

# Print results table from saved JSON
python benchmark.py --results

# Generate bar chart (requires matplotlib)
python benchmark.py --plot
```

Results are saved to `results/<framework>.json`. The benchmark is fully reproducible: re-running produces fresh JSON files.

---

## Environment

| Parameter | Value |
|-----------|-------|
| LLM backend | `gpt-4o-mini` (identical across all frameworks) |
| LLM judge | `gpt-4o-mini` (temperature=0) |
| Embedder | `text-embedding-3-small` (mem0 local mode) |
| Write sessions | 4 (11 memory facts total) |
| Probe questions | 4 |
| Mem0 mode | Local (no Mem0 API key required) |

All frameworks use the **identical LLM, prompting structure, and probe questions**. The only variable is the memory layer.

---

## Framework Details

### `raw_api` (baseline)
No memory. Each probe starts cold. Establishes the accuracy floor — what happens with zero preference context.

### `mem0`
Mem0 local memory. Uses `mem0ai` package in local mode (no API key needed). Stores all 11 preference facts across 4 sessions, then retrieves semantically relevant ones per probe.

### `memanto`
Memanto SDK with Moorcheh retrieval backend. Uses `remember()` / `recall()` pattern directly (no LangChain wrapper). Requires `MOORCHEH_API_KEY`.

### `cathedral` (optional)
Cathedral persistent memory API (`cathedral-ai.com`). Uses `/memories` write endpoint and semantic `/memories?search=` retrieval. Included as an additional reference point.

---

## Interpreting Results

- **Accuracy** is the primary metric. A score of 3.0/3.0 means the system correctly served *only* the current preferences on every probe, including suppressing the session-1 action/rock preferences that were later reversed.
- **Context tokens** reveal token efficiency: how much of the prompt budget the memory layer consumes per call.
- **Read latency** reveals retrieval overhead, which directly affects response time for production agents.

The accuracy/token trade-off is the core tension: a system that dumps all memories into context may score high accuracy but at prohibitive token cost.
