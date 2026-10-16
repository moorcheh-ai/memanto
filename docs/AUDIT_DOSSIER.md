# Memanto Local Audit PoCs

These scripts are isolated, non-destructive demonstrations. They create only temporary fixtures and do not import, patch, or write repository production files.

## Run

From the repository root:

```text
python audit_pocs/run_all.py
```

The symlink test may report `link_creation=unavailable` on Windows when the process lacks Developer Mode or symlink privileges. That is an environment limitation, not a negative security result. Windows directory junctions require a directory fixture and can be tested with the same boundary check.

## Findings

### 1. Unbounded file ingestion

`poc_unbounded_ingestion.py` models `load_okf_bundle` in `memanto/cli/migrate/okf_loader.py`: recursive discovery and `read_text()` materialize each complete Markdown file, and later splitting/parsing creates additional objects. The PoC prints fixture size, files loaded, and the process maximum-resident-memory delta. Reproduce with `--size-mib 128 --depth 200` only on a disposable test host.

Recommended fix: impose limits on file count, total bytes, per-file bytes, recursion depth, and parsed entry count before materialization; prefer bounded streaming where practical.

### 2. Symlink or junction escape

`poc_symlink_ingestion.py` places a Markdown symlink under a temporary bundle that resolves outside the bundle root, then models recursive candidate selection and content reads. It reports the resolved path and whether outside content was ingested.

Recommended fix: reject symlinks and junctions, resolve every candidate, and require it to remain under the resolved import root using `Path.is_relative_to()` (or an equivalent case-aware Windows check) before opening it. Apply the check immediately before the open to reduce check/use races.

### 3. Lock timeout fallback

`poc_lock_timeout.py` holds a temporary `FileLock`, attempts a second acquisition with `timeout=0`, and reports the timeout plus the unsafe consequence if execution proceeds without protected state. The relevant production path is `memanto/app/services/agent_service.py`.

Recommended fix: distinguish contention from “already exists,” use a bounded retry policy where appropriate, and fail closed when the lock cannot be acquired. Never perform state mutation outside the lock.

### 4. Non-atomic report write

`poc_non_atomic_report_write.py` coordinates a reader after `truncate(0)` and before the replacement content is written. The reader can observe an empty or incomplete report, matching the direct `Path.write_text()` report path in `memanto/cli/commands/migrate.py`.

Recommended fix: write a temporary file in the destination directory, flush and optionally `fsync`, then replace the destination with `os.replace()`; retain the old file until the replacement is complete.

## Scope note

The PoCs verify the claimed mechanisms locally. They are not denial-of-service tools, do not access real secrets, and do not alter the repository source tree.
