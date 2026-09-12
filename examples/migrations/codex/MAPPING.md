# Codex to OKF Mapping

The adapter treats one Codex stage-one row as a source record and each
`### Task N` block inside its `raw_memory` as an importable memory. This keeps
Codex's own extraction boundary while avoiding one giant memory per rollout.

## Field Mapping

| Codex source | OKF or Memanto target | Behavior |
| --- | --- | --- |
| `thread_id` + task number | `resource` | Stable `codex://thread/<id>#task-N` provenance |
| Rollout `turn_id` | `resource`, `codex_turn_id` | Adds `/turn/<id>` so multi-turn provenance stays unique |
| Task heading | `title` | Truncated to 100 characters |
| Stage-one `description` | `description` | Falls back to rollout summary or task title |
| Task block | Markdown body | Preserved verbatim after defensive redaction |
| Inferred semantic class | `type` and `x_memanto.type` | Uses a deterministic rule table below |
| Stage-one `keywords` | `tags` | Normalized, deduplicated, capped at 12 |
| Task group or cwd | `tags` | Added as a normalized project-context tag |
| `source_updated_at` | `timestamp` | Unix seconds, milliseconds, or ISO 8601 normalized to UTC |
| `cwd` | `codex_cwd` | Home username replaced with `~` |
| `rollout_path` | `codex_rollout_path` | Home and temporary roots redacted |
| `git_branch` | `codex_git_branch` | Preserved after redaction |
| `cli_version` | `codex_cli_version` | Preserved |
| `rollout_slug` | `codex_rollout_slug` | Preserved |
| Usage and phase-two fields | `codex_*` extras | Preserved in OKF frontmatter |

Memanto's OKF loader maps the standard fields directly. The `codex_*`
frontmatter fields are intentionally unknown to the baseline OKF schema, so
Memanto preserves them in the imported memory's `[Supporting data]` footer.

## Type Inference

Rules are evaluated in this order:

| Signal | Memanto type |
| --- | --- |
| `task_outcome: fail` | `error` |
| Non-empty preference section without reusable or failure content | `preference` |
| A meaningful failure lesson | `learning` |
| Adopted, chosen, or changed decision language | `decision` |
| Preference language | `preference` |
| Durable must/always/never workflow language | `instruction` |
| Goal or plan language | `goal` |
| Raw rollout fallback or uncertain outcome | `context` |
| No stronger signal | `learning` |

`Failures and how to do differently: - No failure ...` is treated as an empty
failure section. It does not override a task's actual decision or preference
semantics.

## Rollout Fallback Mapping

Persisted rollouts contain far more than user-visible memory. The fallback
allowlist is intentionally narrow:

| Rollout event | Included |
| --- | --- |
| `event_msg.user_message` | Yes |
| `event_msg.agent_message` with `phase=final_answer` | Yes |
| `event_msg.task_complete.last_agent_message` | Yes, only as a missing-final fallback |
| Developer messages | No |
| Reasoning and commentary | No |
| Tool calls and tool outputs | No |
| Images and attachments | No |

Each completed turn becomes one `context` memory with the user goal and final
answer. Stage-one memory is preferred because Codex has already distilled the
rollout into durable, secret-redacted knowledge.

## Known Losses and Limits

- SQLite job leases, retry metadata, and phase-two workspace artifacts are not
  agent memories and are not migrated.
- Rollout fallback omits intermediate work by design.
- YAML parsing is deliberately limited to Codex's flat stage-one frontmatter;
  the adapter does not accept arbitrary YAML objects from an untrusted source.
- Memory type inference is deterministic, not an LLM classification.
- Generic redaction reduces accidental leakage but cannot determine whether a
  non-secret business fact is sensitive.
