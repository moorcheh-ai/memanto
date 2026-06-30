# Legacy / Dead-Code Dump

This folder is a **standalone dump for dead code**. Nothing in the active
codebase imports from `memanto/app/legacy/`, and this folder is **excluded from
CI** (ruff lint, ruff format, and mypy — see `pyproject.toml`). Files here may
have broken imports or reference symbols that no longer exist; that is expected.
Do not wire anything in `app/`, `cli/`, or the integrations to this folder.

Last cleanup: **2026-06-29**.

---

## 1. Orphaned "trust" machinery removed from active code

These fields/methods were schema-only — defined but **never populated or called**
by any live write/read flow (the write path uses an `"MVP direct store"` shortcut
that bypasses validation). Conflicts are actually handled by outright deletion via
the `memanto conflicts` CLI, not by supersession flags. All of the following were
deleted:

**`memanto/app/core.py`**
- Fields on `MemoryRecord`: `superseded_by`, `supersedes`, `validated_at`,
  `validation_count`, `contradiction_detected`.
- Methods: `compute_confidence()`, `validate()`, `mark_superseded()`,
  `detect_contradiction()`, `trust_score()`.
- The entire `ValidationPolicy` class (`validate_memory`,
  `_validate_critical_memory`, `make_provisional`) — fully bypassed by the
  write service.
- The serialization of the removed fields in `to_moorcheh_document()`.

**`memanto/app/services/memory_read_service.py`**
- Extraction + formatting of `validation_count`, `contradiction_detected`,
  `superseded_by`, `supersedes`, `validated_at` in `_format_memory_item()`.
- The dead "skip if superseded" branch in `search_as_of()` (depended on
  `superseded_by`, which is never written).
- The large commented-out `compute_confidence()` / `trust_score()` block.

**`memanto/app/models/__init__.py`**
- The five trust fields on the `MemoryItem` response model.
- The unused `SupersedeRequest` model (imported nowhere).

**`memanto/app/routes/memory.py`**
- Dead `trust_score()` comment block in the `remember` response.

**Consistency-only edits (kept in sync with the removed fields):**
- `memanto/app/ui/static/index.html` — removed the `contradiction_detected`
  and `validation_count` table badges.
- `docs/GETTING_STARTED.md` — removed the two fields from the example response.
- `sdks/typescript/openapi.json` — removed the five properties from the
  `MemoryItem` schema.

The live trust signals that **remain** are `confidence`, `provenance`,
`created_at`/`updated_at`, `status`, and TTL (`expires_at`/`ttl_seconds`).

---

## 2. Entirely-unused files moved here

Each was verified to have **no inbound import from active code** before moving:

| Moved from | Moved to | Why |
|---|---|---|
| `memanto/app/utils/idempotency.py` | `legacy/idempotency.py` | `IdempotencyHandler` / `handle_write_idempotency` never imported anywhere |
| `memanto/app/utils/tracing.py` | `legacy/tracing.py` | trace span/decorator helpers never imported |
| `memanto/app/utils/safe_deletion.py` | `legacy/safe_deletion.py` | `SafeDeletion.perform_safe_deletion` never imported |
| `memanto/app/models/phase_d.py` | `legacy/phase_d.py` | Phase-D models never imported |
| `memanto/app/models/universal_endpoints.py` | `legacy/universal_endpoints_models.py` | referenced only by the already-dead legacy `universal_*` files (renamed to avoid colliding with the existing `legacy/universal_endpoints.py` routes file) |

Pre-existing dead files already in this folder (untouched): `context.py`,
`context_summarization_service.py`, `memory.py`, `memory_validation_service.py`,
`universal_endpoints.py`, `universal_services.py`.

---

## 3. Multi-scope / namespace cleanup (2026-06-29)

The live app only ever uses `scope_type="agent"` — every memory namespace is
`memanto_agent_{agent_id}`. The broader multi-scope abstraction
(`user`/`workspace`/`session`/`project`/`task`) was exercised only by dead code.

**`ScopeType` narrowed to `Literal["agent"]`** in `constants.py` (and
`VALID_SCOPE_TYPES = {"agent"}`). The agent-only scope resolution in
`memory_read_service.generate_answer()` / `_get_search_namespaces()` was
simplified accordingly (they always build an `agent` scope now).

**Removed dead namespace machinery:**
- `routes/namespaces.py` → moved to `legacy/namespaces.py`. Its router was
  **never mounted** in `main.py` (only `health`, `sessions`→`memory`, and the
  Web UI are mounted) — the whole file was unreachable.
- `models/__init__.py`: removed `NamespaceCreateRequest`, `NamespaceResponse`,
  `NamespaceListResponse` (imported only by the dead route).
- `NamespaceService`: removed `create_namespace()`, `delete_namespace()`,
  `namespace_exists()` (used only by the dead route + the dead
  `_ensure_namespace`). Kept `list_namespaces()` — the live search path uses it.
- `MemoryWriteService`: removed the uncalled `_ensure_namespace()` and its
  lazy `namespace_service` property.
- `MemoryReadService.search_multi_scope()`: removed. Called only from the dead
  `legacy/memory.py`, and it had a broken `from memanto.memanto.app.constants`
  import (double `memanto`) proving it never ran.

`scope_type` / `scope_id` were still present at this stage; they were fully
removed in the next step (see section 4).

---

## 4. Collapse scope to a single `agent_id` (2026-06-29)

The remaining `scope_type` + `scope_id` pair was replaced everywhere with a
single `agent_id`. The concept is now simply: a memory belongs to an agent, and
its namespace is `memanto_agent_{agent_id}` (unchanged on the wire).

- `core.py`: removed `MemoryScope`, `create_memory_scope`, `parse_namespace`,
  `from_namespace`, `validate_namespace_format`, and `MemoryRecord.get_scope()`.
  `MemoryRecord` now has `agent_id` (not `scope_type`/`scope_id`); namespaces are
  built by the free function `agent_namespace(agent_id)` and `MemoryRecord.namespace()`.
- `constants.py`: `ScopeType` and `VALID_SCOPE_TYPES` removed entirely.
- `to_moorcheh_document()` writes a flat `agent_id` field (was `scope_type`/`scope_id`);
  `MemoryReadService._format_memory_item()` reads it back as `agent_id`.
- All construction / search sites updated: `routes/memory.py`, `agent_service`,
  `session_service`, `daily_analysis_service`, `memory_write_service`,
  `memory_read_service` (search/answer params collapsed to `agent_id`), and both
  CLI clients (`direct_client`, `sdk_client`).
- `models/__init__.py`: deleted the multi-scope models `ScopeDefinition` and
  `MemoryMultiScopeSearchRequest`; renamed `scope_type`/`scope_id` → `agent_id`
  on the rest (`MemoryStoreRequest`, `MemoryBatchWriteRequest`,
  `MemorySearchRequest`, `MemoryAnswerRequest`, `ContextSummarizationRequest`,
  `CustomSummarizationRequest`, `ConversationCompressionRequest`,
  `MemoryResponse`, `MemoryItem`). `sdks/typescript/openapi.json` `MemoryItem`
  updated to match.
- `utils/ids.py`: removed the dead `generate_namespace_id` /
  `extract_scope_type_from_namespace` (wrong colon format, unused).
- `utils/logging.py` + `utils/rate_limiting.py`: dropped the `scope_type` /
  `scope_id` plumbing params (rate-limit keys are per-agent).

**`utils/auth.py` → `legacy/auth.py`:** the whole file was the old tenant /
JWT / multi-scope access-control model (`AuthService`, `authorize_scope`,
`require_scope_access`, `scopes_allowed = ["user","workspace","agent","session"]`).
It is entirely dead — the live app uses session-based auth (`routes/auth_deps.py`
→ `get_current_session`), and the only remaining reference to `auth.py` is from
the already-dead `legacy/universal_endpoints.py`. Rather than rename its
`scope_type`/`scope_id` (a different, access-control concept) it was moved to
the dump wholesale.

---

## Verification (post-cleanup)

- `pytest tests/` → **191 passed**
- `ruff check .` → clean
- `ruff format --check .` → clean
- `mypy memanto` → no issues (legacy excluded)
- `import memanto.app.main` / `import memanto.cli.main` → OK
