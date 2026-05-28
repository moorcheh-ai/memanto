# Claude Code Skills + Memanto Memory Bridge

This example shows how Memanto can act as a global engineering memory companion
for skill-based developer workflows such as `mattpocock/skills`.

The bridge has two lifecycle hooks:

- `pre`: recall relevant engineering memory before a skill starts.
- `post`: distill a completed skill session into a durable memory.

That lets one skill remember an architectural decision and a later skill reuse it
without manual re-prompting.

## Files

```text
examples/claudecode-skills-memanto/
├── README.md
├── requirements.txt
├── .env.example
├── memanto_skills.py
├── run_session_a.py
├── run_session_b.py
└── tests/
    ├── conftest.py
    └── test_memanto_skills.py
```

## Setup

```bash
cd examples/claudecode-skills-memanto
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

The default backend is local JSONL, so reviewers can run the demo without
credentials. To use live Memanto, set `MEMANTO_SKILLS_BACKEND=memanto` and add a
`MOORCHEH_API_KEY` in `.env`.

## Demo

Session A simulates `/grill-with-docs` finding and storing an architecture
decision:

```bash
python run_session_a.py
```

Session B simulates `/tdd` starting later in a fresh process and receiving the
stored decision as injected context:

```bash
python run_session_b.py
```

Expected output from Session B includes:

```text
Relevant engineering memory from previous skill sessions:
- Architecture decision: use a repository layer for Stripe webhook persistence.
```

## Hook Commands

The same flow can be wired into a skill runner:

```bash
python memanto_skills.py pre \
  --skill /tdd \
  --path services/payments \
  --prompt "Add tests for Stripe webhook retries."

python memanto_skills.py post \
  --skill /grill-with-docs \
  --path services/payments \
  --prompt "Review the payments service architecture." \
  --transcript "Decision: use a repository layer for Stripe webhook persistence."
```

## Validation

```bash
cd examples/claudecode-skills-memanto
python -m pytest tests -q
python -m py_compile memanto_skills.py run_session_a.py run_session_b.py
```

## Why This Fits The Challenge

- Active extraction: `post` turns skill output into a durable engineering memory.
- Dynamic injection: `pre` recalls path/task-relevant context before another skill
  runs.
- Zero repeated instructions: the second skill receives the earlier architectural
  decision without the user restating it.
- Review-safe: local JSONL mode proves behavior without secrets; live Memanto mode
  uses the same `remember` and `recall` lifecycle against a Moorcheh-backed agent.
