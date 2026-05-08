# CrewAI + Memanto durable memory example

This focused example shows two CrewAI-style agents using a small memory adapter:

- `dry-run` mode uses a local JSON file with the same high-level adapter methods.
  It is a deterministic proof of the workflow and is not Memanto-backed.
- `live` mode uses `MOORCHEH_API_KEY` and the existing Memanto client to persist
  memory in Moorcheh-backed Memanto storage.

The default path does not call a paid LLM. CrewAI LLM execution is opt-in with
`--enable-crewai-llm`.

## Files

- `crewai_memanto_memory_demo.py` - argparse CLI and memory adapters
- `requirements.txt` - example-only dependency for CrewAI
- `terminal-proof.txt` - terminal recording receipt and replay script with no secrets

## Visual Proof

Terminal recording: https://asciinema.org/a/WPJfJsQ6pqQlXyTX

The recording runs the live Memanto-backed demo without printing secrets. It
shows the Research Agent flow storing durable context, the Writer Agent flow
retrieving current memory in a later step, a newer concise-writing preference
superseding an older contradictory preference, and the final draft using the
retrieved memory.

## Setup

From the repository root:

```bash
python -m pip install -e .
python -m pip install -r examples/crewai_memanto_memory/requirements.txt
```

The script still runs the dry-run memory proof without CrewAI installed, but
installing the requirements lets it instantiate real CrewAI `Agent` objects.

## Dry-Run Proof

No API keys are required. The store below is under `/tmp` so it does not add
generated files to the repository.

```bash
rm -f /tmp/crewai_memanto_memory_demo.json
python examples/crewai_memanto_memory/crewai_memanto_memory_demo.py \
  --mode dry-run \
  --run 1 \
  --store /tmp/crewai_memanto_memory_demo.json

python examples/crewai_memanto_memory/crewai_memanto_memory_demo.py \
  --mode dry-run \
  --run 2 \
  --store /tmp/crewai_memanto_memory_demo.json
```

Expected behavior:

- Run 1 stores research findings, a user preference, a task outcome, and a newer
  corrected preference.
- The newer preference supersedes the older preference in the local JSON store.
- Run 2 starts separately, reads the JSON store, retrieves only current memory,
  and drafts with the newer concise-bullet preference.

You can also run both phases in one process:

```bash
python examples/crewai_memanto_memory/crewai_memanto_memory_demo.py \
  --mode dry-run \
  --run both
```

## Live Memanto Mode

Live mode is Memanto-backed and requires a Moorcheh API key:

```bash
export MOORCHEH_API_KEY="..."

python examples/crewai_memanto_memory/crewai_memanto_memory_demo.py \
  --mode live \
  --run both \
  --agent-id crewai-memanto-memory-demo
```

This creates or reuses the agent, activates a Memanto session, stores memories,
marks the older preference as superseded, and retrieves current memories.

## Optional CrewAI LLM Execution

By default, the example configures CrewAI agents but uses deterministic Python
steps for the demo flow. To let the Writer Agent call an LLM for the final
draft, set OpenAI-compatible environment variables and pass
`--enable-crewai-llm`.

DeepSeek example using OpenAI-compatible settings:

```bash
export MOORCHEH_API_KEY="..."
export DEEPSEEK_API_KEY="..."
export OPENAI_BASE_URL="https://api.deepseek.com"
export OPENAI_MODEL_NAME="deepseek-chat"

python examples/crewai_memanto_memory/crewai_memanto_memory_demo.py \
  --mode live \
  --run both \
  --enable-crewai-llm
```

You can also use OpenAI-compatible variables directly:

```bash
export OPENAI_API_KEY="..."
export OPENAI_BASE_URL="https://api.openai.com/v1"
export OPENAI_MODEL_NAME="gpt-4o-mini"
```

Do not put keys in code, command transcripts, or committed files.

## How Memanto augments CrewAI memory

CrewAI can keep useful context during an agent or crew execution, but durable
product workflows also need memory that survives process boundaries. Memanto
adds that layer by giving each stable agent identity a persistent memory
namespace. A research agent can store facts, preferences, and outcomes during
one execution; a later writer agent can retrieve the current, non-superseded
state before drafting.

In this example, the local JSON adapter proves the control flow. The live
adapter uses Memanto as the durable memory layer.
