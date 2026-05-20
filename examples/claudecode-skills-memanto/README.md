# Claude Code Skills + Memanto

This example adds a small lifecycle layer for command-style developer skills:

- `pre`: recall relevant engineering decisions and emit a compact prompt block.
- `post`: distill a completed skill transcript and store it as typed memory.
- `wrap`: run any skill command between `pre` and `post`, passing recalled memory in `MEMANTO_SKILL_CONTEXT`.

It targets the context-fragmentation problem from issue #508: a decision learned
by one skill, such as `/grill-with-docs`, becomes available to later skills,
such as `/tdd` or `/handoff`, without repeating the same instructions.

## Credential-free preview

Run the full lifecycle locally with no Moorcheh API key:

```bash
python examples/claudecode-skills-memanto/validate.py
```

Manual local run:

```bash
python examples/claudecode-skills-memanto/skill_memory.py \
  --backend local \
  --store /tmp/memanto-skills.jsonl \
  post \
  --skill grill-with-docs \
  --task "Review billing retry architecture" \
  --file src/billing/retries.ts \
  --transcript "Decision: keep retry delays deterministic in tests. Preserve idempotency keys across retries."

python examples/claudecode-skills-memanto/skill_memory.py \
  --backend local \
  --store /tmp/memanto-skills.jsonl \
  pre \
  --skill tdd \
  --task "Add billing retry tests" \
  --file src/billing/retries.ts
```

The local backend is deliberately simple JSONL. It exists for review, demos, and
tests; it is not a replacement for Memanto.

## Optional live Memanto mode

Live mode uses the repository's existing `memanto` CLI and whatever active agent
the developer has configured locally. No credentials are stored in this example.

```bash
export MOORCHEH_API_KEY=...
memanto agent create claude-code-skills --description "Cross-skill engineering memory"

python examples/claudecode-skills-memanto/skill_memory.py \
  --backend memanto \
  post \
  --skill grill-with-docs \
  --task "Review billing retry architecture" \
  --file src/billing/retries.ts \
  --transcript-file /tmp/skill-transcript.txt

python examples/claudecode-skills-memanto/skill_memory.py \
  --backend memanto \
  pre \
  --skill tdd \
  --task "Add billing retry tests" \
  --file src/billing/retries.ts
```

You can also select live mode with:

```bash
export MEMANTO_SKILLS_BACKEND=memanto
```

## Wrapper mode

`wrap` is the integration shape for a skill runner. It prints the recalled block,
sets `MEMANTO_SKILL_CONTEXT` for the child process, captures the child output,
then stores the completed transcript.

```bash
python examples/claudecode-skills-memanto/skill_memory.py \
  --backend local \
  --store /tmp/memanto-skills.jsonl \
  wrap \
  --skill handoff \
  --task "Summarize billing retry test constraints" \
  --file src/billing/retries.ts \
  -- python -m pytest tests/test_billing_retries.py
```

## What gets remembered

Each stored memory includes:

- memory type `decision`
- source skill
- task
- files and project path tags
- distilled engineering decisions from the transcript
- confidence and timestamp

The distiller is intentionally narrow: `RuleBasedDistiller` is used for
credential-free preview and tests. The live backend stores the same structured
decision into Memanto via `memanto remember`, then later retrieves it via
`memanto recall`.

## Validation

```bash
python -m py_compile examples/claudecode-skills-memanto/skill_memory.py \
  examples/claudecode-skills-memanto/validate.py \
  examples/claudecode-skills-memanto/test_skill_memory.py

python examples/claudecode-skills-memanto/validate.py

python -m unittest examples/claudecode-skills-memanto/test_skill_memory.py
```

See `demo-transcript.md` for a concrete before-and-after run.
