---
name: memanto
description: Use this skill when you need to store, search, edit, or manage MEMANTO persistent memories. It defines mandatory guidelines for CLI command syntax, memory types, confidence levels, provenance, tagging rules, and patterns for effective agent memory usage.
---

<!-- memanto-template-version: 1.1.0 -->

# MEMANTO Memory Skill

Detailed reference guide for using MEMANTO persistent memory effectively across sessions.

## Quick Command Reference

All Memanto operations are performed via shell commands. Never simulate commands or keep internal mental notes.

```bash
# Store memory (ALWAYS pass full metadata flags)
memanto remember "Generalized principle or rule" --type TYPE --tags "tag1,tag2" --confidence <0.0-1.0> --provenance PROVENANCE --source kimi-code

# Search memories (Semantic recall for context building)
# Pass --source on reads as well: it is how Memanto knows which agent
# is calling, which drives the live connection view and session attribution.
memanto recall "query string" --limit 10 --type TYPE --min-similarity 0.8 --source kimi-code

# Temporal search variants (no query needed)
memanto recall --recent --limit 10 --source kimi-code            # newest memories first
memanto recall --as-of "YYYY-MM-DD" --source kimi-code           # memory state at a past point in time
memanto recall --changed-since "last 7 days" --source kimi-code  # memories created or updated recently

# Grounded RAG answer (Synthesizes memory into a direct answer)
memanto answer "Question about past decisions or commitments" --source kimi-code

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
   - On `recall` and `answer`, always pass `--source kimi-code`. This is how Memanto identifies the calling agent on reads as well as writes.

5. **Expecting Invisible Context Injection**
   - Do not expect hooks or background tools to automatically inject dynamic memories into chat UI. If context is needed, run `memanto recall` explicitly.

6. **Storing Duplicate Memories**
   - Before storing a major architectural decision or rule, run `memanto recall` to check if a similar rule already exists. Update it with `memanto edit` if necessary.

## Execution Workflows

### Workflow 1: Session Start / Task Initiation
```bash
# Check for existing architectural decisions and instructions relevant to the task
memanto recall "authentication setup guidelines" --limit 10 --source kimi-code
```

### Workflow 2: Learning from Error / Correction
```bash
# Store lesson immediately after fixing a tricky bug or receiving user correction
memanto remember "Next.js standalone build requires output: 'standalone' in next.config.js" --type learning --tags "nextjs,build,deployment" --confidence 1.0 --provenance corrected --source kimi-code
```

### Workflow 3: User Sets Architectural Constraint
```bash
# Store user-defined rule immediately
memanto remember "Use UUID v4 for all primary keys across all PostgreSQL tables" --type instruction --tags "database,postgresql,schema" --confidence 1.0 --provenance explicit_statement --source kimi-code
```
