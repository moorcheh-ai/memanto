---
type: fact
title: Auto Planmaxxer Project Context
description: Rust CLI automating an iterative plan-review-refine cycle across multiple
  AI CLI sessions
tags:
- claude-code
- auto-memory
- project
resource: claude-code:memory:a9516935393f48e90d17
x_memanto:
  id: a9516935393f48e90d17
  confidence: 0.85
  provenance: imported
  source: claude-code
  status: active
  type: fact
---

Rust CLI automating an iterative plan-review-refine cycle across multiple AI CLI sessions

Auto Planmaxxer is a Rust CLI that automates iterative plan optimization using Claude Code for generation and integration and Codex for an independent review.

**Why:** Each manual iteration takes one to three hours of human shepherding. The tool runs unattended, enabling overnight multi-iteration plan refinement.

**How to apply:** This is a rebuild of an earlier functional prototype. Research recommends a hybrid architecture: a PTY for interactive generation, `claude -p --resume` for integration, and `codex exec` for reviews.

Key architectural decision: use `claude -p --resume` to eliminate the PTY from integration phases. Stay synchronous and use `std::thread` for parallel reviews.

The public sample project lives at `${HOME}/Projects/auto-planmaxxer/`.

---
[Supporting data]
- Claude source kind: auto-memory
- claude_memory_type: "project"
- source_file: "${HOME}/.claude/projects/-Users-demo-Projects-auto-planmaxxer/memory/project_context.md"
