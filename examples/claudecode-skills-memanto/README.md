# Claude Code Skills + Memanto

This example shows how Memanto can act as a persistent engineering memory layer for command-oriented skill workflows such as `mattpocock/skills`.

The hook has two phases:

- `pre`: recall relevant engineering decisions before a skill starts and print a compact context block that can be appended to the skill prompt.
- `post`: read the completed skill transcript, distill durable engineering context, and store it in Memanto as typed `decision` memory.

## Setup

```bash
pip install memanto
memanto agent create claude-code-skills
```

The active Memanto agent is used by the hook. A Moorcheh API key must already be configured through `memanto` setup.

## Direct Hook Usage

Before running a skill:

```bash
python examples/claudecode-skills-memanto/memanto_skills_hook.py pre \
  --skill tdd \
  --task "Add the invoice retry policy" \
  --file src/billing/retries.ts
```

After running a skill:

```bash
python examples/claudecode-skills-memanto/memanto_skills_hook.py post \
  --skill tdd \
  --task "Add the invoice retry policy" \
  --file src/billing/retries.ts \
  --transcript-file /tmp/skill-transcript.txt
```

## Credential-Free Preview

Reviewers can validate the lifecycle without a Moorcheh API key by using the local JSONL backend:

```bash
python examples/claudecode-skills-memanto/validate.py
```

The preview backend is intentionally small and file-based. It is not a replacement for Memanto; it exists so reviewers can inspect the skill lifecycle before wiring real credentials.

## Wrapper Usage

`run_skill_with_memory.py` demonstrates a lightweight wrapper around any command:

```bash
python examples/claudecode-skills-memanto/run_skill_with_memory.py \
  --skill grill-with-docs \
  --task "Review the auth middleware for stale-token behavior" \
  --file src/auth/middleware.ts \
  -- python -m pytest tests/test_auth.py
```

In a real Claude Code skill runner, wire the `pre` output into the generated prompt and pipe the skill transcript to `post` when the command finishes.

## mattpocock/skills Adapter

`mattpocock_adapter.py` prints a small JSON command contract for the named skills in the bounty: `/grill-with-docs`, `/tdd`, and `/handoff`.

```bash
python examples/claudecode-skills-memanto/mattpocock_adapter.py handoff \
  --task "Prepare the billing retry handoff" \
  --file src/billing/retries.ts
```

The emitted `pre_hook` recalls relevant engineering memory before the skill starts. The emitted `post_hook` stores the completed skill transcript afterward, so a later skill can reuse the same architectural decisions.

## Global Hook Manifest

`claude-code-hooks.example.json` is a copyable hook manifest for runners that prefer static configuration over generating specs at runtime. Each supported skill has:

- `memory.before`: runs `memanto_skills_hook.py pre` and injects recalled decisions into the prompt.
- `memory.after`: runs `memanto_skills_hook.py post` with `$TRANSCRIPT_FILE` after the skill completes.

The placeholders `$SKILL_TASK` and `$TRANSCRIPT_FILE` are intentionally runner-provided so the same manifest can be used by different Claude Code skill wrappers.

## What Gets Remembered

The stored memory includes:

- the skill name,
- the task,
- files in scope,
- the transcript summary,
- tags for `claude-code-skills`, the skill name, and touched files.

This lets a later `/tdd`, `/handoff`, or `/grill-with-docs` invocation retrieve project-specific decisions without the developer repeating architectural constraints.

## Offline Testability

The hook depends on a small `MemoryBackend` protocol. Tests use an in-memory fake backend, so the example can be reviewed and verified without a Moorcheh API key or network access.

See `demo-transcript.md` for a concrete before/after run that stores a skill decision and injects it into a later skill prompt.
