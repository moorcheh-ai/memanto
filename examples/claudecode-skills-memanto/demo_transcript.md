# Demo Transcript

This transcript shows two separate skill runs sharing engineering context through
the Memanto bridge.

## First Skill

Command:

```bash
python skill_memory.py demo --memory-file .memanto-skill-memory/demo.json
```

The simulated `/grill-with-docs` run stores these decisions:

- Keep authentication middleware stateless.
- Put tenant lookup in a small dependency.
- Avoid global mutable caches because tests run with parallel workers.
- The auth module owns token parsing.

## Later Skill

When a later `/tdd` task asks for auth dependency tests, the bridge recalls:

```text
Memanto recalled these engineering constraints from prior skills:
1. (decision) Review the auth refactor plan for a FastAPI service.
2. (decision) Decision: keep authentication middleware stateless and push tenant lookup into a small dependency.
```

The second skill can now write tests that match the earlier architecture review
without the developer manually pasting the prior plan.
