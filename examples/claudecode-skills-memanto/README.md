# 🧠 Memanto + mattpocock/skills — Claude Code Lifecycle Hooks

Real Claude Code `SessionStart`, `UserPromptSubmit`, and `Stop` hooks that
make Memanto a global, active memory companion across `/tdd`,
`/grill-with-docs`, `/handoff`, and other mattpocock skills.

```text
/grill-with-docs  →  Stop hook: LLM extracts decisions → stored via moorcheh-sdk
                                        ↓  Memanto  ↓
/tdd (new session) ←  SessionStart hook: recall() + answer.generate() RAG inject
```

> **Zero repeated instructions.** Hooks fire automatically — no manual
> pre/post commands, no copy-paste, no forks of mattpocock/skills.

## 🎬 Demo

▶️ [Watch demo](REPLACE_WITH_LOOM_LINK)

📣 X: REPLACE_WITH_X_LINK
📣 Reddit: REPLACE_WITH_REDDIT_LINK

## Why this approach

| | This PR | CLI-subprocess wrappers |
|---|---|---|
| Memanto access | Official `moorcheh-sdk` `MoorchehClient` (in-process) | `subprocess.run(["memanto", ...])` |
| Context injection | `answer.generate()` RAG synthesis + semantic recall | Raw recall text only |
| Extraction | LLM-powered (`answer.generate()`) with heuristic fallback | Regex/heuristic only |
| Hooks | Real `SessionStart` / `UserPromptSubmit` / `Stop` | None (manual wrapper script) |
| Tests | 20 unit tests, `unittest` | — |

## Quick Start

```bash
pip install -r requirements.txt
export MOORCHEH_API_KEY=mk-...   # free key at moorcheh.ai
python install.py                 # registers hooks in .claude/settings.json
```

Open Claude Code in your project — hooks activate automatically.

## Credential-free Demo

```bash
python run_demo.py
```

Runs a full two-session cross-skill memory demo using an offline mock —
no API key required. Use `--live` once `MOORCHEH_API_KEY` is set.

## Validation

```bash
python validate_offline.py
```

Runs syntax checks, 20 unit tests, and the offline demo end-to-end.

## How it works

### SessionStart hook (`hooks/on_session_start.py`)
Detects the active skill, recalls relevant memories via
`similarity_search.query()`, and synthesizes a RAG summary via
`answer.generate()`. Injects an `<engineering-profile>` block.

### UserPromptSubmit hook (`hooks/on_prompt.py`)
Re-detects skill from the prompt text and touched files mid-session,
re-injecting context if you switch skills.

### Stop hook (`hooks/on_stop.py`)
Sends the transcript to `answer.generate()` asking the LLM to extract typed
engineering memories (decision / instruction / preference / error / fact).
Falls back to regex heuristics (`DECISION:`, `CONSTRAINT:`, etc.) if the LLM
returns nothing parseable. Stores via `documents.upload()`.

## Architecture

```text
┌─────────────────────────────────────────────────┐
│              Claude Code session                 │
│                                                   │
│  SessionStart → recall() + answer() → inject     │
│  UserPromptSubmit → re-detect skill → re-inject  │
│  Stop → answer() extracts decisions → store()    │
└───────────────────┬───────────────────────────────┘
                     │ moorcheh-sdk (MoorchehClient)
         ┌───────────▼────────────┐
         │   Moorcheh.ai engine    │
         │  namespaces / documents │
         │  similarity_search      │
         │  answer.generate()      │
         └─────────────────────────┘
```

## Memanto API used (official SDK only)

| Call | Purpose |
|---|---|
| `namespaces.create()` | Create shared engineering-profile namespace |
| `documents.upload()` | Store typed memories |
| `similarity_search.query()` | Semantic recall |
| `answer.generate()` | RAG context synthesis + LLM extraction |

No raw HTTP, no subprocess, no undocumented endpoints.

## Project Structure

```text
examples/claudecode-skills-memanto/
├── memanto_client.py       # official moorcheh-sdk wrapper
├── skills_memory.py         # CLI + SkillsMemory class
├── install.py                # registers Claude Code hooks
├── run_demo.py                # credential-free demo
├── validate_offline.py        # syntax + 20 tests + demo
├── hooks/
│   ├── _common.py             # shared extraction/recall logic
│   ├── on_session_start.py
│   ├── on_prompt.py
│   └── on_stop.py
├── tests/test_skills_memory.py
└── .claude/commands/
    ├── memanto-tdd.md
    ├── memanto-grill-with-docs.md
    └── memanto-handoff.md
```
