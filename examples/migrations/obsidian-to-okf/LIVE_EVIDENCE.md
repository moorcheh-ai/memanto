# Live Memanto round-trip evidence

Run on 2026-09-08 against a dedicated Moorcheh-backed agent named
`obsidian-okf-bounty`. No API key, token, or account identifier is stored in
this repository.

## Shipped CLI dry run

```text
memanto migrate okf sample-okf --dry-run --agent obsidian-okf-bounty

OKF nodes: 21
Mapped memories: 21 (skipped 0)
Type breakdown: artifact: 10, context: 1, decision: 1, fact: 7, goal: 2
Dry run -- no writes performed.
```

## Live import

```text
memanto migrate okf sample-okf --agent obsidian-okf-bounty

OKF nodes: 21
Mapped memories: 21 (skipped 0)
Imported: 21
Failed: 0
Batches: 1
```

## Live semantic recall

The three deterministic questions from `run_demo.py` were repeated against the
live agent with `memanto recall`. The expected source memory ranked first for
all three:

| Query | Top live result | Time |
|---|---|---:|
| Who is the protagonist? | `Mara Vance` | 1.28 s |
| What system governs lamplight memory? | `Lamplight Memory` | 1.28 s |
| What is the Bureau trying to keep forgotten? | `Bureau of Continuance` | 1.13 s |

Live golden recall: **3/3**.

## Portable export and reload

```text
memanto memory export --okf --output round-trip-okf \
  --agent obsidian-okf-bounty

Facts: 7
Decisions: 1
Goals: 2
Context: 1
Artifacts: 10
Exported: 21
Completed in 8.05 s
```

The generated memory bundle is checked in at `round-trip-okf/`. The unrelated
local CLI session transcript was excluded from the public artifact; Memanto's
OKF loader intentionally scopes imports to `memories/`. Reloading the published
post-Memanto memory artifact with the shipped importer produced:

```text
OKF nodes: 21
Mapped memories: 21 (skipped 0)
Type breakdown: artifact: 10, context: 1, decision: 1, fact: 7, goal: 2
```

This proves record-count parity, type parity, live semantic recall, and a valid
portable export. Memanto's existing OKF mapper intentionally bounds unknown
supporting-data values to 200 characters and caps the complete footer; therefore
long nested `x_obsidian` values are fully available in `sample-okf/` but may be
abbreviated in `round-trip-okf/`. The note bodies, mapped schema fields, source
references, and recall-critical content survive the live round trip.

## Savings-report applicability

The shipped `memanto migrate okf` command explicitly reports that OKF is a local
bundle and has no provider savings report. Fabricating token, latency, or storage
savings would be misleading. The measurable Path-B funnel for this run is
21 source notes -> 21 mapped memories -> 21 imported memories -> 21 exported
memories, with zero skipped or failed records.
