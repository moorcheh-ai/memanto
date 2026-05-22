# Claude Code Skills + Memanto

This example shows how Memanto can act as a global memory companion for
developer skills such as `/grill-with-docs`, `/tdd`, and `/handoff`.

It adds two lifecycle hooks:

- `before`: recalls relevant engineering memories and prints a concise context
  block for the next skill invocation.
- `after`: distills explicit `decision:`, `preference:`, `instruction:`,
  `constraint:`, `context:`, and `artifact:` lines from the completed skill
  transcript and stores them for future runs.

The default backend is a local JSONL store so reviewers can validate the flow
without private credentials or network access. Set `MEMANTO_SKILL_BACKEND=cli`
and `MOORCHEH_API_KEY` to route memory through the installed `memanto` CLI.

## Quick Validation

```bash
cd examples/claudecode-skills-memanto
python validate.py
python -m unittest test_skill_memory.py
```

## Manual Demo

```bash
cat > /tmp/skill-transcript.txt <<'EOF'
decision: use a repository-local service layer for billing changes
preference: keep React toolbars dense and keyboard-friendly
instruction: run focused unit tests before broad integration tests
EOF

python skill_memory.py after \
  --skill /grill-with-docs \
  --transcript-file /tmp/skill-transcript.txt \
  --cwd "$PWD"

python skill_memory.py before \
  --skill /tdd \
  --prompt "write billing service tests for the React toolbar" \
  --cwd "$PWD"
```

## Wrapper Generation

Generate executable wrappers that run the memory hooks around the skill command:

```bash
python mattpocock_adapter.py --output-dir ./.memanto-skill-bin
PATH="$PWD/.memanto-skill-bin:$PATH"
```

The generated wrappers preserve the original command arguments, tee the skill
output to a temporary transcript, and then store durable engineering memories.

## Live Memanto Mode

```bash
export MOORCHEH_API_KEY=...
export MEMANTO_SKILL_BACKEND=cli
python skill_memory.py before --skill /handoff --prompt "summarize auth refactor"
```

Live mode uses `memanto remember` and `memanto recall`. The local backend remains
the default so PR reviewers can verify behavior without an API key.
