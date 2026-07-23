# LangGraph checkpoints to OKF

This migration showcase adds a Path B adapter for a source Memanto does not
ship today: LangGraph checkpoint state. It demonstrates the freedom loop:

1. Run a real LangGraph workflow with `MemorySaver`.
2. Export the checkpoint tuples to JSONL.
3. Convert the latest deduped memory state into an OKF bundle.
4. Validate the bundle by loading it through Memanto's shipped
   `load_okf_bundle` and `map_okf` migration path.

The demo is offline and deterministic; no paid API key is required.

## Run

From the repository root:

```bash
pip install -e .
pip install -r examples/migrations/langgraph_checkpoints_to_okf/requirements.txt
python examples/migrations/langgraph_checkpoints_to_okf/run_demo.py
```

Generated artifacts:

- `data/source/langgraph_checkpoints.jsonl`: exported checkpoint records from
  the actual LangGraph run.
- `data/source/source_transcript.json`: the user turns that produced memory.
- `okf_bundle/`: portable, human-readable OKF markdown.
- `reports/migration-summary.md`: source count, mapped count, per-type
  breakdown, and storage comparison.
- `reports/mapping-table.md`: source-to-OKF mapping table.
- `reports/roundtrip-validation.md`: golden Q&A recall parity evidence.

To preview the resulting OKF bundle with Memanto's own importer:

```bash
memanto migrate okf examples/migrations/langgraph_checkpoints_to_okf/okf_bundle --dry-run
```

## Why this source matters

LangGraph agents often accumulate important operating context in checkpoints:
preferences, constraints, task commitments, decisions, and corrections. Those
records are useful but easy to strand inside a graph runtime. This adapter
turns the latest checkpoint memory state into plain markdown OKF, preserving
checkpoint lineage so users can audit where every memory came from.

## Mapping table

| LangGraph source | OKF / Memanto target | Fidelity note |
| --- | --- | --- |
| `memories[].id` | OKF `title`, `x_memanto.id` | Stable source identity is preserved. |
| `memories[].type` | OKF `type`, `x_memanto.type` | Unknown types fall back to `observation`. |
| `memories[].content` | Markdown body | Human-readable portable memory text. |
| `memories[].confidence` | `x_memanto.confidence` | Numeric confidence round-trips. |
| `memories[].tags` | OKF `tags` | Source tags stay filterable. |
| checkpoint ids | OKF `resource` plus provenance footer | Lineage stays auditable. |
| evidence turn | provenance footer | Recall claims point back to source data. |

## Round-trip validation

`validate_roundtrip.py` checks:

- source deduped memory count equals OKF entry count;
- Memanto's OKF loader maps every source memory back to a batch-remember row;
- golden Q&A snippets remain present after OKF load and mapping.

This is intentionally deterministic rather than LLM-judged, so maintainers can
run it in CI without model credentials.
