# FE-P3: Login & Auth Pages

**Priority:** P1 — High (first impression for new users)
**Phase:** 3 of 10
**Depends on:** FE-P1 (Design System Foundation)

---

## Problem Statement

The login page is a plain gray form on a black background. No branding, no visual impact, no atmosphere. The register page mirrors the same bare layout. For a trading platform, the auth experience should convey trust, sophistication, and professionalism.

**Impact:** First impression for every new user. Sets the tone for the entire product experience.

---

## Acceptance Criteria

- [ ] Login page has full-bleed background with atmosphere (gradient mesh, subtle pattern, or financial motif)
- [ ] Branded logo/wordmark prominently displayed
- [ ] Tagline or value proposition visible
- [ ] Form card has glass-morphism or elevated card treatment with depth
- [ ] Input fields have polished focus states (glow, ring animation)
- [ ] Submit button has loading state with spinner/pulse
- [ ] Error messages are styled inline (not plain red text)
- [ ] Register page matches login design language
- [ ] "Remember me" checkbox option
- [ ] Smooth transition between login and register
- [ ] Password visibility toggle
- [ ] Form validation (email format, password min length) with inline errors

---

## Implementation Details

### Visual Direction
- Split layout OR centered card with atmospheric background
- Background: animated gradient mesh or geometric grid pattern (CSS-only)
- Form card: subtle border, backdrop blur, shadow depth
- Accent color used strategically (submit button, links, focus rings)

### Files to Modify
| File | Change |
|------|--------|
| `web/src/pages/LoginPage.tsx` | Full visual redesign |
| `web/src/pages/RegisterPage.tsx` | Match login design language |
| `web/src/index.css` | Background animation keyframes, glass effects |

---

## Out of Scope
- OAuth/SSO integration
- Password reset flow
- 2FA setup
