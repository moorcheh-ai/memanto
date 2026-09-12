# Codex memory → Memanto + OKF

**Take back the memory your Codex agent built about you.**

OpenAI's Codex CLI keeps everything it has learned about you in a proprietary
local store that has no export command:

```
~/.codex/
  memories_1.sqlite    stage1_outputs   ← the distilled memories
  goals_1.sqlite       thread_goals     ← your long-running objectives
  state_5.sqlite       threads          ← 42 sessions, with lineage
  sessions/**.jsonl    rollout-*        ← full transcripts, including the
                                          hidden reasoning traces and every
                                          memory-compaction event
```

There is no `codex export`. Switching tools means the agent starts over with
amnesia. This example is a complete, reproducible escape route: it reads the
real store and emits a standards-based **OKF (Open Knowledge Format)** bundle —
plain markdown you can read, grep, diff, git-version, and hand to any tool.

```
~/.codex ──▶ codex_to_okf.py ──▶ okf-bundle/ ──▶ memanto migrate okf ──▶ Memanto
    trapped                      yours, portable        official CLI
```

## Quick start (under 5 minutes)

```bash
# 1. the only dependency
pip install memanto

# 2. preview what will migrate — writes nothing
python codex_to_okf.py --dry-run

# 3. build the bundle
python codex_to_okf.py --out ./okf-bundle

# 4. let Memanto validate it before anything is stored
memanto migrate okf ./okf-bundle --dry-run

# 5. import
memanto migrate okf ./okf-bundle
```

That is the whole pipeline. On the reference store (42 Codex sessions,
77 MB of transcripts) it produced **5896 memories, 0 skipped** — see
[MAPPING.md](MAPPING.md) for the full validation transcript.

## Look at what you just freed

Every memory is one markdown file with YAML frontmatter:

```markdown
---
type: "codex-distilled-memory"
title: "Codex memory · skills_sh_global_install_and_curated_skill_batches"
description: "# Installed multiple skills from skills.sh topic pages..."
tags:
  - "codex"
  - "distilled-memory"
timestamp: "2026-07-19T05:20:12+00:00"
x_memanto:
  type: "fact"
  source: "codex:memories_1.stage1_outputs"
  provenance: "inferred"
thread_id: "019f5c27-0fd1-7123-a982-e3e846d475e3"
---

## Codex rollout summary
…
```

```bash
grep -r "your project name" okf-bundle/     # it's just text now
git init && git add okf-bundle && git commit -m "my agent's memory"
```

## What gets migrated

| Codex source | Becomes | Memanto type |
|---|---|---|
| `memories_1.sqlite` distilled memories | what your agent concluded | `fact` |
| `goals_1.sqlite` objectives | what you were trying to achieve | `goal` |
| `state_5.sqlite` sessions | the episode envelope | `context` |
| rollout user turns | what you asked for | `preference` |
| rollout assistant turns | what the agent produced | `observation` |
| rollout tool calls | artifacts created | `artifact` |
| rollout `compacted` events | **the exact moment memory was rewritten** | `decision` |
| rollout `session_meta.base_instructions` | the rules the agent ran under | `instruction` |
| rollout `reasoning` (opt-in) | **hidden chain-of-thought** | `learning` |

The last two are the point. Codex exposes neither its base instructions nor its
reasoning traces through any export — they are readable only by parsing the raw
rollout JSONL. This adapter reads them.

## Options

| Flag | Effect |
|---|---|
| `--dry-run` | Print the mapping preview; write nothing. |
| `--out DIR` | Output bundle directory (default `./okf-bundle`). |
| `--codex-home DIR` | Read a store other than `~/.codex` (or set `CODEX_HOME`). |
| `--include-reasoning` | Also migrate the hidden reasoning traces. Off by default. |
| `--no-redact` | Keep absolute paths, e-mails and tokens verbatim. |
| `--stacked` | One file per type separated by Memanto's `<!-- okf-entry -->` sentinel. |
| `--limit N` | Cap rows read per SQLite source. |
| `--rollout-per-file N` | Cap memories taken from each transcript (default: unlimited, so no transcript is silently cut short). |
| `--force` | Replace a non-empty `--out` directory (the new bundle is built in a temp dir and swapped in). |

Redaction is **on by default**: `$HOME`, `C:\Users\<name>`, e-mail addresses
and API-token-shaped strings are replaced with `~`, `<email>` and `<token>`
before anything is written, so the bundle is safe to share.

## Reproducing this without a private store

`make_sample_store.py` builds a small, entirely synthetic Codex store with the
same schema (`memories_1.sqlite`, `goals_1.sqlite`, `state_5.sqlite`,
`sessions/**/*.jsonl`) so you can exercise the adapter end to end without
touching real personal data:

```bash
python make_sample_store.py --out ./sample-codex-store
python codex_to_okf.py --codex-home ./sample-codex-store --out ./sample-bundle
memanto migrate okf ./sample-bundle --dry-run
```

## Fidelity notes

- **Source is real.** The adapter contains no fixtures and no hard-coded
  memories; every field is read from the store on disk.
- **Nothing is dropped.** Source fields that have no first-class Memanto
  destination (`thread_id`, `goal_id`, `usage_count`, `cwd`) are preserved in
  the frontmatter; Memanto's `okf_loader.py` collects unknown keys into `extra`
  and the importer re-emits them under a `[Supporting data]` footer.
- **The layout matches Memanto's own exporter** (`memories/<type>/<n>-<slug>.md`,
  `index.md` ignored), so Memanto → OKF → Memanto round trips losslessly and a
  Codex bundle is indistinguishable from a native export.
- **Read-only.** The adapter opens every SQLite store with
  `file:…?mode=ro`; it never writes to `~/.codex`.

## Files

| File | Purpose |
|---|---|
| `codex_to_okf.py` | The adapter. Standard library only. |
| `make_sample_store.py` | Builds a synthetic Codex store for testing. |
| `MAPPING.md` | Concept mapping table + validation evidence. |
| `requirements.txt` | One line: `memanto`. |
| `okf-bundle/` | A real generated bundle (regenerate any time). |

## Next steps this unlocks

- `memanto memory export --okf -o ./roundtrip` — round trip back out and diff.
- `memanto memory sync` — browse the same memories from a project directory.
- Point `--codex-home` at an archived store to merge several machines into one.
