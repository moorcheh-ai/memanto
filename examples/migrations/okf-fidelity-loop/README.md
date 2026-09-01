# OKF round-trip fidelity loop

Owning your memory means you can carry it out and bring it back. So the question
this example asks is the one nobody had asked yet:

> **What is left of your memory after you carry it out and back four times?**

Every migration showcase proves one hop — source tool in, OKF out. One hop always
looks clean. Portability is the *second* hop, and the third, because a bundle you
keep in git, hand to a teammate, or move between tools gets imported more than
once.

Run four hops through the shipped toolchain and the answer, before this PR, was:
**your memory grows by 285% and never stops.**

## Demo

A two-minute screen recording of the whole thing running — a memory opened as
plain markdown, the harness inflating that bundle against an untouched clone of
upstream `main`, the two-line fix, and the recall scorecard:

**[▶ Watch the demo](https://github.com/AHmedaf123/memanto/assets/demo.mp4)** *(link added to PR)*

## The finding

129 memories, exported to OKF and re-imported four times, on `main`:

| Generation | Memories | Content bytes | Footer marks | Drift vs source |
| --- | --- | --- | --- | --- |
| 0 (source) | 130 | 37,773 | 131 | +0 B |
| 1 (round trip 1) | 131 | 64,545 | 262 | +26,772 B |
| 2 (round trip 2) | 132 | 91,437 | 394 | +53,664 B |
| 3 (round trip 3) | 133 | 118,449 | 527 | +80,676 B |
| 4 (round trip 4) | 134 | 145,581 | 661 | +107,808 B |

37 KB of memory became 145 KB. 129 memories went in; 130 came back on the very
first load, 134 by the fourth. Two independent defects, both in the shipped
import path:

**1. The supporting-data footer stacked, once per round trip.**
`map_okf` rebuilds the `[Supporting data]` footer from the source record on every
import, and `_attach_footer` appended it to content that already carried the
previous pass's footer. Four round trips, four identical footers, +150 bytes each
per memory. All four provider mappers (mem0, letta, supermemory, okf) share that
helper, so all four drifted.

**2. A memory that mentions `<!-- okf-entry -->` was torn in half.**
Stacked OKF files separate documents with that sentinel, and the loader split on
it as a bare substring — anywhere, including mid-sentence. One memory *describing*
the OKF format became three entries on a single import, and gained another on
every round trip. Any agent that has ever stored a markdown snippet, a bundle
excerpt, or a note about OKF itself was silently corrupted.

After the fix in this PR, on the same bundle:

| Generation | Memories | Content bytes | Footer marks | Drift vs source |
| --- | --- | --- | --- | --- |
| 0 (source) | 129 | 37,527 | 130 | +0 B |
| 1 (round trip 1) | 129 | 38,081 | 130 | +554 B |
| 2 (round trip 2) | 129 | 38,081 | 130 | +554 B |
| 3 (round trip 3) | 129 | 38,081 | 130 | +554 B |
| 4 (round trip 4) | 129 | 38,081 | 130 | +554 B |

129 in, 129 out, byte for byte, forever. The one-time +554 B at generation 1 is
the import recording where each memory came from; it is written once and then
never changes again, which is exactly what convergence means.

(The bundle carries 130 footer marks for 129 memories because one memory's own
text quotes the phrase `[Supporting data]`. The column counts occurrences of the
marker; what matters is that the count holds still.)

## Quick start

```bash
pip install -e .                        # from the repository root
./examples/migrations/okf-fidelity-loop/run.sh
```

That round-trips the committed sample bundle four times, writes
`sample/fidelity-report.md`, and runs the harness's own tests. It needs no API
key and no network — the harness drives `OkfExportService` → `load_okf_bundle` →
`map_okf`, the exact code path `memanto migrate okf` uses, minus the wire. A key
is needed once, by whoever regenerates the fixture (see below), never to
reproduce the result.

Point it at any OKF bundle, including the ones produced by the other migration
adapters in this directory:

```bash
python fidelity.py <path-to-bundle> --generations 6
```

It exits non-zero when the loop never reaches a fixed point, so it works as a
portability regression check in CI.

## The live freedom loop

The table above is a format measurement. This is the same loop against real
agents, end to end — one command, `MOORCHEH_API_KEY` required:

```bash
./run_live.sh
```

It previews the import, runs it into a second agent, then asks both agents the
same ten questions:

```
OKF nodes: 129
Mapped memories: 129  (skipped 0)
Type breakdown: artifact: 7, commitment: 1, context: 1, decision: 1, error: 1,
event: 1, fact: 19, goal: 1, instruction: 57, learning: 1, observation: 33,
preference: 1, relationship: 5
Imported: 129  Failed: 0  Batches: 2
```

```
Before migration: 10/10 — after migration: 10/10.
Recall parity held: the round trip cost the agent nothing.
```

129 memories out of one agent, through plain markdown, into another agent —
and it answers every question the original could. That is what owning your
memory is supposed to mean. Full output in
[`sample/migration-summary.txt`](sample/migration-summary.txt) and
[`sample/recall-parity.md`](sample/recall-parity.md); the questions are in
[`golden_qa.json`](golden_qa.json).

## Reproduce the failure

The table above is not a claim, it is a command — and you do not have to take
this branch's word for it. Point the harness at an untouched clone of upstream
`main` and watch the same bundle inflate:

```bash
git clone --depth 1 https://github.com/moorcheh-ai/memanto.git /tmp/memanto-main
echo '__version__ = "0.0.0.dev0"' > /tmp/memanto-main/memanto/app/_version.py

cd examples/migrations/okf-fidelity-loop
PYTHONPATH=/tmp/memanto-main python fidelity.py sample/bundle-gen0 --generations 4
```

Nothing is patched or reverted: that is released code, reading the committed
bundle, growing 37,773 bytes into 145,581 and exiting 1. Drop the `PYTHONPATH`
and the same command against this branch converges and exits 0.

## What survives a round trip

Memanto-only fields ride in the namespaced `x_memanto` frontmatter block, so they
come back intact. What does not is worth knowing before you move an estate:

| Memanto field | OKF frontmatter | Survives |
| --- | --- | --- |
| `type` | `x_memanto.type` (and `type`) | yes |
| `title` | `title` | yes, truncated past 100 chars |
| `content` | document body | yes |
| `tags` | `tags` | yes |
| `confidence` | `x_memanto.confidence` | yes |
| `provenance` | `x_memanto.provenance` | yes, invalid values fall back to `imported` |
| `source` | `x_memanto.source` | yes |
| `source_ref` | `resource` | yes |
| `created_at` | `generated.at` | yes, normalised to UTC |
| `updated_at`, `expires_at`, `ttl_seconds` | `x_memanto.*` | yes |
| `id` | `x_memanto.id` | **no** — see below |
| unknown foreign keys | any other frontmatter key | yes, into `[Supporting data]` |

**Memory identity is not preserved.** `x_memanto.id` is written on export but
`map_okf` never reads it back, because ids are assigned server-side at
`batch_remember`. Re-importing a bundle therefore *adds* memories rather than
updating the ones already there. That is a real portability limit, it is not
fixed here, and you should de-duplicate or import into a fresh agent.

## How the sample bundle was made

`sample/bundle-gen0/` is a real `memanto memory export --okf` bundle, not
hand-written JSON. `seed.sh` regenerates it end to end:

```bash
export MOORCHEH_API_KEY=...             # free key at https://moorcheh.ai
./seed.sh                               # creates the agent, seeds it, exports
```

It runs `build_seed.py`, creates an agent, batch-writes the generated files
through `memanto remember --batch`, and exports the result with
`memanto memory export --okf`. The bundle is the toolchain's own output.

`build_seed.py` derives the memories from the repository itself rather than
inventing them: every registered CLI command with its docstring becomes an
`instruction`, every service and client module a `fact`, every router a
`relationship`, every test file an `observation`, each carrying a `source_ref`
to the file it came from. Fourteen hand-written insights from the code review
that produced this example are prepended. Re-run it after the code changes and
the seed follows.

That yields **129 memories across all thirteen types**, and it matters that
`instruction` lands at 57: past the default threshold of 50, OKF collapses a
type into a single stacked file. So the bundle exercises both layouts — 12 types
as one-file-per-memory, and a 34 KB `instruction.md` holding 57 documents
separated by 56 `<!-- okf-entry -->` sentinels. That stacked file is exactly
where the second bug lives.

## Files

| Path | What it is |
| --- | --- |
| `fidelity.py` | the harness — N round trips, drift table, non-zero exit on drift |
| `run.sh` | single-command entry point, offline, no key |
| `run_live.sh` | the live loop: dry run, import, recall parity (needs a key) |
| `validate_recall.py`, `golden_qa.json` | before/after recall parity scoring |
| `seed.sh` | regenerate the fixture from a live agent |
| `build_seed.py`, `seed_memories.json` | derive the 129 seed memories from this repo |
| `seed/batch-*.json` | the generated batches, as fed to `remember --batch` |
| `sample/bundle-gen0/` | the committed real OKF bundle |
| `sample/fidelity-report.md` | the generated drift table |
| `sample/migration-summary.txt` | dry-run preview + real import counts |
| `sample/recall-parity.md` | the 10-question before/after scorecard |
| `tests/test_fidelity.py` | the harness's own checks |

## The fix

Two changes in the shipped import path, both root-cause rather than per-caller:

- `memanto/cli/migrate/mappers.py` — `_attach_footer` drops a previously
  attached footer before appending, so every mapper converges.
- `memanto/cli/migrate/okf_loader.py` — a document boundary is now the delimiter
  alone on its own line followed by frontmatter, not a bare substring match.

Covered by `test_repeated_round_trips_converge` and
`test_loader_keeps_a_memory_that_mentions_the_entry_delimiter` in
`tests/test_okf.py`.
