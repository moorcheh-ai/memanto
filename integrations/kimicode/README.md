# Kimi Code + Memanto Integration

`kimicode-memanto` installs [Memanto](https://memanto.ai) in [Kimi Code](https://github.com/MoonshotAI/kimi-code). It is a convenience wrapper around the same connection engine used by `memanto connect kimi-code`, so both commands create and remove the same integration.

The integration combines Kimi Code instructions, a memory skill, and lifecycle hooks. It does not depend on `mattpocock/skills` or implement per-skill routing: Kimi Code uses Memanto through its normal conversational workflow.

## Requirements

- Python 3.10 or later.
- Kimi Code.
- A configured Memanto installation. Installing this package also installs `memanto>=0.2.22`.
- `MOORCHEH_API_KEY` available in the environment that starts Kimi Code.

Install the package:

```bash
pip install kimicode-memanto
```

Verify your Memanto configuration before starting Kimi Code:

```bash
memanto --help
```

## Install

Install into the current project:

```bash
kimicode-memanto install
```

This manages the following project-local paths:

| Path | Purpose |
| --- | --- |
| `AGENTS.md` | Adds or updates the Memanto-managed instruction block. |
| `.kimi-code/skills/memanto/SKILL.md` | Deploys the `memanto-memory` command and metadata reference skill. |
| `~/.kimi-code/config.toml` | Adds the Memanto lifecycle hooks and the `Bash(memanto *)` permission allow-rule inside a clearly marked managed section. |

**Hooks are always user-level in Kimi Code.** Kimi Code only supports hooks in the user-level `~/.kimi-code/config.toml`, so even a project-local install writes the hook and permission rules there — inside a `# >>> MEMANTO-MANAGED-SECTION >>>` / `# <<< MEMANTO-MANAGED-SECTION <<<` block, appended at the end of the file. The rest of your `config.toml` is never touched.

**General Rule of Safety:** The integration is strictly non-destructive. Anything you do with this CLI will completely preserve whatever you already have configured in your project. It will never overwrite, delete, or modify your existing custom Kimi Code configurations.

### Global Install

Use `--global` to install for every Kimi Code project run by the current user:

```bash
kimicode-memanto install --global
```

Global installation writes to `~/.kimi-code/AGENTS.md` and `~/.kimi-code/skills/memanto/SKILL.md`. The hooks and permission rule go to the same user-level `~/.kimi-code/config.toml` as a project install.

Project and global installations are independent, so they can be used together when needed.

## What Kimi Code Receives

### Managed `AGENTS.md` Instructions

The installer adds a versioned `MEMANTO-MANAGED-SECTION` to `AGENTS.md`. It tells Kimi Code to treat Memanto as persistent, cross-session memory and to use shell commands for memory operations.

The instructions direct Kimi Code to:

- Store durable facts, decisions, constraints, preferences, goals, and corrections with `memanto remember`.
- Recall relevant context before complex work, after task switches, for ambiguous failures, and when asked about past decisions.
- Use `memanto recall` for source memories and `memanto answer` for grounded answers.
- Use the installed `memanto-memory` skill for complete command syntax, memory types, confidence, provenance, and tagging guidance.

The dynamic-memory portion of the managed block is reserved for `memanto memory sync`. If you run the `install` command again in the future (e.g., after upgrading the CLI), it safely updates the integration in place. As a general rule, anything you do with this CLI will completely preserve whatever you already have configured in your project—it will never touch, delete, or overwrite the rest of your custom `AGENTS.md` content or configurations.

### `memanto-memory` Skill

The installed skill is Kimi Code's reference for Memanto operations. It includes the metadata required when storing memories and examples for recall, answer, edit, forget, and memory synchronization. It is a guide for using the core `memanto` CLI, not a separate memory backend.

### Lifecycle Hooks

The installer appends these hooks to the managed section of the user-level `~/.kimi-code/config.toml`:

| Hook | When it runs | Behavior |
| --- | --- | --- |
| `SessionStart` (matcher `startup\|resume`) | On Kimi Code startup and resume | Runs `memanto memory sync` so dynamic memories are refreshed in `MEMORY.md` and available in the project instructions before work begins. |
| `PreCompact` | Before Kimi Code compacts the conversation | Runs the same memory sync to re-sync the dynamic context before earlier messages are summarized away. |
| `PostToolUse` (matcher `Bash`) | After a Bash tool command | Converts recognized Memanto CLI results into a short context-visible summary, such as stored, recalled, synchronized, or deleted memory. |

The managed section also adds a `Bash(memanto *)` permission allow-rule so Memanto commands can run seamlessly in the background without constant permission prompts.

The `PostToolUse` hook does not run for unrelated tools, and its summary only appears for Bash commands containing `memanto`. The integration does not inject memory automatically for every prompt, distill conversations on stop, or alter third-party skills.

Hook commands use the absolute Python interpreter that installed Memanto and absolute paths to Memanto's bundled hook scripts. This avoids failures caused by a project's active virtual environment or by `python` and `python3` resolving differently on different machines.

## Reinstall and Removal

Re-running installation is safe:

```bash
kimicode-memanto install
```

It replaces only the Memanto-managed section, retains everything else in `config.toml` byte-for-byte (including your own hooks, permission rules, and comments), refreshes the installed skill, and updates the managed `AGENTS.md` section.

Remove the project-local integration:

```bash
kimicode-memanto uninstall
```

Remove the global integration:

```bash
kimicode-memanto uninstall --global
```

Uninstall removes the Memanto instruction blocks, the skill, and the managed section of `config.toml` (hooks and permission rule) that it owns. It preserves other Kimi Code instructions, custom hooks, permissions, and settings, and it never deletes or rewrites `config.toml` itself. Empty files and directories created solely for the integration are cleaned up where possible.

## Equivalent Core Command

These commands are equivalent:

```bash
kimicode-memanto install
memanto connect kimi-code
```

Use `kimicode-memanto` when you want a Kimi Code-specific entry point, or use `memanto connect kimi-code` when managing integrations through the core CLI.
