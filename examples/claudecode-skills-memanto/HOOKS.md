# Claude Code Hooks Configuration for Memanto Memory Bridge

Add this to your Claude Code hooks settings file (`~/.claude/hooks.json` or your project's `.claude/hooks.json`):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "command": "bash /path/to/examples/claudecode-skills-memanto/skills-memory.sh recall \"$CLAUDE_TOOL_INPUT\""
      }
    ],
 "PostToolUse": [
 {
 "matcher": "Bash",
 "command": "bash /path/to/examples/claudecode-skills-memanto/skills-memory.sh distill-and-remember \"$(echo \"$CLAUDE_TOOL_OUTPUT\" | head -c 4000)\""
 }
 ],
 "Stop": [
 {
 "command": "bash /path/to/examples/claudecode-skills-memanto/skills-memory.sh distill-and-remember \"$(cat /tmp/claude-session-output.txt 2>/dev/null | head -c 8000)\""
 }
    ]
  }
}
```

Replace `/path/to/` with the actual location of the `skills-memory.sh` script in your project.

## How it works

1. **PreToolUse** — Before every Bash command Claude Code runs, the hook calls `memanto recall` with the command context. This injects relevant engineering memories into the session.

2. **PostToolUse** — After every Bash command completes, the hook truncates output to 4KB, then calls `distill-and-remember` which extracts engineering decisions from the raw tool output before storing. This avoids persisting sensitive or noisy raw output. The distillation step (not raw persistence) ensures only structured decisions are stored.

## Alternative: Manual skill wrapping

If you prefer explicit control, use the `wrap` command instead of hooks:

```bash
# Wrap any skill invocation
bash skills-memory.sh wrap "/grill-with-docs 'Design the payment system'"
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMANTO_PREVIEW` | `0` | Set to `1` for local preview mode (no API key) |
| `MEMANTO_AGENT` | `claude-code-skills` | Agent namespace in Memanto |
| `MOORCHEH_API_KEY` | — | Your Moorcheh API key (required for live mode) |
