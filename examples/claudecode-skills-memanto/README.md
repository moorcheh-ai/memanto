# Claude Code Skills + Memanto

This example shows how Memanto can act as a durable memory layer across
separate Claude Code skill runs such as `/grill-with-docs`, `/tdd`, and
`/handoff`.

The bridge has two lifecycle steps:

1. `pre` recalls relevant engineering memories before a skill starts and prints
   a compact context block that can be prepended to the skill prompt.
2. `post` scans the skill transcript for typed memory lines such as
   `Decision: ...`, `Preference: ...`, and `Instruction: ...`, then stores those
   memories for later skill runs.

For real command execution, `run` combines those steps: it injects the recalled
context through `MEMANTO_SKILL_CONTEXT`, executes the child skill command, then
stores any explicit memory lines emitted by that command.

The default backend is local JSONL so reviewers can validate the workflow
without secrets. Set `MEMANTO_SKILLS_BACKEND=cli` to route storage and recall
through the installed `memanto` CLI and your Moorcheh-backed agent memory.

## Quickstart

```bash
cd examples/claudecode-skills-memanto
python memanto_skills_memory.py validate --reset
python memanto_skills_memory.py run-demo --reset
```

Expected result: the second session receives architecture decisions saved by
the first session, even though it starts as a separate skill invocation.

## Manual Flow

Store memories after an architecture review:

```bash
python memanto_skills_memory.py \
  --store .memanto-skills-memory.jsonl \
  post \
  --skill grill-with-docs \
  --tags payments,architecture \
  --transcript "Decision: Use FastAPI routers for HTTP boundaries.
Preference: Write pytest coverage before changing shared behavior.
Instruction: Keep service functions pure unless persistence is required."
```

Inject relevant memories before a later TDD session:

```bash
python memanto_skills_memory.py \
  --store .memanto-skills-memory.jsonl \
  pre \
  --skill tdd \
  --prompt "Implement the invoice endpoint after the architecture review."
```

Output:

```markdown
<!-- memanto-skills-context -->
## Relevant Memanto Skill Memory
- [decision] Use FastAPI routers for HTTP boundaries. (...)
- [preference] Write pytest coverage before changing shared behavior. (...)
- [instruction] Keep service functions pure unless persistence is required. (...)
<!-- /memanto-skills-context -->
```

Wrap an actual skill command non-invasively:

```bash
python memanto_skills_memory.py \
  --store .memanto-skills-memory.jsonl \
  run \
  --skill tdd \
  --prompt "Implement the invoice endpoint after the architecture review." \
  --tags payments,tdd \
  -- \
  claude /tdd "Implement the invoice endpoint"
```

The child command receives:

```text
MEMANTO_SKILL_CONTEXT=<rendered recalled memories>
MEMANTO_SKILL_NAME=tdd
MEMANTO_SKILL_PROMPT=Implement the invoice endpoint after the architecture review.
```

If the child output includes lines such as `Decision: ...`, the wrapper stores
them after the command exits. This keeps the skill UX unchanged while allowing
Memanto to carry decisions into future terminal sessions.

## Live Memanto Mode

```bash
pip install memanto
export MEMANTO_SKILLS_BACKEND=cli

python memanto_skills_memory.py post --skill handoff --transcript-file transcript.md
python memanto_skills_memory.py pre --skill tdd --prompt "Continue the feature"
python memanto_skills_memory.py run --skill handoff -- claude /handoff
```

`post` uses `memanto remember` with explicit type, tags, confidence,
provenance, and source. `pre` uses `memanto recall` and renders the recalled
content as skill context. `run` uses the same backend while keeping the child
process decoupled from Memanto.

## Hooking Strategy

Use this file as a thin wrapper around skill execution:

```bash
# Before the skill prompt is sent:
python examples/claudecode-skills-memanto/memanto_skills_memory.py pre \
  --skill tdd \
  --prompt-file prompt.txt

# After the skill finishes:
python examples/claudecode-skills-memanto/memanto_skills_memory.py post \
  --skill tdd \
  --transcript-file transcript.md \
  --tags current-project,tdd
```

This keeps the integration non-invasive: existing skills do not need to know
about Memanto, and the same wrapper can be used for mattpocock-style skills,
custom project skills, or handoff scripts.

## Memory Format

The extractor records only explicit typed lines:

```text
Decision: Use FastAPI routers for HTTP boundaries.
Preference: Write pytest coverage before changing shared behavior.
Instruction: Keep service functions pure unless persistence is required.
Fact: The auth service already owns JWT refresh.
Learning: Batch writes are faster than per-record uploads in this repo.
Error: The generated migration failed when run twice.
```

This is deliberate. It avoids over-storing vague transcript noise while still
making important decisions easy for a skill to save at the end of a run.

## Files

```text
examples/claudecode-skills-memanto/
├── README.md
├── memanto_skills_memory.py
├── demo_transcript.md
└── tests/
    └── test_memanto_skills_memory.py
```
