# Claude Code + Memanto Integration

`claudecode-memanto` installs [Memanto](https://memanto.ai) in [Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview). It is a convenience wrapper around the same connection engine used by `memanto connect claude-code`, so both commands create and remove the same integration.

The integration combines Claude Code instructions, a memory skill, and lifecycle hooks. It does not depend on `mattpocock/skills` or implement per-skill routing: Claude Code uses Memanto through its normal conversational workflow.

## Requirements

- Python 3.10 or later.
- Claude Code.
- A configured Memanto installation. Installing this package also installs `memanto>=0.2.21`.
- `MOORCHEH_API_KEY` available in the environment that starts Claude Code.

Install the package:

```bash
pip install claudecode-memanto
```

Verify your Memanto configuration before starting Claude Code:

```bash
memanto --help
```

## Install

Install into the current project:

```bash
claudecode-memanto install
```

This manages the following project-local paths:

| Path | Purpose |
| --- | --- |
| `CLAUDE.md` | Adds or updates the Memanto-managed instruction block. |
| `.claude/skills/memanto/SKILL.md` | Deploys the `memanto-memory` command and metadata reference skill. |
| `.claude/settings.json` | Adds the Memanto lifecycle hooks. |
| `.claude/settings.local.json` | Allows the `Bash(memanto:*)` command pattern so Memanto can run seamlessly in the background without constant permission prompts. |

**General Rule of Safety:** The integration is strictly non-destructive. Anything you do with this CLI will completely preserve whatever you already have configured in your project. It will never overwrite, delete, or modify your existing custom Claude Code configurations.

### Global Install

Use `--global` to install for every Claude Code project run by the current user:

```bash
claudecode-memanto install --global
```

Global installation writes to `~/.claude/CLAUDE.md`, `~/.claude/skills/memanto/SKILL.md`, `~/.claude/settings.json`, and `~/.claude/settings.local.json`.

Project and global installations are independent, so they can be used together when needed.

## What Claude Code Receives

### Managed `CLAUDE.md` Instructions

The installer adds a versioned `MEMANTO-MANAGED-SECTION` to `CLAUDE.md`. It tells Claude Code to treat Memanto as persistent, cross-session memory and to use shell commands for memory operations.

The instructions direct Claude Code to:

- Store durable facts, decisions, constraints, preferences, goals, and corrections with `memanto remember`.
- Recall relevant context before complex work, after task switches, for ambiguous failures, and when asked about past decisions.
- Use `memanto recall` for source memories and `memanto answer` for grounded answers.
- Use the installed `memanto-memory` skill for complete command syntax, memory types, confidence, provenance, and tagging guidance.

The dynamic-memory portion of the managed block is reserved for `memanto memory sync`. If you run the `install` command again in the future (e.g., after upgrading the CLI), it safely updates the integration in place. As a general rule, anything you do with this CLI will completely preserve whatever you already have configured in your project—it will never touch, delete, or overwrite the rest of your custom `CLAUDE.md` content or configurations.

### `memanto-memory` Skill

The installed skill is Claude Code's reference for Memanto operations. It includes the metadata required when storing memories and examples for recall, answer, edit, forget, and memory synchronization. It is a guide for using the core `memanto` CLI, not a separate memory backend.

### Lifecycle Hooks

The installer adds these hooks to Claude Code's `settings.json`:

| Hook | When it runs | Behavior |
| --- | --- | --- |
| `SessionStart` | On Claude Code startup and resume | Runs `memanto memory sync --project-dir <project>` so dynamic memories are available in the project instructions before work begins. |
| `PreCompact` | Before Claude Code compacts the conversation | Runs the same memory sync to refresh the dynamic context before earlier messages are summarized away. |
| `PostToolUse` | After a Bash tool command matching `memanto *` | Converts recognized Memanto CLI results into a short chat-visible system message, such as stored, recalled, synchronized, or deleted memory. |

The `PostToolUse` hook does not run for unrelated Bash commands. The integration does not inject memory automatically for every prompt, distill conversations on stop, or alter third-party skills.

Hook commands use the absolute Python interpreter that installed Memanto and absolute paths to Memanto's bundled hook scripts. This avoids failures caused by a project's active virtual environment or by `python` and `python3` resolving differently on different machines.

## Reinstall and Removal

Re-running installation is safe:

```bash
claudecode-memanto install
```

It replaces only Memanto-managed hook commands, retains unrelated commands even when they share a hook event, refreshes the installed skill, and updates the managed `CLAUDE.md` section.

Remove the project-local integration:

```bash
claudecode-memanto uninstall
```

Remove the global integration:

```bash
claudecode-memanto uninstall --global
```

Uninstall removes the Memanto instruction blocks, skill, hooks, and local permission that it manages. It preserves other Claude Code instructions, custom hooks, permissions, and settings. Empty files and directories created solely for the integration are cleaned up where possible.

## Equivalent Core Command

These commands are equivalent:

```bash
claudecode-memanto install
memanto connect claude-code
```

Use `claudecode-memanto` when you want a Claude Code-specific entry point, or use `memanto connect claude-code` when managing integrations through the core CLI.
