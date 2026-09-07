"""
MEMANTO CLI - Connect Templates

Per-agent instruction content and skill templates for MEMANTO integration.
"""


# Shared MEMANTO Sentinel markers

MEMANTO_SENTINEL = "<!-- MEMANTO-MANAGED-SECTION -->"
MEMANTO_SENTINEL_END = "<!-- /MEMANTO-MANAGED-SECTION -->"

MEMANTO_DYNAMIC_SENTINEL = "<!-- MEMANTO-DYNAMIC-MEMORIES -->"
MEMANTO_DYNAMIC_SENTINEL_END = "<!-- /MEMANTO-DYNAMIC-MEMORIES -->"

TEMPLATE_VERSION = "1.0.0"
MEMANTO_VERSION_TAG = f"<!-- memanto-template-version: {TEMPLATE_VERSION} -->"


# Shared SKILL.md content (same across all agents)

SKILL_MD_CONTENT = """---
name: memanto-memory
description: Use this skill when you need to store, search, edit, or manage MEMANTO persistent memories. It defines mandatory guidelines for CLI command syntax, memory types, confidence levels, provenance, tagging rules, and patterns for effective agent memory usage.
---

# MEMANTO Memory Skill

Detailed reference guide for using MEMANTO persistent memory effectively across sessions.

## Quick Command Reference

All Memanto operations are performed via shell commands. Never simulate commands or keep internal mental notes.

```bash
# Store memory (ALWAYS pass full metadata flags)
memanto remember "Generalized principle or rule" --type TYPE --tags "tag1,tag2" --confidence <0.0-1.0> --provenance PROVENANCE --source <agent_name>

# Search memories (Semantic recall for context building)
memanto recall "query string" --limit 10 --type TYPE --min-similarity 0.8

# Temporal search variants (no query needed)
memanto recall --recent --limit 10                 # newest memories first
memanto recall --as-of "YYYY-MM-DD"                # memory state at a past point in time
memanto recall --changed-since "last 7 days"       # memories created or updated recently

# Grounded RAG answer (Synthesizes memory into a direct answer)
memanto answer "Question about past decisions or commitments"

# Edit existing memory
memanto edit MEMORY_ID --content "Updated content" --type TYPE --confidence 0.95

# Delete memory
memanto forget MEMORY_ID

# Sync dynamic memories to local project instructions
memanto memory sync --project-dir .
```

## Memory Types: Complete Decision Matrix

Select the exact memory type that best categorizes the information being persisted. Elevate every memory to a clean, declarative principle—never write chat logs or activity narratives (e.g., "User told me...", "Chose X...", "Agreed to...").

| Type | When to Use | Default Confidence | Default Provenance | Example |
|------|-------------|--------------------|--------------------|---------|
| `fact` | Verified technical facts, environment details, project state | 0.9 - 1.0 | `validated` / `observed` | "Database stack is PostgreSQL 15 with Prisma ORM." |
| `decision` | Architecture choices, stack selection, design patterns | 0.9 - 1.0 | `inferred` / `explicit_statement` | "Use Next.js App Router exclusively; Pages Router is deprecated." |
| `instruction` | Standing rules, guidelines, enforced constraints | 0.9 - 1.0 | `explicit_statement` | "Enforce strict TypeScript typing; explicit 'any' is disallowed." |
| `preference` | User style, tooling choices, formatting rules | 0.8 - 1.0 | `explicit_statement` / `observed` | "Use pnpm for dependency management and workspace scripts." |
| `learning` | Workarounds, discovered fixes, post-error insights | 0.8 - 0.95 | `observed` / `corrected` | "Windows build script requires --max-workers=2 to prevent worker process crashes." |
| `goal` | Objectives, roadmap items, target milestones | 0.8 - 1.0 | `explicit_statement` | "Complete OAuth2 authentication workflow integration." |
| `commitment` | Promises, agreed deliverables, explicitly accepted tasks | 1.0 | `explicit_statement` | "Refactor API route handlers before merging PR." |
| `artifact` | Output locations, build targets, file paths | 0.9 - 1.0 | `observed` | "Generated OpenAPI schema lives at ./docs/openapi.json." |
| `event` | Significant milestones, releases, major architectural shifts | 0.8 - 0.95 | `observed` | "Database successfully migrated to v2 schema." |
| `relationship` | Team structure, component ownership, API integrations | 0.85 - 0.95 | `explicit_statement` | "Auth service integrates with Keycloak cluster at auth.example.com." |
| `observation` | Behavioral patterns observed across multiple interactions | 0.6 - 0.85 | `observed` | "Provide concise code blocks without conversational preamble." |
| `error` | Failure post-mortems, bug root causes, regression notes | 0.95 - 1.0 | `observed` / `corrected` | "Parser memory leak was caused by unclosed file handle in logger.py." |
| `context` | Session state summaries, high-level project milestones | 0.9 - 1.0 | `observed` | "Phase 1 backend complete; database models fully migrated." |

## Confidence Levels Guide

Assign a confidence score between `0.0` and `1.0` based on source certainty:

- **1.0** — Explicit user statement, verified codebase fact, standing user instruction.
- **0.9 - 0.95** — Strong technical consensus, verified working code, well-tested pattern.
- **0.8 - 0.85** — Observed pattern (seen 3+ times), indirect user preference with strong evidence.
- **0.7 - 0.75** — Emerging pattern (seen 2 times), reasonable inference from context.
- **0.6 - 0.65** — Single observation, plausible hypothesis needing future confirmation.
- **< 0.6** — **DO NOT STORE.** Too uncertain.

## Provenance Types

Provenance identifies *how* the memory originated. You MUST specify one of the following:

- `explicit_statement` — User directly stated this fact, rule, or preference in conversation.
- `inferred` — Derived logically from user actions, codebase structure, or context.
- `observed` — Witnessed directly during execution, test run, or terminal output.
- `corrected` — Formulated after a previous mistake was corrected by the user or an error.
- `validated` — Verified against code, tests, or official documentation.
- `imported` — Ingested from an external source, config file, or migration.

## Tagging Best Practices

Always pass `--tags` with 2 to 5 specific, lowercase, hyphenated tags. Tags make memories searchable and clusterable.

### Tag Formatting Rules
- **Lowercase & Hyphenated**: Use `bug-fix`, `auth-oauth`, `next-js` (never camelCase or spaces).
- **Be Specific**: Use `prisma-schema` instead of `db`, `jwt-auth` instead of `security`.
- **Include Context & Refs**: Add commit hashes, component names, or issue IDs when relevant (e.g., `commit-a1b2c3d`, `user-router`).

### Good vs Bad Examples
- **GOOD**: `--tags "auth,oauth2,jwt,security"`
- **GOOD**: `--tags "docker,windows,wsl2,networking"`
- **BAD**: `--tags "important,stuff,code"` (Too generic, useless for retrieval)

## Choosing Between `recall` and `answer`

`recall` and `answer` serve distinct, complementary purposes. Choose based on what you need next:

| Criteria | `memanto recall` | `memanto answer` |
|----------|------------------|------------------|
| **Output Type** | Raw memory chunks with IDs, types, and metadata | Synthesized, grounded textual answer |
| **Primary Goal** | Build context for multi-step coding tasks | Answer a direct question or check a decision |
| **When to Use** | Before starting complex work, reviewing options | User asks "What did we decide about X?" |
| **Next Action** | Read memories, extract details, write code | Output answer directly to user or verify a fact |

**Rule of Thumb**:
- Need context to guide your work? Use `memanto recall`.
- Need a synthesized answer to a specific question? Use `memanto answer`.

## Pitfalls & Anti-Patterns to Avoid

1. **Activity Logging (The Chat-Log Anti-Pattern)**
   - **BAD**: `memanto remember "User told me to rename button component"`
   - **GOOD**: `memanto remember "UI components must use PascalCase naming convention"`

2. **Memory Hoarding**
   - Ask: *"Will this principle matter to a fresh agent session 3 months from now?"* If no, do not store.

3. **Vague Content**
   - **BAD**: `memanto remember "Improved API speed"`
   - **GOOD**: `memanto remember "API response time must remain under 200ms using Redis caching"`

4. **Missing Metadata Flags**
   - Never omit `--type`, `--confidence`, `--provenance`, or `--source`. Untyped memories pollute retrieval quality.

5. **Expecting Invisible Context Injection**
   - Do not expect hooks or background tools to automatically inject dynamic memories into chat UI. If context is needed, run `memanto recall` explicitly.

6. **Storing Duplicate Memories**
   - Before storing a major architectural decision or rule, run `memanto recall` to check if a similar rule already exists. Update it with `memanto edit` if necessary.

## Execution Workflows

### Workflow 1: Session Start / Task Initiation
```bash
# Check for existing architectural decisions and instructions relevant to the task
memanto recall "authentication setup guidelines" --limit 10
```

### Workflow 2: Learning from Error / Correction
```bash
# Store lesson immediately after fixing a tricky bug or receiving user correction
memanto remember "Next.js standalone build requires output: 'standalone' in next.config.js" --type learning --tags "nextjs,build,deployment" --confidence 1.0 --provenance corrected --source <agent_name>
```

### Workflow 3: User Sets Architectural Constraint
```bash
# Store user-defined rule immediately
memanto remember "Use UUID v4 for all primary keys across all PostgreSQL tables" --type instruction --tags "database,postgresql,schema" --confidence 1.0 --provenance explicit_statement --source <agent_name>
```
"""


# Per-agent instruction content


def _base_instruction_content(
    agent_id: str = "<agent_name>",
    tool_phrase: str = "the terminal",
    note_suffix: str = "",
) -> str:
    """Generate base MEMANTO instruction content, adapted per agent."""
    note_line = ""
    if note_suffix:
        note_line = f"\n> **Note**: {note_suffix}"

    return f"""{MEMANTO_SENTINEL}
{MEMANTO_VERSION_TAG}
## MEMANTO - Your Active Memory Companion

> **CRITICAL DIRECTIVE**: You are an agent equipped with Memanto. Without it, you are amnesiac. You have zero memory between chat sessions. Your ability to learn and adapt depends ENTIRELY on you actively writing to Memanto.

Every memory operation in this session goes through MEMANTO. There is no exception. All memanto commands are **shell commands**. Always run them using {tool_phrase}. Never simulate, describe, or "pretend to call" them.{note_line}

### 1. ENVIRONMENT-AWARE EXECUTION PROTOCOL
Before you write any code or provide a final answer, you MUST evaluate if the current context contains new memory triggers.

You must actively evaluate:
1. PREFERENCE: Did the user state a [USER PREFERENCE / RULE]? (e.g., code formatting style, choice of library, or tool preference)
2. GOAL: Did we establish or reach a [GOAL / MILESTONE]? (e.g., target feature completion, roadmap deliverable, or sprint objective)
3. FAILURE: Did we learn a [CORRECTION / FAILURE LESSON] from an error, tool, or test? (e.g., a bug fix workaround, error post-mortem, or test failure insight)
4. SYSTEM: Did we uncover a [DOMAIN INVARIANT / SYSTEM QUIRK]? (e.g., a technical constraint, API quirk, or dependency behavior)
5. ENVIRONMENT: Was a key [ENVIRONMENT FACT] verified? (e.g., OS behavior, path layout, or tool version requirement)

**How to Execute the Evaluation:**
- **If you are operating in Native CLI & Integrated IDE Environments (Claude Code, Cursor, Windsurf, Gemini CLI, Cline, Roo, Continue, OpenCode, Codex, Aider, or Anthropic Web UI):**
  You MUST perform this evaluation inside a `<thinking>` block at the very start of your turn.
- **If you are operating in VS Code Agent Environments (VS Code Copilot or VS Code Extension Agent Mode):**
  [CRITICAL SEQUENCE]: You MUST execute the following three steps in exact order ONCE at the very beginning of your turn (immediately after the user's prompt). Do NOT repeat this check before subsequent tool calls in the same turn.
  - **Step 1:** You MUST invoke the terminal tool with the dummy command `echo "memory check"`. You will use this tool call's `explanation` parameter to silently write out your step-by-step evaluation WRAPPED inside a `<thinking>` XML tag.
  - **Step 2:** If your evaluation in Step 1 found a matching trigger, your next immediate tool call MUST be `memanto remember`.
  - **Step 3:** Only AFTER Step 1 (and Step 2 if applicable) are complete, you may proceed to execute productive tools or output normal chat text.
### 2. THE ABSTRACTION RULE (HOW TO THINK ABOUT MEMORY)
Users speak naturally and implicitly. When you store a memory, **ELEVATE IT TO A PRINCIPLE**.
- **WRONG (Activity Log)**: "User told me to use functional components."
- **RIGHT (Universal Principle)**: "Exclusively use functional components for React UI."
Do not record the conversation. Record the universal rule.

### 3. THE DURABILITY TEST (WHAT NOT TO STORE)
Before storing, ask yourself: *"Will this generalized principle fundamentally change how I generate code for this user 3 months from now?"*
- **DO NOT STORE**: Step-by-step progress, routine bug fixes, UI tweaks, temporary code snippets, or literal chat summaries.

### 4. RECALL TRIGGER MATRIX (WHEN TO SEARCH MEMORY)
Do not guess or write code blindly. Run `memanto recall` (or `memanto answer`) using {tool_phrase} before acting if any of the following occur:
- **[TASK INITIATION]** Before starting a complex feature, refactor, or multi-file architecture task, search for relevant stack constraints, rules, and prior decisions.
- **[AMBIGUOUS REPAIR / ERROR]** When facing a cryptic build failure, test failure, or environment bug, search memory for past workarounds and error post-mortems.
- **[UNSTATED PREFERENCE]** When about to choose a library, pattern, or naming convention that isn't specified in the prompt, search memory to see if a preference was established in an earlier session.
- **[EXPLICIT USER QUESTION]** When the user asks "What did we decide about X?", "Check memory", or "Recall context", run `memanto recall` (or `memanto answer`) immediately.
- **[FRESH SESSION / CONTEXT REFRESH]** At session start or after switching tasks, run `memanto recall --recent` to retrieve active task state and recent commitments.

### 5. HOW TO EXECUTE
For all command syntax, required flags, memory types, tagging best practices, and CLI options, refer to the `memanto-memory` SKILL.md. You MUST read this skill before running any memory operations if you do not know the exact command schema.

{MEMANTO_SENTINEL_END}

{MEMANTO_DYNAMIC_SENTINEL}
{MEMANTO_DYNAMIC_SENTINEL_END}"""


def get_instruction_content(agent_name: str) -> str:
    """Get MEMANTO instruction section content for a specific agent."""

    templates = {
        "claude-code": _base_instruction_content(
            agent_id="claude-code",
            tool_phrase="the Bash tool",
            note_suffix="The `memanto-memory` skill contains reference guidelines only (best practices, confidence levels, tagging). It is NOT executable — always use Bash for memanto commands.",
        ),
        "codex": _base_instruction_content(
            agent_id="codex",
            tool_phrase="the terminal",
            note_suffix="The `memanto-memory` skill in `.agents/skills/memanto/` contains detailed reference guidelines (best practices, confidence levels, tagging).",
        ),
        "pi": _base_instruction_content(
            agent_id="pi",
            tool_phrase="the terminal",
            note_suffix="A Pi extension auto-syncs MEMORY.md on each fresh session start; the `memanto-memory` skill in `.pi/skills/memanto/` (or `~/.pi/agent/skills/memanto/`) contains detailed reference guidelines.",
        ),
        "cursor": _get_mdc_content(agent_id="cursor"),
        "windsurf": _base_instruction_content(
            agent_id="windsurf",
            tool_phrase="the terminal",
            note_suffix="The `memanto-memory` skill in `.windsurf/skills/memanto/` contains detailed reference guidelines.",
        ),
        "gemini-cli": _base_instruction_content(
            agent_id="gemini-cli",
            tool_phrase="the terminal",
            note_suffix="The `memanto-memory` skill in `.gemini/skills/memanto/` contains detailed reference guidelines.",
        ),
        "cline": _base_instruction_content(
            agent_id="cline",
            tool_phrase="the terminal",
            note_suffix="Run `memanto memory sync --project-dir .` at the start of each session to inject the latest dynamic memories into your system instructions.",
        ),
        "continue": _base_instruction_content(
            agent_id="continue",
            tool_phrase="the terminal",
            note_suffix="Run `memanto memory sync --project-dir .` at the start of each session to inject the latest dynamic memories into your system instructions.",
        ),
        "opencode": _base_instruction_content(
            agent_id="opencode",
            tool_phrase="the terminal",
            note_suffix="The `memanto-memory` skill in `.agents/skills/memanto/` contains detailed reference guidelines.",
        ),
        "roo": _base_instruction_content(
            agent_id="roo",
            tool_phrase="the terminal",
            note_suffix="Run `memanto memory sync --project-dir .` at the start of each session to inject the latest dynamic memories into your system instructions.",
        ),
        "github-copilot": _get_copilot_content(),
        "augment": _base_instruction_content(
            agent_id="augment",
            tool_phrase="the terminal",
            note_suffix="The `memanto-memory` skill in `.augment/skills/memanto/` contains detailed reference guidelines.",
        ),
    }
    return templates.get(agent_name, _base_instruction_content(agent_id=agent_name))


def _get_mdc_content(agent_id: str = "cursor") -> str:
    """Get MDC-formatted rules content for Cursor."""
    return f"""---
description: MEMANTO — active memory companion. Mandatory rules for storing, recalling, and answering from persistent memory.
alwaysApply: true
---

{_base_instruction_content(agent_id=agent_id, tool_phrase="the terminal")}"""


def _get_copilot_content() -> str:
    """Get frontmatter-formatted rules content for GitHub Copilot."""
    base_content = _base_instruction_content(
        agent_id="github-copilot",
        tool_phrase="the terminal",
        note_suffix="Run `memanto memory sync --project-dir .` at the start of each session to inject the latest dynamic memories into your system instructions.",
    )
    return f"""---
applyTo: "**/*"
---

{base_content}"""


def get_skill_content(agent_name: str = "<agent_name>") -> str:
    """Get the SKILL.md content (shared across all agents)."""
    content = SKILL_MD_CONTENT.strip()
    content = content.replace("<agent_name>", agent_name)
    # Inject the version tag right after the frontmatter
    if "---\n\n# MEMANTO Memory Skill" in content:
        content = content.replace(
            "---\n\n# MEMANTO Memory Skill",
            f"---\n\n{MEMANTO_VERSION_TAG}\n\n# MEMANTO Memory Skill",
        )
    return content + "\n"


# Pi .ts extension content (auto-syncs MEMORY.md on each fresh session start).
# Installed by `memanto connect pi` into ~/.pi/agent/extensions/ (or .pi/extensions/).

EXTENSION_TS_CONTENT = """/**
 * MEMANTO auto-sync extension for Pi.
 *
 * On a fresh process start, runs `memanto memory sync` in the background so the
 * project's MEMORY.md is up to date before you begin working. It is
 * fire-and-forget: it never blocks startup, and errors are swallowed (e.g. when
 * memanto is not installed, not on PATH, or no agent is active).
 *
 * Installed by `memanto connect pi`. Remove with `memanto connect remove pi`.
 */
import { spawn } from "node:child_process";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  pi.on("session_start", (event, ctx) => {
    // Only on a fresh process start — not on /resume, /fork, or /reload.
    if (event.reason !== "startup") return;

    const child = spawn(
      "memanto",
      ["memory", "sync", "--project-dir", ctx.cwd],
      { stdio: "ignore", detached: true },
    );
    child.unref();

    child.on("error", () => {
      /* memanto CLI not installed / not on PATH — ignore. */
    });
    child.on("close", (code) => {
      if (code === 0 && ctx.hasUI) {
        try {
          ctx.ui.notify("Memanto: memory synced", "info");
        } catch {
          /* notification unavailable in this mode — ignore. */
        }
      }
    });
  });
}
"""


def get_extension_content() -> str:
    """Get the Pi .ts extension content (memanto auto-sync on session start)."""
    return EXTENSION_TS_CONTENT.strip() + "\n"
