# LangGraph to Memanto and OKF mapping

Adapter scope: official sync SQLite `SqliteSaver` only. Migrates the **latest**
checkpoint state per `(thread_id, checkpoint_ns)`. Not Postgres/Redis/Async, and
not a full checkpoint-history migration. Non-JSON / non-`BaseMessage` values are
rendered with `repr()` and should be reviewed before import. The OKF importer
does not emit token, latency, or billing savings.

| LangGraph concept | OKF representation | Memanto type | Preservation rule |
| --- | --- | --- | --- |
| Thread ID | `langgraph-thread:<id>` tag | All | Every memory remains traceable to its source thread. |
| Checkpoint namespace | `langgraph-namespace:<ns>` tag | All | Empty namespaces are treated as `root`. |
| Latest checkpoint ID | `langgraph://` resource URI | All | The source checkpoint remains addressable without exposing the database. |
| `messages` channel | Markdown transcript | `artifact` | **Proven in demo.** Human, AI, system, and tool roles are retained. |
| Profile field containing preference, style, or format | One document per field | `preference` | **Proven in demo.** Later LangGraph corrections win because the latest checkpoint is authoritative. |
| `decisions` channel | One document per item | `decision` | **Proven in demo.** List order and text are retained. |
| `goals` channel | One document per item | `goal` | **Proven in demo.** List order and text are retained. |
| Other dictionary / list / scalar application channels (demo: facts) | One document per key or item | `fact` | **Proven in demo for fact-shaped channels.** Non-string values are preserved as readable JSON when possible. |
| `commitments` or `tasks` channel | One document per item | `commitment` | **Heuristic, fixture-tested only.** The focused unit fixture covers list order, text, and type mapping, but the live cloud demo does not exercise this channel. |
| Checkpoint timestamp | OKF `timestamp` | `created_at` on import | The source time survives the OKF import path. |

The adapter migrates the latest state of every discovered thread/namespace
because that is the state an active LangGraph agent recalls. Full checkpoint
counts remain in the summary, and the latest transcript preserves the
conversation that produced that state.
