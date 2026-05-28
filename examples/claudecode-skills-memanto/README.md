# Claude Code Skills + Memanto Global Memory

This example shows how Memanto can act as a shared memory companion for
`mattpocock/skills` and other Claude Code skill collections.

The bridge adds two lifecycle hooks around a skill run:

- `pre`: recall project-specific engineering memories before invoking a skill.
- `post`: distill the skill transcript and store durable decisions back into
  Memanto.

That makes separate skills feel like one continuous engineering partner. A
decision discovered during `/grill-with-docs` can be recalled later by `/tdd`,
`/diagnose`, `/handoff`, or a fresh terminal session.

## Prerequisites

- Python 3.10+
- `memanto` installed and configured
- A Moorcheh API key in `MOORCHEH_API_KEY`
- Optional: `mattpocock/skills` installed through `npx skills@latest add
  mattpocock/skills`

```bash
pip install memanto
memanto
```

For local development from this repository, replace `memanto` with
`python -m memanto`:

```bash
export MEMANTO_COMMAND="python -m memanto"
```

On PowerShell:

```powershell
$env:MEMANTO_COMMAND = "python -m memanto"
```

## 1. Recall Memory Before A Skill

Run the pre-hook with the skill name and current task:

```bash
python memanto_skill_memory.py pre \
  --skill grill-with-docs \
  --project /path/to/your/repo \
  --task "Design billing webhooks without breaking retry semantics"
```

Paste the emitted `Memanto Skill Memory` block into the next Claude Code skill
prompt. If memories exist, the skill receives them as constraints before it
starts reasoning.

## 2. Store Memories After A Skill

When the skill finishes, pass its transcript or handoff summary to the post-hook:

```bash
python memanto_skill_memory.py post \
  --skill grill-with-docs \
  --project /path/to/your/repo \
  --transcript sample_transcripts/grill_with_docs.md
```

You can also store a compact summary directly:

```bash
python memanto_skill_memory.py post \
  --skill tdd \
  --project /path/to/your/repo \
  --summary "Decision: payment retries must be idempotent by provider event id."
```

The post-hook extracts durable engineering memories such as decisions,
constraints, preferences, artifacts, and lessons. It stores them in the shared
`claudecode-skills` Memanto agent with tags for the skill and project.

## 3. Cross-Session Demo

First, store a decision from a planning skill:

```bash
python memanto_skill_memory.py post \
  --skill grill-with-docs \
  --project ./example-saas \
  --summary "Decision: use an outbox table for billing webhooks so retries stay idempotent and auditable."
```

Then recall it from a different skill in a new shell:

```bash
python memanto_skill_memory.py pre \
  --skill tdd \
  --project ./example-saas \
  --task "Write tests for billing webhook retry behavior"
```

Expected outcome: `/tdd` starts with the outbox-table decision already in its
context, without the user repeating it.

## Dry-Run And Local Distillation

You can preview the extracted memories without an API key:

```bash
python memanto_skill_memory.py demo-distill sample_transcripts/grill_with_docs.md
```

You can also dry-run the Memanto commands:

```bash
python memanto_skill_memory.py --dry-run post \
  --skill grill-with-docs \
  --project ./example-saas \
  --transcript sample_transcripts/grill_with_docs.md
```

## Integration Pattern

A practical workflow is:

1. Run `pre` before invoking `/grill-with-docs`, `/tdd`, `/diagnose`, or
   `/handoff`.
2. Paste the recalled memory block into the skill prompt.
3. Run the skill normally.
4. Save the final response or handoff notes to a markdown file.
5. Run `post` to store the new durable engineering context.

This keeps the integration transparent and reversible: the skills still work
without Memanto, but gain cross-session memory when the hook is present.

## What Gets Stored

The extractor intentionally favors durable engineering context:

- architectural decisions
- codebase conventions and preferences
- project constraints
- root-cause learnings
- created or changed artifacts

Transient chat, logs, and low-signal narration are ignored.

## Bounty Mapping

This example addresses the challenge requirements:

- Global memory hook: `pre` and `post` wrap skill execution.
- Active extraction: `post` distills completed skill transcripts into typed
  Memanto memories.
- Dynamic injection: `pre` recalls relevant memories and emits prompt-ready
  constraints for the next skill.
- Cross-session recall: the same Memanto agent is used across skills, projects,
  and terminal sessions.
