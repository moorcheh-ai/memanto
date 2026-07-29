# LangGraph SQLite checkpoints to Memanto OKF

This example adds a reusable migration path from LangGraph's
`SqliteSaver` checkpoints to a portable, human-readable Open Knowledge Format
(OKF) bundle accepted by the shipped `memanto migrate okf` command.

The adapter uses LangGraph's public `SqliteSaver.list` interface and opens the
source database read-only. It never queries LangGraph's private checkpoint
tables and never overwrites an existing output directory.

## What the demonstration contains

`generate_demo.py` runs a real LangGraph `StateGraph` backed by
`SqliteSaver`. Eleven turns across three threads build up messages, profile
facts, preferences, project facts, and decisions. One preference changes from
an aisle seat to a window seat so the migration proves that the latest
materialized checkpoint state wins.

The checked-in artifacts were produced by that run:

- `artifacts/demo-checkpoints.sqlite`: the actual LangGraph checkpoint store.
- `artifacts/demo-okf/`: 34 importable, one-file-per-memory OKF records.
- `artifacts/recall-parity.json`: five deterministic golden questions.

The committed dry run maps all 34 nodes without loss:

```text
OKF nodes: 34
Mapped memories: 34 (skipped 0)
Type breakdown: decision: 2, event: 22, fact: 5, preference: 5
```

The five source-vs-OKF artifact checks all pass (`recall_parity: 1.0`). This
check verifies adapter fidelity before a network import; the live Memanto
recall step is documented separately below and requires the user's own agent.

## Mapping

| LangGraph checkpoint concept | OKF/Memanto mapping | Preservation details |
| --- | --- | --- |
| `messages` channel | one `event` per message | role, message ID, content, thread, checkpoint ID, and namespace |
| channel containing `profile` | `fact` | each profile field becomes a separate record |
| channel containing `fact` | `fact` | list entries and mapping values become separate records |
| channel containing `preference` | `preference` | current materialized value is preserved |
| channel containing `decision` | `decision` | structured fields remain readable markdown plus source metadata |
| channel containing `instruction` or `rule` | `instruction` | content and original channel/key are preserved |
| any other user channel | `observation` | safe default; override with `--channel-type CHANNEL=TYPE` |
| internal/branch channels | excluded | LangGraph execution internals are not user memory |

Every document also carries:

- a deterministic SHA-256-derived identity in its filename;
- a `langgraph://` resource URI;
- thread, channel, checkpoint, namespace, and role tags/metadata;
- `x_memanto.source: tool` and `x_memanto.provenance: imported`.

## Quick start

From this directory, using Python 3.10 or newer:

```bash
python -m venv .venv
python -m pip install -e ../../..
python -m pip install -r requirements.txt
python run_demo.py
```

`run_demo.py` creates a new timestamped directory under `local-runs/`, runs
the real LangGraph source, converts its latest checkpoints, validates the five
golden questions, and invokes the official Memanto OKF dry run. It refuses to
reuse an existing run directory.

To run each step separately:

```bash
python generate_demo.py ./source.sqlite
python migrate.py ./source.sqlite ./okf --exclude-channel event
memanto migrate okf ./okf --dry-run
python validate_roundtrip.py ./source.sqlite ./okf --report ./recall-parity.json
```

For a real application database, make a backup first and point `migrate.py` at
the SQLite file used by `SqliteSaver`. Select threads or customize mapping as
needed:

```bash
python migrate.py ./checkpoints.sqlite ./okf \
  --thread customer-42 \
  --exclude-channel transient_ui \
  --channel-type commitments=decision
```

The adapter reads the latest checkpoint for each `(thread_id, checkpoint_ns)`
pair. Review the generated markdown before importing it, especially when the
source contains secrets or personal data.

## Import and prove the full loop

Dry-run first:

```bash
memanto migrate okf ./okf --dry-run
```

Then activate a disposable Memanto agent and perform the real import:

```bash
memanto agent activate <agent-id>
memanto migrate okf ./okf
```

Ask the five questions listed in `validate_roundtrip.py`, then export that
agent back to portable OKF:

```bash
memanto memory export --okf ./memanto-export
```

The challenge's live demo should record the source answers, the dry-run
summary, the real import, the same post-import answers, and the exported
markdown. Do not publish a real checkpoint database without reviewing it for
private content.

## Savings report

The shipped OKF importer intentionally provides a mapping summary rather than
provider-specific token, latency, or storage estimates. This example therefore
reports exact record counts and recall parity only. It does not invent a
savings baseline that LangGraph checkpoints do not supply.

## Tests and quality checks

From the repository root:

```bash
pytest examples/migrations/langgraph-checkpoints/tests/test_adapter.py -q
ruff check examples/migrations/langgraph-checkpoints
ruff format --check examples/migrations/langgraph-checkpoints
mypy --ignore-missing-imports --follow-imports=skip \
  examples/migrations/langgraph-checkpoints/*.py
```

The tests generate fresh checkpoint databases through LangGraph, validate
Memanto's shipped OKF loader and mapper, verify corrected-state fidelity and
thread filtering, and confirm that non-empty output cannot be overwritten.
