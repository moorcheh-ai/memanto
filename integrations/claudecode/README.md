# Claude Code + Memanto Integration

`claudecode-memanto` installs [Memanto](https://memanto.ai) in [Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview). It is a convenience wrapper around the same connection engine used by `memanto connect claude-code`, so both commands create and remove the exact same integration.

The integration connects Claude Code to Memanto via the **Model Context Protocol (`memanto-mcp`)**, pairs it with managed `CLAUDE.md` instructions, and installs lifecycle hooks for session synchronization and readable tool summaries.

## Requirements

- Python 3.10 or later.
- Claude Code.
- A configured Memanto installation with an active agent (or an agent ID passed with `--agent-id`). Installing this package automatically installs `memanto>=0.2.30` and `memanto-mcp>=0.1.4`.
- `MOORCHEH_API_KEY` configured in `~/.memanto/.env` (via `memanto` setup) or available in the environment.

Install the package:

```bash
pip install claudecode-memanto
```

Verify your Memanto configuration and active agent before starting Claude Code:

```bash
memanto status
```

## Install

Install into the current project:

```bash
claudecode-memanto install
```

Or specify a project directory and/or default Memanto agent ID for the MCP server:

```bash
claudecode-memanto install --project-dir ./my-project --agent-id my-project-assistant
```

This manages the following project-local paths:

| Path | Purpose |
| --- | --- |
| `CLAUDE.md` | Adds or updates the Memanto-managed instruction block. |
| `.mcp.json` | Registers the `memanto` MCP server (`memanto-mcp`) with your default agent ID and `claude` source attribution. |
| `.claude/settings.json` | Adds the Memanto lifecycle hooks (`SessionStart`, `PreCompact`, and `PostToolUse`). |
| `.claude/settings.local.json` | Pre-approves the `memanto` project MCP server (`enabledMcpjsonServers`) and allows `mcp__memanto` so memory operations run seamlessly without permission prompts. |

> **Note on API keys:** `MOORCHEH_API_KEY` is never written into `.mcp.json` or `~/.claude.json`. `memanto-mcp` reads your key directly from `~/.memanto/.env` (or the process environment).

**General Rule of Safety:** The integration is strictly non-destructive. Anything you do with this CLI will completely preserve whatever you already have configured in your project. It will never overwrite, delete, or modify your existing custom Claude Code configurations or user-managed MCP servers.

### Global Install

Use `--global` (`-g`) to install for every Claude Code project run by the current user:

```bash
claudecode-memanto install --global
```

Global installation writes to:

| Path | Purpose |
| --- | --- |
| `~/.claude/CLAUDE.md` | Adds or updates the global Memanto-managed instruction block. |
| `~/.claude.json` | Registers the `memanto` MCP server in `mcpServers`. |
| `~/.claude/settings.json` | Adds the Memanto lifecycle hooks and allows `mcp__memanto` permissions. |

Project and global installations are independent, so they can be used together when needed.

## What Claude Code Receives

### `memanto` MCP Server (`memanto-mcp`)

Claude Code receives native MCP tools for reading and writing persistent memory:

| Tool | Purpose |
| --- | --- |
| `remember` | Store a durable memory with required `type`, `confidence`, and `provenance` metadata. |
| `batch_remember` | Store up to 100 structured memories in a single call. |
| `recall` | Semantic search across stored memories before starting work or answering questions. |
| `recall_recent` | Fetch the newest memories first without a search query. |
| `recall_as_of` | Point-in-time memory snapshot (`as_of` timestamp). |
| `recall_changed_since` | Differential recall for memories created or updated since a given window. |
| `answer` | Synthesize a grounded RAG answer directly from agent memories. |

The MCP entry sets `MEMANTO_DEFAULT_AGENT_ID` (from `--agent-id` or your currently active Memanto agent) and `MEMANTO_DEFAULT_SOURCE="claude"`, so every stored memory is automatically attributed to Claude Code.

### Managed `CLAUDE.md` Instructions

The installer adds a versioned `MEMANTO-MANAGED-SECTION` (`v1.1.0`) to `CLAUDE.md`. It directs Claude Code to actively evaluate using the `memanto` MCP tools (`recall`, `remember`) at every step:

1. **When to Recall:** On task initiation, ambiguous build/test failures, unstated user preferences, or explicit questions about prior decisions.
2. **When to Remember:** When preferences/instructions, goals/commitments, bug-fix learnings/errors, architectural decisions/observations, or verified environment facts are established.
3. **The Abstraction Rule:** Elevate stored memories to clean, declarative principles rather than chat logs.
4. **The Durability Test:** Only store principles that will still matter in future sessions months from now.

The dynamic-memory portion of the managed block (`MEMANTO-DYNAMIC-MEMORIES`) is reserved for `memanto memory sync`. Re-running `install` safely updates the managed block in place while preserving the rest of `CLAUDE.md`.

### Lifecycle Hooks

The installer adds these hooks to Claude Code's `settings.json`:

| Hook | When it runs | Behavior |
| --- | --- | --- |
| `SessionStart` | On Claude Code startup and resume | Runs `memanto memory sync` so standing dynamic memories are refreshed and installs the Memanto status line once if no custom status line is set. |
| `PreCompact` | Before Claude Code compacts the conversation | Runs `memanto memory sync --project-dir <project>` to refresh dynamic context before earlier messages are summarized away. |
| `PostToolUse` | After `mcp__memanto__.*` MCP tool calls | Converts Memanto MCP tool results into a short chat-visible `systemMessage` (e.g., `👾 Memanto · stored a decision`, `👾 Memanto · recalled 3 memories`). |

Hook commands use the resolved Python interpreter that installed Memanto and absolute paths to Memanto's bundled hook scripts. This avoids failures caused by a project's active virtual environment or by `python` and `python3` resolving differently across machines.

## Reinstall and Removal

Re-running installation is safe and idempotent:

```bash
claudecode-memanto install
```

It updates only Memanto-managed entries (marked with `MEMANTO_MANAGED_BY="memanto-connect"` for MCP servers and `_managed_by: "memanto"` for hooks), retains unrelated hooks and MCP servers, and refreshes the managed `CLAUDE.md` section.

Remove the project-local integration:

```bash
claudecode-memanto uninstall
```

Remove the global integration:

```bash
claudecode-memanto uninstall --global
```

Uninstall removes the Memanto instruction blocks, managed MCP server entry, hooks, and local permissions that it manages. It preserves other Claude Code instructions, custom hooks, user-defined MCP servers, permissions, and settings. Empty files and directories created solely for the integration are cleaned up where possible.

## Equivalent Core Commands

These commands are equivalent:

```bash
claudecode-memanto install [--project-dir PATH] [--global] [--agent-id AGENT_ID]
memanto connect claude-code [--project-dir PATH] [--global] [--agent-id AGENT_ID]
```

```bash
claudecode-memanto uninstall [--project-dir PATH] [--global]
memanto connect remove claude-code [--project-dir PATH] [--global]
```

Use `claudecode-memanto` when you want a Claude Code-specific entry point, or use `memanto connect claude-code` when managing integrations through the core CLI.
