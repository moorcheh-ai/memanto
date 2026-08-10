# Agent operational log → Memanto → OKF

A migration path for a source nobody has adapted yet: **an autonomous agent's own operational log** —
the running record of what it tried, on which channel, and what actually happened.

The corpus used here is real. It is 196 dated records from a single continuously-running agent over
roughly 48 hours, and it was not written for this showcase; it accumulated while the agent worked.

## Why an oplog is not just another chat export

Most migration sources are transcripts. Their records are *additive*: more conversation, more facts.

An oplog is different in one specific way that matters to a memory layer. Its records routinely
**overturn** each other. The agent believes something, tests it, and records that it was wrong:

| Channel | Earlier | Later |
|---|---|---|
| `measurement/vercel-analytics` | "404, integration only partial" | "**WORKING now**: returns 200" |
| `channel/lachief-tally` | "deferred — needs field block UUIDs" | "**SUCCESS** — form submitted" |
| `reach/widget-payer-seam` | "cosmetic / dental / aesthetic clinics" | "**refined**: integrative-medicine solo practitioners" |
| `counting competition on freelancer.com` | "scrape the rendered page" | "**unnecessary** — the API returns it exactly" |

Dump that content in flat and you have actively damaged the memory. The stale belief and the finding
that killed it arrive as two equally-confident, equally-recent memories, and retrieval is free to
surface whichever is more lexically similar to the question. The agent gets its own retracted
conclusions back as current advice.

So this adapter migrates the **correction structure**, not just the text.

## What the adapter does

Records are grouped by channel and ordered by timestamp. For each channel:

- the newest record is tagged `oplog-current`, typed `learning`, confidence `0.85`
- every earlier record is tagged `oplog-superseded`, typed `error`, confidence `0.6`, and gets a
  footer line naming the finding that replaced it and when

```
- Supersession: SUPERSEDED by a later finding on the same channel at 2026-07-24T08:43:54+00:00:
  WORKING now: /_vercel/insights/script.js returns 200 (was 404)...
```

That last part is the point: even when retrieval *does* surface the stale memory, the reader is told
it is stale and what replaced it. Confidence and type carry the same signal to anything ranking on
them.

Original `created_at` is preserved on every record, so `--as-of` queries remain meaningful after
import — a migration that stamps everything "now" silently destroys the agent's timeline.

## Run it

```bash
# preview without writing
memanto migrate agent-oplog ./agent_oplog_export.json --dry-run

# import into the active agent
memanto migrate agent-oplog ./agent_oplog_export.json

# then export back out — in → owned → portable
memanto memory export --okf
```

Input shape:

```json
{"records": [
  {"id": "oplog-195",
   "at": "2026-07-26T03:27:10Z",
   "channel": "sizing a market with a keyword filter I wrote myself",
   "action": "estimate how often booking jobs arrive by regexing title+description",
   "result": "INFLATED 8x. Loose regex said 15.6% of arrivals; strict filter gave 2.0%",
   "evidence": "iter-173; 495-project pull"}
]}
```

## Measured result on the real corpus

```
Oplog records: 196
Mapped memories: 196  (skipped 0)
Superseded by a later finding: 22
Type breakdown: error: 22, learning: 174
Imported: 196   Failed: 0   Batches: 2
```

Backend: Moorcheh on-prem, Ollama `nomic-embed-text` + `qwen2.5`. No cloud key required.

## Recall parity — and an honest negative result

The interesting question is not "can it recall" but **"does it hand back a belief the agent already
abandoned?"** Because this corpus has a known answer key, that is directly testable:
`answer_key.json` lists six questions where the agent held a belief and then discarded it on
evidence.

**Five of six returned the current belief as top-1**, including both hard timeline cases
(404→200, deferred→succeeded). The sixth was a retrieval miss on a numeric query.

That sixth case was investigated and **is not a defect**. Ranking the query against all 196 stored
memories by raw cosine put the expected memory at rank 6; a top-3 result correctly excludes it. Two
earlier two-way tests (target vs a single hand-picked distractor) had each suggested a bug, and both
were wrong — with 196 candidates the question is never "does the target beat this one distractor" but
"where does it rank among all of them."

Recorded here because a showcase that only reports flattering results is not evidence of anything.

## Files

| File | What it is |
|---|---|
| `agent_oplog_export.json` | the real 196-record oplog export |
| `answer_key.json` | six belief-reversal cases with the current and superseded answers |
| `corpus.json` | flattened memory view of the same records |
| `reversals_same_channel.json` | the mechanically-detected supersession pairs |

Implementation: `map_agent_oplog` in `memanto/cli/migrate/mappers.py`, registered in `MAPPERS`;
`source_count` branch in `memanto/cli/migrate/runner.py`; CLI in `memanto/cli/commands/migrate.py`.
Tests: `tests/test_agent_oplog_mapper.py`.
