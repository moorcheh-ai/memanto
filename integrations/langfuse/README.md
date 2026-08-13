# langfuse-memanto

Turn Langfuse observability signal into [Memanto](https://www.memanto.ai) memories, live from your application.

Langfuse records *what went wrong*. Memanto remembers *the lesson*. This package connects them: failing spans become durable memories your agents can recall, instead of being re-learned on every run.

## Install

```bash
pip install langfuse-memanto
```

That's the only install. `memanto` comes with it, and **there is no server to run** — memories go straight to the Memanto cloud API from your process.

## Quick start — from nothing

You need one thing: a Memanto API key from [memanto.ai](https://www.memanto.ai).

```bash
export MOORCHEH_API_KEY="your-key"
```

Then two lines in your app:

```python
from langfuse import Langfuse
from langfuse_memanto import attach

Langfuse()                      # your existing setup
attach(agent_id="my-agent")     # start capturing
```

That's the whole setup. No CLI, no config file, no decorators to add, no call sites to change. The agent is created and activated automatically on the first write, and every span your app already sends to Langfuse is now also inspected for failures.

## Configuring capture in code

Anything you'd set with the CLI can be passed to `attach()` instead:

```python
attach(
    agent_id="my-agent",
    capture=["errors", "slow", "costly"],
    latency_ms=5000,            # slower than 5s is an anomaly
    cost_usd=0.10,              # pricier than 10c is an anomaly
    group_by="metadata.error_code",   # if your messages group poorly
)
```

Bad settings fail loudly at `attach()` rather than silently capturing nothing.

Omit a setting and it falls back to the shared profile in `~/.memanto/migrate/langfuse/config.json` — so a team can manage capture rules centrally with `memanto migrate langfuse --save` and individual services need only `attach(agent_id=...)`. Use whichever fits; they compose.

To see what's actually in your Langfuse project before choosing thresholds:

```bash
memanto migrate langfuse --discover     # scores, latency spread, error labels
```

```python
@observe()
def generate(prompt):
    raise ValueError("Model returned malformed output")
```

produces a memory:

```
Model returned malformed output in generate                     [error]
Langfuse recorded 12 failing 'generate' observations:
Model returned malformed output.
Seen 12x between 2026-08-06T18:28:52Z and 2026-08-06T18:31:38Z.
tags: langfuse, capture=errors, sig=c8b2fd9e4d19, op=generate
```

## How it works

Langfuse's Python SDK is built on OpenTelemetry and attaches its own span processor to the global `TracerProvider`. This package attaches a **second** one, so it sees the same spans without calling the Langfuse API at all.

```
your app  ──▶  Langfuse SDK  ──▶  OTel TracerProvider  ──┬──▶  LangfuseSpanProcessor  ──▶  Langfuse
                                                         └──▶  MemantoLangfuseHandler ──▶  Memanto
```

**One memory per signature, not per occurrence.** A thousand identical failures become a single memory whose confidence reflects how often it happened — the same grouping `memanto migrate langfuse` performs, sharing the same code, so both paths write identical content.

**Nothing runs on your hot path.** `on_end` maps the span and appends it to a buffer; grouping and network I/O happen on a daemon thread. Every entry point swallows its own exceptions — a memory that fails to write will never break your application.

**No duplicates with the CLI sync.** Writes are recorded in the same ledger (`~/.memanto/migrate/langfuse/state.json`) under the same `project::agent` scope, so a later `memanto migrate langfuse` sees them as already written.

## What can and cannot be captured live

| Mode | Live | Why |
|---|---|---|
| `errors` | ✅ | The span carries its own level and status message |
| `slow` | ✅ with an absolute `latency_ms` | Timing is on the span; percentile budgets need a population to calibrate against |
| `costly` | ⚠️ only if your app sets `cost_details` | Langfuse otherwise computes cost **server-side after ingestion**, where a span processor cannot see it |
| `low-score` | ❌ | Langfuse scores are attached *after* a trace ends |
| `success` | ❌ | Same |

Anything marked ❌ or ⚠️ is still captured by `memanto migrate langfuse`, which reads the enriched data back from the Langfuse API. The two paths share a ledger, so running both is safe.

The handler logs a warning at startup for any configured mode it cannot honour. For score-driven capture, run `memanto migrate langfuse` periodically — it and the live handler share a ledger, so they compose safely.

## Configuration

Capture rules can come from `attach()` (above) or from `~/.memanto/migrate/langfuse/config.json`, written by `memanto migrate langfuse --save` or the UI tile. Code wins where both are set.

Runtime settings are read from the environment:

| Variable | Required | Default | Description |
|---|---|---|---|
| `MOORCHEH_API_KEY` | Yes | — | Memanto API key. Never logged. |
| `MEMANTO_LANGFUSE_AGENT_ID` | Yes* | — | Agent that receives the memories. *Or pass `agent_id=`. |
| `MEMANTO_LANGFUSE_PROJECT` | No | `default` | Which stored capture profile to use |
| `MEMANTO_LANGFUSE_FLUSH_INTERVAL` | No | `30` | Seconds between background flushes |
| `MEMANTO_LANGFUSE_MAX_BUFFER` | No | `100` | Flush early at this many pending spans |
| `MEMANTO_LANGFUSE_MAX_CACHE` | No | `2000` | Bound on in-process signature memory |
| `MEMANTO_LANGFUSE_AUTO_CREATE_AGENT` | No | `true` | Create + activate the agent on first write |
| `MEMANTO_LANGFUSE_SESSION_HOURS` | No | `24` | Lifetime of the session the handler opens |

Set `auto_create_agent=False` if agents are provisioned by your platform team and an app should fail rather than create one.

For more control:

```python
from langfuse_memanto import MemantoLangfuseHandler

handler = MemantoLangfuseHandler(agent_id="my-agent", host="https://us.cloud.langfuse.com")
handler.attach()
...
handler.flush()           # write immediately
handler.stats()           # {'captured': 12, 'written': 2, 'dropped': 0, 'pending': 0}
handler.shutdown()        # flush and stop (also runs at exit)
```

## Troubleshooting

**No memories appear.** Check `handler.stats()`. `captured: 0` means no span matched your capture settings — confirm with `memanto migrate langfuse --discover`. `captured > 0, written: 0` means the flush failed; enable logging:

```python
import logging; logging.getLogger("langfuse_memanto").setLevel(logging.DEBUG)
```

**`attach()` raises about the TracerProvider.** Call it *after* `Langfuse()`. Before that, OpenTelemetry has only a `ProxyTracerProvider`, which cannot take a processor.

**Langfuse Cloud US.** Keys are region-scoped. Pass `host="https://us.cloud.langfuse.com"` and set `LANGFUSE_HOST` for the CLI.

**Memories stop appearing after a while.** A bounded buffer drops spans during a storm; `stats()["dropped"]` counts them. Lower `MEMANTO_LANGFUSE_FLUSH_INTERVAL` or raise `MEMANTO_LANGFUSE_MAX_BUFFER`.

## Requirements

- Python 3.10+
- `langfuse>=3` in your application (this package does not depend on it — it only needs the OpenTelemetry SDK that Langfuse brings)
- A Memanto API key and an activated agent

## License

MIT

## Links

- [Memanto](https://www.memanto.ai) · [Docs](https://docs.memanto.ai) · [GitHub](https://github.com/moorcheh-ai/memanto)
- [Langfuse](https://langfuse.com)
