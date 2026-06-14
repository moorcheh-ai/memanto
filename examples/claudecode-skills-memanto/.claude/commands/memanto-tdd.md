# /memanto-tdd

Memanto-enhanced `/tdd` skill. SessionStart and UserPromptSubmit hooks
automatically inject your engineering profile (architecture decisions,
preferences) before TDD begins — zero manual context-shoving.

## Automatic behavior (via hooks, no manual steps)

- **SessionStart**: recalls relevant decisions for this project/skill
- **UserPromptSubmit**: re-injects context if skill changes mid-session
- **Stop**: LLM extracts new decisions from this TDD session and stores them

## TDD Loop (vertical-slice, mattpocock pattern)

1. **RED** — write ONE failing test for the next behavior
2. **GREEN** — minimum code to pass, applying recalled architecture decisions
3. **REFACTOR** — clean up per recalled style preferences

## Memory-aware rules

- Apply recalled decisions immediately — never re-ask settled questions
- If a new decision contradicts a stored one, it's auto-extracted on Stop
  and the old fact is preserved via `metadata.previous_content`
