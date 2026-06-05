# Memanto Benchmarks

This directory contains evaluation scripts to reproduce Memanto's reported benchmark results on standard long-term memory datasets.

## Setup

Install benchmark dependencies:

```bash
pip install -e ".[benchmark]"
```

You also need a valid Moorcheh API key set as `MOORCHEH_API_KEY` environment variable.

## Datasets

| Dataset | Description | Script | Reported Score |
|---------|-------------|--------|----------------|
| [LongMemEval](https://huggingface.co/datasets/moorcheh/long_mem_eval) | Long-term memory QA with temporal decay | `long_mem_eval.py` | 89.8% |
| [LoCoMo](https://huggingface.co/datasets/moorcheh/loco_mo) | Long-context memory | `loco_mo.py`¹ | 87.1% |

¹ Coming soon.

## Running

### LongMemEval

```bash
cd benchmarks
python long_mem_eval.py --agent-id my-bench-agent --num-samples 100
```

Arguments:
- `--agent-id`: Memanto agent ID to use (will be auto-created). Default: `bench-longmem`.
- `--num-samples`: Number of test samples to evaluate. Default: all.
- `--max-turns`: Max turns per session (for datasets that simulate multi-turn). Default: 10.
- `--output`: Path to save results JSON. Default: `results_long_mem_eval.json`.

Output: An accuracy score (percentage of correctly answered questions) and detailed per-sample results.

## Results

The script will print a summary like:

```
Accuracy: 89.8% (89/99 correctly answered)
```

And save the raw output to the specified JSON file for further analysis.

## Notes

- The evaluation uses Memanto's `remember` and `answer` primitives. No separate LLM is required.
- Sessions are managed automatically; a new session is created for each evaluation run.
- For reproducing published results, use the same dataset split as the Hugging Face datasets.
