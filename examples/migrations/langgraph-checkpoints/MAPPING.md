# LangGraph to Memanto and OKF mapping

| LangGraph concept | OKF representation | Memanto type | Preservation rule |
| --- | --- | --- | --- |
| Thread ID | `langgraph-thread:<id>` tag | All | Every memory remains traceable to its source thread. |
| Checkpoint namespace | `langgraph-namespace:<ns>` tag | All | Empty namespaces are treated as `root`. |
| Latest checkpoint ID | `langgraph://` resource URI | All | The source checkpoint remains addressable without exposing the database. |
| `messages` channel | Markdown transcript | `artifact` | Human, AI, system, and tool roles are retained. |
| Profile field containing preference, style, or format | One document per field | `preference` | Later LangGraph corrections win because the latest checkpoint is authoritative. |
| `decisions` channel | One document per item | `decision` | List order and text are retained. |
| `goals` channel | One document per item | `goal` | List order and text are retained. |
| `commitments` or `tasks` channel | One document per item | `commitment` | List order and text are retained. |
| Other dictionary fields | One document per key | `fact` | Non-string values are preserved as readable JSON. |
| Other lists or scalars | One document per item or channel | `fact` | Unknown application state is preserved instead of dropped. |
| Checkpoint timestamp | OKF `timestamp` | `created_at` on import | The source time survives the OKF import path. |

The adapter migrates the latest state of every thread because that is the state
an active LangGraph agent recalls. Full checkpoint counts remain in the summary,
and the latest transcript preserves the conversation that produced that state.
