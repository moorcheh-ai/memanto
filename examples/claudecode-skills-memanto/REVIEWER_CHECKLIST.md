# Reviewer Checklist

This checklist maps the bounty requirements to the files and commands in this
example so reviewers can validate the submission quickly.

## Bounty Criteria Mapping

| Requirement | Where to review |
| --- | --- |
| Global memory hook for Claude Code / mattpocock-style skills | `skill_memory.py` implements `pre-skill` and `post-skill`; `mattpocock_adapter.py` generates executable wrappers. |
| Active extraction of useful engineering context | `extract_memories()` classifies decisions, instructions, preferences, context, learning, and errors with typed confidence scores. |
| Dynamic context injection before later skill runs | `pre_skill()` recalls relevant memories and `render_injected_context()` formats prompt-ready constraints. Generated wrappers also export `MEMANTO_SKILL_CONTEXT`. |
| Works without private credentials | Local JSON mode is the default and is exercised by `validate.py`, `test_skill_memory.py`, and `productivity_benchmark.py`. |
| Optional live Memanto backend | `MemantoSdkBackend` uses `SdkClient.recall`, `SdkClient.remember`, and `SdkClient.answer`; `MemantoCliBackend` provides a CLI fallback. |
| mattpocock skills compatibility | `mattpocock_adapter.py --skills-dir ...` discovers every `SKILL.md` in a real skills checkout and generates wrappers. |
| Visual proof / showcase artifact | `demo_terminal.svg`, `demo_transcript.md`, `benchmark_report.md`, and `SOCIAL_SHOWCASE.md`. |

## Credential-Free Verification

Run from the repository root:

```bash
python examples/claudecode-skills-memanto/validate.py
python -m unittest examples/claudecode-skills-memanto/test_skill_memory.py
python examples/claudecode-skills-memanto/productivity_benchmark.py
uvx ruff check examples/claudecode-skills-memanto
uvx ruff format --check examples/claudecode-skills-memanto
git diff --check
```

Expected high-level result:

- validation passes without a Moorcheh API key
- 19 unit tests pass
- benchmark reports 100 percent repeated-instruction reduction
- lint, format, and whitespace checks are clean

## Live Memanto Smoke Path

For reviewers with Memanto configured:

```bash
export SKILL_MEMORY_BACKEND=memanto-sdk
export MEMANTO_AGENT_ID=claudecode-skills
python examples/claudecode-skills-memanto/skill_memory.py pre-skill \
  --skill /tdd \
  --task "Add tests for auth dependency behavior" \
  --cwd services/api \
  --files services/api/auth.py services/api/dependencies.py
```

The SDK backend recalls stored memories, asks Memanto to synthesize concise
constraints with `SdkClient.answer`, and prints context suitable for injection
into the next skill run.

## Wrapper Generation Smoke Path

```bash
python examples/claudecode-skills-memanto/mattpocock_adapter.py \
  --output-dir .memanto-skill-memory/bin \
  --target-command claude
```

This creates:

- `grill-with-docs-with-memanto`
- `tdd-with-memanto`
- `handoff-with-memanto`

Each wrapper:

- recalls Memanto context before invoking the target command
- exports the recalled block as `MEMANTO_SKILL_CONTEXT`
- captures command output
- stores distilled memories after the command completes
- preserves the target command exit status
