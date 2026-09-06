# Two-minute demo script

## 0:00–0:15 — The lock-in

Show the native `~/.gemini/antigravity/brain/<session>/` directory. Point out
the current implementation plan, walkthrough, nine numbered revisions, and
the screenshot artifacts. Do not open or publish the opaque conversation
`.pb`; show its hash-only provenance row.

Narration: “This is a real Antigravity agent session. Its useful history lives
inside one tool-specific directory. We are going to make it readable,
importable, and exactly recoverable.”

## 0:15–0:40 — One-command migration

Run:

```bash
uv run python examples/migrations/antigravity-brain/run_demo.py
```

Highlight the 11 source artifacts, 11 mapped memories, zero skipped records,
and `event 9 / goal 1 / learning 1` breakdown.

## 0:40–1:00 — Open ownership

Open the generated goal and one historical event in `sample/okf/memories/`.
Show that the content is plain Markdown with readable YAML frontmatter. Then
open `metrics/source-provenance.json` and explain that private conversation and
image bytes were intentionally not published.

## 1:00–1:25 — Live Memanto recall

Run the live demo with a configured key:

```bash
uv run python examples/migrations/antigravity-brain/run_live_demo.py \
  --output ./antigravity-live-evidence --execute
```

Show one recall for each golden question: the chosen visual direction, the
dashboard layout, and the terminal-style interaction details. Show one grounded
answer.

## 1:25–1:50 — Export and exact reconstruction

Let the script export the cloud-backed Memanto agent to OKF. Highlight the
matching source and reconstructed tree hashes and `13/13` exact source files.

Narration: “The memory is not merely copied into another black box. It comes
back out as portable Markdown and still rebuilds the source archive exactly.”

## 1:50–2:00 — Close

Show the OKF bundle in a normal file browser or git diff.

Narration: “Eleven evolving Antigravity memories, zero skipped, readable at
rest, live in Memanto, and recoverable. The agent's history belongs to the
user.”
