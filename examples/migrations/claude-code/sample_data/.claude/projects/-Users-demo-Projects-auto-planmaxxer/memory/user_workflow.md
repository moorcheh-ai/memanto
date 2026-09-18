---
name: User Workflow — Plan Optimization Pipeline
description: User runs a multi-stage pipeline for iterative plan refinement with competing AI reviewers
type: user
---

The user is a plan architect who uses a multi-stage pipeline for iterative plan refinement. They use:

- a plan-review stage to generate and reconcile review artifacts;
- Claude Code as the primary plan integrator;
- Codex as an independent reviewer for a second perspective;
- deterministic Rust tooling to automate human-in-the-loop orchestration.

They value unattended automation, overnight iteration, deterministic file operations, full logging and audit trails, and clean separation between language-model work and deterministic operations.
