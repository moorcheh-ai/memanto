# Demo video script (about 2 minutes 30 seconds)

Record the commands live from a clean repository checkout. Keep the source
database, OKF files, and Memanto output readable on screen; do not use slides as
a substitute for the pipeline.

## 0:00–0:20 — The lock-in problem

- Open `scenario.py` briefly and show the eight dated sessions.
- Say: “This release copilot changed its date, owner, and cache policy. Its
  current memory and its correction history live inside Google ADK SQLite.”
- Point out that the script writes conversations through Google ADK's public
  session API, not through raw SQL or a fabricated export.

## 0:20–0:55 — Run the real pipeline

Run:

```bash
uv run --group dev --with google-adk==2.6.0 python examples/migrations/google-adk/run_demo.py --force
```

While it runs, explain that the adapter opens SQLite read-only, captures a
replayable source snapshot, maps current durable state, and invokes Memanto's
shipped OKF dry-run command. Hold on the final line showing 10 memories and
100% / 100% recall.

## 0:55–1:25 — Make ownership visible

- Open `artifacts/adk-live-run/google-adk-okf/index.md`.
- Follow the link to the current release-window memory. Show the plain Markdown
  content, type, tags, `google-adk://` resource, and source key.
- Open the state-history archive for that concept. Show July 31 as superseded
  and August 4 as current.
- Emphasize that the archive is outside `memories/`, so stale values remain
  owned without becoming active facts again.

## 1:25–1:50 — Prove Memanto accepts it

- Open `evidence/memanto-dry-run.txt`.
- Show “OKF nodes: 10”, “Mapped memories: 10”, “skipped 0”, and the nine-type
  breakdown.
- Open `evidence/recall-parity.json` and show `source_average: 1.0`,
  `okf_average: 1.0`, and `zero_amnesia: true`.

## 1:50–2:20 — Real cloud round trip

With `MOORCHEH_API_KEY` already configured off-screen, run:

```bash
uv run --group dev python examples/migrations/google-adk/run_roundtrip.py
```

Show one current-truth query (release window) and one corrected-truth query
(cache TTL), then open `memanto-roundtrip-export/index.md`. Say: “The memory
started in ADK, entered Memanto through its shipped importer, answered the same
questions, and came back out as portable Markdown.”

Never reveal the API key, terminal history containing it, or a local username.

## 2:20–2:30 — Close

End on the bundle root and say: “Events, corrections, and current memory are no
longer trapped in one runtime. The owner can read, diff, version, and move all
of it.”

In the video description, link the pull request, the Memanto repository, and
`youtube.com/@moorchehai` as required by the bounty.
