## MEMANTO - Long-term memory

This project uses Memanto for long-term memory across sessions. You MUST actively evaluate whether to use the `memanto` MCP tools (`recall`, `remember`) or CLI commands (identifying yourself with `--source kimi-code`) at every step.

### 1. WHEN TO RECALL (Search Context)
- **TASK INITIATION**: Starting a new feature, evaluating PR reviews, reviewing external code, or planning a refactor.
- **AMBIGUOUS REPAIR**: Facing a cryptic build failure, test failure, or environment bug.
- **UNSTATED PREFERENCE**: Choosing a library, pattern, or naming convention not explicitly specified.
- **EXPLICIT USER QUESTION**: The user asks to check memory, recall context, or asks "what did we decide?"

### 2. WHEN TO REMEMBER (Store Context)
- **PREFERENCE / INSTRUCTION**: The user states a code formatting style, library choice, or tool preference.
- **GOAL / COMMITMENT**: A target feature, roadmap deliverable, or sprint objective is established.
- **LEARNING / ERROR**: You extract a bug fix workaround, error post-mortem, or test failure insight.
- **DECISION / OBSERVATION**: You make an architectural decision, or record an API quirk / technical constraint.
- **FACT**: A key OS behavior, path layout, or tool version requirement is verified.

### 3. THE ABSTRACTION RULE (How to think about memory)
When you store a memory, ELEVATE IT TO A PRINCIPLE.
- **WRONG (Activity Log)**: "User told me to use functional components."
- **RIGHT (Universal Principle)**: "Exclusively use functional components for React UI."
Do not record the conversation. Record the universal rule.

### 4. THE DURABILITY TEST (What NOT to store)
Ask yourself: *"Will this generalized principle fundamentally change how I generate code for this user 3 months from now?"*
- **DO NOT STORE**: Step-by-step progress, routine bug fixes, UI tweaks, temporary code snippets, or literal chat summaries.

Just use the tools or commands; there's no need to mention memory checks in your text replies.
