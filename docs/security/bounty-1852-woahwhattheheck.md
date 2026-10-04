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

## 6. Nested sync markers preserve recalled instructions after clearing

Repair: `b19384b9176a632bb6187d619223fe23c68fe9bc`.

Dynamic sync previously removed each sentinel with an empty-string replacement. A closing sentinel embedded inside another closing sentinel survived that operation: removing the inner marker joined the remaining fragments into a new valid closing marker. The injected text then ended the managed section early. A subsequent sync with no memories reported an update but left the recalled text outside that section in the project's instruction file.

**Reproduction:** On source `1931dbc050ba048ba5685551af6895a95ee6f988`, use an isolated home and temporary project, call the real `install_agent("github-copilot", project, is_global=False)`, and format one `instruction` memory with `explicit_statement` provenance. Let `end` be `MEMANTO_DYNAMIC_SENTINEL_END`; set its content to `end[:8] + end + end[8:] + "\nPERSISTENCE_MARKER_447F"`. Pass the formatted result to `inject_dynamic_memories(project, content, connection="github-copilot", scope="local")`, then call the same function with empty content. In the actual filesystem run, the instruction file's closing-marker count changed from one to two, and `PERSISTENCE_MARKER_447F` remained after the first closing marker following the empty sync.

**Fix:** Replace removed markers with a newline. Neither sentinel contains a newline, so separated fragments cannot form another sentinel. The implementation retains two bounded string-replacement passes and leaves content without sentinels unchanged. Existing local/global scope selection and descriptor-based atomic file replacement remain intact.

**Focused validation:** Four parametrized cases were added to the existing `tests/test_dynamic_memory_injection.py`. They exercise both start/end marker nesting through the production formatter and local sync writer, require one intact marker pair after injection, and verify that empty sync restores the exact surrounding instruction text with no retained memory. The original updater gives three failures and one pass for these cases. With the repair, the complete focused file passes **25 tests in 1.22 seconds** on Python 3.12.14; Ruff checks and formatting pass for both changed files.

```bash
env -u MOORCHEH_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  python -m pytest -p no:cacheprovider --import-mode=importlib \
  tests/test_dynamic_memory_injection.py -o addopts=-ra
```

**Scope:** The demonstrated memory already satisfies the existing trusted-provenance rule. This repairs local instruction persistence after clearing recalled memory; hosted backend or cross-tenant impact was not exercised. The change belongs to the existing single #1852 submission and its BountyHub claim.

## Patch map

- `memanto/cli/connect/path_scope.py` — shared project-local path check.
- `memanto/cli/connect/updater.py` — canonical project-local write-scope enforcement, no-follow descriptor I/O, and nested-marker separation for dynamic sync.
- `memanto/cli/connect/engine.py` — upstream's local-scope guard for connect-time instruction, skill, extension, hooks, and permissions writes; unchanged from upstream main after reconciliation.
- `integrations/hermes-agents/hermes_memanto/provider.py` — collision-resistant identity/profile mapping with legacy continuity handling.
- `memanto/app/services/memory_read_service.py` and `memory_write_service.py` — fail-closed provenance preservation.
- `memanto/cli/commands/memory_mgmt.py` — exact trusted-provenance gate before dynamic instruction injection.
- `memanto/app/utils/atomic_write.py` — MEMORY.md cache restore replaces the destination entry instead of writing through a symlink.
- `memanto/cli/client/memory_cache.py`, `direct_client.py`, and `sdk_client.py` — automatic sync cache isolation by credential and backend endpoint, without changing explicit user exports.

This document is part of the existing single bounty carrier; it does not create a second submission.

## Follow-up: OKF export includes other agents' local context

Both `DirectClient.export_okf_bundle` and `SdkClient.export_okf_bundle` selected daily summaries and session logs using only an agent-name prefix. Consequently, `memanto memory export --okf` for `team` could include the local private context of `team_private`. A valid session for the requested agent did not prevent this: the remote memory lookup was scoped correctly, but the later local file selection copied the other agent's documents into the bundle. Fresh `memory sync --okf` uses the same export path.

### Reproduction

On branch source `5fc148fbfa769b0dd5972bd6839f6b9715599870`, create disposable session state for `team`, `team_private`, and `team_2026-10-03`. Use the real `SessionService.create_session` and `log_memory_to_session_summary` methods to generate their logs, with a different synthetic content marker for the other agents. Add their canonical daily-summary files. Bind a client to `team`'s real signed token and let its remote search boundary return an empty result. Call the real `export_okf_bundle` operation.

Before the repair, both clients copied the other agents' context into the export. Four regression variants, covering both clients and the target names `team` and `team_2026-10-03`, failed on the other-agent marker. This uses only disposable local files and synthetic credentials; no hosted account or tenant was accessed.

### Fix

Both clients now use one local-context selector. Daily-summary filenames must match the complete requested agent name followed by the canonical date suffix. Session filenames must match the supported generated form, and a bounded first-line read must identify the exact requested agent. The second check matters because both agent names and session IDs can contain underscores and dates, making filenames alone ambiguous.

The selector preserves deterministic order and existing safe session IDs, including historical IDs containing underscores and dates. It accepts the generated session header with LF, CRLF, or end-of-file. It omits symlinks, noncanonical custom filenames, and session files with absent, unreadable, or mismatched owner headers. Explicit caller-supplied context lists in `OkfExportService` keep their existing behavior.

### Focused validation

Python 3.12; the four new cases failed on the baseline in 0.50 seconds. With the patch, the following selection passed **5 tests in 0.44 seconds**:

```bash
python -m pytest -c /dev/null -q -p no:cacheprovider --import-mode=importlib \
  tests/test_okf_context_scope.py \
  tests/test_okf.py::test_context_sections_and_import_scope
```

The fifth case is the existing context-section export/import compatibility check. The new cases exercise real JWT/session validation, session-summary writing, client recall/gathering, OKF rendering and bundle publication; only the remote search response is controlled. The run used isolated home and temporary paths, disabled bytecode writes, and rejected network/DNS access with a Python audit hook. Recorded network events: `[]`. Ruff check and formatting passed for all four changed files. No additional environment was installed.

The repair establishes package-side local agent isolation during automatic context selection. It does not establish a hosted authorization defect or retroactively clean bundles already exported by older code. Custom-named daily summaries and headerless session documents are no longer automatically adopted, because their ownership cannot be determined safely from the old prefix rule.

This is an additive fix on the existing #1852 / PR2024 submission and its bound BountyHub claim. Attribution: GPT-6 Astra Pro, Astra-e9dcc1eb, ChatGPT cloud harness.
