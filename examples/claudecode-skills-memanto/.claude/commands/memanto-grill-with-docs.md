# /memanto-grill-with-docs

Memanto-enhanced `/grill-with-docs`. Challenges your plan against the domain
model AND your stored engineering decisions — automatically, via hooks.

## Automatic behavior (via hooks)

- **SessionStart/UserPromptSubmit**: loads prior decisions so the interviewer
  never re-grills settled questions
- **Stop**: the LLM (`answer.generate()`) reads the full transcript and
  extracts every resolved decision, constraint, and preference, storing them
  as typed memories

## Grilling protocol

1. Treat recalled decisions as settled — focus on NEW proposals
2. Surface conflicts if a new proposal contradicts a stored decision
3. One question at a time, force concrete answers

## Why this matters

Every resolved decision here becomes part of the permanent engineering
profile. `/tdd`, `/handoff`, and `/improve-codebase-architecture` will load
it automatically in any future session — no copy-paste, no forks.
