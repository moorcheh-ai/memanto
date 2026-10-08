# OKF sync fallback must preserve backend identity (#1852)

## Finding and reproduction

At source `8c07b70154a21a084c3515b1852f60909736b9cc`, both
`DirectClient.sync_okf_to_project` and `SdkClient.sync_okf_to_project` use
`~/.memanto/exports/{agent_id}_okf` for automatic fallback. A caller-selected
agent name does not identify the credential or deployment that supplied that
bundle. The earlier `MEMORY.md` cache repair did not cover these OKF methods.

The focused reproduction uses disposable directories and two synthetic API
keys with the same agent name. A successful sync through client A writes one
marked memory using the real OKF exporter. Client B's recall boundary then
raises `ConnectionError`. The original sync method selects A's agent-only cache
and copies it into B's project instead of rejecting the unavailable export.
Changing the cloud endpoint or on-prem endpoint produces the same reuse.
Manually generated exports at the legacy default path are also adopted even
though their owner is not recorded.

The session-validation and recall boundaries are controlled in these tests;
the production export, context selection, bundle writer, loader and project
copy execute against real local files. No live tenant account or hosted
authorization bypass is claimed.

## Repair and compatibility

Both OKF sync methods now derive their cache directory from the existing
`memory_sync_cache_path` identity and pass it explicitly as `output_dir` to
`export_okf_bundle`. Fresh writes and fallback reads therefore use the same
credential/backend scope. The shared helper covers the actual transport
context, cloud credentials and endpoint, and on-prem endpoint; only its digest
appears in the path. The existing cloud/on-prem data-root routing is retained.

Old unbound bundles remain on disk but are not automatically adopted. A new
successful sync establishes the scoped fallback. A new client with the same
identity can still use that bundle during an outage. If there is no matching
cache, sync raises without changing the existing project bundle.

Explicit user exports retain their existing default and selected output paths
inside the permitted data directory. The existing authorization check still
runs before export; a session-expiry rejection is propagated rather than
treated as an offline fallback.

Only the two `sync_okf_to_project` selection blocks change in production. The
session resolver, OKF context-file selector, record framing, loader and shared
cache-identity helper are preserved. This finding does not cover the separately
owned warm-session revocation behavior or alter project-copy concurrency.

## Focused validation (2026-10-04)

`tests/test_okf_cache_scope.py` contains 14 focused cases across both clients:
different credentials, different cloud/on-prem endpoints, same-identity offline
recovery in both backends, explicit-export compatibility, rejection of unbound
fallbacks and propagation of a session authorization rejection.

With the original production sync methods, the corrected test file reports
**8 failed, 6 passed**: credential, endpoint and unbound-cache isolation fail;
same-identity recovery and session-error propagation pass. With this repair,
the same file reports **14 passed in 0.58 seconds**. Python 3.12.14 ran the
repository's pytest dependency; no dependency installation was needed. A process
audit hook rejected network/DNS attempts and recorded **zero events** in both
runs. Ruff checking and formatting passed for both clients and the test file.

Focused command, run with the network audit hook described above:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest -c /dev/null -q \
  -p no:cacheprovider --import-mode=importlib tests/test_okf_cache_scope.py
```

The temporary `-c /dev/null` selection isolates these synchronous cases from an
unavailable optional pytest-asyncio configuration; it is not a full-suite result.
The baseline comparison loads the two unchanged production method definitions
from the pinned source snapshot into the otherwise identical runtime. No
session-resolver, memory-service or export-format repair is included in these
results. This remains part of the original #1852 submission and its existing
conditional top-submission bounty claim.
