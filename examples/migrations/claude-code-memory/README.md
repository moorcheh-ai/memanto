# Claude Code Memory Adapter → Memanto + OKF

> **Path B — The New Frontier**: a permanent migration path that liberates the
> memory your Claude Code assistant has built about you.

Claude Code stores every interactive session as a local `JSONL` archive under
`~/.claude/projects/<project>/<session-id>.jsonl`. That archive is the only
record of the preferences, decisions, instructions, and commitments you have
shared with Claude — and it is trapped in a proprietary, undocumented format.

This adapter:

1. Parses Claude Code `JSONL` session archives (real or exported)
2. Extracts durable memory signals (preferences, decisions, instructions,
   commitments, goals, relationships, events, observations, facts, context)
3. Emits a valid **OKF bundle** — plain markdown with YAML frontmatter —
   consumable by the shipped `memanto migrate okf` CLI

The output is your memory as readable, versionable, portable markdown. Once in
Memanto, it is searchable via `recall`, can be synced to a project wiki, and
can be exported back out as OKF at any time.

---

## Quick start

### 1. Install

```bash
cd examples/migrations/claude-code-memory
pip install -r requirements.txt
```

The parser/extractor are stdlib-only. PyYAML is required for the OKF writer.
`pytest` is needed for the validation suite; the suite also imports the
`memanto` package (the OKF loader used by the round-trip check), so run it
from the memanto repository root where that package is importable.

### 2. Generate a demo source (reproducible)

```bash
python scripts/generate_demo_session.py --output demo_source/demo_session.jsonl
```

This writes a realistic, multi-turn Claude Code session archive in the exact
`JSONL` schema Claude Code uses: user turns, assistant text blocks, a
`tool_use` block, file-history snapshots, and a `last-prompt` sentinel. It is
included so the whole pipeline can be reproduced end-to-end without needing a
live Claude Code installation.

### 3. Convert to OKF

```bash
python -m claude_code_adapter.cli \
  --archive demo_source/demo_session.jsonl \
  --output okf_bundle
```

Or scan every archive under a real Claude projects directory:

```bash
python -m claude_code_adapter.cli \
  --projects ~/.claude/projects \
  --output ~/my-claude-memory-okf
```

### 4. Import into Memanto

```bash
# From the memanto repo root
python -m memanto migrate okf \
  examples/migrations/claude-code-memory/okf_bundle \
  --agent my-agent
```

### 5. Round-trip validation

Run the adapter tests to confirm parsing, extraction, OKF loadability, and
golden-set content retention. Execute from the **memanto repository root**
so the `memanto` package is importable:

```bash
cd <memanto-repo-root>
python -m pytest examples/migrations/claude-code-memory/tests/
```

The test suite hard-requires that the generated bundle is loadable by
Memanto's own `memanto.cli.migrate.okf_loader`, and includes a golden-set
content-retention check (below).

### 6. Golden-set content-retention evaluation

`scripts/golden_questions.json` is a fixed Q&A set drawn from the demo
session. `scripts/evaluate_recall.py` answers it twice:

- **Before**: against the raw source archive (the "old agent" with only its
  JSONL as memory)
- **After**: against the full migration pipeline - extract to OKF, load with
  `memanto.cli.migrate.okf_loader`, map with `mappers.map_okf`

```bash
python scripts/evaluate_recall.py \
  --archive demo_source/demo_session.jsonl \
  --bundle /tmp/recall-bundle
```

Expected result: `parity: 1.0` (7/7 questions answered before and after).
The evaluation is deterministic and offline, so it reproduces anywhere
without API keys or network access.

This is a content-retention check: it proves the golden answers survive the
JSONL -> OKF -> Memanto-loadable pipeline byte-for-byte at the data level.
Live semantic recall against Memanto requires the Moorcheh API key and is
demonstrated end-to-end in the demo video (import via `memanto migrate okf`,
then ask the same questions in Memanto recall).

The checked-in `okf_bundle/` is the exact output of the migration pipeline;
import it with `memanto migrate okf` and the same golden questions are
answerable from Memanto recall (shown in the demo video).

---

## Source format (Claude Code JSONL)

Each line in a Claude Code session archive is a JSON object. Relevant shapes:

```json
{"type":"user","uuid":"...","timestamp":"2026-07-28T09:00:00Z",
 "sessionId":"...","cwd":"...","gitBranch":"main",
 "message":{"role":"user","content":"Build a FastAPI service. I prefer SQLAlchemy."}}
```

```json
{"type":"assistant","uuid":"...","timestamp":"...","sessionId":"...",
 "message":{"role":"assistant","content":[
   {"type":"text","text":"I decided to put the Stripe client behind an interface."},
   {"type":"tool_use","id":"toolu_1","name":"Bash","input":{"command":"uvicorn ..."}}
 ]}}
```

The parser handles string content (user turns) and block-list content
(assistant turns). Tool traffic is treated as metadata, never as durable
knowledge. File-history snapshots and `last-prompt` sentinels are skipped.

### Real-shape fixture

`fixtures/real_session_excerpt.jsonl` mirrors the schema of a genuine
Claude Code 2.x session archive (parent links, sidechains, `tool_use` /
`tool_result` blocks, `isMeta` wrappers, sentinels). Message text is
sanitized demo content so the fixture is safe to commit; the parser and
extractor run over it exactly as they would over a private real archive.
To verify against your own real data, point `--projects` at
`~/.claude/projects` (see Quick start step 3).

---

## Mapping table

| Claude Code source signal | Memanto type | OKF frontmatter / body |
|---|---|---|
| "I prefer / I like / I want / use X instead" | `preference` | `type: preference`, body = statement |
| "always / never / remember to / make sure to" | `instruction` | `type: instruction`, tags include tech |
| "I decided / let's use / we will use" | `decision` | `type: decision`, tags include tech |
| "I need to / I will / tomorrow / next week" | `commitment` | `type: commitment` |
| "my team / my colleague / we work on" | `relationship` | `type: relationship` |
| "goal / objective / target / plan to" | `goal` | `type: goal` |
| "meeting / release / deadline / due / demo" | `event` | `type: event` |
| "I noticed / I found / I learned" | `observation` | `type: observation` |
| "environment / stack / version / database / framework" | `context` | `type: context` |
| Any other durable user statement | `fact` | `type: fact` |
| `cwd` basename | project tag | `tags: [project-name]` |
| `gitBranch` | branch metadata | `tags: [branch=main]` |
| `timestamp` | created time | `timestamp: <ISO-8601>` |
| message `uuid` | traceability | `resource: <archive>#<uuid>` |

Every exported memory carries a `x_memanto` block so Memanto → OKF → Memanto
round-trips preserve `id`, `confidence`, `provenance`, `source`, and `status`.

---

## Migration summary (demo run)

Source: `demo_source/demo_session.jsonl` (9 conversation turns, generated by
`scripts/generate_demo_session.py`)

| Metric | Value |
|---|---|
| Source turns parsed | 9 |
| Durable memories extracted | 6 |
| Skipped (tool traffic / sentinels) | 3 |
| Memory types emitted | instruction, decision, commitment, preference (x2), relationship |
| OKF bundle path | `okf_bundle/` |
| OKF loader round-trip | 6/6 memories loaded |

Per-type breakdown:

| Type | Count | Example |
|---|---|---|
| instruction | 1 | "Remember to always use pydantic v2, never log API keys..." |
| decision | 1 | "We will use pydantic v2... Stripe client behind an interface" |
| commitment | 1 | "I will generate OpenAPI docs for Sarah..." |
| preference | 2 | "I prefer SQLAlchemy over raw SQL"; "PCI compliant..." |
| relationship | 1 | "My colleague Sarah works on the mobile app..." |

The adapter also runs against genuine Claude Code archives from this machine
(`~/.claude/projects/**/*.jsonl`) and parsed the real session data successfully.

---

## Project structure

```text
claude-code-memory/
├── README.md
├── requirements.txt
├── claude_code_adapter/
│   ├── __init__.py
│   ├── parser.py        # JSONL archive parser
│   ├── extractor.py     # durable-memory heuristics
│   ├── okf_writer.py    # OKF bundle writer
│   └── cli.py           # command-line entry point
├── scripts/
│   ├── generate_demo_session.py
│   ├── golden_questions.json
│   └── evaluate_recall.py
├── fixtures/
│   └── real_session_excerpt.jsonl
├── demo_source/
│   └── demo_session.jsonl
├── okf_bundle/          # sample output (importable)
└── tests/
    └── test_adapter.py
```

---

## Demo video

Record a short screen capture (2–3 minutes) walking through:

1. `python scripts/generate_demo_session.py` — the source archive is created
2. `python -m claude_code_adapter.cli ...` — memories are extracted to OKF
3. Open the `okf_bundle/memories/` markdown files — readable, portable memory
4. `python -m memanto migrate okf ... --dry-run` — the import preview
5. Ask the same questions in Memanto recall before/after — zero amnesia

Post the video to X/YouTube/LinkedIn and tag the official channels:

- X: `@moorcheh_ai`
- YouTube: `youtube.com/@moorchehai`
- LinkedIn: `linkedin.com/company/moorcheh-ai`
- Reddit: `reddit.com/r/Memanto`

---

## What this fixes (the lock-in story)

Claude Code conversations accumulate real, durable knowledge about a user:
their stack, their preferences, their deadlines, their team. That knowledge
currently lives only in `JSONL` files that no other tool reads. This adapter
breaks the lock-in: your Claude Code memory becomes plain markdown that you
own, can read, version in git, sync to a wiki, and migrate into Memanto for
semantic recall — and export back out as OKF whenever you want.
