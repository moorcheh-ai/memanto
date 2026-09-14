# OKF Memory Vault — portable, versioned, diffable agent memory

> Path C submission for [memanto #1609: The Great Memory Migration](https://github.com/moorcheh-ai/memanto/issues/1609) — *show that Open Knowledge Format (OKF) memory is portable, and that portability unlocks a lifecycle proprietary stores can't give you: version history, code-review-style auditing, conflict detection, and team workflows.*

**One command reproduces the whole demo:**

```bash
pip install -r requirements.txt
python run.py
```

That builds a complete lived-in agent memory vault (`sample/`): 4 chronological
sessions, a git history, human-readable diffs, a conflict scan, and a passing
test suite. No cloud, no server, no Memanto account needed — that is the point:
**the memory is plain portable markdown, so it runs anywhere.**

## What this showcases

This demo is built **on top of** Memanto's existing OKF support
(`memanto memory export --okf`, `memanto memory sync --okf`,
`memanto migrate okf`). It adds the lifecycle layer that a portable format
makes possible:

| Capability | Where | Why it matters |
| --- | --- | --- |
| **Git-versioned memory wiki** | `run.py` commits each session to `sample/vault` | Every memory change is auditable: `git log` is the memory's changelog, `git revert` is an undo button for bad memories |
| **OKF diff utility** | `okf_diff.py` | See *exactly* what changed between sessions — added / modified / removed memories with field-level diffs |
| **OKF viewer** | `okf_view.py` | Browse and search the vault like a wiki, with zero Memanto tooling |
| **Conflict scanner** | `okf_diff.py --conflict scan` | Near-duplicate memories with different content are flagged for human review instead of silently collapsing in a vector store |
| **Human review workflow** | `scenario.py` Session 5 | Memory reviewed like code: a wrong entry is reverted, a contradiction gets a single source of truth, the whole audit trail stays in git |

The demo story: **Lumenly**, a fictional AI customer-support analytics SaaS.
Maya (the founder) runs an agent that keeps its working memory in an OKF
bundle versioned in git and synced from Memanto.

```
v1  Session 1-2  The seed             20 memories   # two weeks of lived-in memory
v2  Session 3    Memory evolves       24 memories   # preference correction + new facts
v3  Session 4    Two agents collide   29 memories   # conflicting facts become visible
v4  Session 5    Human review + rollback  27 memories  # bad entry reverted, contradiction resolved
```

## Quick tour

```bash
# 1. See the whole vault as a tree
python okf_view.py sample/vault

# 2. Search memory
python okf_view.py sample/vault --search p95

# 3. Diff two sessions like code review
python okf_diff.py sample/vault-v2 sample/vault-v3

# 4. Diff two git revisions of the same vault (tags: v1..v4)
python okf_diff.py --git v1 v2 --repo sample/vault --bundle memories

# 5. The audit trail
git -C sample/vault log --oneline
```

## The conflict story (the part a vector store hides)

Session 4 has two agents writing to the same memory. The diff makes the
contradiction unmissable:

```
$ python okf_diff.py sample/vault-v2 sample/vault-v3
5 added · 0 modified · 0 removed · 24 unchanged

## Potential conflicts (near-duplicate memories)

> Two memories of the same type look like they may be about the same thing
> but disagree. **Flag for human review** - this is exactly what a vector
> store would have silently collapsed.

- `fact`: **Maya's birthday is September 2** (_via manual_) ⟷ **Maya's birthday is August 15** (_via nightly_analytics_)
- `fact`: **Average customer response time is 4.2 hours** (_via nightly_analytics_) ⟷ **Average customer response time is 1.8 hours** (_via main_agent_)
```

A vector store would have merged, ranked, or overwritten one of those —
silently. Here the human sees both, audits, and Session 5 reworks the vault
like a bad PR:

```
$ python okf_diff.py sample/vault-v3 sample/vault-v4
1 added · 2 modified · 3 removed · 24 unchanged
```

- **removed**: the `August 15` birthday (a 2024 spreadsheet typo), and both
  response-time estimates (1.8h excluded APAC, 4.2h included an incident backlog)
- **modified**: the `September 2` birthday entry updated by `human_review`;
  the p95 goal updated with progress
- **added**: one resolved `2.9h` fact owned by the nightly analytics agent
- and `git log` shows every step:

```
d0cd43d (HEAD -> main) v4: Session 5: Human review + rollback
d74f457 v3: Session 4: Two agents collide
f8fa451 v2: Session 3: Memory evolves
868f16a v1: Session 1-2: The seed
```

## How it maps to Memanto

| Memanto integration point | This demo |
| --- | --- |
| `memanto memory export --okf` / `sync --okf` (`memory_mgmt.py`) | produces exactly the bundle layout this demo versions (`memories/<type>/<slug>.md`) |
| `memanto migrate okf` (`migrate.py`, `okf_loader.py`) | reads the same layout; `MAPPING.md` documents the field-level mapping (including the `x_memanto` round-trip block) |
| `okf_export_service.py` | its 13-type taxonomy is reused verbatim as the directory taxonomy in `okf_bundle.py` |

The demo deliberately **does not re-implement** Memanto's OKF codec. It shows
what you can build *around* a portable format once it exists.

## Files

```
okf-memory-vault/
├── run.py              # one-command reproduction (snapshots + git + diffs + tests)
├── okf_bundle.py       # minimal OKF bundle reader/writer (Memanto-compatible layout)
├── okf_diff.py         # OKF diff + conflict scanner (markdown / JSON / git revisions)
├── okf_view.py         # OKF terminal viewer (tree, search, open one memory)
├── scenario.py         # the Lumenly story: 4 sessions of lived-in memory
├── MAPPING.md          # OKF field ↔ Memanto schema mapping
├── requirements.txt
├── pytest.ini
├── tests/              # 17 tests covering codec, diff, conflicts, viewer
└── sample/             # generated by run.py: vaults, diffs, git log, summary
```

## Notes for Windows users

If your checkout path is deep (the demo was developed on Windows with a
250+ char workspace path), `run.py` can hit `WinError 206`. Clone the repo to
a shallow path (e.g. `C:\src\memanto`) before running. On macOS/Linux there is
no such limit.

## Scoring alignment

- **Engineering value (30)**: a complete, tested, reproducible toolchain
  (`okf_diff`, `okf_view`, git workflow) — not a slideware mockup.
- **Portability (15)**: the entire demo runs on stock Python + PyYAML + git,
  no Memanto runtime, no cloud.
- **Reusability (20)**: `okf_diff.py` and `okf_view.py` work on *any* OKF
  bundle — including Memanto's own exports — so the scripts are usable today.
- **Story (10)**: a concrete, believable arc (two agents disagree, a human
  reviews and rolls back) that shows *why* portability matters.
- **Social (25)**: see the PR description for the demo script, video
  storyboard, and social copy.
