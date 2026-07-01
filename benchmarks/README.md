# Memanto Benchmarking Suite
## Submission for Bounty #639 — $100

This benchmark suite pits **Memanto** against **Mem0** (a leading alternative)
in a rigorous, reproducible evaluation of agentic memory performance.

## Challenge Focus

Two scenarios as per the bounty requirements:

### Scenario A: Context-Overhead & Latency Sprint
Feed agents dense, shifting technical logs. Measure:
- Total tokens consumed per conversation turn
- Retrieval latency (p95)
- Memory precision under load

### Scenario B: Shifting Persona & Temporal Tracking
Build an evolving entertainment curator agent where user preferences
mutate across sessions. Measure:
- Preference retention accuracy over time
- Context window inflation
- Stale state detection

## Requirements

- Python 3.10+
- Memanto (`pip install memanto`)
- Mem0 (`pip install mem0ai`)
- Moorcheh API key (get one at https://moorcheh.ai)
- OpenAI API key (for LLM-as-a-Judge)

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set API keys
export MOORCHEH_API_KEY="your-key"
export OPENAI_API_KEY="your-key"

# Run Scenario A
python benchmark_a_context_latency.py

# Run Scenario B
python benchmark_b_persona_tracking.py

# Run full report
python run_all.py --output results.md
```

## Methodology

### Scientific Controls
- Same dataset runs through both Memanto and Mem0
- Identical LLM backend (GPT-4o) for both systems
- Fixed hardware/environment documented in each run
- 5-run warmup before measurement to normalize caching

### Metrics Collected
| Metric | Unit | Description |
|---|---|---|
| Total Tokens Ingested | count | Cumulative tokens sent to the memory system |
| Total Tokens Retrieved | count | Cumulative tokens returned by the memory system |
| p95 Latency | seconds | 95th percentile retrieval response time |
| Retrieval Accuracy | % | LLM-as-a-Judge score on correct vs hallucinated recall |
| Context Inflation Ratio | % | (actual tokens / baseline tokens) × 100 |

### Judgment
Each run outputs a structured table. The `run_all.py` script aggregates
results into a final Markdown report.

## Output Structure

```
results/
├── scenario_a/
│   ├── memanto_run1.json
│   ├── mem0_run1.json
│   └── comparison_table.md
├── scenario_b/
│   ├── memanto_run1.json
│   ├── mem0_run1.json
│   └── comparison_table.md
└── final_report.md
```
