# Reference Results

`20260607T014457127413Z/` is a completed live Memanto-versus-Mem0 run:

- 3 seeds: `7`, `19`, and `43`
- 48 sessions per seed
- checkpoints at sessions `8`, `16`, `24`, `32`, and `48`
- 120 paired probes per backend
- top-k: `5`

The directory preserves the generated artifacts without modification:

- `config.json`: run parameters
- `environment.json`: host and package versions
- `raw_traces.jsonl`: every query, returned item, score, and read latency
- `write_traces.jsonl`: every write and write latency
- `summary.json` and `summary.csv`: aggregate metrics
- `report.md`: human-readable report

The run completed before the free Moorcheh account reached its API-request
limit. The later submission commit adds deterministic write IDs, bounded retry
handling for transient transport failures, and Git source metadata. Dataset
content, retrieval queries, golden scoring, and summary calculations are
unchanged. These original artifacts remain intact so reviewers can audit the
claim rather than relying on a rewritten report.
