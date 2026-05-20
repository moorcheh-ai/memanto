# Share-Ready Showcase

This file is intentionally an in-repo showcase, not an external social post.
Issue #508 maintainers clarified that external posts are optional for technical
review. The copy below can be used later if the contributor chooses to amplify
the demo without changing the implementation.

## Short X / LinkedIn Copy

I built a Memanto bridge for `mattpocock/skills`-style Claude Code commands.

The flow:

1. `/grill-with-docs` captures architecture choices and local rules.
2. Memanto stores typed engineering memories after the skill completes.
3. `/tdd` and `/handoff` recall those decisions later, including file context,
   without repeating the instructions.

The local reviewer path needs no API key, while live mode uses Memanto's
`SdkClient.recall`, `SdkClient.remember`, and `SdkClient.answer` to produce a
prompt-ready constraint block.

Demo proof:

```bash
python examples/claudecode-skills-memanto/validate.py
python examples/claudecode-skills-memanto/productivity_benchmark.py
```

Visual proof is included at:

```text
examples/claudecode-skills-memanto/demo_terminal.svg
```

The benchmark reports 100% repeated-instruction reduction across:

```text
/grill-with-docs -> /tdd -> /handoff
```

## Reddit-Style Technical Summary

I tried solving context fragmentation between small, single-purpose developer
skills. The problem is that one skill can learn an architectural rule, but the
next skill starts cold in a fresh terminal session.

This example adds a lightweight wrapper layer around `mattpocock/skills`-style
commands:

- `pre-skill` recalls relevant engineering memories by task, cwd, and file path.
- `post-skill` distills completed transcripts into typed memories such as
  decisions, preferences, instructions, context, artifacts, and errors.
- Generated wrappers export `MEMANTO_SKILL_CONTEXT` so child commands can use
  the recalled constraints directly.
- `SKILL_MEMORY_FILES` lets callers pass touched files through both recall and
  storage, so future runs can retrieve module-specific choices.
- `--skills-dir` can discover every `SKILL.md` from a real
  `mattpocock/skills` checkout.

Reviewer-safe local storage is deterministic JSON. Live mode uses the Memanto
SDK and asks Memanto's retrieval-backed answer step to synthesize a concise
constraint block instead of dumping raw memories into the prompt.

## Evidence Commands

```bash
python examples/claudecode-skills-memanto/validate.py
python -m unittest examples/claudecode-skills-memanto/test_skill_memory.py
python examples/claudecode-skills-memanto/productivity_benchmark.py
uvx ruff check examples/claudecode-skills-memanto
uvx ruff format --check examples/claudecode-skills-memanto
```

For upstream skill discovery:

```bash
git clone --depth=1 https://github.com/mattpocock/skills.git /tmp/mattpocock-skills
python examples/claudecode-skills-memanto/mattpocock_adapter.py \
  --skills-dir /tmp/mattpocock-skills/skills \
  --output-dir /tmp/memanto-skill-wrappers \
  --target-command claude
```
