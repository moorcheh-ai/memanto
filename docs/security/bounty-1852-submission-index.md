## Summary

Refs #1852.

This single PR repairs package-side boundaries around project-local writes, agent/session identity, memory provenance, exports, and recalled content. Reproductions use controlled local files and synthetic credentials. The findings do not establish a hosted-backend or cross-tenant compromise.

Earlier cumulative product source: [`5a695228728ee4b7439479a87783c737639ec31a`](https://github.com/woahwhattheheck/memanto/commit/5a695228728ee4b7439479a87783c737639ec31a). The branch incorporates upstream main `c421ab8bb27f7dc4fca9abe938dc693d2998638d`, including #2010's connect-time symlink containment fix. That upstream fix is preserved; subsequent local-connect hard-link protection changes `engine.py`, so it is no longer identical to that upstream revision.

The results below are measured at the individual source revisions stated. They are not a full-suite result for this cumulative head, and overlapping counts must not be added together. Detailed reproductions and commands are committed in the same PR and linked below.

### Focused composition validation

The selected session/agent-binding, conversation-token-redaction and active-session-marker regressions were subsequently run **together: 60 passed, 0 failed, 0 errors, 0 skipped** at `79f6ee17c06496b53a2652a8033ba77b3d83f599`, the documentation-only child of cumulative product `5a695228728ee4b7439479a87783c737639ec31a`. [Run 37189951329, job 111399866655](https://github.com/woahwhattheheck/memanto/actions/runs/37189951329/job/111399866655) used the repository's original `pytest.ini` and `tests/conftest.py`, with CPython 3.12.14 and pytest 8.4.2.

The [source-pinned composition report](https://github.com/woahwhattheheck/memanto/blob/fe383d7bb24b4a1c334ca88b9fd925e617b2909e/docs/security/bounty-1852-composition-20261004.md) is now included in this same PR. Its integration commit `fe383d7bb24b4a1c334ca88b9fd925e617b2909e` changes documentation only. The report contains the exact selection, command, environment, hashes and limitations. Network-enabled dependency installation preceded a guarded test process that recorded no blocked network/DNS events. Existing mocked backend and answer fixtures remained in use.

This is focused composition evidence for the three selected areas, not a full-suite result or proof of every repair. Earlier component counts overlap and must not be added to 60. Sponsor acceptance, the competitive prize decision and payment remain pending.

### Subsequent transport-policy repair

Product commit [`8136b954ec0fb60addb7506add12f3db86604d69`](https://github.com/woahwhattheheck/memanto/commit/8136b954ec0fb60addb7506add12f3db86604d69) subsequently restricts the optional plaintext exception to direct loopback requests without forwarding indicators. When `MEMANTO_REQUIRE_SECURE=true`, a plaintext request forwarded by a loopback proxy no longer inherits that exception. Trusted-proxy HTTPS, direct loopback HTTP without forwarding fields, and disabled-policy behavior are preserved.

The [source-pinned report](https://github.com/woahwhattheheck/memanto/blob/8136b954ec0fb60addb7506add12f3db86604d69/docs/security/bounty-1852-proxied-http.md) contains the preconditions, maintained reproduction and compatibility limits. The complete production ASGI middleware and loopback helper recorded **6 failed / 6 passed before the repair, then 12 passed after it**. Configuration loading was isolated; these in-process results do not establish full FastAPI startup, an actual reverse proxy, browser behavior or TLS negotiation. The earlier 60-case composition run predates this change and does not validate it; the counts are not cumulative.

### Original findings and upstream reconciliation

1. **Project-local dynamic sync could escape through symlinks.** Create a supported local instruction file containing the dynamic sentinel, then make the file or its parent directory resolve outside the project and run `memanto memory sync --project-dir <project>`. The vulnerable writer changes the outside target. The repair rejects escaping destinations and performs local I/O through a no-follow directory-descriptor chain rooted at the selected project. Explicit global scope retains its intentional behavior.
2. **Project-local connect symlink escape was already fixed upstream.** A repository-controlled `.claude/settings.local.json`, settings file, or skill-parent symlink could redirect a local install outside the project. Upstream #2010's `_assert_local_write_scope` rejects escaping instruction, skill, extension, hook and permission destinations before writes. This branch preserves that fix and its regressions; the distinct hard-link follow-up below remains part of this PR.
3. **Hermes identity normalization could alias profiles.** `alice@example.com` and `alice_example_com` both became `alice_example_com`. Safe short identifiers now stay unchanged; unsafe, truncated or reserved-prefix identities receive a bounded `memh_<slug>-<sha256>` namespace. Legacy profiles are reused only with continuity evidence, and ambiguous old/new profiles fail closed.
4. **Rejected Hermes reinitialization retained the preceding client.** Initialize identity A, then reject identity B because its profile metadata mismatches. On `a9149646`, subsequent public `prefetch` still returns A's marker. Initialization now clears `_active` and `_client` before identity/configuration resolution; rejected initialization disables prefetch, prompts, tools and capture, while a later valid identity recovers.
5. **Missing provenance could become trusted instructions.** Recalling an instruction/preference/goal without stored provenance manufactured `explicit_statement`, and unrelated edits could persist it. Missing provenance now reads as `unknown`; unrelated updates preserve missing/non-standard values. Dynamic injection accepts only exact stored `explicit_statement`, `corrected` or `validated` values.

The [main finding report][main-report] contains the original reproductions and current patch map. The separate MEMORY.md symlink vector already covered by upstream #1875 is not presented as a new finding here.

### Additional repairs retained on this carrier

| Finding | Reproduction, repair and evidence |
| --- | --- |
| Dynamic-sync hard links | Real local Copilot install → outside hard-link alias → dynamic injection changed the outside inode on `70d9d49d`. `ed7f6d9f` stages/renames through the held parent descriptor; outside bytes and mode 0640 are preserved, and unchanged sync retains its inode. 27 focused cases passed in 1.36s, zero network/DNS; [source/regressions](https://github.com/woahwhattheheck/memanto/commit/ed7f6d9fa02f639a8831d3c3af20debf2fe5abac). |
| Local-connect hard links | Real `install_agent`/`remove_agent` rewrote an outside alias on `1931dbc0`. `2cdb0fd5` replaces local entries atomically, preserving modes and allowed in-project symlinks, and exclusively creates new entries. Repaired operations preserve outside bytes; 30 focused cases passed; [reproduction/command][connect-hardlink]. |
| Hermes token-file aliases | Token saving/loading adopted symlink/hard-link aliases. `19fb536b` atomically publishes a private staged file and rejects aliased/non-regular reads with opened-file identity checks and no-follow where available. Five baseline failures; repaired provider file passed 50/50. [Source/tests](https://github.com/woahwhattheheck/memanto/commit/19fb536b103d0504d1d75914927135ad4340f6ee). Linux/local evidence; Windows behavior untested. |
| Bounded Hermes profile metadata | The 4 KiB limit was checked after unbounded reading/decoding. `1931dbc0` requests 4,097 bytes before decoding. Same ~16 MiB ASCII/UTF-8 fixtures: ~32/~48 MiB peak traced allocation → ~9 KiB, identical rejection. Six new and 45 existing cases passed on `ed7f6d9f` plus this delta, composed over the separately tested token fix. [Source/tests](https://github.com/woahwhattheheck/memanto/commit/1931dbc050ba048ba5685551af6895a95ee6f988). Local resource hardening. |
| Client session/agent binding | A real `other-agent` token attached to a `target-agent` client reached the target read service; replacing tokens could reuse old cache state. `ebf04f2c` binds validated/cached/recreated sessions to the requested agent and exact token. Baseline: 6 failed, 4 passed; repaired: 16 passed in 2.90s. [Source/public-client cases](https://github.com/woahwhattheheck/memanto/commit/ebf04f2c026d2c9ed1c915d89146554c2309f339); real signing/persistence, isolated read service. |
| Warm-client revocation | Warm either client, then log out/delete/replace through another real shared-file service. All six original-resolver cases at `8c07b701` reached I/O despite persisted rejection. `a0ddbb7e` revalidates before cached renewal/I/O and clears rejected cache entries. Repaired: 22 passed in 0.15s; [reproduction/command][cached-revocation]. |
| MEMORY.md cache ownership | A's export became B's outage fallback after a credential or endpoint switch with the same agent name. `508af7e2` keys automatic caches by actual credential/backend identity digest, refusing unbound legacy exports. Same-identity offline recovery and explicit exports preserved; 25 focused cases passed in 2.72s. [Real export/file reproduction][memory-cache]; controlled recall boundary. |
| OKF cache ownership | `sync_okf_to_project` still adopted agent-only/manual unbound bundles. `756b876c` scopes fresh export and fallback to the same backend identity. Baseline: 8 failed, 6 passed; repaired: 14 passed in 0.58s, zero network/DNS, offline/explicit-export/auth-error controls preserved. [Real exporter/loader/file reproduction][okf-cache]; controlled session/recall boundaries. |
| Nested sync sentinels | Nested markers re-formed a closing sentinel during removal and left recalled instructions after empty sync. `b19384b9` separates removed-marker fragments with newlines. Production formatter/writer baseline: 3 failed, 1 passed; repaired focused file: 25 passed in 1.22s. [Reproduction][nested-markers]; the memory already met trusted-provenance requirements. |
| Conversation provider/JSON credentials | Provider assignments and quoted JSON keys/escaped values retained credentials in normalized titles/content. Complete provider-name recognition and escaped-value matching preserve surrounding text while redacting values. Provider: 3 baseline failures, 12 repaired passes; quoted keys: 7 baseline failures, 19 repaired passes in 0.51s. [Provider][credential-provider] / [JSON report][credential-json]; actual extractor, fake answer client, synthetic values. |
| Opaque conversation tokens | Ordinary access/refresh/ID/session token fields bypassed prefix/JWT/Bearer redaction at `756b876c`. `5a695228` extends both field-name expressions. Actual extractor baseline: 24 failed, 9 controls passed; repaired: 33 passed, Python 3.13.5/pytest 9.0.2, zero network/DNS. [Report/command][opaque-tokens]; complete source/parser/constants, inert import collaborators and in-memory answer fixture. No storage write or full-package run. |
| Cross-process renewal/logout | Paused real auth renewal resumed after completed logout and restored a usable bearer. `5133637c` uses stable per-agent lifecycle file locks; repaired logout waits, then terminates the replacement token. Ten selected cases passed in 3.96s; [real signing/persistence/auth reproduction and command][session-lock]; independent-agent concurrency retained. |
| Active-session marker publication | A's failed symlink creation fell back to truncating through B's newly published marker, corrupting B's JSON/token. `7c714a2b` publishes a staged sibling link or private atomic text. Real near-expiry bearer/auth interleave now preserves both tokens; baseline: 1 failed; repaired: 5 passed, 32 deselected in 0.44s. [Report][active-marker]; shared-file multi-service availability, not auth bypass. |
| Proxy forwarding-chain authorization | A later remote hop/repeated header inherited local trust under loopback-proxy/header preconditions. `93cfdd0a` parses every physical field/comma element and rejects remote/ambiguous sources; valid credentials/all-loopback chains retained. Baseline: 3 failed; repaired auth file: 45 passed. [Reproduction/preconditions/pinned environment][forwarded-chain]. |
| OKF record framing | A delimiter/frontmatter inside one imported fact became an extra trusted instruction after real export→load→map. Export-controlled body-length framing treats it as content; invalid recognized framing fails closed. Baseline: 8 sentinel cases failed; repaired selection: 99 passed in 2.42s. [Payload/command][okf-framing]; unmarked legacy parsing retained, arbitrary metadata not authenticated. |
| OKF local-context ownership | Export for `team` included `team_private` summaries/logs. Exact canonical summary names and bounded session owner-header validation replace prefix matching. Baseline: 4 failed; repaired: 5 passed in 0.44s including compatibility. [Real signed session/log/export reproduction][okf-context]; headerless/custom-named/symlink context omitted. |
| Restricted Hermes writes | Real `memanto_remember` dispatch bypassed the existing cron/flush/subagent restriction. Handler, schemas and prompts now enforce it while preserving reads. Baseline: 3 failed; repaired: 10 passed, 43 deselected in 0.41s. [Reproduction/controls][restricted-hermes]; existing in-memory client fixture, no live backend. |
| External-date HTML injection | Malformed externally stored dates became recall/explorer markup. Existing escaping now covers ten substitutions. Component renderer image count 1 → 0; eight rendered regression cases and full inline-script syntax pass. [Data trace/command/limits][ui-date]. Authorized recall and namespace write access required; no browser event handler/API-server exploit exercised. |

### Source-bound validation retained from the original submission

At reconciliation source `a9149646665ec6fc7574b8c2c81e822ba979fe08` (tree `373061b3f1db2b8fed4d01dac82ad8171962762b`), Python 3.12.14:

```bash
env -u MOORCHEH_API_KEY PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=.:integrations/hermes-agents \
  .venv/bin/python -m pytest -p no:cacheprovider --import-mode=importlib \
  tests/test_connect_local_symlink_scope.py \
  tests/test_dynamic_memory_injection.py \
  integrations/hermes-agents/tests/test_provider.py \
  tests/test_delete_agent_memories.py \
  tests/test_memory_read_temporal_recall.py
# 80 passed in 1.24s
```

The isolated local `memanto connect claude-code --project-dir <temporary project>` smoke exited 0, created the four expected instruction/skill/settings files and registered the local connection, with the provider key unset and zero network/DNS attempts.

The rejected-Hermes-reinitialization follow-up at `70d9d49d3120d51a6b2b2870d542390585e93ea9` (tree `65f60afa2cc6f3a834b7b33eadb53d49befedf60`) separately passed 45 provider tests in 0.76s and Ruff. That run used the existing in-memory client fixture. Later component results appear beside their findings above and in committed reports; none is presented as re-execution of this parent suite at the latest head.

### Scope and limitations

These are package-side reproductions using disposable local state, synthetic keys/tokens and controlled service boundaries where stated. No live tenant, real credential, hosted persistence or hosted authorization bypass was tested. Linux filesystem evidence does not establish every platform's behavior. Atomic local replacement preserves recorded Unix modes and outside aliases, but requires parent-directory write permission; ownership/ACL preservation and arbitrary concurrent parent relocation are outside the demonstrated guarantee. Warm-client revocation covers revocation completed before the subsequent validation check, matching the existing cold/API boundary.

This remains the single #1852 carrier and its existing BountyHub claim. Acceptance, the competitive prize award and payment remain pending.

[main-report]: https://github.com/woahwhattheheck/memanto/blob/5a695228728ee4b7439479a87783c737639ec31a/docs/security/bounty-1852-woahwhattheheck.md
[connect-hardlink]: https://github.com/woahwhattheheck/memanto/blob/5a695228728ee4b7439479a87783c737639ec31a/docs/security/bounty-1852-woahwhattheheck.md#follow-up-local-connect-hard-link-aliases
[cached-revocation]: https://github.com/woahwhattheheck/memanto/blob/5a695228728ee4b7439479a87783c737639ec31a/docs/security/bounty-1852-cached-session-revocation.md
[memory-cache]: https://github.com/woahwhattheheck/memanto/blob/5a695228728ee4b7439479a87783c737639ec31a/docs/security/bounty-1852-woahwhattheheck.md#5-automatic-sync-can-reuse-another-credentials-or-deployments-export
[okf-cache]: https://github.com/woahwhattheheck/memanto/blob/5a695228728ee4b7439479a87783c737639ec31a/docs/security/bounty-1852-okf-cache-isolation.md
[nested-markers]: https://github.com/woahwhattheheck/memanto/blob/5a695228728ee4b7439479a87783c737639ec31a/docs/security/bounty-1852-woahwhattheheck.md#6-nested-sync-markers-preserve-recalled-instructions-after-clearing
[credential-provider]: https://github.com/woahwhattheheck/memanto/blob/5a695228728ee4b7439479a87783c737639ec31a/docs/security/bounty-1852-woahwhattheheck.md#7-moorcheh-credentials-survive-conversation-memory-extraction
[credential-json]: https://github.com/woahwhattheheck/memanto/blob/5a695228728ee4b7439479a87783c737639ec31a/docs/security/bounty-1852-json-credential-redaction.md
[session-lock]: https://github.com/woahwhattheheck/memanto/blob/5a695228728ee4b7439479a87783c737639ec31a/docs/security/bounty-1852-woahwhattheheck.md#8-automatic-renewal-can-undo-a-completed-logout-across-processes
[active-marker]: https://github.com/woahwhattheheck/memanto/blob/5a695228728ee4b7439479a87783c737639ec31a/docs/security/bounty-1852-active-session-marker.md
[forwarded-chain]: https://github.com/woahwhattheheck/memanto/blob/5a695228728ee4b7439479a87783c737639ec31a/docs/security-reports/1852-forwarded-chains.md
[okf-framing]: https://github.com/woahwhattheheck/memanto/blob/5a695228728ee4b7439479a87783c737639ec31a/docs/security/bounty-1852-okf-framing.md
[okf-context]: https://github.com/woahwhattheheck/memanto/blob/5a695228728ee4b7439479a87783c737639ec31a/docs/security/bounty-1852-woahwhattheheck.md#follow-up-okf-export-includes-other-agents-local-context
[restricted-hermes]: https://github.com/woahwhattheheck/memanto/blob/5a695228728ee4b7439479a87783c737639ec31a/docs/security/bounty-1852-woahwhattheheck.md#follow-up-honor-restricted-hermes-contexts-for-explicit-memory-writes
[ui-date]: https://github.com/woahwhattheheck/memanto/blob/5a695228728ee4b7439479a87783c737639ec31a/docs/security/ui-date-html-injection.md
[opaque-tokens]: https://github.com/woahwhattheheck/memanto/blob/5a695228728ee4b7439479a87783c737639ec31a/docs/security/bounty-1852-opaque-token-redaction.md
