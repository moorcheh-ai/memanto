---
type: event
title: "Implementation plan revision 2"
description: "Imported Antigravity implementation plan revision 2"
resource: "antigravity://session-0fe08c92635a/brain/implementation_plan.md.resolved.2#part-1"
tags: ["antigravity", "artifact_type_implementation_plan"]
timestamp: "2025-11-19T15:03:03.539957300Z"
x_memanto:
  confidence: 1.0
  provenance: imported
  source: tool
  status: active
  type: event
---
# Dawn Chorus - High-Fidelity ASCII UI Refinement

## Goal Description
Address the "lack of space, style, and UI/UX" by elevating the "Dark ASCII Tech" aesthetic to a premium, high-fidelity interface.
- **Space**: Increase negative space (padding/margins). Use a strict grid to organize information logically.
- **Style**: "Curated Phosphor" aesthetic. Less "default green", more nuanced shades. Clean lines, intentional typography.
- **UX**: Clearer hierarchy. Interactive elements should feel responsive and tactile (even in text).

## User Review Required
> [!IMPORTANT]
> I will be applying standard UI/UX principles (Alignment, Proximity, Contrast) to the ASCII theme.
> - **Strict Grid**: Everything aligns perfectly.
> - **Visual Hierarchy**: Size and color will guide the eye.
> - **Breathing Room**: No more cramped text.

## Proposed Changes

### Styling & Design System
#### [MODIFY] [src/index.css](file://[redacted-path])
- **Grid System**: Define a global grid variable or utility.
- **Palette**: Refine colors.
  - Background: Deepest Black (`#050505`).
  - Primary: Phosphor Green (`#33ff00`) -> maybe slightly desaturated for body text to reduce eye strain.
  - Surface: Very subtle gray (`#111`) for panels.
- **Typography**: Adjust line heights and letter spacing for better readability.

### Components
#### [MODIFY] [src/components/ui/Layout.jsx](file://[redacted-path])
- Create a "Main Frame" border that encompasses the app.
- Improve the header/nav to look like a high-end dashboard top bar.

#### [MODIFY] [src/components/ui/Card.jsx](file://[redacted-path])
- Remove "box" borders for a cleaner look? Or make them very subtle.
- Use "corner markers" `└ ┘` instead of full boxes to open up space.

#### [MODIFY] [src/components/ui/Button.jsx](file://[redacted-path])
- Make them look like clickable command zones.
- Add a subtle background hover effect.

### Pages
#### [MODIFY] [src/pages/Dashboard.jsx](file://[redacted-path])
- Reorganize into a cleaner 3-column layout with distinct "zones".
- Use whitespace to separate the "Army" section from "Stats".

#### [MODIFY] [src/pages/LandingPage.jsx](file://[redacted-path])
- Center the experience.
- Make the faction selection feel more like a "character creation" menu.

## Verification Plan
- **Visual Check**: Does it breathe? Is it aligned?
- **Browser Tool**: Verify the new layout and spacing.

<!-- antigravity-source-v1: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 -->
