# Claude Code Skills + Memanto

This example shows how to use Memanto as a shared engineering memory layer across Claude Code skill runs. It is built for workflows such as `/grill-with-docs`, `/tdd`, `/handoff`, and custom project skills where the same architectural decisions and project preferences need to survive across separate sessions.

The bridge has two jobs:

1. Before a skill starts, recall relevant project memories and print a compact context block that can be injected into the prompt.
2. After a skill finishes, extract durable engineering facts from the request and result, then store them for future skill runs.

The example works in two modes:

- Local mode: deterministic JSON storage for validation, demos, and CI.
- Live mode: optional Memanto/Moorcheh storage when `MOORCHEH_API_KEY` is present.

## Why this solves the bounty

The common failure mode in skill-based workflows is context fragmentation. A review skill may discover that a service must stay within the free tier, but a later implementation skill does not know that. This bridge preserves those decisions as reusable memory.

It is intentionally small:

- No changes to the main Memanto package are required.
- The hook accepts JSON from stdin, so it can be wired into Claude Code hooks, shell wrappers, or other skill runners.
- The recall step uses a strict character budget so the injected memory block stays concise.
- The write step only stores durable engineering guidance, not raw transcripts or secrets.

## Files

```text
examples/claudecode-skills-memanto/
├── README.md
├── .env.example
├── settings.example.json
├── validate_offline.py
├── skill_memory_bridge/
│   ├── __init__.py
│   ├── bridge.py
│   └── cli.py
└── tests/
    └── test_bridge.py
```

## Quick validation

Run the offline proof from the repository root:

```bash
python examples/claudecode-skills-memanto/validate_offline.py
```

Expected output:

```text
offline validation passed
```

Run the focused tests:

```bash
python -m pytest examples/claudecode-skills-memanto/tests -q
```

## Claude Code hook setup

Copy the example settings into your Claude Code settings file, then adjust paths for your machine:

```bash
cp examples/claudecode-skills-memanto/settings.example.json ~/.claude/settings.json
```

The important parts are:

- `UserPromptSubmit` calls `cli.py pre` and injects recalled memory.
- `Stop` calls `cli.py post` and stores durable decisions from the completed run.

The hook reads JSON from stdin. If your runner uses a different event shape, keep the same fields when possible:

```json
{
  "skill": "/tdd",
  "project": "billing-api",
  "file_path": "src/billing/routes.py",
  "input": "Add invoice retry tests.",
  "output": "Implemented tests. Keep Stripe calls mocked in unit tests."
}
```

## Live Memanto mode

Local mode is the default. To use the Memanto backend, create a free Moorcheh API key and set:

```bash
export MOORCHEH_API_KEY="..."
export MEMANTO_SKILLS_AGENT_ID="claude-skills-memory"
export MEMANTO_SKILLS_BACKEND="memanto"
```

When live mode is enabled, the bridge stores memories through the Memanto Python package. If the live backend is unavailable, the CLI exits with a clear error instead of silently dropping memory.

## Demo transcript

First skill run stores architectural guidance:

```bash
printf '%s' '{
  "skill": "/grill-with-docs",
  "project": "support-api",
  "file_path": "src/support/router.py",
  "input": "Review the API design.",
  "output": "Decision: keep FastAPI endpoints async. Preference: do not add paid services. Constraint: redact customer emails in logs."
}' | python examples/claudecode-skills-memanto/skill_memory_bridge/cli.py post
```

Later, a different skill receives the relevant context:

```bash
printf '%s' '{
  "skill": "/tdd",
  "project": "support-api",
  "file_path": "src/support/tests/test_router.py",
  "input": "Write tests for the support ticket route."
}' | python examples/claudecode-skills-memanto/skill_memory_bridge/cli.py pre
```

Example injected block:

```text
<memanto_memory_context>
- Keep FastAPI endpoints async.
- Do not add paid services.
- Redact customer emails in logs.
</memanto_memory_context>
```

## Safety behavior

The extractor is conservative by design. It stores lines that look like durable decisions, preferences, constraints, or project facts. It skips secrets, tokens, passwords, and raw low-signal transcript text. This keeps the memory layer useful without turning it into an unsafe session recorder.
