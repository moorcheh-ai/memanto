---
type: event
title: "Implementation plan revision 3"
description: "Imported Antigravity implementation plan revision 3"
resource: "antigravity://session-0fe08c92635a/brain/implementation_plan.md.resolved.3#part-1"
tags: ["antigravity", "artifact_type_implementation_plan"]
timestamp: "2025-11-19T15:03:03.539957300Z"
x_memanto:
  confidence: 1.0
  provenance: imported
  source: antigravity
  status: active
  type: event
---
# Implementation Plan - Tensor-Green Visual Overhaul

## Goal
Pivot the UI from "Retro ASCII" to a "Modern Engineering" / "Tensor-Green" aesthetic. The interface should feel like a high-end data processing tool with a deep charcoal background, mint green accents, and a mix of sans-serif and monospace typography.

## User Review Required
> [!IMPORTANT]
> This is a complete visual pivot. The "Retro ASCII" elements (text borders, bracket buttons) will be removed in favor of modern CSS styling.

## Proposed Changes

### Design System ([src/index.css](file://[redacted-path]))
- **Colors**:
  - Background: `#0A0A0A` (Deep Charcoal)
  - Surface: `#111111` (slightly lighter for panels)
  - Accent Mint: `#4ade80` (Primary Action)
  - Accent Slate: `#94a3b8` (Secondary/Muted)
  - Border: `#333333` (Thin, crisp)
- **Typography**:
  - Global: System Sans-Serif (Inter/Roboto style) for UI labels and headings.
  - Mono: `JetBrains Mono` / `Consolas` for data values, code, and IDs.
- **Background Pattern**:
  - Implement a subtle CSS linear-gradient grid.

### Components

#### [MODIFY] [src/components/ui/Card.jsx](file://[redacted-path])
- Remove ASCII borders.
- Implement "Panel" styling: Dark background, thin border.
- Add "Corner Markers" (SVG or CSS pseudo-elements) for the technical look.

#### [MODIFY] [src/components/ui/Button.jsx](file://[redacted-path])
- Remove bracket style `[ LABEL ]`.
- Implement sharp rectangular buttons.
- Primary: Solid Mint text/bg or outline.
- Secondary: Muted outline.

#### [MODIFY] [src/components/game/ProgressBar.jsx](file://[redacted-path])
- Remove ASCII text bar.
- Implement CSS-based progress bar (container div + width-based filler div).
- Use Mint Green for the fill.

#### [MODIFY] [src/components/game/StatBlock.jsx](file://[redacted-path])
- Update typography: Label in Sans-Serif, Value in Monospace.
- Clean up spacing.

### Pages

#### [MODIFY] [src/pages/Dashboard.jsx](file://[redacted-path])
- Implement "Bento Grid" layout (CSS Grid).
- Group related metrics into distinct Panels.
- Ensure strict alignment.

#### [MODIFY] [src/components/ui/Layout.jsx](file://[redacted-path])
- Update header/footer to match the new "Data Interface" look (less "Terminal").

## Verification Plan
### Automated Tests
- Use `browser_subagent` to render the Dashboard and Landing Page.
- Verify the absence of ASCII borders and presence of new CSS styles.

### Manual Verification
- Check contrast ratios (Mint on Charcoal).
- Verify font hierarchy (Headers vs Data).

<!-- antigravity-source-v1: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 -->
