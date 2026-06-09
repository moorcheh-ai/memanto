# Claude Code Skills + Memanto SkillChain

This example adds a lightweight memory bridge for Claude Code / mattpocock-style developer skills such as `/grill-with-docs`, `/tdd`, and `/handoff`.

The goal is to reduce context fragmentation between separate skill runs. A completed skill run emits durable engineering decisions, the bridge stores them as memory cards, and later skill runs receive relevant recalled context before they start.

## Modes

- **Reviewer-safe local mode** stores memory in `.skillchain/memory.jsonl` and requires no private credentials.
- **Live Memanto mode** uses the `memanto` CLI when `MEMANTO_LIVE=1` and `MOORCHEH_API_KEY` are configured.

Reviewer-safe local mode is the canonical review path so maintainers can verify behavior without API keys, network calls, or hidden local state.

## Quick proof

```bash
cd examples/claudecode-skills-memanto
python3 validate.py
```

Expected result:

```text
PASS: local SkillChain proof completed
```

## Example lifecycle

### Before a skill

```bash
python3 skill_memory.py before \
  --skill /grill-with-docs \
  --task "Review materialization architecture" \
  --query "materialization architecture ADR context"
```

### After a skill

```bash
python3 skill_memory.py after \
  --skill /grill-with-docs \
  --task "Review materialization architecture" \
  --transcript demo/demo-transcript.md
```

### Recall before the next skill

```bash
python3 skill_memory.py before \
  --skill /tdd \
  --task "Implement tests from the architecture review" \
  --query "materialization ADR tests"
```

## Live Memanto mode

```bash
export MOORCHEH_API_KEY='...'
export MEMANTO_LIVE=1
python3 skill_memory.py before --skill /tdd --task "Implement tests" --query "architecture decisions"
```

The key is read from the environment only. It is never printed by this example.

## Reviewer-safe demo repo

Public showcase and deterministic proof:

https://github.com/cwwjacobs/mdemo

## Social showcase

X: https://x.com/TerminusProto/status/2064451356392661020?s=20
