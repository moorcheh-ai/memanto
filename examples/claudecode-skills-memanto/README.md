# Claude Code Skills + Memanto

This example adds a lightweight memory layer around Claude Code and
mattpocock-style skill commands. It captures a skill run, distills durable
engineering decisions from the transcript, stores them in Memanto or an
offline JSONL review store, and injects relevant memories before the next
skill starts.

It is designed for the BountyHub issue
[`moorcheh-ai/memanto#508`](https://github.com/moorcheh-ai/memanto/issues/508).

## What It Demonstrates

- A pre-skill hook that recalls project-specific engineering memory.
- A post-skill hook that extracts decisions, preferences, instructions, and
  learnings from completed skill transcripts.
- Secret redaction before any transcript text is stored.
- A credential-free local backend for reviewers and CI.
- Optional live storage and recall through the Memanto SDK.
- Shell wrappers for `/grill-with-docs`, `/tdd`, and `/handoff` style commands.

## Install

```bash
cd examples/claudecode-skills-memanto
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

The default mode is credential-free:

```bash
export MEMANTO_SKILL_BACKEND=local
```

To use live Memanto memory:

```bash
export MEMANTO_SKILL_BACKEND=memanto
export MOORCHEH_API_KEY=your_moorcheh_api_key
export MEMANTO_AGENT_ID=developer-skills
```

## Run The Offline Demo

```bash
python validate.py
```

Expected output:

```text
offline validation passed
```

A reviewer-friendly transcript is included in
[`demo-transcript.md`](demo-transcript.md).

## Wrap A Skill Command

The `wrap` command runs a skill command with pre/post memory hooks:

```bash
memanto-skill-memory wrap --skill tdd --prompt "Add pagination tests" -- \
  python -c "print('Decision: keep pagination state in the URL.')"
```

The post-hook stores a redacted, typed memory in
`.memanto-skills/memories.jsonl`. A later run receives relevant context through:

- `MEMANTO_SKILL_CONTEXT`
- `.memanto-skills/last_context.md`
- `MEMANTO_SKILL_CONTEXT_FILE`

## Generate mattpocock-style Wrappers

```bash
memanto-skill-memory install-mattpocock --output-dir .memanto-skills/bin
export PATH="$PWD/.memanto-skills/bin:$PATH"
```

Generated wrappers include:

- `memanto-grill-with-docs`
- `memanto-tdd`
- `memanto-handoff`

Each wrapper preserves the original command UX while routing execution through
`memanto-skill-memory wrap`.

## Lifecycle

```text
skill prompt + cwd
      |
      v
pre-hook recall -> MEMANTO_SKILL_CONTEXT
      |
      v
skill command runs
      |
      v
post-hook transcript redaction -> distillation -> Memanto/local storage
```

## Verification

These checks run without private API keys:

```bash
PYTHONPATH=. python -m unittest discover -s tests -v
python validate.py
python -m py_compile memanto_skill_memory/*.py validate.py
```

## Notes For Reviewers

The local backend is intentionally deterministic so the example can be reviewed
without a Moorcheh account. The live backend uses
`memanto.cli.client.sdk_client.SdkClient` to create or activate a `tool` agent,
then stores extracted memories as typed Memanto records with
`source=skill:<skill-name>` and `provenance=inferred`.
