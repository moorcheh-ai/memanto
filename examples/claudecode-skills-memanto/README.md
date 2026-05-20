# Claude Code Skills + Memanto

This example shows how Memanto can act as a global memory companion across
separate Claude Code / mattpocock-style skill runs.

The bridge wraps a skill command with a small lifecycle:

1. Recall relevant memories for the current skill and task.
2. Inject them through `MEMANTO_SKILL_CONTEXT`.
3. Run the original skill command.
4. Distill durable decisions, conventions, instructions, and caveats from the
   transcript.
5. Store those memories for the next isolated skill execution.

## Credential-Free Demo

```bash
python examples/claudecode-skills-memanto/run_demo.py
```

The demo uses a local JSONL backend so reviewers can validate cross-session
recall without a Moorcheh API key.

To inspect the memories that would be available to later skill runs:

```bash
python examples/claudecode-skills-memanto/run_demo.py \
  --memory-file /tmp/memanto-skills-demo.jsonl
cat /tmp/memanto-skills-demo.jsonl
```

The second and third skill executions print `Relevant Memanto memories:` before
running. That is the practical productivity gain: each isolated command starts
with the project decisions and constraints learned by earlier skills, without
asking the user to repeat them in every prompt.

## Use Real Memanto

Install and configure Memanto first:

```bash
pip install memanto
memanto
```

Then run a command through the bridge:

```bash
MEMANTO_SKILLS_BACKEND=cli \
python examples/claudecode-skills-memanto/skill_memory_bridge.py tdd \
  --task "add tests for the billing adapter" -- \
  bash -lc "echo 'Decision: keep billing tests deterministic'"
```

## Generate Claude Command Wrappers

```bash
python examples/claudecode-skills-memanto/generate_claude_commands.py
```

This creates `.claude/commands/*-with-memanto.md` wrappers for:

- `/grill-with-docs`
- `/tdd`
- `/handoff`

The generated files are intentionally small. They keep the original skills as
the source of truth while adding Memanto recall and storage around each run.

## Review Checklist

- Run the demo once and confirm later skills receive `MEMANTO_SKILL_CONTEXT`.
- Inspect the JSONL file and confirm only durable decisions, preferences,
  instructions, and observations are stored.
- Run the tests to cover recall scoring, transcript distillation, context
  injection, and child-process exit handling.

```bash
python -m pytest examples/claudecode-skills-memanto/test_skill_memory_bridge.py -q
```

## Safety Boundary

The distiller stores only durable engineering context such as decisions and
preferences. It does not store API keys, payment details, or raw hidden prompts.
Teams can add their own redaction layer before calling `remember` if their
workflow handles sensitive transcripts.
