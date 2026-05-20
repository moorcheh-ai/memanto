# Claude Code Skills + Memanto Memory Bridge

This example adds a memory layer for command-style developer skills such as
`/grill-with-docs`, `/tdd`, and `/handoff`.

The bridge gives each skill two hooks:

- `pre-skill`: recall relevant engineering memories before a skill starts
- `post-skill`: distill durable decisions from the completed skill run

It runs without credentials in local preview mode, and can use the real Memanto
Python SDK or CLI when a reviewer has a Moorcheh API key configured.

## Why This Helps

Developer skills are useful because they are focused, but that focus also
fragments context. An architecture decision made during `/grill-with-docs` is
usually invisible when `/tdd` runs later in a fresh terminal.

This bridge stores compact engineering memories after each skill:

- architectural decisions
- local coding rules
- codebase ownership boundaries
- repeated failure modes
- file and module context

Later skills receive only the relevant recalled constraints, keeping prompt
injection concise instead of replaying full transcripts.

## Quick Start

Run the credential-free demo:

```bash
python skill_memory.py demo
```

Run validation:

```bash
python validate.py
python -m unittest test_skill_memory.py
python productivity_benchmark.py
```

Generate wrappers for mattpocock-style skills:

```bash
python mattpocock_adapter.py --output-dir .memanto-skill-memory/bin --target-command claude
```

This creates executable wrappers for:

- `grill-with-docs-with-memanto`
- `tdd-with-memanto`
- `handoff-with-memanto`

Each wrapper recalls context before running the target command, captures the
command output, and stores distilled memories afterward. The generator also
copies the helper script into the wrapper directory, so the wrappers remain
executable when they are placed on `PATH`.

Wrappers print the recalled context for transparency and export the same block
as `MEMANTO_SKILL_CONTEXT`, letting child processes consume the prompt-ready
constraints directly instead of scraping terminal output.

Set `SKILL_MEMORY_FILES` to a space-separated list of touched files when the
caller has that context. The wrappers pass those paths into both recall and
storage so later skills can retrieve decisions by file or module.

## Live Memanto Mode

Install and configure Memanto:

```bash
pip install memanto
memanto
```

The preferred live path uses the package's `SdkClient` directly:

```bash
export SKILL_MEMORY_BACKEND=memanto-sdk
export MEMANTO_AGENT_ID=claudecode-skills
```

In SDK mode, `post-skill` calls:

```python
SdkClient.remember(
    agent_id=MEMANTO_AGENT_ID,
    memory_type="<typed memory>",
    content="<distilled engineering memory>",
)
```

and `pre-skill` calls:

```python
SdkClient.recall(agent_id=MEMANTO_AGENT_ID, query="<skill task and file context>")
SdkClient.answer(
    agent_id=MEMANTO_AGENT_ID,
    question="Which recalled engineering constraints should be injected here?",
)
```

The `answer` step asks Memanto's retrieval-backed LLM layer to synthesize the
recalled memories into a short prompt-ready constraint block, so later skills
receive useful context without replaying full transcripts.

There is also a CLI fallback:

```bash
export SKILL_MEMORY_BACKEND=memanto-cli
```

In CLI mode, `post-skill` shells out to:

```bash
memanto remember "<distilled engineering memory>" --type <memory_type>
```

No API keys are committed or required for local validation.

## Manual Hook Usage

Before a skill:

```bash
python skill_memory.py pre-skill \
  --skill /tdd \
  --task "Add tests for auth dependency behavior" \
  --cwd services/api \
  --files services/api/auth.py services/api/dependencies.py
```

After a skill, write a run JSON:

```json
{
  "skill": "/grill-with-docs",
  "task": "Review the auth refactor plan for a FastAPI service.",
  "cwd": "services/api",
  "files": ["services/api/auth.py", "services/api/dependencies.py"],
  "output": "Decision: keep authentication middleware stateless..."
}
```

Then store memories:

```bash
python skill_memory.py post-skill --run-json run.json
```

## Files

- `skill_memory.py`: extraction, local backend, optional Memanto CLI backend,
  `pre-skill`, `post-skill`, and demo commands
- `mattpocock_adapter.py`: wrapper generator for slash-command style skills
- `validate.py`: no-credential validation script, including generated wrapper
  execution
- `test_skill_memory.py`: focused unit tests
- `productivity_benchmark.py`: three-session benchmark showing repeated
  instruction reduction across `/grill-with-docs`, `/tdd`, and `/handoff`
- `demo_transcript.md`: reviewable proof of cross-skill recall

## Review Notes

The local backend is intentionally simple and deterministic so reviewers can
inspect the lifecycle without provisioning a Moorcheh key. The live backend is
kept behind `SKILL_MEMORY_BACKEND=memanto-sdk`, so the same example can be used
with real Memanto memory once credentials are configured.
