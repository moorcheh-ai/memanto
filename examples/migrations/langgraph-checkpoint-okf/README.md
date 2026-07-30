# LangGraph Checkpoint to OKF Migration Showcase

This example is a reproducible migration path from a real
`langgraph-checkpoint-sqlite` database into a Memanto-compatible Open Knowledge
Format (OKF) bundle.

It targets the bounty path for unsupported sources: LangGraph checkpoints. The
source data is produced by actually running a LangGraph app with `SqliteSaver`;
the adapter then reads the checkpoint through LangGraph's serializer, extracts
durable memory channels, exports OKF markdown, and validates recall parity with
a deterministic golden Q&A set.

## What It Proves

- A LangGraph app can keep its memory in normal checkpoint channels.
- Those checkpoint memories can be exported into portable OKF markdown.
- The OKF bundle is human-inspectable and importable with `memanto migrate okf`.
- A golden Q&A set passes against both the source checkpoint and the OKF bundle.

## Quickstart

```bash
cd examples/migrations/langgraph-checkpoint-okf
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e ../../..
python run_showcase.py
```

On macOS/Linux, activate with:

```bash
source .venv/bin/activate
```

The runner writes:

- `sample_output/source/langgraph_memory.sqlite`
- `sample_output/okf_bundle/`
- `sample_output/validation/recall-parity-report.md`
- `sample_output/memanto_migrate_okf_dry_run.txt`

## Manual Steps

Generate the source checkpoint:

```bash
python generate_langgraph_checkpoint.py
```

Convert it to OKF:

```bash
python langgraph_checkpoint_to_okf.py sample_output/source/langgraph_memory.sqlite --output sample_output/okf_bundle
```

Validate source-to-OKF recall parity:

```bash
python validate_recall_parity.py --source-db sample_output/source/langgraph_memory.sqlite --okf-dir sample_output/okf_bundle
```

Preview Memanto import without writing memories:

```bash
memanto migrate okf sample_output/okf_bundle --dry-run
```

## Mapping Table

| LangGraph source | OKF field | Memanto import behavior |
| --- | --- | --- |
| `thread_id` | `tags`, `resource` | Preserved for provenance |
| `checkpoint_id` | `resource`, provenance footer | Preserved for traceability |
| checkpoint timestamp | `timestamp` | Becomes `created_at` when imported |
| memory `type` or channel name | `type`, `x_memanto.type` | Maps to Memanto memory type |
| memory `title` | `title` | Maps to Memanto title |
| memory `content` | markdown body | Maps to Memanto content |
| memory `tags` | `tags` | Maps to Memanto tags |
| memory `confidence` | `x_memanto.confidence` | Round-trips into Memanto confidence |
| extra source fields | body provenance block | Human-readable supporting data |

## Sample Result

The included sample run maps five LangGraph memories:

| Type | Count |
| --- | --- |
| decision | 1 |
| goal | 1 |
| instruction | 1 |
| preference | 2 |

The deterministic recall parity report scores 5/5 for the source checkpoint and
5/5 for the OKF bundle.

## Why This Is Useful

LangGraph checkpoints often contain the most valuable application state: user
preferences, decisions, goals, and instructions accumulated during agent runs.
This adapter gives that state an exit path into portable markdown without
requiring a bespoke migration for every LangGraph app.
