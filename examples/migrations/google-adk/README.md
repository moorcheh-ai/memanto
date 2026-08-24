# Google ADK → OKF → Memanto

Google ADK can persist an agent's session events and durable state in a local
SQLite database. This example turns that state into portable, reviewable OKF
without asking an LLM to reinterpret it.

The adapter reads the official `SqliteSessionService` database in read-only
mode. Current app, user, and session state becomes typed memory under
`memories/`; source conversations remain readable under `sessions/`; and old
values recovered from ADK's event log go to an audit-only `archive/`. That last
separation matters: importing the bundle cannot silently make a corrected date,
owner, or configuration active again.

## Verified result

The committed run was generated with Google ADK `2.6.0` on July 31, 2026.

| Evidence | Result |
|---|---:|
| Real ADK sessions | 8 |
| Persisted ADK events | 17 |
| Durable state updates | 13 |
| Current state records → OKF memories | 10 → 10 |
| Typed memories | 9 types |
| Corrected timelines isolated in audit archive | 3 |
| Golden questions answered from source state | 8/8 (100%) |
| Golden questions answered after OKF mapping | 8/8 (100%) |
| `memanto migrate okf --dry-run` | 10 mapped, 0 skipped |
| Artifact/checksum verification | pass |

See the [migration report](artifacts/adk-live-run/migration-report.json),
[recall parity evidence](artifacts/adk-live-run/evidence/recall-parity.json),
and [captured Memanto dry run](artifacts/adk-live-run/evidence/memanto-dry-run.txt).
The complete human-readable bundle starts at
[google-adk-okf/index.md](artifacts/adk-live-run/google-adk-okf/index.md).

## One-command reproduction

From the Memanto repository root, with
[uv](https://docs.astral.sh/uv/getting-started/installation/) installed:

```bash
uv run --group dev --with-requirements examples/migrations/google-adk/requirements.txt python examples/migrations/google-adk/run_demo.py --force
```

The command performs the whole offline proof:

1. creates a fresh SQLite store through Google ADK's public
   `SqliteSessionService` and `append_event` APIs;
2. runs eight time-evolving release-copilot sessions, including three
   corrections;
3. captures the database in read-only mode and writes a replayable JSON
   snapshot plus SHA-256 provenance;
4. builds the OKF bundle atomically;
5. validates the same eight questions against current source state and the
   Memanto-mapped OKF preview;
6. invokes the shipped `memanto migrate okf ... --dry-run` command; and
7. verifies every committed bundle file against the manifest.

No model or external service is required for this stage. The disclosure in
`evidence/source-run.json` records that the source run uses deterministic
scripted turns rather than pretending a hand-written export came from ADK.

## Migrate your own ADK database

The adapter itself uses only Python's standard library; Google ADK does not
need to be installed when converting an existing database.

```bash
python examples/migrations/google-adk/adapter.py \
  --db /path/to/sessions.db \
  --app your-app \
  --user your-user \
  --output ./your-google-adk-okf
```

Omit `--app` or `--user` to capture more scopes. Credential-like state fields,
including camelCase names such as `accessToken`, are replaced by a non-reversible
`<redacted>` marker. Use
`--include-sensitive` only for a private bundle you control.

Preview exactly what Memanto will ingest:

```bash
memanto migrate okf ./your-google-adk-okf --dry-run
```

Then import it into an agent:

```bash
memanto migrate okf ./your-google-adk-okf --agent your-agent
```

## Full cloud round trip

The final leg uses a free Moorcheh key and the shipped Memanto commands—not a
mock client. The key is read only from the environment and is never written to
the evidence files.

```bash
export MOORCHEH_API_KEY="..."
uv run --group dev python examples/migrations/google-adk/run_roundtrip.py
```

That script creates a dedicated Memanto agent, imports the bundle, executes all
eight recall questions (with bounded retries for indexing), and exports the
Memanto agent back to OKF. It writes `roundtrip-summary.json` and
`memanto-roundtrip-export/` under the run artifacts.

## Portability layout

```text
google-adk-okf/
├── memories/                 # only current truth; imported by Memanto
├── sessions/                 # readable ADK conversations; context only
├── archive/state-history/    # superseded values; audit only
├── source/                   # normalized replayable ADK snapshot
├── migration-manifest.json   # counts, source digest, per-file SHA-256
└── index.md
```

Memanto's OKF loader intentionally scopes a bundle containing `memories/` to
that directory. The transcripts and archive therefore stay owned and
inspectable without polluting active recall. The full field and type policy is
documented in [MAPPING.md](MAPPING.md).

## Source compatibility and failure behavior

This version is tested against the JSON-backed Google ADK `2.6.0`
`SqliteSessionService` schema (`app_states`, `user_states`, `sessions`, and
`events`). It validates every required table and column before reading. A
legacy SQLAlchemy/pickle database fails with an explicit instruction to run
ADK's documented `adk migrate session --source_db_url=... --dest_db_url=...`
command; it is never guessed at or partially converted. The adapter hashes the
database before and after the read and aborts if a concurrent writer changed it,
so the published digest cannot describe a different SQLite state.

Output replacement is opt-in with `--force` and uses a sibling staging
directory. A failed build leaves an existing bundle intact. Snapshot replay is
byte deterministic, and `verify_artifacts.py` checks both the recorded hashes
and the result of Memanto's real OKF loader/mapper.

## Honest limits

- ADK state is application-defined. A type prefix such as `decision.*` maps
  deterministically; unknown keys conservatively become `context`.
- Nested objects are kept intact as one concept unless they explicitly expose
  `content`, `title`, `tags`, or `confidence` fields.
- Temporary `temp:` state is never persisted by ADK and cannot be migrated.
- A state key deleted before capture has no current memory and no standalone
  `archive/state-history/` document. Its retained `stateDelta` events remain in
  `source/google-adk-sqlite-snapshot.json`, which is the complete replay source.
- Credential values replaced solely by `<redacted>` remain provable in the
  source snapshot but are counted as skipped instead of becoming empty recall
  memories.
- The OKF importer has no provider savings report, and SQLite stores no token,
  latency, or billing baseline. The migration report deliberately claims no
  synthetic savings.
- The local validation is deterministic lexical retrieval. The cloud script is
  the separate evidence for Memanto's semantic recall and OKF export.
