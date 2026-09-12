---
type: goal
title: "Implementation plan"
description: "Imported Antigravity implementation plan"
resource: "antigravity://session-0fe08c92635a/brain/implementation_plan.md#part-1"
tags: ["antigravity", "artifact_type_implementation_plan"]
timestamp: "2025-11-19T15:03:03.539957300Z"
x_memanto:
  confidence: 1.0
  provenance: imported
  source: tool
  status: active
  type: goal
---
# Implementation Plan - Tensor-Green ASCII Hybrid

## Goal
Refine the "Dawn Chorus" UI to a "Tensor-Green ASCII" aesthetic. This blends the "Retro ASCII" charm (monospace, text borders) with the "Modern Engineering" polish (Deep Charcoal, Mint Green, Bento Grid, strict spacing) of the reference images.

## User Review Required
> [!NOTE]
> This is a hybrid approach. We are keeping the ASCII soul but upgrading the "body" to be cleaner, darker, and more structured.

## Proposed Changes

### Design System (`src/index.css`)
- **Colors**:
  - Background: `#0A0A0A` (Deep Charcoal) - *From Tensor*
  - Surface: `#111111` (Panel bg) - *From Tensor*
  - Accent Mint: `#4ade80` (Primary Action) - *From Tensor*
  - Accent Slate: `#94a3b8` (Secondary) - *From Tensor*
  - Border: `#333333` (Dim) vs `#4ade80` (Active)
- **Typography**:
  - Global: `JetBrains Mono` / `Consolas` (Keep the ASCII feel).
  - Hierarchy: Use weight and color to distinguish headers from data, rather than font family.
- **Background Pattern**:
  - Subtle CSS grid (linear-gradient) to give that "graph paper" technical feel behind the ASCII.

### Components

#### [MODIFY] `src/components/ui/Card.jsx`
- **Hybrid Style**: Keep the ASCII feel but make it cleaner.
- Use CSS borders for the main shape (sharp corners).
- Use ASCII characters (`+`, `L`, `¬`) as *decorative* corner markers or section dividers, rather than full text borders.
- Dark background (`#111`) to separate content from the grid.

#### [MODIFY] `src/components/ui/Button.jsx`
- **Hybrid Style**: "Technical" buttons.
- Sharp rectangular shape.
- Subtle ASCII decoration (e.g., `[ COMMAND ]` or `> COMMAND`) but with modern hover states (solid Mint fill).

#### [MODIFY] `src/components/game/ProgressBar.jsx`
- **Hybrid Style**:
- Keep the "Block" concept but make it high-res.
- Use a solid CSS bar but overlay a "grid" or "tick marks" to retain the data feel.

#### [MODIFY] `src/components/game/StatBlock.jsx`
- Clean up spacing.
- Use the Mint Green for the value, Slate for the label.

### Pages

#### [MODIFY] `src/pages/Dashboard.jsx`
- **Bento Grid**: Strict 12-column grid.
- Panels separated by gaps.
- Use ASCII lines to connect related panels visually (optional).

#### [MODIFY] `src/components/ui/Layout.jsx`
- "System Status" header/footer in Mint Green.

## Verification Plan
### Automated Tests
- Render Dashboard.
- Verify the "Tensor" color palette is applied.
- Verify ASCII elements are present but refined.

### Manual Verification
- Does it feel like a "Hacker Terminal" (ASCII) met a "Modern Data Tool" (Tensor)?

<!-- antigravity-source-v1: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 -->
