# Memanto MCP Server

**Persistent semantic memory for any MCP-compatible agent.**

This package exposes [Memanto's](https://memanto.ai) memory primitives —
`remember`, `recall`, `answer`, and friends — as
[Model Context Protocol (MCP)](https://modelcontextprotocol.io) tools so any
MCP client (Claude Desktop, Cursor, Windsurf, Cline, Continue, Goose,
custom agents, …) can plug into long-term memory in a single config line.

> One Moorcheh API key → typed semantic memory across every agent that
> shares the namespace, with sub-90 ms retrieval, conflict detection, and
> zero ingestion latency.

---

## Install

```bash
pip install memanto-mcp
```

Requires Python 3.10+ and a [Moorcheh API key](https://console.moorcheh.ai/api-keys)
(free tier: 100K ops/month).

## Quick start (Claude Desktop)

1. Get a Moorcheh API key from the [console](https://console.moorcheh.ai/api-keys).
2. Edit `claude_desktop_config.json` (Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "memanto": {
      "command": "memanto-mcp",
      "env": {
        "MOORCHEH_API_KEY": "mch_xxxxxxxxxxxxxxxxxx",
        "MEMANTO_DEFAULT_AGENT_ID": "my-assistant"
      }
    }
  }
}
```

3. Restart Claude Desktop. Ask it to *"remember that I prefer concise
   answers"* — then in a brand-new chat tomorrow ask *"what do I prefer?"*.

The first call auto-creates the `my-assistant` agent and namespace; every
subsequent call reuses the same persistent memory.

## Quick start (Cursor / Windsurf / Cline / Continue / Goose)

Most clients consume a config file in the
[standard MCP shape](https://modelcontextprotocol.io/docs/clients).
The same JSON snippet works almost verbatim:

```json
{
  "mcpServers": {
    "memanto": {
      "command": "memanto-mcp",
      "env": {
        "MOORCHEH_API_KEY": "mch_xxxxxxxxxxxxxxxxxx",
        "MEMANTO_DEFAULT_AGENT_ID": "cursor-workspace"
      }
    }
  }
}
```

| Client | Config path |
|---|---|
| Claude Desktop | `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) / `%APPDATA%\Claude\claude_desktop_config.json` (Windows) |
| Cursor | `~/.cursor/mcp.json` (or per-project `.cursor/mcp.json`) |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` |
| Cline (VS Code) | `~/.config/Code/User/globalStorage/cline.cline/settings/cline_mcp_settings.json` |
| Continue | `~/.continue/config.json` → `experimental.modelContextProtocolServers` |
| Goose | `~/.config/goose/config.yaml` |

## Available tools

The server registers **7 memory tools by default**. Set
`MEMANTO_EXPOSE_ADMIN=true` to also expose **4 agent-management tools**.

### Memory tools (always on)

| Tool | When the agent should call it |
|---|---|
| `remember` | Persist a single new fact/preference/decision/goal/instruction. |
| `batch_remember` | Persist up to 100 memories in one call (e.g. extracted from a document). |
| `recall` | Semantic search — *always* check here before asking the user to repeat stable info. |
| `recall_recent` | "What did we just decide?" — newest-first, no query needed. |
| `recall_as_of` | Point-in-time recall — "what did we know on 2025-11-01?" |
| `recall_changed_since` | Differential — "what's new since I last checked?" |
| `answer` | RAG: grounded LLM answer synthesized over the agent's memories. |

### Agent admin tools (opt-in)

Enabled when `MEMANTO_EXPOSE_ADMIN=true`:

| Tool | Purpose |
|---|---|
| `create_agent` | Create a new memory namespace. |
| `list_agents` | List every agent the API key can see. |
| `get_agent` | Look up an agent's metadata. |
| `delete_agent` | Remove an agent's local metadata. |

Memory types accepted by `remember` / `batch_remember`:
`fact`, `preference`, `goal`, `decision`, `artifact`, `learning`, `event`,
`instruction`, `relationship`, `context`, `observation`, `commitment`,
`error`.

Provenance values: `explicit_statement`, `inferred`, `corrected`,
`validated`, `observed`, `imported`.

## Configuration

All config is via environment variables (load order: process env →
`.env` file in the working directory).

| Variable | Required | Default | Description |
|---|---|---|---|
| `MOORCHEH_API_KEY` | **yes** | — | Moorcheh API key. |
| `MEMANTO_DEFAULT_AGENT_ID` | recommended | _none_ | Default agent. When set, tool calls may omit `agent_id`. |
| `MEMANTO_AGENT_PATTERN` | no | `tool` | Pattern (`support`/`project`/`tool`) used when auto-creating the default agent. |
| `MEMANTO_AGENT_AUTO_CREATE` | no | `true` | Create the default agent on first use if missing. |
| `MEMANTO_SESSION_DURATION_HOURS` | no | server default (6) | Session lifetime in hours. |
| `MEMANTO_EXPOSE_ADMIN` | no | `false` | Register the 4 agent-management tools. |
| `MEMANTO_MCP_TRANSPORT` | no | `stdio` | `stdio`, `sse`, or `streamable-http`. |
| `MEMANTO_MCP_HOST` | no | `127.0.0.1` | Bind host for sse/http transports. |
| `MEMANTO_MCP_PORT` | no | `8765` | Bind port for sse/http transports. |
| `MEMANTO_MCP_LOG_LEVEL` | no | `INFO` | Log level (logs are always sent to stderr). |

CLI flags (`memanto-mcp --transport sse --port 9000`) override env vars.

## Running over HTTP / SSE

For remote clients or multi-process setups, run the server over a network
transport:

```bash
# Streamable HTTP (recommended modern transport)
memanto-mcp --transport streamable-http --host 0.0.0.0 --port 8765

# Server-Sent Events (older, still widely supported)
memanto-mcp --transport sse --host 0.0.0.0 --port 8765
```

Then point your client at `http://your-host:8765/mcp` (or whatever path the
chosen transport advertises). Pair with a reverse proxy + auth for
production deployments — the server itself authenticates upstream to
Moorcheh using your API key but does **not** authenticate inbound MCP
clients.

## How it works

```
┌──────────────┐    MCP/stdio    ┌──────────────────┐    Moorcheh API    ┌─────────────┐
│ Claude / IDE │ ──────────────► │  memanto-mcp     │ ────────────────► │   Moorcheh  │
│   (client)   │ ◄────────────── │  (this package)  │ ◄──────────────── │   Service   │
└──────────────┘    tool calls   └──────────────────┘    HTTPS+API key   └─────────────┘
                                          │
                                          └─ uses memanto.cli.client.SdkClient
                                             (same client the Memanto CLI uses)
```

- On startup, settings are validated; the API key is verified lazily on
  first tool call.
- On the first memory tool invocation for a given agent, the server
  ensures the agent exists (auto-creates if needed) and activates a JWT
  session. Sessions auto-renew before expiry, so long-running MCP
  connections never hit a session-expired error mid-conversation.
- The server intentionally keeps the session alive on shutdown: JWT
  sessions are TTL-bound and other Memanto clients (CLI, REST) may want
  to share them.

## Programmatic embedding

If you're building a custom MCP host or wiring this server into a larger
process, you can construct the FastMCP instance yourself:

```python
from memanto_mcp import MCPServerSettings, build_server

settings = MCPServerSettings()  # reads env / .env
mcp = build_server(settings)

# Add your own tools alongside Memanto's, then run.
mcp.run(transport="stdio")
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `configuration error: MOORCHEH_API_KEY is required` | Set the env var in your MCP client config's `env` block. |
| `Agent '…' does not exist and MEMANTO_AGENT_AUTO_CREATE is disabled` | Either re-enable auto-create or call `create_agent` (admin tools) / `memanto agent create <id>` once. |
| Tools never appear in the client | Confirm the client supports MCP and the config path matches. Look at the client's MCP log: the server's stderr lines (prefixed `memanto_mcp`) will appear there on startup. |
| Garbled output in stdio mode | Something on your side is writing to **stdout** — that channel is reserved for JSON-RPC. Move logs to stderr. The server itself only writes to stderr. |
| Slow first call | Cold-start cost: SDK import + first session activation. Subsequent calls reuse the live session. |

## License

MIT — same as the [Memanto](https://github.com/moorcheh-ai/memanto)
project. See [LICENSE](../../LICENSE).

## Links

- [Memanto](https://memanto.ai) — the memory agent itself
- [Moorcheh](https://moorcheh.ai) — the no-indexing semantic DB underneath
- [Model Context Protocol spec](https://modelcontextprotocol.io)
- [Anthropic MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
