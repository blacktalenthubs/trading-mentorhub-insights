# Trading Page UX Issues — To Address

**Created**: 2026-04-08
**Priority**: Medium
**Status**: Backlog

## Issues

### 1. Score Badges (A/B/C Letter Grades)
- Current: Letter grades (A, B, C) with colored circles look confusing
- Problem: Users don't intuitively know what "51 Strong" or "45 Weak" means with a letter
- Fix: Replace with progress bar, colored dots, or just the numeric score with color coding (green >70, yellow 50-70, red <50)
- Reference: Webull uses simple numeric scores without letter grades

### 2. Watchlist Panel Width
- Current: Fixed width panel takes ~25% of screen, can collapse but loses all context
- Problem: Chart area feels cramped, especially on smaller screens
- Fix: Make panel resizable (drag handle like Webull) or make it narrower by default with compact rows
- Reference: Webull allows dragging panel width, shows symbol + price + change in compact rows

### 3. Light Theme Broken
- Current: Enabling light theme makes text invisible, charts unreadable
- Problem: CSS variables for light mode not properly defined — text colors, background colors, border colors all need light-mode values
- Fix: Audit all CSS custom properties (--surface-1, --text-primary, --border-subtle, etc.) and define proper light-mode values. Test every component.
- Reference: Webull's light theme uses soft grays, dark text, subtle borders — clean and readable

### 4. General Trading Page Polish
- Sector rotation bar could be more compact
- AI Coach panel on right side could have better spacing
- Signal Feed cards could be more scannable
- Mobile layout needs attention (panels stack poorly)

## Notes
- These are all pre-existing issues, not related to AI CoPilot feature
- Light theme fix is the most impactful — many users prefer light mode
- Resizable watchlist panel requires a drag handle implementation (react-resizable or custom)
