# Claude Code Skills + Memanto Social Showcase

Use this file when sharing the demo for the Memanto + mattpocock Developer Skills bounty. The technical proof is runnable without credentials, while the post copy is ready for X, LinkedIn, or Reddit.

## Short Post

```text
I built a Claude Code skills memory bridge for Memanto.

It lets a later /tdd skill recover prior engineering decisions, constraints, preferences, and commands without manual re-prompting.

The local productivity check recovers 4/4 remembered items across skill runs.

PR: https://github.com/moorcheh-ai/memanto/pull/515
#Memanto @moorcheh-ai
```

## Longer Post

```text
I built a Memanto example for Claude Code-style skills.

The problem:
Skill runs like /grill-with-docs, /tdd, and /handoff are useful, but each run can lose project decisions unless the developer repeats them manually.

The bridge:
- before hook recalls relevant memories by skill, task, and path
- after hook distills the transcript into typed memories
- local JSON backend lets reviewers run it without credentials
- live Memanto CLI backend keeps the same interface for real persistent memory
- mattpocock/skills manifest reader lists installed skill names from .claude-plugin/plugin.json

The productivity check proves the later /tdd run recovers:
- PostgreSQL storage decision
- backwards-compatible response rule
- dependency-light preference
- pytest command

PR: https://github.com/moorcheh-ai/memanto/pull/515
#Memanto @moorcheh-ai
```

## Demo Proof

Run from `examples/claudecode-skills-memanto`:

```bash
python productivity_check.py
PYTHONPATH=. python -m unittest discover -s tests
```

Expected productivity result:

```text
Repeated instructions avoided: 4 / 4
```

## What The Demo Shows

1. A `/grill-with-docs` session records project decisions, constraints, preferences, artifacts, and commands.
2. A later `/tdd` session starts without repeating those instructions.
3. The bridge recalls the relevant memories through Memanto-style retrieval.
4. `productivity_check.py` fails unless all four expected context items are recovered.
