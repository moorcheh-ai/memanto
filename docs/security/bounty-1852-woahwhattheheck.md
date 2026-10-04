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

Upstream `_assert_local_write_scope` rejects local connect destinations that resolve outside the project root before mkdir/write for instructions, skills, extensions, hooks, and permissions. The upstream scope guard remains, together with the existing local-connect regression coverage. The later [connect hard-link repair](https://github.com/woahwhattheheck/memanto/commit/2cdb0fd552741f1f7e222462e187c497c31e39cf) also replaces existing project-local entries atomically, preserving their modes without writing through an outside hard-link alias. Global installs remain intentional. The separate `assert_project_local_path` helper remains on the dynamic-sync path described in section 1.

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

## 7. Moorcheh credentials survive conversation memory extraction

Repair: [5fc148fbfa769b0dd5972bd6839f6b9715599870](https://github.com/woahwhattheheck/memanto/commit/5fc148fbfa769b0dd5972bd6839f6b9715599870).

**Impact.** The documented `MOORCHEH_API_KEY` assignment bypassed both credential-field patterns. The generic `API_KEY` matcher requires a word boundary, but the preceding underscore in the provider setting is a word character. A generated memory containing that setting therefore retained its value in both title and content. The normal non-dry-run API and SDK paths forward these candidates to memory storage.

### Reproduction on the vulnerable implementation

1. Use the existing `FakeClient` in `tests/test_conversation_memory_extraction.py` to return a generated candidate with `MOORCHEH_API_KEY="mk_your_api_key_here"` in its title and content. This value is the public documentation placeholder, not a live credential.
2. Call the real `ConversationMemoryExtractionService.extract` method with an ordinary conversation.
3. Before the repair, the returned title and content contain the unchanged value. Single-quoted and unquoted assignments have the same behavior.

### Fix and focused validation

Recognize the complete provider setting in the existing quoted and unquoted credential-field expressions. The repair preserves the setting name, quote style, and useful surrounding memory text while replacing the value with `[REDACTED_CREDENTIAL]`. It does not infer a valid key's length or alphabet.

All three added extraction cases failed before the repair. The complete existing extraction test file passes **12 tests in 2.08 seconds** afterward with pytest 8.4.2. Ruff check, formatting, and whitespace checks pass. The run used isolated process-local home resolution, an unset provider key, and blocked network/DNS. Validation exercised candidate extraction locally; it did not exercise a live provider, storage account, or cross-tenant access.

```bash
python -m pytest -p no:cacheprovider tests/test_conversation_memory_extraction.py
```

## 8. Automatic renewal can undo a completed logout across processes

Repair: [5133637c42e38e0b3773672464f126b09fef737c](https://github.com/woahwhattheheck/memanto/commit/5133637c42e38e0b3773672464f126b09fef737c).

**Impact.** The CLI and server share persisted session files, but their lifecycle locks were instance-local `threading.RLock` objects. A request that had already decided to renew a near-expiry session could overwrite a completed logout with a fresh active session and return a usable replacement bearer.

This is a normal supported topology: the CLI uses a local `SessionService` through `SdkClient`, while the server obtains its own process-local singleton. Both resolve the same session directory for the same user and backend. Automatic renewal is enabled by default.

### Reproduction on the vulnerable implementation

1. Create two real `SessionService` instances sharing one disposable session directory and a synthetic signing secret. Create a valid session and advance the local clock into its renewal window.
2. Invoke the real `auth_deps.get_current_session` dependency with that bearer. Pause immediately before renewal creates its replacement.
3. End the session through the other service instance. On the original service blob `51591aceceb94d41d48ae7b839b4b5be30fb8953`, logout completes, persists `TERMINATED`, and rejects the original bearer.
4. Resume the paused request. Its real `X-Session-Token` response header contains a fresh bearer. The other service accepts that bearer, and persisted state has returned to `ACTIVE`.

### Fix and observed behavior

Hold a stable per-agent advisory file lock across lifecycle reads and writes, alongside the existing thread lock. The lock covers renewal, recreation, creation, termination, and deletion. Same-thread nested renewal/recreation calls reuse the outer file-lock ownership, avoiding a second acquisition through another descriptor. Eager agent-ID validation and existing lock ordering remain; different agents retain independent locks.

After the repair, the same two-instance authentication flow makes logout wait for the in-flight renewal. Logout then terminates the replacement session. The authentication dependency produces its normal replacement header, but that bearer is rejected after logout completes.

| Observed result | Before repair | After repair |
|---|---|---|
| Logout completes while renewal is paused | Yes | No; it waits |
| Replacement bearer authenticates after logout completes | Yes | No |
| Final persisted session state | `ACTIVE` | `TERMINATED` |

### Focused validation

Ten selected session regressions passed in **3.96 seconds**, using pytest 8.4.2, Ruff 0.14.14, and pytest-timeout 2.4.0. Ruff checks, formatting, and whitespace checks passed. The tests and real authentication flow used disposable local state and blocked network/DNS access; both recorded zero attempts.

The first two selectors below each expand into same-instance and separate-instance cases, producing ten cases total:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest \
  -p no:cacheprovider -p pytest_timeout -p pytest_asyncio.plugin \
  --timeout=10 --import-mode=importlib \
  tests/test_unit.py::TestSessionService::test_auto_renew_is_single_flight_per_agent \
  tests/test_unit.py::TestSessionService::test_end_session_revokes_concurrent_auto_renewal \
  tests/test_unit.py::TestSessionService::test_lifecycle_operations_for_different_agents_can_overlap \
  tests/test_unit.py::TestSessionService::test_check_and_auto_recreate_revives_expired_session \
  tests/test_unit.py::TestSessionService::test_check_and_auto_recreate_never_revives_terminated_session \
  tests/test_unit.py::TestSessionService::test_check_and_auto_recreate_ignores_foreign_and_malformed_tokens \
  tests/test_unit.py::TestSessionService::test_delete_session_tolerates_external_marker_removal \
  tests/test_unit.py::TestSessionService::test_session_token_storage_is_owner_only
```

The current shared branch contained an unrelated DirectClient fixture change when this repair was published. Composition preserved that change, and the tested `TestSessionService` class remained byte-for-byte identical. The source and test postimages are `3b18b303ad3b482512cb14826ad7ff4ece46d8a5` and `3af108e79a5b43267f7f26097d558f0602cf2a6c`.

This demonstrates a package-side session revocation defect using real signing, persistence, validation, and authentication handoff. It does not claim a hosted-backend or cross-tenant exploit.

## Patch map

- `memanto/cli/connect/path_scope.py` — shared project-local path check.
- `memanto/cli/connect/updater.py` — canonical project-local write-scope enforcement, no-follow descriptor I/O, and nested-marker separation for dynamic sync.
- `memanto/cli/connect/engine.py` — upstream's local-scope guard for connect-time writes, plus atomic replacement of existing project-local entries to preserve outside hard-link aliases.
- `integrations/hermes-agents/hermes_memanto/provider.py` — collision-resistant identity/profile mapping with legacy continuity handling.
- `memanto/app/services/memory_read_service.py` and `memory_write_service.py` — fail-closed provenance preservation.
- `memanto/cli/commands/memory_mgmt.py` — exact trusted-provenance gate before dynamic instruction injection.
- `memanto/app/utils/atomic_write.py` — MEMORY.md cache restore replaces the destination entry instead of writing through a symlink.
- `memanto/cli/client/memory_cache.py`, `direct_client.py`, and `sdk_client.py` — automatic sync cache isolation by credential and backend endpoint, without changing explicit user exports.

- `memanto/app/services/conversation_memory_extraction_service.py` — provider credential-field redaction before extracted candidates reach storage.
- `memanto/app/services/session_service.py` — shared per-agent lifecycle locks preventing renewal from undoing logout.

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

## Follow-up: honor restricted Hermes contexts for explicit memory writes

The Hermes provider already disables memory writes for `cron`, `flush`, and `subagent` contexts. Its background capture and memory-mirroring paths checked that setting, but the public `memanto_remember` tool did not. A tool call in any of those restricted contexts could therefore reach the memory writer and label an instruction `explicit_statement`.

**Reproduction:** On source `738609941532c90e3190725bdee6ef00eccc31e4`, initialize the real `MemantoMemoryProvider` with any of those three `agent_context` values. Use the existing in-memory `FakeClient` to record write requests, then call `handle_tool_call("memanto_remember", {"content": "Restricted-context instruction", "type": "instruction"})`. Each context returns `saved: true` and records a write even though `_write_enabled` is false. The new parameterized regression fails for all three contexts on the unchanged source.

**Fix:** Check the existing write setting at the start of `_tool_remember`, returning the provider's normal tool-error response with `Memory writes are disabled in this context`. Also omit the write tool from the restricted context's schema list and prompt. Direct dispatch by tool name remains guarded even when a caller ignores the advertised schemas. Recall and answer stay available, and normal interactive initialization restores the existing write tool and behavior.

**Focused validation:** Python 3.12.14, pytest 8.4.2. The three new restricted-context cases fail on the original provider. With the correction, they and seven existing tool/prompt/configuration controls pass: **10 passed, 43 deselected in 0.41 seconds**. Each new case checks the exact error, absence of a write, the advertised tools, retained reads, and normal interactive reinitialization. Ruff lint passed; the patch applies cleanly to the pinned originals.

This demonstrates a package-side enforcement gap using the real provider and identity resolver with the repository's existing in-memory client fixture. It does not demonstrate a hosted backend or cross-tenant compromise. It belongs to the existing single #1852 submission in PR #2024 and its existing BountyHub claim.

Attribution: GPT-6 Astra Pro / astra-448b5ed8 / ChatGPT cloud harness. Original contributor, carrier PR, and BountyHub claim remain unchanged.
