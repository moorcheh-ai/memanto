# Claude Code Skills + Memanto

This example shows how Memanto can act as a persistent engineering memory layer for command-oriented skill workflows such as `mattpocock/skills`.

The hook has two phases:

- `pre`: recall relevant engineering decisions before a skill starts and print a compact context block that can be appended to the skill prompt.
- `post`: read the completed skill transcript, use Memanto's backend LLM to distill durable engineering context when the SDK backend is active, and store typed memories back into Memanto. Local review falls back to deterministic structured extraction.

## Setup

```bash
pip install memanto
memanto agent create claude-code-skills
```

The active Memanto agent is used by the hook. A Moorcheh API key must already be configured through `memanto` setup.

For production wiring, use the SDK backend so the hook talks to Memanto through the in-process Python client:

```bash
export MEMANTO_SKILLS_BACKEND=memanto-sdk
export MEMANTO_AGENT_ID=claude-code-skills
```

If `MEMANTO_AGENT_ID` is omitted, the hook uses the active agent from the local Memanto CLI configuration. The `memanto-cli` backend remains available for environments that prefer shelling out to the installed CLI.

In SDK mode, the `post` hook asks Memanto to extract durable `decision`, `preference`, `instruction`, and `context` memories from the skill transcript before calling `remember`. If the SDK cannot provide an answer, the hook falls back to the local structured extractor used by the credential-free preview.

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

## Productivity Benchmark

The bounty's core metric is fewer repeated instructions across `/grill-with-docs`, `/tdd`, and `/handoff`. `productivity_benchmark.py` runs a deterministic local scenario where the first skill stores auth-session decisions and later skills retrieve them instead of requiring the developer to repeat the same constraints.

```bash
python examples/claudecode-skills-memanto/productivity_benchmark.py
```

Expected output:

```text
skill_runs=3
stored_memories=6
baseline_repeated_prompts=2
memanto_reused_prompts=2
repeated_instruction_reduction=100%
```

## Wrapper Usage

`run_skill_with_memory.py` demonstrates a lightweight wrapper around any command:

```bash
python examples/claudecode-skills-memanto/run_skill_with_memory.py \
  --skill grill-with-docs \
  --task "Review the auth middleware for stale-token behavior" \
  --file src/auth/middleware.ts \
  -- python -m pytest tests/test_auth.py
```

The wrapper uses the same backend selector as the direct hook:

```bash
python examples/claudecode-skills-memanto/run_skill_with_memory.py \
  --backend local-jsonl \
  --store .memanto-skills-preview.jsonl \
  --skill tdd \
  --task "Add retry-policy tests" \
  -- python -m pytest tests/test_retries.py
```

When recalled memory exists, the wrapper prints the prompt block and also sets `MEMANTO_SKILL_CONTEXT` for the child command. Skill runners can either append the printed block to the prompt or read the environment variable before invoking their model/tool flow. After the command exits, stdout and stderr are summarized through the `post` memory path.

## mattpocock/skills Adapter

`mattpocock_adapter.py` prints a small JSON command contract for the named skills in the bounty: `/grill-with-docs`, `/tdd`, and `/handoff`.

```bash
python examples/claudecode-skills-memanto/mattpocock_adapter.py handoff \
  --task "Prepare the billing retry handoff" \
  --file src/billing/retries.ts
```

The emitted `pre_hook` recalls relevant engineering memory before the skill starts. The emitted `post_hook` stores the completed skill transcript afterward, so a later skill can reuse the same architectural decisions.

To write copyable Claude Code command wrappers for every supported skill:

```bash
python examples/claudecode-skills-memanto/mattpocock_adapter.py install \
  --output-dir .claude/commands \
  --task "Use Memanto memory around this skill run" \
  --backend memanto-sdk
```

This creates `grill-with-docs.md`, `tdd.md`, and `handoff.md` wrapper files. Each wrapper tells the runner to execute the Memanto `pre` hook before the skill and the `post` hook after the transcript is available.

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
- Memanto SDK-distilled memories from the completed transcript when `MEMANTO_SKILLS_BACKEND=memanto-sdk`,
- structured transcript findings such as `Decision:`, `Preference:`, `Must:`,
  `Never:`, `Quirk:`, `Caveat:`, and `Trade-off:` lines when present,
- a fallback transcript summary when no structured finding is present,
- tags for `claude-code-skills`, the skill name, and touched files.

This lets a later `/tdd`, `/handoff`, or `/grill-with-docs` invocation retrieve project-specific decisions without the developer repeating architectural constraints.

## Offline Testability

The hook depends on a small `MemoryBackend` protocol. Tests use an in-memory fake backend, so the example can be reviewed and verified without a Moorcheh API key or network access.

See `demo-transcript.md` for a concrete before/after run that stores a skill decision and injects it into a later skill prompt.
