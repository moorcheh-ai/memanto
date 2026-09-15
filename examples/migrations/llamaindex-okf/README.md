# LlamaIndex Memory → Memanto → portable OKF

This example adds a permanent migration path for the current LlamaIndex
`Memory` API and its `SQLAlchemyChatStore`. It reads the real SQLite store,
preserves each message's text, session, role, status, order, and
`additional_kwargs`, and emits a human-readable Open Knowledge Format (OKF)
bundle accepted by `memanto migrate okf`.

The offline showcase costs nothing and calls no LLM. The source database is
created by running LlamaIndex itself, rather than by hand-writing an export.

## What the demo proves

1. `generate_source.py` creates two lived-in LlamaIndex memory sessions through
   `Memory.from_defaults(...)` and `Memory.put(...)`.
2. `migrate_to_okf.py` opens that SQLite store read-only and converts every
   message to one OKF memory document.
3. `validate_round_trip.py` compares source and target field by field and runs a
   six-question golden recall set.
4. The resulting bundle feeds the shipped `memanto migrate okf` command; the
   adapter does not bypass or reimplement Memanto's importer.

The included sample run contains 13 source records (including three that
LlamaIndex moved through its real active-to-archived waterfall), 13 mapped
memories, zero skips, 100% record recall, and 100% golden-question recall.

## Quick start (under 15 minutes)

From this directory, using Python 3.10 or newer:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run_demo.py
```

For a byte-for-byte pinned Python 3.12 demo environment, install
`requirements-lock.txt`. The smaller `requirements.txt` remains the portable
minimum for users integrating the adapter into an existing environment.

The command prints the run directory and the exact next command. Preview what
Memanto will import, without making any server write:

```bash
memanto migrate okf <run-dir>/okf-bundle --dry-run
```

For the complete live ownership loop, configure the free Memanto/Moorcheh
account as described in the main project docs, then run:

```bash
memanto migrate okf <run-dir>/okf-bundle --agent <agent-id>
memanto memory export --okf
```

Open any Markdown document in the exported bundle: the memory is readable,
versionable, and no longer tied to LlamaIndex's database schema.

## Bring your own LlamaIndex database

The adapter expects the schema used by LlamaIndex core 0.14's
`SQLAlchemyChatStore` (`llama_index_memory` by default):

```bash
python migrate_to_okf.py /path/to/llamaindex.sqlite ./my-okf-bundle
python validate_round_trip.py /path/to/llamaindex.sqlite ./my-okf-bundle \
  --golden golden_qa.json --report fidelity-report.json
memanto migrate okf ./my-okf-bundle --dry-run
```

The converter refuses to overwrite an existing output directory and opens the
source database in SQLite read-only mode.

To reproduce the lock-in and recovery story without a paid model:

```bash
python show_portability.py ./source.sqlite ./my-okf-bundle
```

The command proves the same golden recall sequence shown in the demo:
LlamaIndex source `6/6` → fresh tool without an export `0/6` → portable OKF
`6/6`.

## Mapping table

| LlamaIndex concept | Memanto type | OKF representation |
| --- | --- | --- |
| Message text blocks | Explicit type or deterministic fallback | Markdown body |
| `additional_kwargs.memory_type` | Same type when supported | `type` and `x_memanto.type` |
| Session key | Tag and provenance | `session:<id>` tag, `x_llamaindex.session_id` |
| Message role | Fallback classification and tag | `role:<role>`, `x_llamaindex.role` |
| Active/archived status | Source status | `x_llamaindex.status`, `x_memanto.status` |
| Timestamp and row id | Creation time and source reference | `timestamp`, `resource` |
| Tool metadata / arbitrary kwargs | Preserved source extension | `x_llamaindex.additional_kwargs` |
| Database order | Stable conversation order | `x_llamaindex.order` |

If a message has no explicit supported `memory_type`, the adapter uses small,
documented deterministic rules: preferences, decisions, goals, instructions, and
commitments are recognized by phrases; tool messages become artifacts;
assistant messages become observations; remaining messages become facts.
Memanto can still auto-classify or refine these after import.

### Human-reviewed fallback decision

The submitter reviewed the ambiguous assistant-message fallback and explicitly
selected `observation` rather than `learning`. The rationale is that an
assistant reply records what the agent said or observed at that moment; it does
not prove that the content became a durable, validated learning. An explicit
supported `memory_type` still takes precedence over this fallback.

## Privacy and integrity

- The source database is never modified.
- Common email and secret patterns are redacted from text and metadata.
- Every generated document has a SHA-256 digest in
  `migration-manifest.json`.
- Unknown `additional_kwargs` are preserved under a namespaced OKF extension.
- No API key, paid model, remote service, or destructive action is required for
  the offline proof.

## Savings report

The official `memanto migrate okf` help states that OKF is a local file bundle
with no API key and no savings report. This Path B showcase therefore reports
the applicable values directly: zero remote API calls, zero remote writes in
dry-run mode, zero paid-model calls, and zero skipped records. It deliberately
does not invent token or latency savings that the OKF importer does not emit.

## Tests

From the repository root with its development dependencies installed:

```bash
pytest examples/migrations/llamaindex-okf/test_migration.py
```

The tests build a real LlamaIndex database in a temporary directory, migrate
it, assert 100% parity, run the golden questions, and verify overwrite safety.

## Reproducible demo video

The optional recorder executes the same pipeline, the official Memanto dry
run, an OKF document inspection, and the fidelity report. It then renders the
captured terminal output to an MP4; the adjacent text transcript makes every
frame auditable. It does not fabricate command results.

```bash
pip install -r requirements-demo.txt
python record_demo.py --output llamaindex-okf-demo.mp4
```
