---
name: memanto
description: Use this skill when you need to store, search, edit, or manage MEMANTO persistent memories. It defines mandatory guidelines for CLI command syntax, memory types, confidence levels, provenance, tagging rules, and patterns for effective agent memory usage.
---

# MEMANTO Memory Skill

Detailed reference guide for using MEMANTO persistent memory effectively across sessions.

## Quick Command Reference

All Memanto operations are performed via the `memanto` MCP tools (when registered) or via shell commands:

```bash
# Store memory (ALWAYS pass full metadata flags)
memanto remember "Generalized principle or rule" --type TYPE --tags "tag1,tag2" --confidence <0.0-1.0> --provenance PROVENANCE --source kimi-code

# Search memories (Semantic recall for context building)
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

Select the exact memory type that best categorizes the information being persisted. Elevate every memory to a clean, declarative principle—never write chat logs or activity narratives.

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
