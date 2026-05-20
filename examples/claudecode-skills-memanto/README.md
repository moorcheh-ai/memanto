# Claude Code Skills + Memanto

This example shows Memanto acting as a global engineering memory layer for
Claude Code or `mattpocock/skills`-style command workflows.

The important distinction is that this uses Claude Code hook events directly:

- `Stop` distills durable engineering memory from a completed skill session.
- `UserPromptSubmit` and `UserPromptExpansion` recall relevant decisions and
  inject them through `hookSpecificOutput.additionalContext`.
- A credential-free JSONL backend is the default so maintainers can review the
  behavior without private API keys.
- Optional live Memanto sync is available with `MEMANTO_SYNC=1` and
  `MOORCHEH_API_KEY`.

## Quick Validation

```bash
cd examples/claudecode-skills-memanto
python3 validate.py
python3 -m unittest test_claude_skill_memory.py
python3 -m py_compile claude_skill_memory.py validate.py test_claude_skill_memory.py
```

Expected:

```text
credential-free Claude Code hook validation passed
..
OK
```

## Hook Configuration

Copy `settings.example.json` into your Claude Code settings and adjust the path
to this repository if needed. The hook command reads the JSON hook payload from
stdin and writes a Claude-compatible JSON response to stdout.

## Live Memanto Mode

Local JSONL mode is always used for deterministic review. To also mirror
distilled memories into Memanto:

```bash
export MEMANTO_SYNC=1
export MOORCHEH_API_KEY="..."
export MEMANTO_AGENT_ID="claude-code-skills"
```

The hook creates or reuses the configured agent, activates a session, then
stores typed `decision`, `preference`, `instruction`, and `context` memories via
`SdkClient.remember`.

## Demo Transcript

Session A, `/grill-with-docs` finishes:

```text
Decision: use Redis streams for billing retries.
Prefer pytest fixtures over mutable module globals.
Never commit generated SDK clients.
```

`Stop` stores three durable memories.

Session B, a fresh `/tdd` run starts:

```text
Use /tdd to add billing retry tests.
```

`UserPromptSubmit` injects:

```text
Memanto engineering memory for this skill run:
- [decision] Decision: use Redis streams for billing retries.
- [preference] Prefer pytest fixtures over mutable module globals.
- [instruction] Never commit generated SDK clients.
```

That is the bounty's productivity goal in miniature: the later skill receives
the earlier architectural choices without manual context shoving.

## Safety

The distiller redacts common API-key, token, secret, and password forms before
anything is stored. Local mode stores only in the configured JSONL file. Live
Memanto mode is opt-in.
