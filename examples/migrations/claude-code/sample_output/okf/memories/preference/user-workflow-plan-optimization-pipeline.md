---
type: preference
title: User Workflow — Plan Optimization Pipeline
description: User runs a multi-stage pipeline for iterative plan refinement with competing
  AI reviewers
tags:
- claude-code
- auto-memory
- user
resource: claude-code:memory:bce35dda9156523b9281
x_memanto:
  id: bce35dda9156523b9281
  confidence: 0.85
  provenance: imported
  source: claude-code
  status: active
  type: preference
---

User runs a multi-stage pipeline for iterative plan refinement with competing AI reviewers

The user is a plan architect who uses a multi-stage pipeline for iterative plan refinement. They use:

- a plan-review stage to generate and reconcile review artifacts;
- Claude Code as the primary plan integrator;
- Codex as an independent reviewer for a second perspective;
- deterministic Rust tooling to automate human-in-the-loop orchestration.

They value unattended automation, overnight iteration, deterministic file operations, full logging and audit trails, and clean separation between language-model work and deterministic operations.

---
[Supporting data]
- Claude source kind: auto-memory
- claude_memory_type: "user"
- source_file: "${HOME}/.claude/projects/-Users-demo-Projects-auto-planmaxxer/memory/user_workflow.md"
