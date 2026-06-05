# Claude Code Skills + MEMANTO

This example wires MEMANTO into the `mattpocock/skills` style of Claude Code
slash-skill workflows. It turns MEMANTO into an active memory companion around
skill execution:

1. `UserPromptExpansion` recalls relevant prior engineering context when a
   slash skill such as `/grill-with-docs`, `/tdd`, or `/handoff` expands.
2. Claude Code receives a `<memanto-skill-context>` block before the skill runs.
3. `Stop` reads the transcript after the run and captures high-signal decisions,
   preferences, and codebase facts back into MEMANTO.

The bridge is dependency-free and has a dry-run path, so it can be tested without
a Moorcheh API key. When `memanto` is configured, pass `--commit` on capture to
store memories through the normal CLI.

## Layout

```text
examples/claudecode-skills-memanto/
  .claude/settings.json
  .claude/skills/memanto-skill-companion/SKILL.md
  claudecode_skills_memanto/bridge.py
  tests/test_bridge.py
```

## Install

Copy the example into the root of a Claude Code project that already uses
slash skills.

```bash
cp -R examples/claudecode-skills-memanto/.claude .
```

Then adjust the `python examples/claudecode-skills-memanto/...` paths in
`.claude/settings.json` if your copy lives somewhere else.

## Dry Run

Capture candidate memories from a transcript:

```bash
python examples/claudecode-skills-memanto/claudecode_skills_memanto/bridge.py \
  capture \
  --transcript ~/.claude/projects/example/transcript.jsonl \
  --skill grill-with-docs \
  --project checkout-api \
  --dry-run-output .memanto/skill-candidates.jsonl
```

Inject those memories into a later slash-skill prompt:

```bash
echo '{"hook_event_name":"UserPromptExpansion","command_name":"tdd","command_args":"implement auth retry tests"}' \
  | python examples/claudecode-skills-memanto/claudecode_skills_memanto/bridge.py \
      hook-inject \
      --memories .memanto/skill-candidates.jsonl
```

For the checked-in Claude Code hook, `UserPromptExpansion` uses a slash-command
matcher so recall only runs for skill-like commands. The `Stop` hook does not
support matchers in Claude Code, so capture stays dry-run by default and should
only be switched to `--commit` after inspecting `.memanto/skill-candidates.jsonl`.
`UserPromptSubmit` is intentionally not configured for recall because it cannot
be filtered by slash command name and would spawn the bridge for every prompt.

## Live MEMANTO Mode

For prompt injection, `hook-inject` calls:

```bash
memanto recall "<skill> <prompt>" --limit 8
```

For post-run capture, add `--commit` to the `Stop` hook command. Each candidate
is stored with explicit `--type`, `--confidence`, `--provenance`, `--source`,
and `--tags` metadata.

## Offline Verification

```bash
python examples/claudecode-skills-memanto/tests/test_bridge.py
```
