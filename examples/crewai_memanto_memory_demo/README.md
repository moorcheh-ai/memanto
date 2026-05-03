# CrewAI + Memanto Agentic Memory Demo

This example demonstrates a CrewAI-style two-agent workflow where Memanto is the
durable memory layer:

- Session 1: a Research Agent stores findings, a user preference, and a task
  outcome in Memanto.
- Session 2: a Writer Agent starts later, receives no Python variables from
  Session 1, recalls the prior context through Memanto, and drafts from that
  recalled context.
- Contradiction test: an old tone preference is superseded by a corrected
  preference. The demo uses Memanto's real storage and current-only recall path.

The default path is deterministic and recording-friendly. It does not require an
LLM key. The optional `--use-real-crewai` path runs a real CrewAI kickoff after
Memanto recall and requires an LLM configuration such as `OPENAI_API_KEY`.

## Why Memanto Helps CrewAI

CrewAI's standard memory is useful during a crew run, but long-lived agent
workflows often need memory that survives process exits, separate sessions, and
handoffs between agents. Memanto gives the crew a persistent, searchable memory
namespace:

1. Before a task, call Memanto recall and hydrate the task context.
2. After a task, call Memanto remember and persist findings, preferences,
   decisions, and task outcomes.
3. For changed facts, store a corrected memory and prefer current-only recall.

## Setup

Requirements:

- Python 3.10 to 3.12
- A Moorcheh API key for Memanto storage and recall
- Optional: `OPENAI_API_KEY` for the LLM-backed CrewAI kickoff

From the repository root:

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e .
python -m pip install -r examples/crewai_memanto_memory_demo/requirements.txt
```

Set credentials in your shell. Do not commit `.env` or real keys.

PowerShell:

```powershell
$env:MOORCHEH_API_KEY="your-moorcheh-api-key"
$env:OPENAI_API_KEY="your-openai-api-key" # optional
```

macOS/Linux:

```bash
export MOORCHEH_API_KEY="your-moorcheh-api-key"
export OPENAI_API_KEY="your-openai-api-key" # optional
```

You can also copy `.env.example` to `.env` for local testing. Keep `.env`
untracked.

## Run Commands

Full deterministic demo:

```bash
python examples/crewai_memanto_memory_demo/crewai_memanto_memory_demo.py --phase full-demo --simulate-24h
```

Separate cross-session flow:

```bash
python examples/crewai_memanto_memory_demo/crewai_memanto_memory_demo.py --phase store
python examples/crewai_memanto_memory_demo/crewai_memanto_memory_demo.py --phase recall --simulate-24h
python examples/crewai_memanto_memory_demo/crewai_memanto_memory_demo.py --phase update
```

Use an isolated namespace while recording:

```bash
python examples/crewai_memanto_memory_demo/crewai_memanto_memory_demo.py --phase full-demo --namespace crewai-memanto-recording
```

Optional LLM-backed CrewAI kickoff:

```bash
python examples/crewai_memanto_memory_demo/crewai_memanto_memory_demo.py --phase recall --use-real-crewai
```

## Expected Output

The store phase prints lines like:

```text
[Session 1] Research Agent storing findings in Memanto
[Memanto] Stored memory: fact id=...
[Memanto] Stored memory: preference id=...
[Memanto] Stored memory: artifact id=...
```

The recall phase prints lines like:

```text
[Session 2] Writer Agent recalling Memanto memory (24 hours later)
[Boundary] No Session 1 Python variables are used in this phase.
[Memanto] Retrieved memories from durable storage:
[Writer Agent] Draft based only on recalled Memanto context:
```

If credentials are missing, the script exits cleanly with setup instructions
instead of a stack trace.

## Recording Visual Proof

Recommended Loom flow:

1. Open a terminal at the repository root.
2. Start a 30 to 60 second Loom recording.
3. Run:

```bash
python examples/crewai_memanto_memory_demo/crewai_memanto_memory_demo.py --phase store --namespace crewai-memanto-recording
python examples/crewai_memanto_memory_demo/crewai_memanto_memory_demo.py --phase recall --simulate-24h --namespace crewai-memanto-recording
python examples/crewai_memanto_memory_demo/crewai_memanto_memory_demo.py --phase update --namespace crewai-memanto-recording
```

Asciinema alternative:

```bash
asciinema rec crewai_memanto_demo.cast
python examples/crewai_memanto_memory_demo/crewai_memanto_memory_demo.py --phase store --namespace crewai-memanto-recording
python examples/crewai_memanto_memory_demo/crewai_memanto_memory_demo.py --phase recall --simulate-24h --namespace crewai-memanto-recording
python examples/crewai_memanto_memory_demo/crewai_memanto_memory_demo.py --phase update --namespace crewai-memanto-recording
exit
```

## Swapping CrewAI Memory For Memanto

Before, standard CrewAI memory is configured on the crew:

```python
from crewai import Crew, Process

crew = Crew(
    agents=[researcher, writer],
    tasks=[research_task, writing_task],
    process=Process.sequential,
    memory=True,
)
```

After, Memanto becomes the durable memory layer around each task:

```python
memory = MemantoCrewMemory(
    agent_id="crewai-production-memory",
    api_key=os.environ["MOORCHEH_API_KEY"],
)

recalled = memory.recall(
    "customer support automation research findings and preferences",
    memory_types=["fact", "preference", "artifact"],
)
context = "\n".join(item["content"] for item in recalled)

writing_task.description = (
    "Use this recalled Memanto context before drafting:\n"
    f"{context}\n\n"
    f"{writing_task.description}"
)

result = crew.kickoff()

memory.remember(
    MemoryPayload(
        title="Writer task outcome",
        content=f"Writer Agent completed the launch note: {result}",
        memory_type="artifact",
        tags=["writer", "task-outcome"],
        source="writer-agent",
    )
)
```

For changed facts, this demo stores a corrected memory with supersession
metadata and uses current-only recall. The high-level `memanto remember` command
does not expose every supersession field yet, so the example uses Memanto's real
`MemoryRecord` and `MemoryWriteService` for that small metadata step.

## Limitations

- `MOORCHEH_API_KEY` is required for real Memanto storage and recall.
- `OPENAI_API_KEY` is required only for `--use-real-crewai`.
- The deterministic mode proves the memory layer without paying for LLM calls.
- The example does not delete cloud memories. Use a unique `--namespace` for
  repeat recordings.
- Visual proof still needs to be recorded manually with Loom, Asciinema, or GIF
  tooling after credentials are configured.
- Local no-key validation covered `compileall`, `--help`, and graceful
  `MOORCHEH_API_KEY` setup failure. Credentialed store/recall/update phases must
  be run after configuring a real key.
