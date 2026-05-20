# Claude Code Skills + Memanto

This example makes Memanto a global memory companion for Claude Code skill
workflows such as `/grill-with-docs`, `/tdd`, and `/handoff`.

The integration uses Claude Code's hook lifecycle directly:

- `SessionStart`, `UserPromptSubmit`, `UserPromptExpansion`, and `PostToolBatch`
  recall relevant engineering memory and return `additionalContext`.
- `Stop` captures the completed skill transcript, distills durable decisions,
  preferences, instructions, and codebase quirks, then stores them in Memanto.

That means the next skill run starts with the decisions from the previous skill
without asking the developer to repeat them manually.

References:

- Claude Code hooks: https://code.claude.com/docs/en/hooks
- Memanto agent integration guide: ../../docs/AGENT_INTEGRATION_GUIDE.md

## What Makes This Different

Most wrapper-only approaches can log that a command ran, but they do not reliably
add useful context back into Claude Code. This example targets the hook events
that Claude Code documents as context-bearing and returns the event-specific
`additionalContext` payload.

The result is a concrete before/after loop:

1. `/grill-with-docs` decides that planning docs must stay out of public PRs.
2. `Stop` stores that rule as a typed Memanto instruction.
3. A later `/tdd` invocation asks for PR prep.
4. `UserPromptExpansion` injects the prior docs-hygiene rule into context.

## Files

```text
examples/claudecode-skills-memanto/
+-- README.md
+-- claude_memory_hooks.py       # hook CLI and local/SDK backends
+-- settings.example.json        # Claude Code hook configuration
+-- validate.py                  # credential-free lifecycle validation
+-- test_claude_memory_hooks.py  # stdlib regression tests
```

## Quick Validation, No API Key

```bash
python3 examples/claudecode-skills-memanto/validate.py
python3 -m unittest discover -s examples/claudecode-skills-memanto -p 'test_*.py' -v
```

Expected output:

```text
credential-free validation passed
...
OK
```

## Local Hook Demo

Capture memories from a completed skill transcript:

```bash
cat > /tmp/claude-skill-transcript.jsonl <<'EOF'
{"type":"assistant","message":{"content":"Decision: keep planning docs out of public PR branches."}}
{"type":"assistant","message":{"content":"Preference: run make verify before posting review updates."}}
EOF

printf '%s' '{
  "hook_event_name": "Stop",
  "session_id": "demo-1",
  "cwd": "/repo/clinicpulse",
  "transcript_path": "/tmp/claude-skill-transcript.jsonl"
}' | python3 examples/claudecode-skills-memanto/claude_memory_hooks.py capture \
  --backend local \
  --store /tmp/claude-skills-memory.jsonl
```

Inject that memory into a later skill:

```bash
printf '%s' '{
  "hook_event_name": "UserPromptExpansion",
  "session_id": "demo-2",
  "cwd": "/repo/clinicpulse",
  "command_name": "tdd",
  "command_args": "prepare public PR",
  "prompt": "/tdd prepare public PR"
}' | python3 examples/claudecode-skills-memanto/claude_memory_hooks.py inject \
  --backend local \
  --store /tmp/claude-skills-memory.jsonl
```

The hook returns JSON with:

```json
{
  "suppressOutput": true,
  "hookSpecificOutput": {
    "hookEventName": "UserPromptExpansion",
    "additionalContext": "Memanto engineering memory relevant to this Claude Code skill:\n- [decision 0.88] Decision: keep planning docs out of public PR branches.\n- [preference 0.80] Preference: run make verify before posting review updates.\nApply these as constraints unless the current user prompt overrides them."
  }
}
```

## SDK Mode

Install Memanto with its runtime dependencies, then set a Moorcheh API key and
use the SDK backend:

```bash
python3 -m pip install memanto
export MOORCHEH_API_KEY="..."

printf '%s' '{
  "hook_event_name": "UserPromptSubmit",
  "session_id": "demo-sdk",
  "cwd": "/repo/clinicpulse",
  "prompt": "/tdd prepare public PR"
}' | python3 examples/claudecode-skills-memanto/claude_memory_hooks.py inject \
  --backend sdk
```

Then adapt `settings.example.json` into your Claude Code project or user
settings file. The SDK backend creates or activates the `claude-code-skills`
Memanto agent and stores memories through the normal Memanto client. The source
checkout's local validation mode does not require package installation.

## Hook Strategy

| Hook event | Mode | Purpose |
| --- | --- | --- |
| `SessionStart` | inject | Warm the session with recent engineering memory |
| `UserPromptSubmit` | inject | Add relevant constraints before Claude processes a prompt |
| `UserPromptExpansion` | inject | Add memory when slash skills expand |
| `PostToolBatch` | inject | Rehydrate context after batched tool activity |
| `Stop` | capture | Store durable decisions from the completed transcript |

The capture path only stores lines that look like reusable engineering memory:
decisions, preferences, instructions, context caveats, and error/fix notes. It
does not blindly upload whole transcripts.

## Bounty Criteria Mapping

- Global memory hook: `claude_memory_hooks.py inject` and `capture` plug into
  Claude Code's documented hook configuration.
- Active extraction: `distill_memories()` turns transcript lines into typed
  decision, preference, instruction, context, and error memories.
- Dynamic injection: `build_context()` searches Memanto or local JSONL and
  returns `hookSpecificOutput.additionalContext` for the current hook event.
- Reviewer-safe validation: local JSONL mode proves the full lifecycle without
  private credentials.
- Productivity multiplier: `benchmark` reports how many repeated instruction
  lines were injected automatically into a second skill session.
