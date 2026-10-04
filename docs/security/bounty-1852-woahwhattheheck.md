# Bounty #1852 security findings

PR: https://github.com/moorcheh-ai/memanto/pull/2024

This submission fixes package-side trust-boundary failures that can turn untrusted local state or recalled memory into durable agent instructions, the wrong memory namespace, or out-of-project config writes. The branch incorporates upstream main `c421ab8bb27f7dc4fca9abe938dc693d2998638d`; that upstream revision already includes the connect-time path-scope fix described in section 2 via PR #2010. The remaining source changes preserve dynamic-sync isolation, Hermes identity separation, provenance handling, and atomic memory-cache replacement.

## 1. Project-local dynamic sync can escape the project through a symlink

**Impact.** A project-local `memanto memory sync` can follow an instruction-file symlink (or a parent-directory symlink) outside the requested project and inject recalled memory into that external file.

### Reproduction on the vulnerable code

1. Create a project directory with a supported local instruction path containing the Memanto dynamic sentinel.
2. Make that instruction path a symlink to a file outside the project root, or make a parent directory (for example `.github`) a symlink that resolves outside the project.
3. Run `memanto memory sync --project-dir <project>`.
4. The old updater opens the unresolved path and writes the dynamic section into the out-of-project target.

### Fix

Resolve the destination before instruction-file I/O, reject local destinations that do not resolve beneath the project root, then perform local reads/writes through a no-follow directory-descriptor chain rooted at the project. Explicit global sync remains supported.

## 2. Project-local connect can escape through settings / skill / instruction symlinks

**Impact.** A project-local `memanto connect` install can follow repository-controlled symlinks under agent integration directories (for example `.claude/settings.json`, `.claude/settings.local.json`, or a skill parent) and mutate files outside the selected project.

### Reproduction on the vulnerable code

1. Create a temporary project and an external Claude settings file outside that project.
2. Inside the project, make `.claude/settings.local.json` or `.claude/settings.json` a symlink to the external file.
3. Invoke the corresponding local Claude integration update (`_install_permissions` or `_install_hooks`) with `is_global=False`.
4. On the vulnerable code, the nominally project-local operation follows the symlink and modifies the external settings file.

### Fix

Upstream `_assert_local_write_scope` rejects local connect destinations that resolve outside the project root before mkdir/write for instructions, skills, extensions, hooks, and permissions. This branch keeps the upstream implementation unchanged, together with the existing local-connect regression coverage. Global installs remain intentional. The separate `assert_project_local_path` helper remains on the dynamic-sync path described in section 1.

## 3. Hermes identity normalization aliases distinct identities

**Impact.** The legacy sanitizer replaces every character outside `[A-Za-z0-9_-]` with `_`. Distinct identities can therefore collapse onto the same Hermes profile and Memanto memory namespace.

### Reproduction on the vulnerable code

1. Initialize a Hermes/Memanto profile with identity `alice@example.com`.
2. Initialize another with identity `alice_example_com`.
3. The legacy sanitizer maps both to `alice_example_com`, so local profile/token state and the derived memory namespace are not separated.

### Fix

Already-safe short identifiers remain unchanged. Unsafe, truncated, or reserved-prefix values move into a bounded `memh_<slug>-<sha256>` namespace. Existing legacy profiles are reused only when they prove continuity; if both generations exist, initialization fails closed rather than silently joining histories.

## 4. Missing provenance can be promoted into durable agent instructions

**Impact.** Legacy or external memories without stored provenance were read as `explicit_statement`. An unrelated edit could serialize that default back into storage. Dynamic sync then formatted recalled instruction/preference/goal memories without an exact trust check, allowing missing-provenance content to cross into durable coding-agent instruction files.

### Reproduction on the vulnerable code

1. Retain an `instruction`, `preference`, or `goal` memory whose stored metadata has no provenance.
2. Recall it through `memanto memory sync`.
3. The read path manufactures `explicit_statement` provenance and the sync path formats the recalled content for instruction injection.
4. Editing the record can persist the manufactured provenance, laundering the legacy record into a trusted-looking one.

### Fix

Missing provenance now reads as the non-authoritative `unknown` sentinel. Unrelated updates preserve missing or non-standard stored provenance instead of laundering it. Dynamic sync injects only exact trusted provenance values: `explicit_statement`, `corrected`, and `validated`.

## 5. Automatic sync can reuse another credential's or deployment's export

**Impact.** Both `DirectClient.sync_memory_to_project` and `SdkClient.sync_memory_to_project` used a cache identified only by the caller-selected agent name. A later client using a different Moorcheh credential, or a different backend endpoint, could copy the earlier client's private memory into its project's `MEMORY.md` when its own refresh failed. The copied content came from local cache; this does not demonstrate a breach of the hosted backend's tenant authorization.

### Reproduction on the vulnerable implementation

The local reproduction used `ed7f6d9fa02f639a8831d3c3af20debf2fe5abac`. The affected cache code is unchanged through `1931dbc050ba048ba5685551af6895a95ee6f988`.

1. Use one disposable home directory and two clients of either class, with distinct synthetic API-key strings and the same agent name.
2. Control only session validation and recall at the service boundary. For client A, return one fact with a unique private marker. Run the real `sync_memory_to_project` method into project A, including its export formatter and filesystem writes.
3. For client B, make recall raise `ConnectionError` and sync into project B. On the parent code, the result is `source="stale-cache"` and project B's `MEMORY.md` contains A's marker.
4. The same boundary is crossed when the cloud API endpoint or on-prem deployment changes while the agent name stays the same. No live account, real credential, operating-system compromise, or network request is needed for this package-side reproduction.

The focused regressions are in `tests/test_export_resilience.py`: `test_cache_is_not_reused_across_credentials` and `test_cache_is_not_reused_after_endpoint_switch` exercise both production client implementations with disposable files. On the repaired code the failed refresh raises and the destination is left intact.

### Fix and compatibility

Automatic sync passes an explicit, private cache destination to the existing exporter. Its directory is keyed by a SHA-256 digest of structured backend context: API endpoint and credential for cloud, and deployment endpoint for on-prem, whose transport ignores the API key. An already-created transport's configuration takes precedence over changed environment values. Credentials and endpoint strings are never embedded in cache paths or metadata.

Successful sync followed by an outage remains usable by a new client with the same backend identity. Explicit user exports retain their paths and contents. Old agent-only exports are left in place but never adopted as automatic fallback because they have no ownership evidence; one successful sync establishes the new cache. Project publication continues using the existing atomic copy helper, preserving the earlier symlink and hard-link destination repair.

## Patch map

- `memanto/cli/connect/path_scope.py` — shared project-local path check.
- `memanto/cli/connect/updater.py` — canonical project-local write-scope enforcement plus no-follow descriptor I/O for dynamic sync.
- `memanto/cli/connect/engine.py` — upstream's local-scope guard for connect-time instruction, skill, extension, hooks, and permissions writes; unchanged from upstream main after reconciliation.
- `integrations/hermes-agents/hermes_memanto/provider.py` — collision-resistant identity/profile mapping with legacy continuity handling.
- `memanto/app/services/memory_read_service.py` and `memory_write_service.py` — fail-closed provenance preservation.
- `memanto/cli/commands/memory_mgmt.py` — exact trusted-provenance gate before dynamic instruction injection.
- `memanto/app/utils/atomic_write.py` — MEMORY.md cache restore replaces the destination entry instead of writing through a symlink.
- `memanto/cli/client/memory_cache.py`, `direct_client.py`, and `sdk_client.py` — automatic sync cache isolation by credential and backend endpoint, without changing explicit user exports.

This document is part of the existing single bounty carrier; it does not create a second submission.
