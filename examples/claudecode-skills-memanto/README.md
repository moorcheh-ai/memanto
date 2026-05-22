# Claude Code Skills Memanto Bridge

This example shows how to give `mattpocock/skills`-style commands a shared
engineering memory. It records decisions after one skill run and injects the
relevant ones before the next run, so `/grill-with-docs`, `/tdd`, and
`/handoff` do not need the same project rules repeated in every terminal
session.

The default backend is a local JSONL store, which makes the demo runnable by
maintainers without credentials. Set `MEMANTO_SKILLS_BACKEND=sdk` after
configuring the `memanto` CLI to use the live Memanto SDK backend, or
`MEMANTO_SKILLS_BACKEND=cli` to shell out through existing CLI commands.

## Quick Start

```bash
cd examples/claudecode-skills-memanto
python validate.py
python -m pytest test_skill_memory_bridge.py
```

Run the offline demo:

```bash
python skill_memory_bridge.py run-skill \
  --skill grill-with-docs \
  --task "Review the checkout flow" \
  --cwd demo-shop \
  --output "Decision: use server actions for checkout mutations. Preference: keep forms accessible."

python skill_memory_bridge.py inject \
  --skill tdd \
  --task "Add checkout tests" \
  --cwd demo-shop
```

The second command prints a concise `MEMANTO_SKILL_CONTEXT` block containing
the architecture decision and preference learned from the first run.

Generate a Claude Code hook snippet:

```bash
python skill_memory_bridge.py write-claude-settings --out claude-settings.snippet.json
```

The repository also includes a relative-path `claude-settings.snippet.json`
that can be copied into an existing Claude Code settings merge workflow.

Run the repeated-instruction benchmark:

```bash
python skill_memory_bridge.py benchmark
```

Install or remove Claude Code hooks:

```bash
./install.sh
./uninstall.sh
```

`install.sh` creates a timestamped backup of `~/.claude/settings.json`, merges
the Memanto hooks idempotently, and leaves existing hooks intact.

## How It Maps To The Bounty

- Global memory hook: `SkillMemoryBridge.before_skill()` and
  `SkillMemoryBridge.after_skill()` wrap any skill command.
- Active extraction: `extract_engineering_memories()` turns skill transcripts
  into typed engineering profile memories.
- Dynamic injection: `before_skill()` queries by skill, task, and current
  working directory, then emits a compact system constraint.
- Safety filtering: extracted memories skip likely secrets and prompt-injection
  text before anything is persisted.
- Claude Code hook wiring: `write-claude-settings` creates a
  `UserPromptSubmit` and `Stop` settings snippet for teams that want lifecycle
  hooks instead of shell wrappers. A checked-in settings snippet is included
  for quick review.
- Installer flow: `install.sh` and `uninstall.sh` merge and remove only the
  Memanto hook entries, with a settings backup before mutation.
- Lightweight architecture: the local backend uses append-only JSONL; the live
  backend shells out to the existing `memanto remember` and `memanto recall`
  commands instead of adding new service dependencies.
- Reviewer-safe validation: `validate.py` runs the complete two-session memory
  flow without a Moorcheh API key.

## Live Memanto Mode

Install and configure Memanto first:

```bash
pip install memanto
memanto
memanto agent create claude-skills
```

Then enable the CLI backend:

```bash
export MEMANTO_SKILLS_BACKEND=cli
export MEMANTO_SKILLS_SOURCE=claude_code_skills
python skill_memory_bridge.py run-skill \
  --skill handoff \
  --task "Capture release constraints" \
  --cwd "$PWD" \
  --output "Instruction: always run the installer smoke test before release."
```

For direct SDK mode:

```bash
export MEMANTO_SKILLS_BACKEND=sdk
export MEMANTO_SKILLS_AGENT_ID=claude-skills
python skill_memory_bridge.py inject --skill tdd --task "Add checkout tests" --cwd "$PWD"
```

## Wrapper Generation

Create shell wrappers for common skills:

```bash
python skill_memory_bridge.py install-wrappers --out-dir ./.memanto-skill-wrappers
```

Each generated wrapper calls `inject` before the real skill command and records
the command transcript through `run-skill` after completion.

## Showcase Script

Session A:

```text
/grill-with-docs "Review auth architecture"
Decision: keep auth in the server boundary.
Instruction: never put service tokens in browser code.
```

Session B:

```text
/tdd "Add auth tests"
MEMANTO_SKILL_CONTEXT:
- [decision] keep auth in the server boundary
- [instruction] never put service tokens in browser code
```

That is the productivity multiplier: later skills receive the durable rule
without the user restating it.
