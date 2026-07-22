# Escape LangGraph checkpoints into portable OKF

This example turns a real LangGraph SQLite checkpoint history into readable,
git-friendly Open Knowledge Format files. It proves the complete local half of
the freedom loop:

`LangGraph threads -> latest owned state -> OKF bundle -> Memanto dry run`

The source is not a hand-written export fixture. `generate_source.py` runs a
real `StateGraph` through seven turns across two persistent threads. One thread
also corrects an earlier preference from PDF to Markdown. LangGraph writes all
checkpoints through its official sync `SqliteSaver`.

## Adapter scope

- Official sync SQLite `SqliteSaver` only, not Postgres, Redis, or Async
  checkpointers.
- Latest checkpoint state per `(thread_id, checkpoint_ns)` only, not a full
  checkpoint-history migration.
- Proven channels in this demo: `messages` → artifact transcripts;
  profile → preference; `decisions`; fact-shaped channels; `goals`.
- `commitments` / `tasks` naming is a heuristic mapping covered by a focused
  fixture test, but it is not exercised by the live cloud demo.
- Non-JSON / non-`BaseMessage` values are rendered with `repr()` and should be
  reviewed before import.
- No token, latency, or billing savings are claimed from the OKF importer.

See [MAPPING.md](MAPPING.md) for the complete field mapping.

## What this adds

- A reusable adapter for LangGraph sync SQLite checkpoints whose latest state
  uses LangChain messages and JSON-friendly built-in values.
- Read-only source handling through SQLite's online backup API.
- Deserialization through LangGraph's public `SqliteSaver.list` API.
- Strict MessagePack mode, as recommended by LangGraph for safer imports.
- Explicit mapping for the proven demo channels above. Unsupported Python
  objects are rendered with `repr()` and should be reviewed before import.
- A valid OKF bundle with source URIs, timestamps, tags, and `x_memanto`
  round-trip metadata.
- Golden-question validation that proves the corrected and accumulated state is
  still present after conversion.

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

`record_live_terminal.py` resolves the example and repository virtualenv
interpreters the same way: it prefers `.venv/Scripts/python.exe` on Windows and
`.venv/bin/python` (or `python3`) on macOS/Linux.

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
deserialize only the snapshot. For each `(thread_id, checkpoint_ns)` it migrates
the latest state, which is what the live agent would recall.

## Preview the Memanto import

From the repository root, after running the demo (local preview of the
top-level generated bundle):

```bash
memanto migrate okf \
  ./examples/migrations/langgraph-checkpoints/artifacts/langgraph-okf \
  --dry-run
```

During a live evidence run, the recorder stages that bundle under
`artifacts/runs/<run-id>/langgraph-okf/` and dry-runs / imports **that staged
path**, not the mutable top-level copy.

The dry run validates the bundle through Memanto's shipped loader and writes a
fully inspectable preview without storing anything. To import for real, activate
an agent and repeat the command without `--dry-run`.

Then export the same agent again:

```bash
memanto memory export --okf
```

The verified reference run under
`artifacts/runs/20260722T223523Z-27da3254/` contains the real cloud export.
It contains the same eight memories as the staged first bundle, and its parity
report passes all five identical questions.

Historical note for that run only: the live cast and `run-manifest`
`evidence_report` step record the report as printed during the command (no
`Memanto import:` line yet). The committed `migration-evidence.{json,md}` also
includes `memanto_import` parsed from the same run's measured `cloud_import`
CLI output (`Imported: 8 Failed: 0`, visible earlier in the cast/manifest).
That attachment happened after the cast was written; it is measured, not
invented. Newer recorder runs capture `cloud-import-output.txt` and pass it
into `build_evidence_report.py` before cast/video so those artifacts match.

Build the measured evidence report after a cloud round trip with:

```bash
# Prefer the run-scoped artifacts produced by record_live_terminal.py
.venv\Scripts\python build_evidence_report.py \
  --source artifacts/runs/<run-id>/langgraph-checkpoints.sqlite \
  --source-bundle artifacts/runs/<run-id>/langgraph-okf \
  --roundtrip-bundle artifacts/runs/<run-id>/memanto-roundtrip-okf \
  --source-recall artifacts/runs/<run-id>/source-answers.json \
  --roundtrip-recall artifacts/runs/<run-id>/recall-parity.json \
  --run-id <run-id> \
  --import-output artifacts/runs/<run-id>/cloud-import-output.txt \
  --output-dir artifacts/runs/<run-id>
```

Run-scoped `migration-evidence.{json,md}` is canonical. Top-level
`artifacts/migration-evidence.*` is only a convenience copy of the latest
verified run (or is omitted). The report never invents Memanto import counts;
those appear only when parsed from real `memanto migrate` CLI output
(`Imported: N Failed: M`). It does not claim token, latency, or billing savings
because the OKF importer does not emit those provider metrics.

Pre-reference top-level cast and round-trip files are quarantined under
`artifacts/legacy/`. They are retained only as development history and must not
be cited as evidence. Submission evidence always comes from the verified
run-scoped directory below.

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
- the summary count matches the files in the OKF bundle;
- evidence reports embed `run_id` and do not invent `memanto_import`;
- demo-video helpers render type counts from the measured summary;
- the venv Python resolver finds `Scripts/python.exe` or `bin/python`.

## Captioned trailer vs live terminal cast

Two different video artifacts exist:

1. **Captioned trailer** — `build_demo_video.py` reads the local migration
   summary / content-coverage report and renders
   `artifacts/langgraph-memory-escape.mp4`. This is a short walkthrough, not
   acceptance evidence.
2. **Live terminal cast** — `record_live_terminal.py` executes the real cloud
   round trip and writes `live-terminal-demo.{json,mp4}` inside
   `artifacts/runs/<run-id>/`. That cast is the required evidence artifact.

### Build the captioned trailer

```bash
.venv\Scripts\python -m pip install -e ".[video]"
.venv\Scripts\python build_demo_video.py
```

FFmpeg must be available on `PATH`. This trailer is not a substitute for the
required live terminal walkthrough.

### Record the live cloud round trip

```bash
.venv\Scripts\python record_live_terminal.py
```

The recorder creates a unique run id and agent namespace, then executes the real
source run, required OKF dry run against the staged run bundle, cloud import,
all five source and Memanto questions, OKF export, parity validation, and
evidence report. One directory at `artifacts/runs/<run-id>/` holds the raw
answers, round-trip bundle, report, terminal cast, video, hashes, command
output, and timestamps. It captures real timings, redacts local paths, and
never reads or displays the API key.

## Verified reference run

The committed run
[`20260722T223523Z-27da3254`](artifacts/runs/20260722T223523Z-27da3254/)
is one continuous execution. It freezes the exact source database and first OKF
bundle before the dry run, then records the measured checkpoint/memory counts,
successful imports parsed from CLI output, memories exported back to OKF, and
5/5 identical questions passing before and after migration.

- [Run manifest with command output and hashes](artifacts/runs/20260722T223523Z-27da3254/run-manifest.json)
- [Measured migration report](artifacts/runs/20260722T223523Z-27da3254/migration-evidence.md)
- [Before and after answers](artifacts/runs/20260722T223523Z-27da3254/recall-parity.json)
- [Auditable terminal cast](artifacts/runs/20260722T223523Z-27da3254/live-terminal-demo.json)
- [Rendered live terminal video](artifacts/runs/20260722T223523Z-27da3254/live-terminal-demo.mp4)

Older runs under `artifacts/runs/` remain for audit history but are
**not** the verified reference.

## Demo video shot list

1. Open `generate_source.py` and show the seven real LangGraph turns.
2. Run `python run_demo.py` in a clean `artifacts` directory.
3. Show the checkpoint count and the two discovered thread IDs.
4. Open the Markdown preference file and show that Markdown replaced PDF.
5. Open the transcript artifact and one source `langgraph://` URI.
6. Show local content coverage at `1.0`, then the cloud parity report at `1.0`.
7. Run `memanto migrate okf ... --dry-run` from the repository root against the
   staged run bundle.
8. Open Memanto's mapped preview and show the retained types and tags.

This sequence is short enough for a two-minute screen recording while still
showing the real pipeline rather than slides.
