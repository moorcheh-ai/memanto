# Sample Source Provenance

The committed source is not hand-written migration data. It came from an actual
Codex CLI run and Codex's own memory extraction job.

## Environment

- Codex CLI: `0.145.0-alpha.30`
- Source project: `sample_project/`
- Sandbox: read-only
- Git branch: `feat/codex-memory-okf`
- Isolated Codex home: a temporary directory outside the repository

The fixture project starts with SQLite, mixed local/UTC timestamps, text logs,
and an unresolved shared-worker design question. The real Codex task supplied
the adopted decisions:

- PostgreSQL 16 for shared workers;
- Python 3.10 remains the minimum;
- all stored timestamps use UTC;
- production logs use structured JSON; and
- status updates stay concise, with test failures explained before fixes.

Codex read `PROJECT.md`, reconciled those choices, produced a final answer, and
made no file edits.

## Stage-One Generation

Codex's memory pipeline only extracts sessions after an idle threshold. Waiting
for that product delay would make fixture generation unnecessarily slow, so one
timing-only adjustment was made:

1. A normal interactive Codex session completed the read-only task.
2. In the isolated demo state database, only that thread's `updated_at` time was
   moved two hours into the past and `has_user_event` was confirmed.
3. A second root Codex session started, triggering the official asynchronous
   memory pipeline.
4. The `memory_stage1` job completed and wrote one row to
   `memories_1.sqlite.stage1_outputs`.
5. `codex_to_okf.py` read that row and emitted the committed sanitized JSON and
   OKF bundle.

No memory text, summary, slug, or extraction result was inserted or edited in
SQLite. The timing adjustment only made an otherwise eligible isolated session
old enough for the normal startup claim.

## Evidence in the Fixture

The generated record contains:

- the real Codex thread ID and rollout slug;
- Codex's `raw_memory` and `rollout_summary` formats;
- the source and generation timestamps;
- Codex CLI version and git branch provenance; and
- redacted home and temporary paths.

The adapter summary reports four home-path redactions and one temporary-path
redaction. A repository test loads the committed JSON, maps the committed OKF
through Memanto's shipped loader and mapper, and checks that no personal path,
email, or common secret format remains.

The script `generate_rollout_sample.sh` is the fast, public reproduction route.
It creates a fresh real Codex rollout in an isolated home and exercises the
adapter's immediate fallback without requiring the memory idle window.

