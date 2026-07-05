# Sub-spec E — Apps Download

Part of the Landing Redesign master spec.

## Goal
Route visitors to the mobile and desktop apps — the "your desk, everywhere" promise for a
professional who's alerted on the phone and studies on the desktop.

## What it shows
Header: "Alerts on your phone. Full charting on your desktop." Sub: one account, every screen.
Three targets: **iPhone & iPad** (App Store) · **Android** (Google Play) · **Mac & Windows**
(desktop app). Plus hero badges (Sub-spec A) pointing here.

## Requirements
- **E1** Real download URLs for each platform that is live. **[NEEDS INPUT: iOS / Android / desktop
  URLs; which are shipped today.]**
- **E2** If a platform isn't live yet, show "Coming soon" rather than a dead link — never a broken
  CTA.
- **E3** Value per platform: mobile = get pinged the instant a setup fires; desktop = study the
  chart + levels.
- **E4** Downloading a file requires the user's action off our link (store/installer) — no silent
  download from the page.

## Acceptance
- Every badge/button resolves to a real destination or an honest "coming soon" (SC4).
- Consistent across the hero badges and this section.

## Reuse / build notes
- New section. Real store-badge assets (embed as self-contained SVG/data-URI for the marketing page).
- Desktop app is the existing Electron build (per PWA/desktop notes); confirm distribution URL.

## Effort: S (blocked on the real links)
