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

- A reusable adapter for any LangGraph SQLite checkpoint database.
- Read-only source handling through SQLite's online backup API.
- Deserialization through LangGraph's public `SqliteSaver.list` API.
- Strict MessagePack mode, as recommended by LangGraph for safer imports.
- Loss-aware mapping for messages, profiles, decisions, goals, lists, and
  unknown application channels.
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
  recall-report.json
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

## Validation evidence

`golden_qa.json` checks five facts that span both threads, including the
corrected report format. A successful run reports `recall_parity: 1.0`.

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

## Build the captioned demo video

The video builder reads the real migration summary and recall report produced by
`run_demo.py`. It renders those results into a short captioned terminal
walkthrough without recording the desktop.

```bash
.venv\Scripts\python -m pip install -e ".[video]"
.venv\Scripts\python build_demo_video.py
```

The result is written to `artifacts/langgraph-memory-escape.mp4`. FFmpeg must be
available on `PATH`.

## Demo video shot list

1. Open `generate_source.py` and show the seven real LangGraph turns.
2. Run `python run_demo.py` in a clean `artifacts` directory.
3. Show the checkpoint count and the two discovered thread IDs.
4. Open the Markdown preference file and show that Markdown replaced PDF.
5. Open the transcript artifact and one source `langgraph://` URI.
6. Show the recall report at `1.0`.
7. Run `memanto migrate okf ... --dry-run` from the repository root.
8. Open Memanto's mapped preview and show the retained types and tags.

This sequence is short enough for a two-minute screen recording while still
showing the real pipeline rather than slides.
