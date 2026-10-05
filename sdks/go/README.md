# Memanto Go SDK

Go client for [Memanto](https://github.com/moorcheh-ai/memanto) — memory that AI agents love.

The client talks to a Memanto REST server. Point it at one you run (`BaseURL`), or leave `BaseURL` empty and it starts `uvx memanto serve` on first use, like the TypeScript SDK.

## Install

```bash
go get github.com/moorcheh-ai/memanto/sdks/go
```

Requires Go 1.24+. To let the client start the server itself, install [uv](https://docs.astral.sh/uv/getting-started/installation/) (it ships `uvx`):

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## Quick start

```go
package main

import (
	"context"
	"fmt"
	"log"
	"os"

	memanto "github.com/moorcheh-ai/memanto/sdks/go"
)

func main() {
	ctx := context.Background()
	client, err := memanto.New(memanto.Options{
		AgentID: "my-agent",
		APIKey:  os.Getenv("MOORCHEH_API_KEY"),
	})
	if err != nil {
		log.Fatal(err)
	}
	defer client.Close() // stops the server the client started

	if _, err := client.Remember(ctx, memanto.RememberInput{
		Content: "Alex prefers oat milk.",
		Type:    "preference",
	}); err != nil {
		log.Fatal(err)
	}

	recalled, err := client.Recall(ctx, memanto.RecallInput{Query: "what does Alex drink?"})
	if err != nil {
		log.Fatal(err)
	}
	for _, m := range recalled.Memories {
		if m.Content != nil { // optional fields in api types are pointers
			fmt.Println(*m.Content)
		}
	}

	answer, err := client.Answer(ctx, memanto.AnswerInput{Question: "Does Alex drink dairy?"})
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println(answer.Answer)
}
```

New writes take about a second to become searchable, so a `Recall` right after a `Remember` may not return the new memory yet.

On the first call the client:

1. Starts the server, unless `BaseURL` is set: picks a free port, runs `uvx memanto serve --host 127.0.0.1 --port <port>`, and waits for `/health`.
2. Creates the agent if it does not exist (unless `DisableAutoCreate` is set).
3. Activates a session and sends its token with each memory call. If the server rejects the token, the client activates a new session and retries once.

`Close` stops a server the client started. Go has no exit hooks, so always call it (`defer client.Close()`); otherwise the server keeps running after your program exits.

Memanto allows one active session per agent: activating from this client signs out other clients (the CLI, MCP, another process) using the same agent, and the other way round.

### Use a running server

```go
client, err := memanto.New(memanto.Options{
	AgentID: "my-agent",
	BaseURL: "http://127.0.0.1:8000", // started with `memanto serve`
	APIKey:  os.Getenv("MOORCHEH_API_KEY"),
})
```

`APIKey` is sent as `X-Api-Key` on every request. A server reachable beyond loopback requires it for agent management and session activation.

## Options

| Field | Default | Description |
| --- | --- | --- |
| `AgentID` | — | **Required.** The agent this client works with. |
| `DisableAutoCreate` | `false` | Do not create the agent when it is missing. |
| `BaseURL` | — | A running server. When empty, the client starts one with `uvx`. |
| `APIKey` | — | Moorcheh API key. Passed to a started server as `MOORCHEH_API_KEY` and sent as `X-Api-Key`. |
| `HTTPClient` | `http.DefaultClient` | HTTP client for all requests. |
| `Host` | `127.0.0.1` | Bind host of a started server. |
| `Port` | free port | Port of a started server. |
| `UvxPath` | `uvx` | Path to `uvx`. |
| `PackageSpec` | `memanto` | Package passed to `uvx`. Use `memanto==0.2.3` to pin. |
| `HealthTimeout` | `60s` | How long to wait for a started server to become healthy. |
| `Verbose` | `false` | Stream a started server's logs to stdout/stderr. |

For on-prem, configure Memanto once with `uvx memanto` and pick the on-prem backend; a started server inherits that config from `~/.memanto/`, so no `APIKey` is needed.

## Methods

Every method takes a `context.Context` first. Typed responses come from the generated package [`github.com/moorcheh-ai/memanto/sdks/go/api`](api); endpoints without a response schema return `map[string]any`.

**Memory writes**

- `Remember(ctx, RememberInput)` — `Confidence` defaults to 0.8, `Source` to `agent`, `Provenance` to `explicit_statement`.
- `BatchRemember(ctx, []RememberInput)` — up to 100 items.
- `ExtractMemories(ctx, ExtractMemoriesInput)` — extract memories from chat turns; `DryRun` previews without writing.
- `UploadFile(ctx, UploadFileInput)` — `.pdf`, `.docx`, `.xlsx`, `.json`, `.txt`, `.csv` or `.md`.
- `DeleteMemory(ctx, memoryID)`

**Memory reads**

- `Recall(ctx, RecallInput)` — `Tags` returns only memories carrying all of them.
- `RecallAsOf(ctx, RecallAsOfInput)` — memories as of a date (`YYYY-MM-DD` or ISO 8601).
- `RecallChangedSince(ctx, RecallChangedSinceInput)`
- `RecallRecent(ctx, RecallRecentInput)` — newest first.
- `Answer(ctx, AnswerInput)`

Optional numbers where zero is meaningful (`RecallInput.MinSimilarity`, `AnswerInput.Threshold`, `AnswerInput.Temperature`) are pointers; use `memanto.Ptr(0.0)`. Leave them nil for the server default.

**Analysis**

- `DailySummary(ctx, DailySummaryInput)`
- `GenerateConflicts(ctx, ConflictDateInput)`, `ListConflicts(ctx, ConflictDateInput)`
- `ResolveConflict(ctx, ResolveConflictInput)` — `Action` is `keep_old`, `keep_new`, `keep_both`, `remove_both` or `manual`.

**Agent and session**

- `ListAgents(ctx)`, `GetAgent(ctx)`
- `CreateAgent(ctx, CreateAgentInput)` — only needed with `DisableAutoCreate`.
- `DeleteAgent(ctx, DeleteAgentInput)` — memories stay in Moorcheh unless `DeleteMemories` is true.
- `Deactivate(ctx)` — end the session; the next call activates a new one.
- `Status(ctx)` — the server's active session.
- `Close()`

## Errors

A non-2xx response returns `*memanto.APIError` with `StatusCode` and the server's message in `Detail`:

```go
var apiErr *memanto.APIError
if errors.As(err, &apiErr) && apiErr.StatusCode == http.StatusNotFound {
	// ...
}
```

## Development

The `api` package is generated with [oapi-codegen](https://github.com/oapi-codegen/oapi-codegen) from `sdks/typescript/openapi.json`, the spec shared with the TypeScript SDK (Web UI routes excluded). After the spec changes:

```bash
cd sdks/go
go generate ./...
go test ./...
```

## License

MIT
