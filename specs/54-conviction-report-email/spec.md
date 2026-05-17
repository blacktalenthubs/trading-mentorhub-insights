# Spec 54 — Daily Conviction Report Email Digest (2026-05-16)

**Status**: Draft — buildable child of [Spec 48](../48-v3-cleanup-and-paid-ai-revamp/spec.md) (V3 manifest).
**Depends on**: [Spec 49 (V1 Cleanup)](../49-v1-cleanup/spec.md) — relies on the V2 `triage-agent/eod.py` cron path being clean and stable; independent of 50/51/52/53.
**Touches**: `triage-agent/eod.py` (data source — read-only), `api/app/routers/billing.py` (opt-in tracking), `web/src/pages/PublicEODReportPage.tsx` (deep-link target), email delivery (existing transactional provider).

## Why this spec exists

The `triage-agent/eod.py` cron already produces the EOD conviction recap and posts it to Telegram every trading day at market close. The same content, repackaged as a paid daily email digest with deep links into the in-product `PublicEODReportPage`, is a real subscription product: traders pay for "tomorrow's prep in my inbox tonight." This spec is intentionally narrow — zero new infrastructure, pure repackaging of an existing artifact into a billable surface with opt-in management.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Daily digest in inbox within 30 minutes of close (Priority: P1)

A Pro-tier subscriber opts in to the Daily Conviction Report. After market close (16:00 ET) the existing EOD cron fires. Within 30 minutes the subscriber receives an email containing the day's conviction-rated alerts, formatted for email readability, with deep links into the in-product `PublicEODReportPage` for full detail.

**Why this priority**: The entire feature.

**Independent Test**: With a Pro account opted in, observe a trading day's close. Verify the email arrives within 30 minutes of 16:00 ET, contains all alerts from the day's `triage-agent/eod.py` output, is formatted readably in major email clients (Gmail, Outlook, Apple Mail), and that every deep link resolves to the corresponding `PublicEODReportPage` entry.

**Acceptance Scenarios**:

1. **Given** a Pro subscriber opted in, **When** the market close cron fires (16:00 ET), **Then** the digest email arrives in their inbox within 30 minutes.
2. **Given** the digest email is opened, **When** the subscriber clicks any alert in the digest, **Then** they deep-link into the corresponding entry on `PublicEODReportPage`.
3. **Given** the email renders in Gmail, Outlook, and Apple Mail, **When** a tester inspects it on each, **Then** layout, links, and content are readable in all three with no broken images or empty content blocks.

---

### User Story 2 — Pro-tier opt-in management (Priority: P1)

A Pro subscriber finds the Daily Conviction Report opt-in in Settings → Notifications (or equivalent). They opt in once, receive subsequent digests, can opt out at any time, and the opt-out takes effect for the next scheduled send (no orphaned email after opt-out).

**Why this priority**: Without easy opt-in/opt-out, this becomes a deliverability liability.

**Independent Test**: Opt in from Settings; verify the next day's digest arrives. Opt out from Settings; verify the next day's digest does NOT arrive.

**Acceptance Scenarios**:

1. **Given** a Pro subscriber, **When** they toggle "Daily Conviction Report" on in Settings, **Then** the opt-in is recorded and a confirmation appears in the UI.
2. **Given** an opted-in subscriber, **When** they toggle the opt-in off, **Then** subsequent scheduled sends MUST NOT include their email; the opt-out MUST take effect within 5 minutes of the toggle.
3. **Given** every digest email, **When** the subscriber views the footer, **Then** an unsubscribe link is present that takes effect within 5 minutes of being clicked.

---

### User Story 3 — Free-tier paywall on opt-in (Priority: P1)

A Free-tier user attempts to opt in to the Daily Conviction Report. They see a paywall pointing to the Pro upgrade before the opt-in is recorded. No digest is ever sent to a Free account.

**Why this priority**: Without the paywall, the feature isn't paid.

**Independent Test**: From a Free account, attempt to toggle on the opt-in; verify a paywall appears and no opt-in record is created.

**Acceptance Scenarios**:

1. **Given** a Free-tier user, **When** they attempt to toggle on the digest opt-in, **Then** they see a paywall pointing to the Pro upgrade before any opt-in is recorded.
2. **Given** a Free account, **When** the daily cron runs, **Then** no digest is sent to that account.

---

### User Story 4 — Optional weekly digest variant (Priority: P3)

In addition to daily, a subscriber can opt for a weekly summary digest delivered Sunday evening covering the previous five trading days. This is a low-effort variant of the daily flow.

**Why this priority**: Some subscribers will prefer weekly. P3 because daily is enough to validate willingness-to-pay; weekly is a polish iteration.

**Independent Test**: Opt in to weekly only; verify daily digests do NOT arrive and a single weekly digest arrives Sunday evening covering the prior 5 trading days.

**Acceptance Scenarios**:

1. **Given** a Pro subscriber opted in to weekly only, **When** the daily cron fires, **Then** no daily digest is sent.
2. **Given** the weekly cron fires Sunday evening, **When** the subscriber checks their inbox, **Then** they receive a single weekly digest covering the prior 5 trading days.

---

### Edge Cases

- **Email delivery failure to a specific recipient** (bounce, blocklist) — bounce handling per the email provider's standard flow; persistent bouncers are auto-suspended from the digest list with an in-app notice on next login.
- **Cron runs but `triage-agent/eod.py` produced zero alerts** (slow market day) — digest still sends with a brief "quiet day — no conviction-rated setups today" body rather than skipping silently.
- **Cron fails entirely** — digest is skipped for that day; subscribers see no email; an operator alert fires (existing monitoring path). Catch-up digests are NOT sent retroactively.
- **Subscriber opted in after market close but before send time** — they receive that day's digest if opt-in landed ≥10 minutes before send; otherwise the next trading day's.
- **API keys / magic-link tokens / session tokens in email content** — Spec 11's hard rule applies: 0 credentials in any digest. Automated regression on every release.
- **Timezone preference** — v1 sends in ET (market close local); per-user timezone selection is out of scope.

## Requirements *(mandatory)*

### Functional Requirements

#### Source and delivery

- **FR-601**: A new email-delivery job MUST consume `triage-agent/eod.py`'s output and send a digest email to all opted-in Pro subscribers within 30 minutes of market close (16:00 ET).
- **FR-602**: Each alert in the digest MUST deep-link to its corresponding entry on `PublicEODReportPage`.
- **FR-603**: The digest MUST render readably in Gmail, Outlook, and Apple Mail (mobile and desktop). Layout MUST degrade gracefully on text-only clients.
- **FR-604**: On a trading day with zero conviction-rated alerts, the digest MUST send with a brief "quiet day — no conviction-rated setups today" body rather than skipping silently.
- **FR-605**: When the cron fails entirely, no digest MUST be sent for that day; existing operator monitoring catches the failure. Catch-up digests MUST NOT be sent retroactively.

#### Opt-in management

- **FR-606**: A Pro subscriber MUST be able to opt in to the Daily Conviction Report from Settings → Notifications (or equivalent surface).
- **FR-607**: Opt-out MUST take effect for the next scheduled send within 5 minutes of the toggle being changed.
- **FR-608**: Every digest email MUST contain an unsubscribe link that takes effect within 5 minutes of being clicked, per email-compliance norms.
- **FR-609**: A Free-tier user attempting to toggle on the opt-in MUST see a paywall pointing to the Pro upgrade BEFORE any opt-in record is created. No digest MUST ever be sent to a Free account.

#### Optional weekly variant

- **FR-610**: A Pro subscriber MAY opt in to a weekly summary digest delivered Sunday evening covering the previous 5 trading days, in addition to or in place of the daily digest. Implementation of the weekly variant is P3.

#### Security and privacy

- **FR-611**: Digest emails MUST NOT contain API keys, magic-link tokens, session tokens, or any other credential. Verified by automated regression on every release.
- **FR-612**: Persistent email bouncers MUST be auto-suspended from the digest list per email-provider standard bounce handling, with an in-app notice on next login.

### Key Entities *(if applicable)*

- **Conviction Digest Subscription**: A user-account-scoped record indicating opt-in status (daily / weekly / both / none) and opt-in timestamp.
- **Conviction Digest Email**: An individual email send. Carries owning user, send timestamp, source-cron run ID, delivery status (sent / bounced / opened).

## Success Criteria *(mandatory)*

- **SC-601**: ≥99% of digest emails arrive in the subscriber's inbox within 30 minutes of market close.
- **SC-602**: 0 cases of API keys, magic-link tokens, or session tokens appearing in any digest, verified by automated regression on every release.
- **SC-603**: 0 cases of a digest being sent to a Free-tier account.
- **SC-604**: ≥90% of digests render readably (no broken layout, no broken images) in Gmail, Outlook, and Apple Mail across mobile + desktop, verified by Email-on-Acid-style visual regression.
- **SC-605**: Opt-out takes effect within 5 minutes in 99% of test runs.
- **SC-606**: ≥30% of Pro subscribers opt in to the daily digest within 30 days of feature launch.
- **SC-607**: ≥40% open rate on the first 100 digests sent (industry-strong; tracks engagement, not strictly required at launch).

## Assumptions

- The platform already uses an established transactional email provider for magic-link auth (Spec 49's V2 stack inherits this); the digest job sends through the same provider.
- `triage-agent/eod.py` output schema is stable; if it changes, this spec coordinates with the change rather than locking the schema.
- The digest job runs as part of the existing `triage-agent` cron infrastructure rather than introducing a new scheduler.
- Per-user timezone preferences are out of scope; v1 sends in ET.
- Open/click tracking is implemented via the email provider's standard mechanism; no custom tracking pixel work.
- Catch-up digests after a cron failure are explicitly out of scope; missed days are missed.
- The weekly variant (FR-610) is acceptable as a P3 follow-up to the daily.
- Email-provider standard bounce handling is sufficient for FR-612; custom suppression logic is out of scope for v1.
