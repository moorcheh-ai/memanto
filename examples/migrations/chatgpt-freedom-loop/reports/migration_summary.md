# Migration Summary — ChatGPT Freedom Loop

- Generated: `2026-07-25T09:32:45.152662+00:00`
- Source file: `/Users/trinity-hub/DOME-HUB/development/active/sovereign-income/worktrees/memanto-1634/examples/migrations/chatgpt-freedom-loop/data/conversations.json`
- Source conversations: **4**
- Mapped memories: **5**

## Type breakdown

| Type | Count |
|------|------:|
| auto | 1 |
| decision | 1 |
| observation | 1 |
| preference | 2 |

## Fidelity notes

- Temporal timestamps preserved from ChatGPT message `create_time`
- `source_ref` format: `{conversation_id}:{message_id}`
- Branching edits linearized via first-child path
- Multimodal parts emit text + `[image]` markers

## Next (live Memanto)

```bash
memanto migrate chatgpt --file ./data/conversations.json --dry-run --report
memanto migrate chatgpt --file ./data/conversations.json
memanto memory export --okf ./okf_live
```
