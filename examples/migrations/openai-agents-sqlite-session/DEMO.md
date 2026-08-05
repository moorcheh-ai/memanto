# Demo storyboard — OpenAI Agents SDK session → Memanto

Target: **75–90 seconds**, one terminal, no cuts needed. Everything below runs
credential-free, so the take can be recorded end to end without redaction.

## Before you hit record

```bash
cd examples/migrations/openai-agents-sqlite-session
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e ../../..
rm -rf sample/okf sample/source/agent_sessions.db     # start from a clean slate
clear
```

Shots 1–6 below walk through the stages one at a time, which reads better on
camera. If you want a single take with no typing, `./run_demo.sh` runs all of it
end to end in a throwaway workspace — good for the closing shot or a short cut.

Terminal ~100 columns, large font. Have `sample/okf/memories/tool-call/` open in
an editor in a second window for shot 4.

---

## Shot 1 — the problem (0:00–0:12)

**On screen:** the title line, then `generate_session.py` running.

```bash
python generate_session.py
```

> "The OpenAI Agents SDK stores your agent's memory in a SQLite file. This is a
> real Runner, a real SQLiteSession, seven turns of a workspace assistant —
> preferences, a correction, two tool calls."

Let the seven `turn N (…)` lines scroll. Land on `Items : 21`.

## Shot 2 — the raw source (0:12–0:25)

```bash
sqlite3 sample/source/agent_sessions.db \
  "SELECT id, substr(message_data,1,72) FROM agent_messages LIMIT 5;"
```

> "That's what's in there. Raw OpenAI Responses items — a JSON blob per row.
> Portable to nothing."

## Shot 3 — the bridge (0:25–0:45)

```bash
python okf_adapter.py --db sample/source/agent_sessions.db --list-sessions

python okf_adapter.py \
  --db sample/source/agent_sessions.db \
  --session workspace-buddy-demo \
  --out sample/okf --report report.json
```

Pause on the summary block:

```
Source items : 19
Mapped docs  : 16 (assistant-message=7, tool-call=2, user-message=7)
Skipped items: 1 (reasoning_trace=1)
```

> "One command turns it into OKF 0.2. Nineteen items in, sixteen documents out —
> the tool call and its result merge into one, and the model's reasoning trace is
> skipped, not smuggled in as a fake memory. Every row is accounted for."

## Shot 4 — human-readable output (0:45–1:00)

```bash
cat sample/okf/memories/tool-call/0007-lookup-team-calendar.md
```

> "Readable markdown. The arguments, the result, the role, the timestamp, and the
> exact SQLite rows it came from — provenance you can audit."

Scroll the frontmatter slowly; hover on `resource:` and `sources:`.

## Shot 5 — into Memanto (1:00–1:20)

```bash
memanto migrate okf sample/okf --dry-run
```

Land on the panel:

```
OKF nodes: 16
Mapped memories: 16  (skipped 0)
Type breakdown: artifact: 2, auto: 14
```

> "And Memanto takes it. Sixteen in, sixteen mapped, nothing dropped. Tool
> records land as artifacts; the conversation is left for Memanto's classifier
> instead of the bridge guessing."

*(If a Moorcheh key is on hand, re-run without `--dry-run` and add a
`memanto recall "deploy window"` to show the correction winning. Otherwise stop
at the dry run — do not imply a live import happened.)*

## Shot 6 — the receipts (1:20–1:30)

```bash
python verify_artifacts.py
```

> "The committed sample regenerates byte-for-byte from the committed source.
> Eight checks, all green."

Hold on `8/8 checks passed`.

---

## Caption / post copy

> Your OpenAI Agents SDK session is a SQLite file full of raw Responses items.
> This bridge turns it into an OKF 0.2 bundle that `memanto migrate okf` imports
> — roles, timestamps, tool calls and source row ids intact. 19 items → 16
> memories, 1 reasoning trace skipped on purpose. Stdlib only, deterministic,
> read-only on your source DB.
>
> `examples/migrations/openai-agents-sqlite-session` — Memanto #1609

## Claims that must stay accurate

* The source database is written by the real SDK; **the model is scripted** —
  say "no API key needed" rather than implying a live model call.
* The Memanto step shown is a **dry run**. Do not describe it as an import.
* "19 → 16, 1 skipped" is the committed result for this session; re-record the
  numbers if the scenario changes.
