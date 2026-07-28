# Migration summary

- Generated at: 2026-07-23T08:20:08.954349+00:00
- Source file: `data/source/langgraph_checkpoints.jsonl`
- LangGraph checkpoint records: 15
- Memory versions observed across checkpoints: 48
- Latest deduped memories exported: 6
- OKF mapped memories: 6
- Per-type breakdown: `{"commitment": 1, "decision": 1, "fact": 1, "instruction": 1, "preference": 2}`
- OKF output: `okf_bundle`

## Savings report

This local demo intentionally avoids paid APIs. The storage comparison below measures source checkpoint JSONL versus readable OKF markdown.

- Source checkpoint JSONL bytes: 62525
- OKF markdown bytes: 8270
- Compression ratio (OKF/source): 0.13

## Fidelity summary

Every exported OKF file keeps the source thread, checkpoint id, parent checkpoint id, step, confidence, tags, and the original evidence turn.
