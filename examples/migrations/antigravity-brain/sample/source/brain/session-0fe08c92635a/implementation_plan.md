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
