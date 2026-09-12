# Codex → Memanto mapping table

Every Codex concept below is read from a **real, unmodified** Codex store
(`~/.codex`) and written to one OKF document under
`okf-bundle/memories/<memanto-type>/`.

The authoritative Memanto memory type lives in the namespaced
`x_memanto.type` frontmatter key. The top-level OKF `type` keeps the *source*
concept name, so non-Memanto OKF consumers still see provenance.

## 1. Source concept → Memanto memory type

| Codex source | Codex object | Memanto type (`x_memanto.type`) | OKF `type` | Why |
|---|---|---|---|---|
| `memories_1.sqlite` → `stage1_outputs.raw_memory` / `.rollout_summary` | distilled memory | `fact` | `codex-distilled-memory` | Codex already distilled this; it is a settled statement of what happened. |
| `goals_1.sqlite` → `thread_goals.objective` | long-running objective | `goal` | `codex-thread-goal` | Direct analogue: an objective with a lifecycle status. |
| `state_5.sqlite` → `threads` | session registry row | `context` | `codex-session` | Session/episode envelope: cwd, model, provider, timestamps. |
| `sessions/**/rollout-*.jsonl` → `response_item.message` (role `user`) | user turn | `preference` | `codex-user-message` | The human's stated intent — what they wanted, and by extension what they prefer. |
| … same file → `response_item.message` (role `assistant`) | assistant turn | `observation` | `codex-assistant-message` | What the agent concluded or produced. |
| … → `response_item.reasoning` | hidden chain-of-thought | `learning` | `codex-reasoning` | *Opt-in* (`--include-reasoning`). The single most valuable and least portable artifact: Codex exposes it through no export at all. |
| … → `response_item.function_call` / `custom_tool_call` | tool invocation | `artifact` | `codex-tool-call` | A produced artifact: tool name + arguments. |
| … → `compacted` | memory compaction event | `decision` | `codex-compaction` | The moment Codex decided what to forget. An explicit memory-management decision. |
| … → `session_meta.base_instructions` | system instructions | `instruction` | `codex-base-instructions` | The rules the agent was actually governed by. |

Nothing is silently dropped: concepts that do not map onto a first-class
Memanto field are preserved verbatim in the frontmatter (`thread_id`,
`usage_count`, `goal_id`, `cwd`, …), which `okf_loader.py` collects into
`extra` and the importer re-emits into the `[Supporting data]` footer.

## 2. Memanto memory type → OKF frontmatter

| OKF key | Origin | Notes |
|---|---|---|
| `type` | source concept | Free-form; auto-classified by Memanto when it has no mapping. |
| `title` | generated from the memory's first line | Human-readable, ≤ 120 chars. |
| `description` | summary / intent line | Short; also what a search preview shows. |
| `tags` | `["codex", <concept>, …]` | Drives filtering; carries `status:` and `tool:` facets. |
| `timestamp` | `generated_at` / rollout `timestamp` | ISO-8601 UTC. |
| `x_memanto.type` | **authoritative** Memanto type | One of the 13 valid types. |
| `x_memanto.source` | `codex:<db>.<table>` / `codex:rollout.<event>` | Exact provenance for audit. |
| `x_memanto.provenance` | `explicit_statement` \| `inferred` \| `observed` \| `imported` | Matches Memanto's `VALID_PROVENANCE_TYPES`. |
| extra keys | `thread_id`, `goal_id`, `cwd`, `usage_count` | Preserved, never discarded. |

## 3. Round-trip semantics

```
~/.codex ──(codex_to_okf.py)──▶ okf-bundle/ ──(memanto migrate okf)──▶ Memanto
                                      │                                    │
                                      │                       memanto memory export --okf
                                      │                                    ▼
                                      └──────── identical layout ◀──── roundtrip/
```

Because the adapter writes the same layout Memanto's own exporter uses
(`memories/<type>/<n>-<slug>.md`, one document per file, `index.md` ignored),
the round trip Memanto → OKF → Memanto is lossless, and a Codex bundle is
indistinguishable from a native Memanto export.

`--stacked` writes one file per type with documents separated by Memanto's
`<!-- okf-entry -->` sentinel instead — the exact form `memanto memory export`
produces at scale, and the loader splits it back apart identically.

## 4. Privacy posture

Codex stores absolute paths, host names and e-mail addresses. Migration output
is meant to be shareable, so `codex_to_okf.py` redacts **by default**:

| Pattern | Replaced with |
|---|---|
| `$HOME` and `C:\Users\<name>` | `~` |
| `/Users/<name>`, `/home/<name>` | `~` |
| e-mail addresses | `<email>` |
| `ghp_…`, `sk-…`, `xoxb-…` tokens | `<token>` |

`--no-redact` keeps everything verbatim for local-only use, and
`--include-reasoning` is opt-in for the same reason.

## 5. Validation evidence

Run against a real store (42 rollout transcripts, 77 MB, 42 threads,
5 distilled memories):

```
$ python codex_to_okf.py --out ./okf-bundle
Memories    : 295
  artifact       17
  context        42
  fact            5
  instruction    47
  observation   106
  preference     78

$ memanto migrate okf ./okf-bundle --dry-run
┌───────────────────────────── Dry run complete ──────────────────────────────┐
│ OKF nodes: 295                                                              │
│ Mapped memories: 295  (skipped 0)                                           │
│ Type breakdown: artifact: 17, context: 42, fact: 5, instruction: 47,        │
│ observation: 106, preference: 78                                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

295/295 nodes mapped, **0 skipped** — the bundle is accepted by Memanto's own
loader with the intended type breakdown preserved exactly.
