# Bounty #1852 security findings

PR: https://github.com/moorcheh-ai/memanto/pull/2024

This submission fixes package-side trust-boundary failures that can turn untrusted local state or recalled memory into durable agent instructions, the wrong memory namespace, or out-of-project config writes.

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

Shared `assert_project_local_path` rejects local connect destinations that resolve outside the project root before mkdir/write for instructions, skills, extensions, hooks, and permissions. Global installs remain intentional.

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

## Patch map

- `memanto/cli/connect/path_scope.py` — shared project-local path check.
- `memanto/cli/connect/updater.py` — canonical project-local write-scope enforcement plus no-follow descriptor I/O for dynamic sync.
- `memanto/cli/connect/engine.py` — same local-scope guard for connect-time instruction, skill, extension, hooks, and permissions writes.
- `integrations/hermes-agents/hermes_memanto/provider.py` — collision-resistant identity/profile mapping with legacy continuity handling.
- `memanto/app/services/memory_read_service.py` and `memory_write_service.py` — fail-closed provenance preservation.
- `memanto/cli/commands/memory_mgmt.py` — exact trusted-provenance gate before dynamic instruction injection.
- `memanto/app/utils/atomic_write.py` — MEMORY.md cache restore replaces the destination entry instead of writing through a symlink.

This document is part of the existing single bounty carrier; it does not create a second submission.
