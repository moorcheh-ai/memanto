---
type: event
title: "Implementation plan revision 1"
description: "Imported Antigravity implementation plan revision 1"
resource: "antigravity://session-0fe08c92635a/brain/implementation_plan.md.resolved.1#part-1"
tags: ["antigravity", "artifact_type_implementation_plan"]
timestamp: "2025-11-19T15:03:03.539957300Z"
x_memanto:
  confidence: 1.0
  provenance: imported
  source: antigravity
  status: active
  type: event
---
# Dawn Chorus - ASCII Tech Visual Overhaul

## Goal Description
Pivot the visual design to a "dark ASCII tech aesthetic". The goal is a raw, terminal-like interface that feels like a CLI tool or a retro-futuristic dashboard.
- **Everything Monospace**: No system sans-serif fonts.
- **Clean & Minimal**: Remove "card" backgrounds, use negative space and ASCII borders.
- **Tech Aesthetic**: Green/Amber on Black.

## User Review Required
> [!IMPORTANT]
> This is a significant departure from the previous "Ink-Forward" spec.
> - **Font**: `monospace` everywhere.
> - **Colors**: High contrast terminal style (Green/Amber on Black).
> - **UI Elements**: Buttons will look like `[ CLICK ME ]` or `> CLICK ME`. Cards will use ASCII borders.

## Proposed Changes

### Styling & Design System
#### [MODIFY] [src/index.css](file://[redacted-path])
- **Typography**: Set `font-family: monospace` globally.
- **Colors**: Update palette to be strictly high-contrast terminal colors.
- **Reset**: Remove default web styling (no rounded corners, no shadows).

### Components
#### [MODIFY] [src/components/ui/Card.jsx](file://[redacted-path])
- Remove background color.
- Add ASCII border wrapping using `fieldset` or pseudo-elements, or just simple borders that look technical.

#### [MODIFY] [src/components/ui/Button.jsx](file://[redacted-path])
- Change style to text-based: `[ LABEL ]` or `> LABEL`.
- Hover effects: Invert colors or add blinking cursor.

#### [MODIFY] [src/components/ui/Layout.jsx](file://[redacted-path])
- Redesign header to look like a terminal status bar.
- Remove "web" footer, replace with command-line style prompt or status line.

### Pages
#### [MODIFY] [src/pages/Dashboard.jsx](file://[redacted-path])
- Update grid to use ASCII separators instead of whitespace gaps if possible, or just clean spacing.
- Ensure StatBlocks look like raw data outputs.

#### [MODIFY] [src/pages/LandingPage.jsx](file://[redacted-path])
- Replace "hero" with a large ASCII art logo (text-based).
- Simplify faction selection to a list or text-based grid.

## Verification Plan

### Automated Tests
- `npm run dev` is already running. I will rely on hot-reloading.
- Browser tool to verify the new aesthetic.

### Manual Verification
- Check that NO sans-serif fonts remain.
- Verify the "terminal" feel (high contrast, raw text).

<!-- antigravity-source-v1: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 -->
