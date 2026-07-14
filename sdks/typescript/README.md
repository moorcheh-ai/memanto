# @moorcheh-ai/memanto

TypeScript SDK for [Memanto](https://github.com/moorcheh-ai/memanto) — memory that AI agents love.

The SDK boots a local Memanto server on demand via `uvx` and exposes a small ergonomic client for storing and recalling memories.

## Prerequisites

You need `uv` (which ships `uvx`) installed on the machine. The SDK will not install it for you.

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

See https://docs.astral.sh/uv/getting-started/installation/ for other install methods.

## Install

```bash
npm install @moorcheh-ai/memanto
```

## Quick start

```ts
import { Memanto } from "@moorcheh-ai/memanto";

const memanto = new Memanto({
  agentId: "my-agent",
  apiKey: process.env.MOORCHEH_API_KEY,
});

await memanto.remember({ content: "Alex prefers oat milk." });

const { memories } = await memanto.recall({ query: "what does Alex drink?" });
console.log(memories);

const { answer } = await memanto.answer({ question: "Does Alex drink dairy?" });
console.log(answer);

await memanto.close();
```

On the first call, the SDK:

1. Picks a free port and spawns `uvx memanto serve --port <port>`.
2. Polls `/health` until the server is ready.
3. Creates the agent (if `autoCreate` is enabled — default `true`) and activates a session.
4. Sends the request with the session token attached.

When `close()` is called (or the Node process exits), the server is sent `SIGTERM`.

## API

### `new Memanto(options)`

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `agentId` | `string` | — | **Required.** Agent identifier. |
| `apiKey` | `string` | — | Moorcheh API key, passed to the server as `MOORCHEH_API_KEY`. |
| `autoCreate` | `boolean` | `true` | Create the agent if it does not exist. |
| `baseUrl` | `string` | — | Use an already-running server at this URL instead of spawning one. |
| `port` | `number` | auto | Bind the spawned server to this port. |
| `host` | `string` | `127.0.0.1` | Bind host. |
| `uvxPath` | `string` | `uvx` | Override the path to `uvx`. |
| `packageSpec` | `string` | `memanto` | Package spec passed to `uvx`. Use `memanto==0.2.3` to pin. |
| `healthTimeoutMs` | `number` | `60000` | Health-check timeout. |
| `verbose` | `boolean` | `false` | Stream server logs to the parent process. |

### Methods

**Memory writes**

- `remember({ content, type?, title?, confidence?, tags?, source?, provenance? })`
- `batchRemember(items[])` — up to 100 items per request, same shape as `remember`.
- `extractMemories({ messages, dryRun?, maxMemories?, aiModel? })` — extract typed memory candidates from chat-style turns. Set `dryRun: true` to preview without writing. Requires `memanto >= 0.2.3`.
- `uploadFile({ path, filename? })` — uploads a `.pdf`, `.docx`, `.xlsx`, `.json`, `.txt`, `.csv`, or `.md` file (max 5GB).
- `deleteMemory(memoryId)` — delete a single memory by id.

**Memory reads**

- `recall({ query, limit?, minSimilarity?, type? })`
- `recallAsOf({ asOf, limit?, type? })` — point-in-time recall. `asOf` is `YYYY-MM-DD` or ISO 8601.
- `recallChangedSince({ since, limit?, type? })` — what changed after `since`.
- `recallRecent({ limit?, type? })` — newest-first.
- `answer({ question, limit?, threshold?, temperature?, aiModel?, kioskMode? })`

**Analysis**

- `dailySummary({ date?, outputPath? })`
- `generateConflicts({ date? })` — run conflict detection.
- `listConflicts({ date? })` — list unresolved conflicts.
- `resolveConflict({ conflictIndex, action, date?, manualContent?, manualType? })` — `action` is `keep_old | keep_new | keep_both | remove_both | manual`.

**Agent + session lifecycle**

- `listAgents()`
- `getAgent()`
- `createAgent({ pattern?, description? })` — explicit create (only needed when `autoCreate: false`).
- `deleteAgent()`
- `deactivate()` — end the current session (the next call rebootstraps).
- `status()` — current session info.
- `close()` — stop the spawned server.

### Helpers

```ts
import { doctor } from "@moorcheh-ai/memanto";

const result = await doctor();
if (!result.uvxAvailable) {
  console.error(result.hint);
}
```

## Versioning

The npm package version tracks the matching PyPI release of `memanto`. To pin a specific server build, pass `packageSpec: "memanto==<version>"`.

## License

MIT
