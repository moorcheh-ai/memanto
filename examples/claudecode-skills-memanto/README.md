# Claude Code Skills + Memanto

This example adds a small bridge that lets Claude Code skill workflows recall
and record engineering context through the `memanto` CLI.

It is designed for the repeated-instructions problem: when one skill captures a
design decision, later skills can retrieve that decision without asking you to
paste the same project rules again.

## Setup

```bash
pip install memanto
memanto connect claude-code
```

No extra Python dependencies are required by this example.

## Usage

Inject relevant prior memories before starting a skill:

```bash
python skill_memory.py inject --event '{
  "skill": "tdd",
  "task": "add retry tests",
  "project_path": "/workspace/billing",
  "files": ["billing/retry.py"]
}'
```

Record what a completed skill learned:

```bash
python skill_memory.py record --event '{
  "skill": "tdd",
  "task": "add retry tests",
  "project_path": "/workspace/billing",
  "summary": "Retries stop after the third failed provider attempt.",
  "decisions": ["Keep retry policy per provider adapter."]
}'
```

Both commands also accept the event JSON on stdin, which makes them easy to wrap
from Claude Code hooks or custom skill runners.

## How It Works

- `inject` builds a query from the current skill, task, project, and touched
  files, then calls `memanto recall ... --json`.
- Recalled memories are formatted as concise additional context so the next
  skill gets only the relevant decisions.
- `record` writes a completion summary and explicit decisions with
  `memanto remember --type decision`.
- Empty summaries are skipped so the memory namespace does not accumulate noise.

## Hook Wrapper Sketch

A skill runner can call `inject` before invoking a skill and prepend the returned
`additionalContext` to the skill prompt. After the skill finishes, call `record`
with a short summary and the decisions worth preserving.

```bash
python skill_memory.py inject < skill-start-event.json
python skill_memory.py record < skill-complete-event.json
```

