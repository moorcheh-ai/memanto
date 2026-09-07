# Live Memanto validation

Validated against the Moorcheh cloud backend on 2026-07-29 UTC using an
isolated `codex-session-okf` agent.

## Results

- Source OKF: 4 conversation nodes, 2,213 bytes.
- Import: 4 mapped, 4 imported, 0 skipped, 0 failed, one batch.
- Import wall time: 5.6 seconds.
- Golden retrieval: all 3 questions returned the expected memory as rank 1.
- Round-trip export: 4 context memories, 11 bundle files, 6,388 bytes.
- Export wall time: 10.7 seconds.

The live run exposed and fixed an OKF interoperability bug: producer-specific
`x_memanto.source` values such as `codex-session-jsonl` were passed into
`MemoryRecord.source`, whose schema only accepts `user`, `agent`, `tool`, or
`system`. The importer now preserves the producer value in supporting data and
maps conversational roles onto valid sources (`assistant` to `agent`, for
example). A regression test covers this boundary.

No API key, session token, cloud record ID, or private source path is included
in this evidence.
