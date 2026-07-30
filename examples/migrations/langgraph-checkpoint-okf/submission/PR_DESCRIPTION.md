# PR: Add LangGraph checkpoint to OKF migration showcase

## Summary

This PR adds a reproducible migration example for exporting durable LangGraph
checkpoint memory into a Memanto-compatible OKF bundle.

It includes:

- A deterministic LangGraph app that writes a real SQLite checkpoint using
  `langgraph-checkpoint-sqlite`.
- `langgraph_checkpoint_to_okf.py`, an adapter that reads checkpoints through
  LangGraph's `SqliteSaver` serializer and writes OKF markdown.
- A sample exported OKF bundle under `sample_output/okf_bundle`.
- A deterministic golden Q&A parity check comparing the source checkpoint and
  the OKF export.
- A captured `memanto migrate okf --dry-run` log.

## Migration Summary

- Source: LangGraph SQLite checkpoint
- Source thread: `founder-os-agent`
- Source turns: 5
- Mapped memories: 5
- OKF memory files: 5
- Type breakdown:
  - preference: 2
  - goal: 1
  - decision: 1
  - instruction: 1

## Validation

- Source checkpoint recall: 5/5
- OKF recall: 5/5
- Source-to-OKF parity: 100.0%

## Reproduce

```bash
cd examples/migrations/langgraph-checkpoint-okf
pip install -r requirements.txt
pip install -e ../../..
python run_showcase.py
```

## Demo Video

TODO: Add video link.

## Social Posts

TODO: Add public post links.
