# Claude Code Skills + Memanto

This example shows how Memanto can act as a persistent memory companion for
Claude Code style skill workflows such as `/grill-with-docs`, `/tdd`, and
`/handoff`.

The integration is intentionally small and reviewer-safe:

- `bridge.py` exposes `before` and `after` lifecycle hooks.
- `skills_manifest.py` reads the real `.claude-plugin/plugin.json` shape used by
  `mattpocock/skills`, so the demo can list available skill names from a local
  checkout.
- `skill_memory_hook.sh` wraps any skill command and stores a transcript.
- `local` backend stores memories in JSON so the demo works without credentials.
- `memanto` backend shells out to the real Memanto CLI for live recall and
  remember operations.

## What The Bridge Solves

Skills are usually run as isolated commands. A review skill may discover that a
project requires backwards-compatible API fields, but a later TDD skill will not
see that decision unless the developer manually repeats it.

This bridge turns each skill run into a memory event:

1. Before a skill starts, query Memanto for memories relevant to the skill name,
   task, and touched paths.
2. Print a compact context block that can be injected into the next prompt.
3. After the skill completes, distill the transcript into typed memories:
   `decision`, `instruction`, `preference`, `learning`, `artifact`, or
   `context`.
4. Store those memories so the next skill run gets the project-specific context
   automatically.

## Reviewer-Safe Offline Demo

Run from this directory:

```bash
./run_offline_demo.sh
```

The full expected output is captured in
[`demo/expected-output.md`](demo/expected-output.md), and the flow is shown in
[`demo/terminal-demo.svg`](demo/terminal-demo.svg).

Manual commands:

```bash
python bridge.py \
  --backend local \
  --store demo/memory.json \
  after \
  --skill grill-with-docs \
  --task "review API pagination design" \
  --path docs/api-pagination.md \
  --transcript demo/session-one-transcript.md

python bridge.py \
  --backend local \
  --store demo/memory.json \
  before \
  --skill tdd \
  --task "add pagination tests" \
  --path tests/test_api.py
```

Expected behavior: the second command prints remembered decisions and
constraints from the first transcript, including the Postgres choice,
backwards-compatibility rule, dependency-light preference, and useful pytest
command.

To score the productivity goal directly, run:

```bash
python productivity_check.py
```

It performs the same two-skill local flow and fails if a later `/tdd` run does
not recover the architectural decision, response-compatibility rule,
dependency-light preference, and pytest command without repeated instructions.

For share-ready X, LinkedIn, or Reddit copy, see
[`SOCIAL_SHOWCASE.md`](SOCIAL_SHOWCASE.md).

## mattpocock/skills Manifest Check

The upstream `mattpocock/skills` repo lists runnable skills in
`.claude-plugin/plugin.json`, with each skill described by a `SKILL.md`
frontmatter block. To verify this example against a local checkout:

```bash
git clone https://github.com/mattpocock/skills /tmp/mattpocock-skills
python skills_manifest.py /tmp/mattpocock-skills --format markdown
```

Use any listed skill name, such as `grill-with-docs`, `tdd`, `diagnose`, or
`handoff`, as the `--skill` value for `bridge.py` or `skill_memory_hook.sh`.

## Live Memanto Mode

Install and configure Memanto first:

```bash
pip install memanto
memanto
memanto agent create claudecode-skills
```

Then run the same lifecycle with the live backend:

```bash
python bridge.py --backend memanto after \
  --skill grill-with-docs \
  --task "review API pagination design" \
  --path docs/api-pagination.md \
  --transcript demo/session-one-transcript.md

python bridge.py --backend memanto before \
  --skill tdd \
  --task "add pagination tests" \
  --path tests/test_api.py
```

The live backend keeps the same public interface as the local backend, but
persists and recalls memories through the configured Memanto CLI.

## Shell Hook

Wrap a command with the skill lifecycle:

```bash
MEMANTO_SKILL_BACKEND=local \
./skill_memory_hook.sh tdd "add pagination tests" -- \
  python -m unittest discover -s tests
```

For live use, set `MEMANTO_SKILL_BACKEND=memanto` after configuring the Memanto
CLI and Moorcheh API key.

## Validation

```bash
python -m py_compile bridge.py
python -m py_compile skills_manifest.py
PYTHONPATH=. python -m unittest discover -s tests
python bridge.py --backend local --store demo/memory.json after \
  --skill grill-with-docs \
  --task "review API pagination design" \
  --path docs/api-pagination.md \
  --transcript demo/session-one-transcript.md
python bridge.py --backend local --store demo/memory.json before \
  --skill tdd \
  --task "add pagination tests" \
  --path tests/test_api.py
python productivity_check.py
```

## Files

```text
examples/claudecode-skills-memanto/
├── README.md
├── .env.example
├── bridge.py
├── skills_manifest.py
├── productivity_check.py
├── SOCIAL_SHOWCASE.md
├── run_offline_demo.sh
├── skill_memory_hook.sh
├── demo/
│   ├── expected-output.md
│   ├── terminal-demo.svg
│   └── session-one-transcript.md
└── tests/
    └── test_bridge.py
```
