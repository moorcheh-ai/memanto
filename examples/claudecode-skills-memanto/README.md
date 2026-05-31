# Claude Code skills + Memanto memory bridge

This example shows a lightweight integration layer for using Memanto as a global memory companion around Claude Code skill-style workflows.

It has two tiny shell hooks:

- `scripts/skill-start.sh` — recall relevant engineering memory before a skill starts and write a prompt-injection snippet.
- `scripts/skill-finish.sh` — distill the just-finished skill transcript/summary into Memanto memory.

The goal is zero repeated instructions across terminal sessions: decisions saved after one skill become concise constraints for the next skill.

## Setup

```bash
pip install memanto
export MOORCHEH_API_KEY="..."
memanto status
```

Copy this example into any project that uses Claude Code skills:

```bash
cp -R examples/claudecode-skills-memanto .memanto-skills
```

## Start a skill with dynamic memory injection

```bash
.memanto-skills/scripts/skill-start.sh \
  --skill tdd \
  --task "implement billing retry tests" \
  --path src/billing/retry.ts
```

The script writes `.memanto-skills/generated/memanto-context.md`. Paste/include that file at the top of the next Claude Code skill prompt.

Example output:

```md
## Memanto engineering memory
- Prefer pytest-style table tests for retry logic.
- Billing code keeps provider errors wrapped; never leak raw gateway messages.
```

## Finish a skill and persist the useful context

```bash
.memanto-skills/scripts/skill-finish.sh \
  --skill tdd \
  --summary-file /tmp/skill-summary.md \
  --tags billing,retry,claude-code
```

Only durable engineering decisions should be stored: architecture choices, project quirks, coding preferences, and gotchas. Avoid secrets and large raw transcripts.

## Optional Claude Code hook

Claude Code can run Memanto sync at session start via `.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "type": "command",
            "command": "memanto memory sync --project-dir .",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

Use the hook for baseline sync, then use `skill-start.sh` / `skill-finish.sh` for active per-skill recall and distillation.
