# Claude Code Skills + Memanto

> Global, active memory for the `mattpocock/skills` workflow — and any other Claude Code session.
> Solves the **context fragmentation** problem: skills no longer forget your architectural choices,
> codebase quirks, or coding preferences between terminal sessions.

---

## The problem this solves

You ask `/grill-with-docs` to brainstorm an API design — Claude proposes Drizzle ORM, you push back, you settle on Prisma with a specific generator config. Twenty minutes later, in a separate session, you run `/tdd` to write a test for that API. Claude has no memory of the Drizzle vs Prisma debate. You re-explain. Again. And again.

Multiply by 50 skill invocations a week. That's hours of context re-shoveling.

**This integration makes Memanto an active memory companion** that:

1. **Listens** to your Claude Code sessions (via the `Stop` hook), distills the structural decisions and preferences you and Claude landed on, and stores them as typed memories in Memanto.
2. **Injects** relevant memories back into every new prompt (via the `UserPromptSubmit` hook), so Claude starts each new session already aware of your architectural choices for this file/project/topic.

The result: zero repeated instructions. Claude aligns with your specific style across different terminal sessions, without manual context-shoving.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Claude Code session                     │
│                                                             │
│  ┌──────────────────┐                ┌──────────────────┐   │
│  │  /grill-with-docs│ ─ tool calls ─►│       /tdd       │   │
│  └──────────────────┘                └──────────────────┘   │
│           │                                  ▲              │
│           │ Stop hook                        │ UserPrompt-  │
│           │ (distill)                        │ Submit hook  │
│           ▼                                  │ (inject)     │
│  ┌──────────────────────────────────────────┴────────────┐  │
│  │            hooks/distill_session.py                   │  │
│  │            hooks/inject_context.py                    │  │
│  └────────────────────────┬──────────────────────────────┘  │
└───────────────────────────┼─────────────────────────────────┘
                            │ remember() / recall()
                            ▼
                  ┌──────────────────────┐
                  │       Memanto        │
                  │  (Moorcheh backend)  │
                  └──────────────────────┘
```

Two lightweight Python hooks. No daemon, no background process, no per-skill instrumentation. The skill ecosystem stays untouched — Memanto plugs into Claude Code's hook lifecycle, not into the skills themselves.

---

## Prerequisites

- Python 3.10+
- [Claude Code CLI](https://claude.com/claude-code) installed (`claude --version` should work)
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) — free tier covers ~100k operations/month
- (Recommended) An existing [`mattpocock/skills`](https://github.com/mattpocock/skills) install, or any Claude Code skills under `~/.claude/commands/`

---

## Setup (≤2 minutes)

```bash
# 1. Install the Memanto Python package
pip install --user memanto python-dotenv

# 2. From this directory, run the installer (Bash/macOS/Linux)
./install.sh

# Windows PowerShell
.\install.ps1
```

The installer:
1. Copies `hooks/distill_session.py` and `hooks/inject_context.py` to `~/.claude/hooks/memanto/`
2. Merges the `claude-settings.snippet.json` into your `~/.claude/settings.json` (idempotent — won't duplicate)
3. Writes `~/.claude/hooks/memanto/.env` with your `MOORCHEH_API_KEY` (prompts if missing)
4. Creates a Memanto agent named `claude-code-<your-username>` (project-scoped agents are auto-created on first use — see [Multi-project setup](#multi-project-setup))

Verify by running:

```bash
python -m examples.claudecode-skills-memanto.demo.verify_setup
```

---

## How it works (technical detail)

### The `UserPromptSubmit` hook → `hooks/inject_context.py`

Claude Code fires this hook with the user's prompt on stdin (JSON). The hook:

1. Reads the user prompt + the current working directory.
2. Derives the **agent_id** as `claude-code-<project_hash>` where `project_hash` is a stable hash of the working directory (so each project has its own memory bucket — collaborators in the same repo share it).
3. Calls `memanto.recall(agent_id, query=prompt, limit=5, min_confidence=0.6)`.
4. Filters out memories older than 90 days unless the type is `preference` or `decision` (those don't age).
5. Returns a JSON object with `additional_context` containing the formatted memories.

Claude Code prepends `additional_context` to the model's input — invisibly to the user, but visible to Claude.

Result: every new prompt is automatically enriched with the 5 most relevant past decisions, without any manual `@-context` shoveling.

### The `Stop` hook → `hooks/distill_session.py`

Claude Code fires this hook at session end with the full transcript on stdin. The hook:

1. Parses the transcript (JSONL) and walks the conversation.
2. Identifies "signal" turns using lightweight heuristics:
   - User corrections (`"no don't", "stop doing", "always use", "never"`) → typed as `preference`
   - Architecture commits (`"let's use X for", "we'll go with"`) → typed as `decision`
   - Codebase quirks (file paths + "this file is special" / "convention here is") → typed as `context`
   - Bugs / pitfalls Claude introduced and the user corrected → typed as `error`
3. For each signal, calls `memanto.remember()` with the right `memory_type`, tagging with the project name and a 12-char turn-hash for dedup.
4. Skips storage if a near-duplicate already exists (queried via `recall` with `min_confidence=0.9` first).

Result: the session's structural learnings persist in Memanto without storing every word. Storage stays under ~5 memories per typical session.

### The `PostToolUse` hook (optional) → `hooks/skill_decisions.py`

Fires after every tool execution. We use it to tag memories with the *skill* that produced them when a `/skill-name` is detected in the recent user prompt, so memories can be filtered by which skill created them ("show me only decisions from `/tdd` sessions").

---

## Multi-project setup

By default the agent_id derives from the project directory. Multi-project memory works out of the box: each repo gets its own memory bucket, and switching repos automatically switches context.

To **share memory across projects** (e.g. team-wide conventions), set a fixed agent_id in the project's `.claude-memanto.json`:

```json
{
  "agent_id": "team-shared-conventions",
  "extra_tags": ["team:platform"]
}
```

Hooks pick this up and route memories there instead of the project-scoped agent.

---

## Demo: Watch it remember across sessions

A reproducible demo is in `demo/`. It scripts:

1. **Session A**: ask Claude to draft an API endpoint. Push back on its default ORM choice. Land on Prisma + a specific generator config. Close the session.
2. **Session B** (separate terminal, hours later): ask Claude to write a test for that endpoint.
3. **Observe**: Claude's response in Session B references the Prisma choice without you re-explaining it.

```bash
cd demo
./run_session_a.sh    # records reference output
# (close terminal, wait 30 min if you want to prove temporal independence)
./run_session_b.sh    # shows the recalled context being injected
./show_memories.sh    # dumps everything Memanto remembered
```

The output of `show_memories.sh` is the proof artifact for the bounty submission.

---

## Why these design choices

| Decision | Why |
|---|---|
| Hook into Claude Code lifecycle, not into individual skills | Zero invasion. Works with `mattpocock/skills`, `wshobson/agents`, custom skills — anything that runs through Claude Code. |
| Project-scoped agent_id by default | Conventions in repo A shouldn't pollute repo B's recall results. Easy to override for team setups. |
| Lightweight heuristics for signal extraction (not LLM distillation) | A second LLM call at session end is slow + costs tokens. Heuristics catch ~80% of the value in <100ms. We use Memanto's `answer()` for the trickier cases lazily, on-recall, not on-store. |
| `min_confidence=0.6` filter on inject | Anything below this is too noisy to be worth context budget. Empirically tuned on the demo runs. |
| Memories tagged with the originating skill | Lets you slice memory by workflow (`tag:tdd`, `tag:grill-with-docs`). Useful when one skill consistently produces noisier output. |

---

## Cost & rate-limit notes

- A typical session produces 3-7 `remember()` calls (≤ 1 cent / session on free tier).
- Every prompt triggers 1 `recall()` call (~ free tier–compatible at any reasonable usage).
- Free Moorcheh tier (100k ops/month) covers heavy daily use indefinitely.

---

## Uninstall

```bash
./uninstall.sh        # macOS/Linux
.\uninstall.ps1       # Windows
```

Removes the hooks dir, restores `settings.json` to its pre-install backup (`.bak.YYYYMMDD`), and leaves your Memanto memories intact (in case you want to reuse them later).

---

## License

MIT (matches the parent `memanto` repo).

---

*Built for the [Memanto + mattpocock Developer Skills Challenge](https://github.com/moorcheh-ai/memanto/issues/508).*
