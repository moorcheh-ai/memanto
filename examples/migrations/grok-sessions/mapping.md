# Source → Memanto / OKF mapping (Path B)

| Source concept | Where it lives | OKF `type` | OKF fields used | Notes |
| --- | --- | --- | --- | --- |
| Operator preference | `MEMORY.md` `## Preferências` bullets | `preference` | title, body, tags, generated.at | Durable, git-friendly |
| Project map row | `MEMORY.md` table | `fact` | title = path, body = path → meaning | Skips header rows |
| Recurring failure | `MEMORY.md` `## Padrões` | `observation` | title, body | Not a secret dump |
| Session identity | `summary.json` | `episode` | title, body, resource | Model, counts, cwd |
| Goal text | `goal/state.json` `objective` | `goal` | body redacted | Emails stripped |
| Plan change | `goal/plan.md` `## Deviations` | `decision` | one doc per bullet | |
| Operator utterance | `chat_history.jsonl` `<user_query>` | `observation` | first 20 queries | compaction_meta skipped |
| Tool traces / system prompts | JSONL other types | — | dropped | Keeps the wiki readable |

Redaction: `mj_live_*`, `ot_art_*`, JWTs, `sk-`/`ak_`/`tq_`/`gho_` tokens, and email addresses become `[REDACTED]` before write.
