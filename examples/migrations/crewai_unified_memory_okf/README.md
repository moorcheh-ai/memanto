# Escape current CrewAI unified memory to Memanto + OKF

This Path B showcase migrates the **current CrewAI 1.15.12 unified-memory
LanceDB format** into human-readable Open Knowledge Format (OKF), feeds the
bundle through Memanto's shipped `migrate okf` command, and verifies that the
semantic and provenance fields can be reconstructed exactly.

The included source is not a hand-authored JSON fixture. `generate_source.py`
runs CrewAI's public `Memory.remember`, `Memory.list_records`, and
`Memory.recall` APIs to create and query a real LanceDB store. A deterministic
local embedder makes the run free, offline, and repeatable; the LLM mock is
asserted to receive zero calls because every memory field is explicit.

## One-command reproduction

From this directory, with Python 3.10–3.13:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e ../../..
python run_demo.py
```

The run performs four visible steps:

1. populate a real CrewAI unified-memory LanceDB store;
2. migrate it to portable OKF Markdown;
3. run `python -m memanto migrate okf <bundle> --dry-run`;
4. verify exact SHA-256 reconstruction, Memanto field mappings, and golden
   top-3 recall parity.

Expected final line:

```text
Freedom loop complete: CrewAI -> owned OKF -> Memanto-ready
```

To reproduce the checked-in terminal recording from another real run:

```bash
python -m pip install -r requirements-video.txt
python record_demo.py
```

The complete run normally finishes in under two minutes after dependencies
are installed. No API key is required for generation, migration, validation,
or the Memanto dry-run.

**Demo:** [`artifacts/verified/demo.mp4`](artifacts/verified/demo.mp4) is an
18-second recording generated from a successful real run. It ends with the
separately verified live import, recall, and export totals.

## Use your own CrewAI store

CrewAI's default memory directory is usually resolved from its platform data
directory, or from `$CREWAI_STORAGE_DIR/memory` when that environment variable
is set. Point the adapter at the directory containing the `memories` LanceDB
table:

```bash
python migrate.py /path/to/crewai/memory ./my-okf-bundle
python -m memanto migrate okf ./my-okf-bundle --dry-run
```

Private CrewAI records are excluded by default. Include them only after
reviewing the destination:

```bash
python migrate.py /path/to/crewai/memory ./my-okf-bundle \
  --include-private --redact-secrets
```

`--force` is required to replace an existing output directory. Reads omit the
heavy vector column and are capped at 50,000 records unless the operator sets
a lower `--max-records` limit.

## What is preserved

All vector-free CrewAI fields are preserved in the OKF document: ID, content,
scope, categories, arbitrary nested metadata, importance, creation and access
times, source, and privacy flag. Embedding vectors are intentionally omitted
because they are derived, model-specific data that the destination retrieval
engine must regenerate. See [MAPPING.md](MAPPING.md) for the complete mapping
and its rationale.

The generated bundle has this layout:

```text
okf-bundle/
├── index.md
├── migration-manifest.json
├── MIGRATION_SUMMARY.md
└── memories/
    ├── index.md
    ├── decision/
    ├── error/
    ├── goal/
    ├── instruction/
    ├── learning/
    ├── preference/
    └── relationship/
```

Each memory remains reviewable Markdown. Each record also carries a canonical
source hash, while the manifest records its OKF file hash and mapping basis.

## Validation and tests

```bash
python -m pytest tests -v
python -m ruff check .
python -m ruff format --check .
```

`validate.py` uses Memanto's own OKF loader and mapper. It fails unless:

- source count = OKF count = mapped Memanto count;
- every source/declaration/reconstruction SHA-256 triple matches;
- type, confidence, tags, and source resource survive mapping;
- all six golden questions retrieve the expected record in the top three
  before and after portability.

The repository includes a verified run under `artifacts/verified/`, including
the real LanceDB source, the sample OKF bundle, the Memanto dry-run transcript,
and machine-readable and Markdown validation reports.

## Live import and export verification

The dry-run is credential-free. To complete a live import after configuring a
Memanto agent and Moorcheh key, run:

```bash
memanto migrate okf artifacts/latest/okf-bundle --agent crewai-escape
memanto memory export --okf --agent crewai-escape
```

The live step uses Memanto as the destination; the adapter never bypasses or
reimplements its migration CLI.

The checked-in verified run was also imported to a real Moorcheh namespace:
8/8 memories imported with zero failures, all six identical golden questions
returned the expected memory at rank 1, and the subsequent OKF export loaded
and mapped 8/8 memories with Memanto's own code. See
[`LIVE_MOORCHEH_REPORT.md`](artifacts/verified/evidence/LIVE_MOORCHEH_REPORT.md),
the machine-readable [`live-recall-report.json`](artifacts/verified/evidence/live-recall-report.json),
and the exported [`live-export`](artifacts/verified/live-export/) bundle.

## Privacy and limitations

- Migration is local and read-only with respect to the CrewAI database.
- Secret redaction is opt-in because silent mutation would violate fidelity.
- A redacted record correctly will not pass an exact-content hash check; the
  manifest reports its redaction count.
- The deterministic embedder is solely for the reproducible source run. The
  adapter reads stores produced by any embedding provider because vectors are
  not migrated.
- The bundled golden test proves deterministic content parity; the included
  live report separately proves authenticated import, retrieval, and export.
