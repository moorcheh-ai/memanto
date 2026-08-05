# OpenAI Agents SDK `SQLiteSession` → Memanto (OKF 0.2)

A migration bridge for a source Memanto does not support yet: the persistent
**`SQLiteSession`** that the [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/sessions/)
uses to store conversation history.

The SDK keeps history as raw OpenAI *Responses* items — one JSON object per row in
`agent_messages.message_data`. Memanto can import an [OKF](https://docs.memanto.ai/integrations/okf)
bundle. Nothing connected the two. `okf_adapter.py` is that connector, and
`sample/` is a complete worked example produced by running the real SDK.

```
agents.Runner + agents.SQLiteSession  ->  sessions.db  ->  okf_adapter.py  ->  OKF 0.2 bundle
                                                                                    |
                                                                    memanto migrate okf <bundle>
```

| | |
|---|---|
| Source tool | `openai-agents` **0.19.4** (pinned in `requirements.txt`, recorded in every report) |
| Source data | A real `Runner` run over a real `SQLiteSession` — see [Is the source data real?](#is-the-source-data-real) |
| Output | OKF **0.2** bundle, 16 documents from 19 source items |
| Import path | `memanto migrate okf <bundle>` — verified end to end as a dry run |
| Dependencies | The adapter and the verifier are **standard library only** |

---

## Files

```
run_demo.sh              One-command reproduction: generate -> convert -> import -> verify.
okf_adapter.py           The bridge: SQLiteSession -> OKF 0.2. Stdlib only, CLI driven.
generate_session.py      Populates a real SQLiteSession by running the SDK's Runner.
verify_artifacts.py      Re-derives sample/okf from sample/source and diffs it.
requirements.txt         openai-agents==0.19.4 (only generate_session.py needs it).
DEMO.md                  Storyboard + exact keystrokes for the demo video.

sample/source/session_snapshot.json    Verbatim dump of the SDK's rows (the .db is gitignored).
sample/okf/                            The generated OKF 0.2 bundle.
sample/evidence/                       Console output and the migration report, as produced.
```

Tests live with the repo suite: `tests/test_openai_agents_session_migration.py`.

---

## Reproduce it

From this directory, with Python 3.10+:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # openai-agents==0.19.4
pip install -e ../../..                  # the memanto CLI, for the import step

./run_demo.sh                            # everything below, in one command
```

`run_demo.sh` runs a fresh SDK session, the adapter, Memanto's real dry-run
import and the artifact verifier inside a temporary workspace that it deletes on
exit. It needs no API keys, keeps Memanto's run directory inside that workspace
rather than your `~/.memanto`, never writes to `sample/`, and fails fast on the
first error. Its transcript is committed as
`sample/evidence/07-run-demo.txt`.

The individual steps, if you'd rather drive them yourself:

```bash
# 1. Produce the source data with the real SDK (no API key, no network).
python generate_session.py

# 2. See what is in the database.
python okf_adapter.py --db sample/source/agent_sessions.db --list-sessions

# 3. Convert one session into an OKF 0.2 bundle.
python okf_adapter.py \
    --db sample/source/agent_sessions.db \
    --session workspace-buddy-demo \
    --out sample/okf \
    --report sample/evidence/adapter-report.json \
    --source-package-version 0.19.4 \
    --force

# 4. Import it through Memanto's real OKF path.
memanto migrate okf sample/okf --dry-run     # drop --dry-run to write, needs a Moorcheh key

# 5. Prove the committed artifacts match the committed source.
python verify_artifacts.py
```

Steps 2–5 need no API keys at all. Step 1 needs none either — see below.

Re-running step 1 rewrites the database with fresh wall-clock timestamps, so the
regenerated bundle will differ from the committed one in its `timestamp` fields
(only). `verify_artifacts.py` and the test suite compare against
`sample/source/session_snapshot.json`, the committed record of the run that
produced `sample/okf`, so they stay exact.

## Is the source data real?

Yes. `generate_session.py` drives `agents.Runner` across seven turns against a
real `agents.SQLiteSession`; the SDK does the tool dispatch and every database
write. Nothing in `sample/source/` is hand-authored — `session_snapshot.json` is
a verbatim dump of the schema and rows SQLite ended up holding, including the
SDK's own `CREATE TABLE` statements and the exact `message_data` TEXT.

The one stand-in is the **model**. Following the SDK's own test pattern,
`ScriptedModel` implements `agents.models.interface.Model` and replays a fixed
list of Responses outputs, so the demo runs with no API key, no network and no
spend. The assistant replies and tool arguments are therefore *scripted demo
copy, not generated text* — but the agent loop, the tool execution and the
persisted item shapes are exactly what a live model produces. Swap
`ScriptedModel` for `model="gpt-4o-mini"` and the same script runs against OpenAI.

The `.db` file is not committed (`*.db` is gitignored repo-wide); the snapshot is
its committed equivalent, and both the verifier and the tests rebuild a real
SQLite database from it before doing anything else.

### The scenario

Seven turns of an evolving workspace assistant, chosen to exercise the shapes a
migration has to survive:

| Turn | What happens | Why it is there |
|---|---|---|
| 1 | A standing rule: metric units, three sentences max | preference / instruction |
| 2 | The orders service runs PostgreSQL 16 | plain fact |
| 3 | Deploy-window question → `lookup_team_calendar` tool call | **structured content blocks**, reasoning item, tool call + output |
| 4 | "Correction: the window moved to Thursday 09:00 UTC" | a correction that supersedes the tool's answer |
| 5 | "Actually, drop the three-sentence rule" | a preference that reverses turn 1 |
| 6 | A migration plan promised by 2026-08-14 | commitment with a due date |
| 7 | An incident logged → `record_incident` tool call | second tool, different argument shape |

A second session, `sandbox-smoke-test`, shares the database so `--list-sessions`
and `--session` have something to select between.

---

## Source → OKF mapping

One OKF document per source item, except that a `function_call` and its matching
`function_call_output` merge into one document — a call id without its result is
not a memory.

| Source item (`message_data`) | OKF `type` | Memanto type | Notes |
|---|---|---|---|
| `{"role": "user", "content": "..."}` | `openai-agents.user-message` | *auto* | plain-string content |
| `{"role": "user", "content": [{"type": "input_text", ...}]}` | `openai-agents.user-message` | *auto* | structured blocks; all text blocks joined |
| `{"type": "message", "role": "assistant", "content": [{"type": "output_text", ...}]}` | `openai-agents.assistant-message` | *auto* | assistant output item |
| `{"role": "system" \| "developer", ...}` | `openai-agents.system-message` | *auto* | |
| `{"type": "function_call", ...}` **+** `{"type": "function_call_output", ...}` | `openai-agents.tool-call` | `artifact` | merged; both row ids preserved |
| `{"type": "function_call_output", ...}` with no call | `openai-agents.tool-output` | `artifact` | kept, labelled as an orphan |
| `{"type": "reasoning", ...}` | — | — | **skipped**: internal scratchpad |
| any other `type` (hosted tool calls, handoffs, …) | — | — | **skipped**, counted by type |

### Field mapping

| OKF frontmatter | Value | Where it lands in Memanto |
|---|---|---|
| `type` | `openai-agents.<kind>` | free-form → `[Supporting data]` footer |
| `title` | `User · turn 5 · <first 60 chars>` | memory title |
| `description` | first body line | prefix of memory content |
| `resource` | `openai-agents-sqlite://<session>/<table>/<row id>` | `source_ref` |
| `tags` | `openai-agents`, `session:<id>`, `turn:<n>`, `item:<kind>`, `role:<role>`, `tool:<name>` | memory tags |
| `timestamp` | row `created_at`, normalised to ISO 8601 UTC — omitted if unparseable | `created_at` |
| `status` | `stable` | footer |
| `generated` | `{by: openai-agents-sqlite-session-to-okf/<version>, at: <timestamp>}` (OKF 0.2 §5.2 trust) | footer |
| `sources` | one entry per contributing row (OKF 0.2 §5.1 provenance) | footer |
| `x_memanto.source` | `openai-agents-sqlite-session` | memory `source` |
| `x_memanto.confidence` | 0.9 user / 0.75 assistant / 0.9 tool | memory `confidence` |
| `x_memanto.type` | `artifact` for tool records only | memory `type` |
| `x_memanto.provenance` | `explicit_statement` / `observed` | round-trip only — Memanto stamps imports as `imported` |
| body | the message text verbatim, plus a `**Provenance**` line naming the session, row id(s), role and timestamp | memory content |

### OKF 0.2 conformance notes

* **`generated.by` is the adapter, not the speaker.** Spec §7 allows exactly
  three actor forms — `<producer>/<version>`, `human:<id>` and `process:<id>` — so
  a bare `user` / `assistant` is not a valid identity, and it would also misstate
  authorship: the adapter wrote the document. Every concept therefore carries
  `openai-agents-sqlite-session-to-okf/1.0.0`. The speaker is preserved where it
  belongs — the `role:` tag, the body's `**Provenance**` line, and
  `x_memanto.provenance`. `generated.at` stays the source item's timestamp, which
  §5.2 defines as the last meaningful *content* change.
* **Index files carry no frontmatter** (§8). The one exception the spec allows is
  the bundle-root `index.md`, which declares `okf_version: "0.2"` and nothing
  else. Memanto's loader skips `index.md` by name, so this costs nothing on
  import.
* **No malformed trust data.** `timestamp` and `generated.at` must be ISO 8601,
  so a source row whose `created_at` cannot be parsed yields a document with
  *neither* field rather than an invalid one. The omission is called out in a
  `> Note:` line in the document and counted in the report as
  `counts.mapped_without_timestamp` — it is never backfilled with a guess.
* **Honest code fences.** Tool arguments and results are fenced as `json` only
  when they really parse as JSON; a tool that returns a plain string gets a
  `text` fence and its bytes untouched.

### Why most documents carry no Memanto type

The adapter has no model and does not guess. Calling every user turn a
`preference` (or a `fact`, or a `context`) would be wrong more often than right
and would *override* Memanto's own classifier, which reads the text and picks a
type. So message documents deliberately omit `x_memanto.type` — the dry run
reports them as `auto`. The single exception is a tool record: Memanto's
`artifact` type is defined as "tool outputs, files, reports, and external
references", which is exactly what it is.

### Design rules the adapter holds to

* **Read-only, identifier-safe.** The database is opened `mode=ro` through a
  percent-encoded `file:` URI, so a path containing `?` or `#` cannot be
  misparsed. Table names are validated against a strict identifier pattern *and*
  introspected from `sqlite_master` / `PRAGMA table_info` before any SQL is
  built, so a custom `--messages-table` can never become an injection point. A
  test asserts the source file's hash is unchanged after a migration.
* **One consistent read snapshot.** `SQLiteSession` runs in WAL mode, so
  committed rows can live only in the `-wal` sidecar and separate connections
  each get their own view. Before reading anything, the adapter copies the
  source through SQLite's backup API — a single read transaction, WAL content
  included — into a private temporary file, then reads rows, reads metadata and
  computes the evidence hash from that one closed copy. The copy is always
  deleted, and only the user's own filename appears in output.

  **`read_snapshot_sha256` therefore hashes that consistent snapshot, not the
  raw `.db`.** Hashing the main file would be misleading evidence: a WAL-only
  write leaves it byte-identical while the data changes, so two different
  migrations could show one hash. `session_snapshot.json` records the same value
  under the same key (plus `db_file_sha256`, the raw main-file hash, for
  reference), which is what ties the committed report to the committed capture.
* **Tolerant of custom schemas.** `created_at` / `updated_at` on the sessions
  table are optional: a table carrying only `session_id` reads back as `None`
  instead of raising.
* **Nothing is silently stringified.** Non-text content blocks (images, files,
  refusals) are named in a `> Note:` line, never dumped as a Python dict.
  Unsupported item types are skipped and counted, not coerced into prose.
* **Nothing is silently lost.** Every source row appears in the report as either
  mapped or skipped; `source_items_consumed` must equal `source_items`.
* **Deterministic.** Output is a pure function of the source rows — no wall
  clock, no randomness, sorted iteration. Only the report carries a
  `generated_at`.
* **Safe output directory.** The adapter refuses to write into a non-empty
  directory it did not produce, and needs `--force` to replace one it did.

---

## Results

From `sample/evidence/03-adapter-run.txt`:

```
Session      : workspace-buddy-demo
Source items : 19
Mapped docs  : 16 (assistant-message=7, tool-call=2, user-message=7)
Skipped items: 1 (reasoning_trace=1)
OKF bundle   : sample/okf
Report       : sample/evidence/adapter-report.json
```

19 source rows → 16 documents: 18 rows map (two pairs of tool rows merge), and
one reasoning item is skipped.

From `sample/evidence/04-memanto-migrate-dry-run.txt` — the repository's real
`memanto migrate okf` command, run against the committed bundle:

```
╭──────────────────────────────── Dry run complete ────────────────────────────────╮
│ OKF nodes: 16                                                                    │
│ Mapped memories: 16  (skipped 0)                                                 │
│ Type breakdown: artifact: 2, auto: 14                                            │
│                                                                                  │
│ Dry run — no writes performed.                                                   │
╰──────────────────────────────────────────────────────────────────────────────────╯
```

Memanto loads all 16 documents and maps all 16 — nothing is dropped at the import
boundary. `sample/evidence/05-memanto-mapped-preview.json` is the
`mapped_preview.json` Memanto itself wrote for that run: the exact
`batch_remember` payloads, with `source_ref`, `created_at`, tags and confidence
carried through.

> **No live import was run.** No Moorcheh API key is available in this
> environment, so `memanto migrate okf sample/okf` (without `--dry-run`) and any
> subsequent recall have **not** been executed, and no such output is claimed.
> Everything above is a credential-free dry run reproduced by the commands in
> this README. With a key, drop `--dry-run` and add `--agent <id>`.

### Evidence

| File | What it is |
|---|---|
| `sample/evidence/01-generate-session.txt` | the SDK run that produced the source database |
| `sample/evidence/02-list-sessions.txt` | `--list-sessions` against that database |
| `sample/evidence/03-adapter-run.txt` | the conversion |
| `sample/evidence/adapter-report.json` | per-item report: every mapped row, every skipped row and why |
| `sample/evidence/04-memanto-migrate-dry-run.txt` | `memanto migrate okf --dry-run` |
| `sample/evidence/05-memanto-mapped-preview.json` | Memanto's own mapped preview for that dry run |
| `sample/evidence/06-verify-artifacts.txt` | `verify_artifacts.py`, 8/8 checks |
| `sample/evidence/07-run-demo.txt` | a full `./run_demo.sh` transcript, end to end |

---

## Tests

```bash
pytest tests/test_openai_agents_session_migration.py -q      # from the repo root
```

54 tests, no `openai-agents` install required (they rebuild a real SQLite
database from the committed snapshot):

* **Source parser** — schema introspection, identifier rejection (`agent_messages;
  DROP TABLE …`), missing table/column, missing file, a database path containing
  `?` and `#`, a sessions table without the optional timestamp columns, and the
  source file left untouched.
* **Identifier safety** — a session id holding spaces, `/`, `?`, `#`, `%`, a tab
  and non-ASCII is percent-encoded into one URI component, while ordinary ids
  stay byte-identical.
* **Role and content variants** — plain strings, structured blocks, multi-block
  assistant output, system messages, turn numbering, non-text blocks reported
  rather than stringified.
* **Tool calls** — call+output merge, call without output, orphan output, JSON vs
  non-JSON payloads getting the right fence tag, and the merged record taking its
  timestamp from the *result* row (dropping it, with a caveat, when that row has
  none).
* **WAL consistency** — a database written through the WAL while a writer holds
  it open: the migration picks up the WAL-only rows, and the recorded hash moves
  with the logical state even though the main `.db` file is byte-identical.
* **Malformed rows** — invalid JSON, wrong top-level shape, BLOB `message_data`:
  each skipped with a reason, never fatal.
* **OKF 0.2 conformance** — index files carry no frontmatter except the root's
  `okf_version`; `generated.by` matches a §7 actor form; an unparseable source
  timestamp emits neither `timestamp` nor `generated`.
* **Determinism** — two runs, byte-identical trees and identical reports.
* **Committed artifact integrity** — `sample/okf` is regenerated from
  `sample/source/session_snapshot.json` and diffed byte for byte; the committed
  report is re-derived; the bundle is pushed through Memanto's real
  `load_okf_bundle` + `map_okf`; and no local path or home directory appears in
  any committed artifact.

## Limitations

* **Text only.** Images, files, audio and refusal blocks are named but not
  carried across; there is no OKF representation for their bytes here.
* **Reasoning items are dropped by design.** They are the model's scratchpad, not
  something to recall later. They appear in the report's `skipped_by_reason`.
* **Hosted tool calls** (`file_search_call`, `web_search_call`, computer use,
  handoffs) are skipped and counted rather than guessed at. Each is a distinct
  shape that deserves its own mapping; adding one means adding a branch in
  `transform()` and a test.
* **One document per item.** The adapter does not summarise or deduplicate, so a
  correction and the statement it corrects both arrive as memories. Resolving
  that is Memanto's job, not the bridge's.
* **Second-resolution timestamps.** `SQLiteSession` stores SQLite's
  `CURRENT_TIMESTAMP`, so every item within one turn shares a second. The demo
  sleeps ~1.1 s between turns (real elapsed time) so turns are distinguishable.
  A row whose `created_at` is not ISO 8601 (possible if another writer shares the
  table) loses its `timestamp` and `generated` block rather than gaining a
  fabricated one — see `counts.mapped_without_timestamp` in the report.
* **Sessions are migrated one at a time.** Run the adapter once per `--session`;
  each bundle is self-contained.
* **`x_memanto` extras do not survive import.** Memanto's mapper reads
  `type`, `confidence` and `source` from that block; anything else there is for
  OKF round-trips only. That is why session, role and row ids are written into
  the document body, where they stay searchable.
