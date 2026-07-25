# Escape Hindsight lock-in with Memanto and OKF

This example adds a permanent migration path from a Hindsight memory bank to a
human-readable [Open Knowledge Format (OKF) 0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
bundle that Memanto's shipped importer consumes directly.

The included showcase runs a release copilot through eight dated sessions:
dates and owners change, a bad cache value is corrected, the agent performs two
staging rehearsals, and an explicit rollback policy emerges. Hindsight—not a
fixture generator—extracts and reconciles the memories. The adapter then proves
the `in → owned → portable` loop:

```text
source conversations
  → Hindsight retain + recall
  → live paginated API snapshot
  → OKF 0.2 bundle
  → memanto migrate okf --dry-run
  → Memanto import + shared-set recall
  → source/destination parity report + OKF re-export
```

## What is new

- A dependency-free adapter for both local and Hindsight Cloud banks.
- Offset pagination, bearer authentication, deterministic replay, and atomic
  output replacement.
- A full source snapshot and SHA-256 digest for auditability.
- Explicit Hindsight world → fact, experience → event, and observation →
  learning semantics.
- Invalidated memories preserved as deprecated OKF concepts without
  reactivating them in Memanto.
- A real local run using embedded PostgreSQL, Ollama, Hindsight retain/recall,
  Memanto's shipped dry-run importer, and a deterministic eight-question
  validation set.

See [MAPPING.md](MAPPING.md) for the loss and compatibility analysis.
The committed
[migration report](artifacts/beacon-live-run/evidence/migration-report.md)
publishes exact counts, byte sizes, and an explicit explanation of why no
provider savings figure is available for the direct-OKF path.

## Quick start: replay the committed source snapshot

Replay needs no Hindsight server, LLM, account, or API key:

```bash
cd /path/to/memanto
uv sync --group dev
uv run python examples/migrations/hindsight/adapter.py \
  --source-json examples/migrations/hindsight/artifacts/beacon-live-run/hindsight-okf/source/hindsight-memory-snapshot.json \
  --output /tmp/hindsight-okf
uv run memanto migrate okf /tmp/hindsight-okf --dry-run
```

The first command regenerates the committed bundle byte-for-byte.

## Reproduce the real source run

Prerequisites:

- Python 3.12 and [`uv`](https://docs.astral.sh/uv/)
- [Ollama](https://ollama.com/) running locally
- about 5 GB of free disk space for Hindsight dependencies and the local model

One-time setup from the repository root:

```bash
uv sync --group dev
ollama pull qwen3:4b
uv venv --python 3.12 examples/migrations/hindsight/.hindsight-venv
uv pip install \
  --python examples/migrations/hindsight/.hindsight-venv/bin/python \
  -r examples/migrations/hindsight/requirements.txt
```

Run the whole source-to-dry-run pipeline:

```bash
examples/migrations/hindsight/.hindsight-venv/bin/python \
  -m examples.migrations.hindsight.run_demo \
  --reset-bank \
  --force
```

The first Hindsight startup downloads its local embedding model and may take a
few minutes. No paid service or external LLM is used. `--reset-bank` deletes
only the isolated `beacon-release-copilot` demo bank.

The command:

1. warms the local Ollama model;
2. starts Hindsight with its real embedded PostgreSQL API;
3. feeds eight source conversations through `retain`;
4. queries Hindsight with the shared golden set;
5. reads active and invalidated records through the paginated list API;
6. creates and validates the OKF bundle;
7. invokes `memanto migrate okf --dry-run` and saves the terminal transcript.

## Prove the real Memanto round trip

After configuring a free Moorcheh API key, run the whole cloud round trip with
one fresh agent ID:

```bash
export MOORCHEH_API_KEY="your-free-key"
uv run python -m examples.migrations.hindsight.run_roundtrip \
  --agent hindsight-okf-beacon-yourname
```

Memanto also reads the key from `~/.memanto/.env`, which avoids keeping it in
shell history. The key is never copied into a transcript or generated bundle.

That command creates the isolated agent, imports the committed bundle, waits
for every row to be indexed, runs the shared eight-question validation, and
exports the resulting Memanto agent and evidence to the git-ignored
`artifacts/local-roundtrip-run/`. To regenerate the committed live evidence,
add `--output examples/migrations/hindsight/artifacts/beacon-live-run`.

The same flow can also be run one step at a time:

```bash
uv run memanto agent create hindsight-okf-beacon \
  --pattern project \
  --description "Hindsight to OKF migration verification"
uv run memanto migrate okf \
  examples/migrations/hindsight/artifacts/beacon-live-run/hindsight-okf \
  --agent hindsight-okf-beacon
uv run python examples/migrations/hindsight/validate_memanto.py \
  --agent hindsight-okf-beacon
```

The validator waits for all imported rows to become visible, runs the same
eight questions used against Hindsight, writes both raw result sets, and
publishes a per-question score delta in `evidence/recall-parity.{json,md}`.
It exits nonzero if any destination question is not a full pass.

The round-trip command also checks that Memanto's re-export contains exactly
the same number of concepts as the imported bundle. It protects existing
agents and non-empty export directories rather than silently overwriting them.

## Migrate your own bank

Local Hindsight:

```bash
python examples/migrations/hindsight/adapter.py \
  --base-url http://localhost:8888 \
  --bank-id my-agent \
  --output ./my-agent-okf
```

Hindsight Cloud or an authenticated server:

```bash
export HINDSIGHT_API_TOKEN="..."
python examples/migrations/hindsight/adapter.py \
  --base-url https://your-hindsight-api.example \
  --bank-id my-agent \
  --output ./my-agent-okf
```

By default, both active and invalidated records are captured. Use
`--valid-only` only when the audit archive is intentionally out of scope.
Existing non-empty output is protected unless `--force` is explicit.

Offline replay:

```bash
python examples/migrations/hindsight/adapter.py \
  --source-json ./hindsight-memory-snapshot.json \
  --output ./replayed-okf
```

The snapshot accepts the adapter schema, a raw Hindsight list response, or a
raw JSON list. Supply `--bank-id` when a raw file does not identify its bank.

## Output

```text
hindsight-okf/
├── index.md
├── migration-manifest.json
├── source/
│   └── hindsight-memory-snapshot.json
├── memories/
│   ├── index.md
│   ├── event/
│   ├── fact/
│   ├── learning/
│   └── observation/
└── archive/
    └── invalidated/
```

Only directories that contain records are emitted. Every concept is plain
Markdown with parseable YAML frontmatter. Filenames combine a readable slug
with a stable hash of the Hindsight ID, so duplicate titles cannot overwrite
one another.

## Validation

Run the focused tests:

```bash
uv run pytest tests/test_hindsight_okf_adapter.py -q
uv run python -m examples.migrations.hindsight.verify_artifacts
```

They cover:

- all type mappings and Memanto's real OKF loader/mapper;
- source-field and OKF 0.2 provenance preservation;
- invalidation isolation;
- deterministic replay and protected/atomic replacement;
- malformed input and duplicate IDs;
- live HTTP pagination and bearer authentication;
- deterministic golden-set scoring.

The artifact verifier also rebuilds the committed OKF bundle from its source
snapshot and byte-compares every file. After a live cloud run, pass
`--require-roundtrip` to require 100% destination recall retention and an
equal-count Memanto OKF re-export. For the default local output, also pass
`--roundtrip-artifacts examples/migrations/hindsight/artifacts/local-roundtrip-run`.

The showcase calls Hindsight recall before migration and records every result.
Its scores are explicit phrase-group coverage, not an LLM grading its own
answer. Both sides score the top 10 raw retrieval results for each question;
the live Memanto report uses the identical questions and result cap.

## Privacy and security

The source snapshot contains the original memory text and metadata. Review it
before publishing a bundle built from a private bank. Authentication tokens are
read from the environment, used only as `Authorization: Bearer ...`, and never
written to the snapshot, manifest, or OKF files.
