# @moorcheh-ai/memanto

TypeScript SDK for [Memanto](https://github.com/moorcheh-ai/memanto) — memory that AI agents love.

Connects directly to **Memanto Cloud** ([console.memanto.ai/sign-in](https://console.memanto.ai/sign-in)) with `MEMANTO_API_KEY` (`mk_...`), or boots a local Memanto server on demand via `uvx` when using **Memanto local** (`MOORCHEH_API_KEY` or Moorcheh on-prem).

## Install

```bash
npm install @moorcheh-ai/memanto
```

## Quick start (Memanto Cloud — recommended)

Create a Memanto Cloud API key at [console.memanto.ai/sign-in](https://console.memanto.ai/sign-in) and set `MEMANTO_API_KEY`:

```ts
import { Memanto } from "@moorcheh-ai/memanto";

const memanto = new Memanto({
  agentId: "my-agent",
  apiKey: process.env.MEMANTO_API_KEY,
});

await memanto.remember({ content: "Alex prefers oat milk." });

const { memories } = await memanto.recall({ query: "what does Alex drink?" });
console.log(memories);

const { answer } = await memanto.answer({ question: "Does Alex drink dairy?" });
console.log(answer);

await memanto.close();
```

With a Memanto Cloud key (`mk_...` or `MEMANTO_API_KEY`), the SDK talks directly to the hosted Memanto Cloud API over HTTPS — no local `uvx` server is needed.

## Memanto local (`MOORCHEH_API_KEY` or On-Prem)

To run locally against Moorcheh Cloud (`MOORCHEH_API_KEY` from [console.moorcheh.ai/api-keys](https://console.moorcheh.ai/api-keys)) or Moorcheh on-prem, install `uv` (which ships `uvx`):

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

See https://docs.astral.sh/uv/getting-started/installation/ for other install methods.

On the first call in local mode, the SDK:

1. Picks a free port and spawns `uvx memanto serve --port <port>`.
2. Polls `/health` until the server is ready.
3. Creates the agent (if `autoCreate` is enabled — default `true`) and activates a session.
4. Sends the request with the session token attached.

When `close()` is called (or the Node process exits), the server is sent `SIGTERM`.

### On-prem (no API key)

To run fully on-prem (no API key), configure it once with the CLI:

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
| `apiKey` | `string` | `MEMANTO_API_KEY` / `MOORCHEH_API_KEY` | Memanto Cloud API key (`mk_...`, recommended) or Moorcheh API key for local fallback. |
| `autoCreate` | `boolean` | `true` | Create the agent if it does not exist. |
| `baseUrl` | `string` | — | Override the Memanto Cloud API URL or use an already-running local server instead of spawning one. |
| `port` | `number` | auto | Bind the spawned local server to this port. |
| `host` | `string` | `127.0.0.1` | Bind host for the spawned local server. |
| `uvxPath` | `string` | `uvx` | Override the path to `uvx` (local mode). |
| `packageSpec` | `string` | `memanto` | Package spec passed to `uvx` (local mode). Use `memanto==0.2.3` to pin. |
| `healthTimeoutMs` | `number` | `60000` | Health-check timeout (local mode). |
| `verbose` | `boolean` | `false` | Stream local server logs to the parent process. |

When `apiKey` is set it is sent as `X-Api-Key` on every request. Memanto Cloud authenticates every call with `X-Api-Key`; a local server reachable beyond loopback requires it for agent management, activation, and session renewal while memory requests use the server-issued session token.

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
- `deleteAgent({ deleteMemories? })` — on Memanto local, memories are kept in Moorcheh unless `deleteMemories: true`. On Memanto Cloud, deleting an agent always deletes its memories.
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

## Framework Integrations

The SDK ships pre-built memory tools (`recallMemory`, `rememberMemory`, `answerMemory`) for these agent frameworks, each behind its own subpath import so unused framework code never enters your bundle:

| Framework | Import | Docs |
| --- | --- | --- |
| Vercel AI SDK | `@moorcheh-ai/memanto/ai-sdk` | [Vercel AI SDK](https://docs.memanto.ai/integrations/vercel-ai-sdk) |
| Composio | `@moorcheh-ai/memanto/composio` | [Composio](https://docs.memanto.ai/integrations/composio) |
| Eve | `@moorcheh-ai/memanto/eve` | [Eve](https://docs.memanto.ai/integrations/eve) |
| Mastra | `@moorcheh-ai/memanto/mastra` | [Mastra](https://docs.memanto.ai/integrations/mastra) |
| VoltAgent | `@moorcheh-ai/memanto/voltagent` | [VoltAgent](https://docs.memanto.ai/integrations/voltagent) |
| OpenAI Node SDK | `@moorcheh-ai/memanto/openai` | [OpenAI](https://docs.memanto.ai/integrations/openai) |

The eve adapter requires `eve >=1.0.0` and Node.js 24 or newer. `memantoMemory()` recalls on
`turn.started`, exposes scope-bound `remember` and `recall` tools, and
optionally captures on `turn.completed` (`capture: true`, off by default).

## Versioning

The npm package version tracks the matching PyPI release of `memanto`. To pin a specific server build, pass `packageSpec: "memanto==<version>"`.

## License

MIT
