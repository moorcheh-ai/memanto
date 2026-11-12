# Kimi Code + Memanto Integration

`kimicode-memanto` installs [Memanto](https://memanto.ai) in [Kimi Code](https://www.kimi.com/code/). It is a convenience wrapper around the same connection engine used by `memanto connect kimi-code`, so both commands create and remove the exact same integration.

The integration connects Kimi Code to Memanto via the **Model Context Protocol (`memanto-mcp`)** (or falls back to the `memanto-memory` CLI skill when MCP is unavailable), pairs it with managed `AGENTS.md` instructions, and installs lifecycle hooks for session synchronization and readable tool summaries.

## Requirements

- Python 3.10 or later.
- Kimi Code.
- A configured Memanto installation with an active agent (or an agent ID passed with `--agent-id`). Installing this package automatically installs `memanto>=0.2.30` and `memanto-mcp>=0.1.4`.
- `MOORCHEH_API_KEY` configured in `~/.memanto/.env` (via `memanto` setup) or available in the environment.

Install the package:

```bash
pip install kimicode-memanto
```

Verify your Memanto configuration and active agent before starting Kimi Code:

```bash
memanto status
```

## Install

Install into the current project:

```bash
kimicode-memanto install
```

Or specify a project directory and/or default Memanto agent ID for the MCP server:

```bash
kimicode-memanto install --project-dir ./my-project --agent-id my-project-assistant
```

This manages the following paths:

| Path | Purpose |
| --- | --- |
| `AGENTS.md` | Adds or updates the Memanto-managed instruction block. |
| `.kimi-code/mcp.json` | Registers the `memanto` MCP server (`memanto-mcp`) with your default agent ID and `kimi-code` source attribution (or deploys `.kimi-code/skills/memanto/SKILL.md` when MCP is skipped). |
| `~/.kimi-code/config.toml` | Adds the Memanto lifecycle hooks and `Bash(memanto *)` / `mcp__memanto*` permission allow-rules inside a clearly marked managed section. |

> **Note on API keys:** `MOORCHEH_API_KEY` is never written into `.kimi-code/mcp.json`, `~/.kimi-code/mcp.json`, or `config.toml`. `memanto-mcp` reads your key directly from `~/.memanto/.env` (or the process environment).

**Hooks are always user-level in Kimi Code.** Kimi Code only supports hooks in the user-level `~/.kimi-code/config.toml` (or `$KIMI_CODE_HOME/config.toml`), so even a project-local install writes the hook and permission rules there — inside a `# >>> MEMANTO-MANAGED-SECTION >>>` / `# <<< MEMANTO-MANAGED-SECTION <<<` block. The rest of your `config.toml` is never touched.

**General Rule of Safety:** The integration is strictly non-destructive. Anything you do with this CLI will completely preserve whatever you already have configured in your project. It will never overwrite, delete, or modify your existing custom Kimi Code configurations or user-managed MCP servers.

### Global Install

Use `--global` (`-g`) to install for every Kimi Code project run by the current user:

```bash
kimicode-memanto install --global
```

Global installation writes to `~/.kimi-code/AGENTS.md` and `~/.kimi-code/mcp.json` (or under `$KIMI_CODE_HOME` when set). The hooks and permission rules go to the same user-level `~/.kimi-code/config.toml` as a project install.

Project and global installations are independent, so they can be used together when needed.

## What Kimi Code Receives

### `memanto` MCP Server (`memanto-mcp`)

Kimi Code receives native MCP tools for reading and writing persistent memory:

| Tool | Purpose |
| --- | --- |
| `remember` | Store a durable memory with required `type`, `confidence`, and `provenance` metadata. |
| `batch_remember` | Store up to 100 structured memories in a single call. |
| `recall` | Semantic search across stored memories before starting work or answering questions. |
| `recall_recent` | Fetch the newest memories first without a search query. |
| `recall_as_of` | Point-in-time memory snapshot (`as_of` timestamp). |
| `recall_changed_since` | Differential recall for memories created or updated since a given window. |
| `answer` | Synthesize a grounded RAG answer directly from agent memories. |

The MCP entry sets `MEMANTO_DEFAULT_AGENT_ID` (from `--agent-id` or your currently active Memanto agent) and `MEMANTO_DEFAULT_SOURCE="kimi-code"`, so every stored memory is automatically attributed to Kimi Code.

### Managed `AGENTS.md` Instructions

The installer adds a versioned `MEMANTO-MANAGED-SECTION` (`v1.1.0`) to `AGENTS.md`. It directs Kimi Code to actively evaluate using the `memanto` MCP tools (`recall`, `remember`) or CLI commands at every step:

1. **When to Recall:** On task initiation, ambiguous build/test failures, unstated user preferences, or explicit questions about prior decisions.
2. **When to Remember:** When preferences/instructions, goals/commitments, bug-fix learnings/errors, architectural decisions/observations, or verified environment facts are established.
3. **The Abstraction Rule:** Elevate stored memories to clean, declarative principles rather than chat logs.
4. **The Durability Test:** Only store principles that will still matter in future sessions months from now.

The dynamic-memory portion of the managed block (`MEMANTO-DYNAMIC-MEMORIES`) is reserved for `memanto memory sync`. Re-running `install` safely updates the managed block in place while preserving the rest of `AGENTS.md`.

### Lifecycle Hooks

The installer appends these hooks to the managed section of the user-level `~/.kimi-code/config.toml`:

| Hook | When it runs | Behavior |
| --- | --- | --- |
| `SessionStart` (matcher `startup\|resume`) | On Kimi Code startup and resume | Runs `memanto memory sync` so standing dynamic memories are refreshed before work begins. |
| `PreCompact` | Before Kimi Code compacts the conversation | Runs `memanto memory sync --project-dir .` to re-sync dynamic context before earlier messages are summarized away. |
| `PostToolUse` (matchers `Bash` and `mcp__memanto__.*`) | After Memanto CLI or MCP tool calls | Converts recognized Memanto operations into a short summary (e.g., `👾 Memanto · stored a decision`, `👾 Memanto · recalled 3 memories`). |

The managed section also adds `Bash(memanto *)` and `mcp__memanto*` permission allow-rules so Memanto operations run seamlessly without permission prompts.

Hook commands use the resolved Python interpreter that installed Memanto and absolute paths to Memanto's bundled hook scripts. This avoids failures caused by a project's active virtual environment or by `python` and `python3` resolving differently on different machines.

## Reinstall and Removal

Re-running installation is safe and idempotent:

```bash
kimicode-memanto install
```

It replaces only the Memanto-managed sections, retains everything else in `config.toml` byte-for-byte (including your own hooks, permission rules, and comments), updates the managed MCP entry (or skill fallback), and refreshes the managed `AGENTS.md` section.

Remove the project-local integration:

```bash
kimicode-memanto uninstall
```

Remove the global integration:

```bash
kimicode-memanto uninstall --global
```

Uninstall removes the Memanto instruction blocks, managed MCP server entry (or skill), and the managed section of `config.toml` when no other Kimi Code project or global installation remains active. It preserves other Kimi Code instructions, custom hooks, user-defined MCP servers, permissions, and settings, and it never deletes `config.toml` itself.

## Equivalent Core Commands

These commands are equivalent:

```bash
kimicode-memanto install [--project-dir PATH] [--global] [--agent-id AGENT_ID]
memanto connect kimi-code [--project-dir PATH] [--global] [--agent-id AGENT_ID]
```

```bash
kimicode-memanto uninstall [--project-dir PATH] [--global]
memanto connect remove kimi-code [--project-dir PATH] [--global]
```

Use `kimicode-memanto` when you want a Kimi Code-specific entry point, or use `memanto connect kimi-code` when managing integrations through the core CLI.
