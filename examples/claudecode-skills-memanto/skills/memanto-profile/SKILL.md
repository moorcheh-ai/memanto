---
name: memanto-profile
description: Display your full persistent engineering profile — all architectural decisions, coding preferences, instructions, and lessons learned across all sessions. Use when you want to review, audit, or share your accumulated engineering knowledge.
---

# Memanto Profile — Engineering Memory Overview

Display your complete cross-session engineering profile.

## Steps

1. Run:

```bash
memanto-skills profile --limit 30
```

2. Print the full output verbatim.

3. Summarise what you see in one paragraph:
   - How many memories are stored
   - Which skills have contributed the most
   - The most important decisions and instructions

4. Ask the user: "Would you like to store anything new, or is there a memory here you'd like to update?"

## Tip

Memories of type `instruction` and `decision` are enforced in every future skill run. If you see outdated ones, use `/memanto-store` to record an updated decision — Memanto's conflict resolution will handle the contradiction automatically.
