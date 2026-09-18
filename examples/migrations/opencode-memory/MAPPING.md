# opencode → OKF mapping

Source: opencode SQLite (`session` / `message` / `part`, JSON `data` columns).

| opencode element | OKF `type` | Notes |
|---|---|---|
| session row | `context` | title, directory, agent, model, tokens in/out, cost preserved in `x_memanto` |
| user `text` part | `goal` | the request being made |
| assistant `text` part (conclusion) | `decision` | default for assistant output |
| assistant `text` part stating a reusable lesson | `learning` | matched on lesson-cues ("lesson", "remember", "going forward", …) |
| `tool` part, status completed | `artifact` | tool name + input + truncated output as fenced code |
| `tool` part, status error | `observation` | failures are memory too |
| `step-start` / `step-finish` / `reasoning` | — | folded into the session `context` (tokens/cost), not separate files |

All rows carry `x_memanto: {source: opencode, provenance: imported, …}`
for structured consumers, plus top-level `opencode_*` frontmatter keys
(session/model/token/cost provenance). The loader preserves unknown keys as
`extra` and `map_okf` surfaces them in the row footer, so they survive real
imports. Tool outputs are REDACTED by default at export
(`--include-tool-payloads` opts back into truncated payloads and may leak
secrets — never commit such exports).
