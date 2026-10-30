# Installing the Memanto MCP server

These steps are for an AI agent (such as Cline) setting up memanto-mcp for
a user. Memanto gives the agent persistent memory that survives across
sessions.

## 1. Ask the user for two values

- **Moorcheh API key** (required). The user can create one at
  https://console.moorcheh.ai/api-keys. The free tier is enough to start.
  Keys look like `mch_...`. Do not invent or guess a key.
- **Agent ID** (recommended). A short name for this memory space, for
  example `cline-assistant` or the project name. Letters, digits, `-` and
  `_` work. If the user has no preference, use `cline-assistant`.

## 2. Install the package

Python 3.10 or newer is required.

```bash
pip install memanto-mcp
```

Check that it installed:

```bash
memanto-mcp --help
```

If `memanto-mcp` is not found, the pip scripts folder is not on PATH. Use
the absolute path to the `memanto-mcp` executable in the config below
instead. It is in the `Scripts` folder (Windows) or `bin` folder
(macOS/Linux) of the Python install that ran `pip install`.

## 3. Add the server to the MCP settings

Add this entry to `cline_mcp_settings.json`, keeping any servers that are
already there:

```json
{
  "mcpServers": {
    "memanto": {
      "command": "memanto-mcp",
      "env": {
        "MOORCHEH_API_KEY": "<the user's Moorcheh API key>",
        "MEMANTO_DEFAULT_AGENT_ID": "<the agent ID from step 1>"
      },
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

The agent and its memory space are created automatically on the first tool
call. No other setup is needed.

## 4. Verify

After the server shows as connected, the client should list 7 tools:
`remember`, `batch_remember`, `recall`, `recall_recent`, `recall_as_of`,
`recall_changed_since`, and `answer`.

Run a quick read-only check: call `recall_recent` with `limit` 1. A result
with `status` `ok` means the server is connected and the API key works. On a
new agent the memory list is empty, which is expected.

Don't save a test memory to check the install. Memories are permanent, so a
test entry would show up in the user's later recalls.

## Troubleshooting

| Problem | Fix |
|---|---|
| `MOORCHEH_API_KEY is required` | The key is missing from the `env` block. Add it and restart the server. |
| Authentication error on the first call | The key is wrong or revoked. Ask the user to create a new one in the console. |
| Tools do not appear | Check that `command` points to a working `memanto-mcp` (see step 2) and look at the server's log output in the MCP panel. |
| First call is slow | Normal: the first call opens a session. Later calls are fast. |

More details: https://github.com/moorcheh-ai/memanto/tree/main/integrations/mcp
