# Claude Code Skills + Memanto

This example shows how to use Memanto as a persistent memory layer around
`mattpocock/skills` style agent workflows. It is intentionally small: instead
of patching Claude Code or the skills package, it wraps any command you already
use to run a skill.

The wrapper does three things:

1. Recalls relevant project memories before the skill starts.
2. Captures the skill input, output, exit code, and working directory.
3. Stores a durable post-run summary back into Memanto.

That gives separate skills such as `/grill-with-docs`, `/tdd`, `/diagnose`, and
`/handoff` a shared engineering memory without making each skill know about the
others.

## Prerequisites

- Python 3.10+
- `memanto` installed and configured
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) available as
  `MOORCHEH_API_KEY`
- A Memanto agent created and activated
- Any agent CLI command that can run your skill

```bash
pip install memanto
cp .env.example .env
# Edit .env and set MOORCHEH_API_KEY, or export it in your shell:
export MOORCHEH_API_KEY="your-moorcheh-api-key"
memanto
memanto agent create claudecode-skills
memanto agent activate claudecode-skills
```

## Run A Skill Through The Memory Hook

Use `run_skill.py` as a prefix for the command you normally run.

```bash
python run_skill.py \
  --skill tdd \
  --task "Fix the checkout total rounding bug" \
  --agent-id claudecode-skills \
  -- claude "/tdd Fix the checkout total rounding bug"
```

Before the wrapped command runs, the wrapper writes recalled context to
`.memanto-skill-context.md`. Point your agent at that file or include it in the
skill prompt when your agent CLI supports file/context injection.

After the command exits, the wrapper appends a transcript under
`.memanto-skill-runs/` and stores a compact Memanto memory containing:

- the skill name
- task text
- files and topics inferred from the transcript
- exit status
- a short implementation or diagnosis summary

## Example Workflow

```bash
# First session: align terminology and architecture.
python run_skill.py \
  --skill grill-with-docs \
  --task "Design persistent cart recovery" \
  --agent-id claudecode-skills \
  -- claude "/grill-with-docs Design persistent cart recovery"

# Later session: TDD gets the prior decisions automatically.
python run_skill.py \
  --skill tdd \
  --task "Implement persistent cart recovery" \
  --agent-id claudecode-skills \
  -- claude "/tdd Implement persistent cart recovery"

# Handoff has access to the same memory trail.
python run_skill.py \
  --skill handoff \
  --task "Summarize cart recovery progress" \
  --agent-id claudecode-skills \
  -- claude "/handoff Summarize cart recovery progress"
```

## Dry Run

Use `--dry-run` to verify the hook without calling Memanto or the agent command:

```bash
python run_skill.py --skill tdd --task "demo" --dry-run -- echo "hello"
```

## Files

```text
examples/claudecode-skills-memanto/
|-- README.md
|-- requirements.txt
|-- .env.example
|-- memanto_skill_memory.py
`-- run_skill.py
```

## Why This Shape

The wrapper keeps the integration portable. It works with installed skills,
forked skills, Claude Code, or any other agent CLI because it treats the skill as
a normal command and uses Memanto through the public CLI.
