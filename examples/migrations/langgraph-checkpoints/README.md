# Escape LangGraph checkpoints into portable OKF

This example turns a real LangGraph SQLite checkpoint history into readable,
git-friendly Open Knowledge Format files. It proves the complete local half of
the freedom loop:

`LangGraph threads -> latest owned state -> OKF bundle -> Memanto dry run`

The source is not a hand-written export fixture. `generate_source.py` runs a
real `StateGraph` through seven turns across two persistent threads. One thread
also corrects an earlier preference from PDF to Markdown. LangGraph writes all
checkpoints through its official `SqliteSaver`.

## What this adds

- A reusable adapter for LangGraph SQLite checkpoints whose latest state uses
  LangChain messages and JSON-friendly built-in values.
- Read-only source handling through SQLite's online backup API.
- Deserialization through LangGraph's public `SqliteSaver.list` API.
- Strict MessagePack mode, as recommended by LangGraph for safer imports.
- Explicit mapping for messages, profiles, decisions, goals, lists, and
  JSON-friendly application channels. Unsupported Python objects are rendered
  with `repr()` and should be reviewed before import.
- A valid OKF bundle with source URIs, timestamps, tags, and `x_memanto`
  round-trip metadata.
- Golden-question validation that proves the corrected and accumulated state is
  still present after conversion.

See [MAPPING.md](MAPPING.md) for the complete field mapping.

## Quick start

From this directory:

```bash
python -m venv .venv
# Windows
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python run_demo.py

# macOS or Linux
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python run_demo.py
```

The run creates:

```text
artifacts/
  langgraph-checkpoints.sqlite
  langgraph-okf/
    index.md
    memories/
    metrics/migration-summary.md
    migration-summary.json
  content-coverage-report.json
```

No API key is needed for this reproducible source run, conversion, or recall
test.

## Convert your own checkpoint database

Only convert a checkpoint database you trust and own. LangGraph checkpoints can
contain serialized application types.

```bash
langgraph-to-okf /path/to/checkpoints.sqlite ./my-agent-okf
```

The command refuses to replace an existing bundle. Pass `--force` only when
you intentionally want to rebuild that output directory.

The source database is never opened for writing. The adapter takes a consistent
SQLite snapshot, discovers every thread and namespace, and asks LangGraph to
deserialize only the snapshot. For each thread it migrates the latest state,
which is what the live agent would recall.

## Preview the Memanto import

From the repository root, after running the demo:

```bash
memanto migrate okf \
  ./examples/migrations/langgraph-checkpoints/artifacts/langgraph-okf \
  --dry-run
```

The dry run validates the bundle through Memanto's shipped loader and writes a
fully inspectable preview without storing anything. To import for real, activate
an agent and repeat the command without `--dry-run`.

Then export the same agent again:

```bash
memanto memory export --okf
```

The verified run under `artifacts/runs/20260722T210746Z-ab8e8c6f/` contains the
real cloud export. It contains the same eight memories as the staged first
bundle, and its parity report passes all five identical questions.

Build the measured evidence report after a cloud round trip with:

```bash
.venv\Scripts\python build_evidence_report.py
```

The report compares the raw SQLite file, the first OKF bundle, and the OKF
bundle exported back from Memanto. It does not claim token, latency, or billing
savings because the OKF importer does not emit those provider metrics.

## Validation evidence

`golden_qa.json` defines five identical questions spanning both threads,
including the corrected report format. `query_source.py` answers them from the
latest LangGraph checkpoint state. During the cloud run, `query_memanto.py`
asks Memanto those exact questions and saves its unmodified RAG answers.
`validate_parity.py` passes only when both sides contain every expected term.

Run the focused tests with:

```bash
pytest
```

The tests prove that:

- a real checkpoint database is generated and discovered;
- both threads become portable memories;
- the corrected preference wins;
- the source database is byte-for-byte unchanged;
- invalid SQLite files fail clearly;
- the summary count matches the files in the OKF bundle.

## Build the captioned trailer

The video builder reads the real migration summary and content-coverage report
produced by `run_demo.py`. It renders those results into a short captioned terminal
walkthrough without recording the desktop.

```bash
.venv\Scripts\python -m pip install -e ".[video]"
.venv\Scripts\python build_demo_video.py
```

The result is written to `artifacts/langgraph-memory-escape.mp4`. FFmpeg must be
available on `PATH`. This trailer is not a substitute for the required live
terminal walkthrough.

## Record the live cloud round trip

Run:

```bash
.venv\Scripts\python record_live_terminal.py
```

The recorder creates a unique run id and agent namespace, then executes the real
source run, required OKF dry run, cloud import, all five source and Memanto
questions, OKF export, parity validation, and evidence report. One directory at
`artifacts/runs/<run-id>/` holds the raw answers, round-trip bundle, report,
terminal cast, video, hashes, command output, and timestamps. It captures real
timings, redacts local paths, and never reads or displays the API key.

## Verified reference run

The committed run
[`20260722T210746Z-ab8e8c6f`](artifacts/runs/20260722T210746Z-ab8e8c6f/)
is one continuous execution. It freezes the exact source database and first OKF
bundle before the dry run, then records 21 checkpoints, 8 mapped memories, 8
successful imports, 8 memories exported back to OKF, and 5/5 identical
questions passing before and after migration.

- [Run manifest with command output and hashes](artifacts/runs/20260722T210746Z-ab8e8c6f/run-manifest.json)
- [Measured migration report](artifacts/runs/20260722T210746Z-ab8e8c6f/migration-evidence.md)
- [Before and after answers](artifacts/runs/20260722T210746Z-ab8e8c6f/recall-parity.json)
- [Auditable terminal cast](artifacts/runs/20260722T210746Z-ab8e8c6f/live-terminal-demo.json)
- [Rendered live terminal video](artifacts/runs/20260722T210746Z-ab8e8c6f/live-terminal-demo.mp4)

## Demo video shot list

1. Open `generate_source.py` and show the seven real LangGraph turns.
2. Run `python run_demo.py` in a clean `artifacts` directory.
3. Show the checkpoint count and the two discovered thread IDs.
4. Open the Markdown preference file and show that Markdown replaced PDF.
5. Open the transcript artifact and one source `langgraph://` URI.
6. Show local content coverage at `1.0`, then the cloud parity report at `1.0`.
7. Run `memanto migrate okf ... --dry-run` from the repository root.
8. Open Memanto's mapped preview and show the retained types and tags.

This sequence is short enough for a two-minute screen recording while still
showing the real pipeline rather than slides.
