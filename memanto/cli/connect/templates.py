"""
MEMANTO CLI - Connect Templates

Per-agent instruction content and skill templates for MEMANTO integration.
"""


# Shared MEMANTO Sentinel markers

MEMANTO_SENTINEL = "<!-- MEMANTO-MANAGED-SECTION -->"
MEMANTO_SENTINEL_END = "<!-- /MEMANTO-MANAGED-SECTION -->"

MEMANTO_DYNAMIC_SENTINEL = "<!-- MEMANTO-DYNAMIC-MEMORIES -->"
MEMANTO_DYNAMIC_SENTINEL_END = "<!-- /MEMANTO-DYNAMIC-MEMORIES -->"

TEMPLATE_VERSION = "1.1.0"
MEMANTO_VERSION_TAG = f"<!-- memanto-template-version: {TEMPLATE_VERSION} -->"


# Shared SKILL.md content (same across all agents)

SKILL_MD_CONTENT = """---
name: memanto
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
# Reads have no --source, so pass --tool: it is how Memanto knows which agent
# is calling, which drives the live connection view and session attribution.
memanto recall "query string" --limit 10 --type TYPE --min-similarity 0.8 --tool <agent_name>

# Temporal search variants (no query needed)
memanto recall --recent --limit 10 --tool <agent_name>            # newest memories first
memanto recall --as-of "YYYY-MM-DD" --tool <agent_name>           # memory state at a past point in time
memanto recall --changed-since "last 7 days" --tool <agent_name>  # memories created or updated recently

# Grounded RAG answer (Synthesizes memory into a direct answer)
memanto answer "Question about past decisions or commitments" --tool <agent_name>

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
   - On `recall` and `answer`, always pass `--tool <agent_name>`. Reads carry no `--source`, and this is how Memanto identifies the calling agent.

5. **Expecting Invisible Context Injection**
   - Do not expect hooks or background tools to automatically inject dynamic memories into chat UI. If context is needed, run `memanto recall` explicitly.

6. **Storing Duplicate Memories**
   - Before storing a major architectural decision or rule, run `memanto recall` to check if a similar rule already exists. Update it with `memanto edit` if necessary.

## Execution Workflows

### Workflow 1: Session Start / Task Initiation
```bash
# Check for existing architectural decisions and instructions relevant to the task
memanto recall "authentication setup guidelines" --limit 10 --tool <agent_name>
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


def _base_instruction_content(agent_id: str = "<agent_name>") -> str:
    """Shared MEMANTO instruction section.

    The text is identical for every agent apart from ``agent_id``: IDEs often
    read several instruction files at once (e.g. Copilot reads its own file and
    CLAUDE.md), so per-agent wording would hand the model conflicting rules.
    It works both for agents with the memanto MCP server and for agents that
    can only run the CLI, and it never asks the model to write out its
    reasoning, which some models refuse to do.
    """
    return f"""{MEMANTO_SENTINEL}
{MEMANTO_VERSION_TAG}
## MEMANTO - Long-term memory

This project uses Memanto for long-term memory across sessions. You MUST actively evaluate whether to use the `memanto` MCP tools (`recall`, `remember`) or CLI commands (identifying yourself with `--tool {agent_id}`) at every step.

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

{MEMANTO_SENTINEL_END}

{MEMANTO_DYNAMIC_SENTINEL}
{MEMANTO_DYNAMIC_SENTINEL_END}"""


def get_instruction_content(agent_name: str, target_agent_id: str | None = None) -> str:
    """Get MEMANTO instruction section content for a specific agent.
    If target_agent_id is provided (e.g. --agent-id override), it is injected into the text rules.
    """
    display_id = target_agent_id if target_agent_id else agent_name
    if agent_name == "cursor":
        return _get_mdc_content(agent_id=display_id)
    if agent_name == "github-copilot":
        return _get_copilot_content(agent_id=display_id)
    return _base_instruction_content(agent_id=display_id)


def _get_mdc_content(agent_id: str = "cursor") -> str:
    """Get MDC-formatted rules content for Cursor."""
    return f"""---
description: MEMANTO long-term memory. When to recall and remember with the memanto tools.
alwaysApply: true
---

{_base_instruction_content(agent_id=agent_id)}"""


def _get_copilot_content(agent_id: str = "github-copilot") -> str:
    """Get frontmatter-formatted rules content for GitHub Copilot."""
    return f"""---
description: "Use on every task to recall and remember project context, user rules, and decisions with Memanto."
applyTo: "**"
---

{_base_instruction_content(agent_id=agent_id)}"""


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
