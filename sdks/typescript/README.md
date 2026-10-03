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

## On-prem (no API key)

The SDK is a thin wrapper around the Memanto server, so backend selection lives in Memanto — not in this SDK. To run fully on-prem (no Moorcheh API key), configure it once with the CLI:

```bash
uvx memanto
```

Pick the **on-prem** backend when prompted. This sets up the local Moorcheh server (Docker) and writes the on-prem config to `~/.memanto/`.

After that, use the SDK normally — **no `apiKey` needed:**

```ts
const memanto = new Memanto({ agentId: "my-agent" });
```

The spawned `memanto serve` inherits the on-prem config from `~/.memanto/`, and the client authenticates with a session token only. Alternatively, point `baseUrl` at an on-prem server you started yourself.

> Requires Docker (for the Moorcheh on-prem server) in addition to `uv`. The SDK does not start the Moorcheh container itself — the `uvx memanto` setup does.

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

When `apiKey` is set it is sent as `X-Api-Key` on every request. A server
reachable beyond loopback requires it for agent management, activation, and
session renewal. Memory requests are still authorized by the server-issued
session token.

### Methods

**Memory writes**

- `remember({ content, type?, title?, confidence?, tags?, source?, provenance? })`
- `batchRemember(items[])` — up to 100 items per request, same shape as `remember`.
- `extractMemories({ messages, dryRun?, maxMemories?, aiModel? })` — extract typed memory candidates from chat-style turns. Set `dryRun: true` to preview without writing. Requires `memanto >= 0.2.3`.
- `uploadFile({ path, filename? })` — uploads a `.pdf`, `.docx`, `.xlsx`, `.json`, `.txt`, `.csv`, or `.md` file (max 5GB).
- `deleteMemory(memoryId)` — delete a single memory by id.

**Memory reads**

- `recall({ query, limit?, minSimilarity?, type?, tags? })` — `tags` returns only memories carrying all of them.
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
- `deleteAgent({ deleteMemories? })` — memories are kept in Moorcheh unless `deleteMemories: true`
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

## eve

`@moorcheh-ai/memanto/eve` gives [eve](https://github.com/vercel/eve) agents long-term memory. Requires Node.js 24 and eve 0.60 or later.

### Memory provider

Add a memory slot:

```ts
// agent/memory/memanto.ts
import { memantoMemory } from "@moorcheh-ai/memanto/eve";
import { defineMemory } from "eve/memory";
import { byPrincipal } from "eve/memory/scope";

export default defineMemory({
  description: "Recall and manage durable context for the current user.",
  provider: memantoMemory({
    apiKey: process.env.MOORCHEH_API_KEY,
    baseUrl: process.env.MEMANTO_BASE_URL,
  }),
  scope: byPrincipal,
});
```

- **Recall.** Before each turn, the memories most relevant to the user's message are added to the model's context as one user-role message marked as data, not instructions. It supersedes the previous turn's recall.
- **Tools.** The model gets `memanto__remember` and `memanto__recall` (eve names them after the slot file). Each call shows an activity label such as `Recalling "coffee order"` → `Found 2 memories`.
- **Capture** (`capture: true`, off by default). After each completed turn, durable memories are extracted from the user's words and saved. This makes one server-side LLM call per turn.

| Option | Default | Description |
| --- | --- | --- |
| `apiKey` | — | Moorcheh API key. Sent as `X-Api-Key` to authorize a remote server. |
| `baseUrl` | — | A running Memanto server. Omit it in `eve dev` to start one locally with `uvx`. |
| `agentId` | `"eve"` | Memanto agent that stores the slot's memories. |
| `recallLimit` | `5` | Memories recalled before each turn (1–50). |
| `capture` | `false` | Extract and save memories from each completed turn. |
| `client` | — | An existing `Memanto` client to use. |

**Isolation.** Every eve scope (with `byPrincipal`, each authenticated user) shares one Memanto agent. Each scope's memories carry a tag derived from eve's opaque scope key. Recall filters on that tag inside the search query, so one user's memories are never candidates for another's. Tools are bound to the turn's scope, so the model cannot address another user's memories.

**Deploying.** eve deployments (for example, on Vercel) cannot start a local server. Run `memanto serve` somewhere the agent can reach, set `MEMANTO_BASE_URL` to its URL, and set `MOORCHEH_API_KEY` to the key that server uses. The server only allows agent activation for callers presenting that key. Treat recalled memories as user-provided data. Tell the model in `agent/instructions.md` not to save secrets or credentials.

### Tools only

To add tools without a memory slot, use `createMemantoEveTools(memanto)`. It returns `recallMemory`, `rememberMemory`, and `answerMemory`; re-export each one from its own file under `agent/tools/`. These tools share one agent across every caller, so use the memory provider when different users must not see each other's memories.

## Versioning

The npm package version tracks the matching PyPI release of `memanto`. To pin a specific server build, pass `packageSpec: "memanto==<version>"`.

## License

MIT
