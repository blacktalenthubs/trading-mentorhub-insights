# Hero Stat Fallback Contract — Spec 50 FR-202b

**Purpose**: Defines the exact render output for the hero live-stat in every possible state. FR-202b explicitly forbids `NaN%` or empty stat slots; this contract is how we keep that promise.

---

## The 3-state machine

```ts
type TrackRecordState =
  | { status: "loading" }
  | { status: "ok"; data: TrackRecord }
  | { status: "error" };
```

Initial state: `{ status: "loading" }`.

Transitions:
- Fetch succeeds with 2xx + valid JSON → `{ status: "ok", data }`
- Fetch fails (network, 5xx, JSON parse fail, missing required fields) → `{ status: "error" }`
- API response has `total_signals === 0` → still **ok**, NOT error. (0 signals is real data, ship it.)

---

## Render branches

### Branch A — Loading

Trigger: state.status === "loading" (first ~500 ms after mount, until fetch resolves).

**Render**:
```
┌────────────────────────────────────────┐
│ Track record loading…                  │
│ (subtle pulse animation, 1.5s loop)    │
└────────────────────────────────────────┘
```

CSS: `text-text-muted` (lower contrast than the happy-path stat, so users don't read it as a real number). Pulse via Tailwind `animate-pulse`. Respect `prefers-reduced-motion` — no animation when set.

### Branch B — Happy path (data with signals)

Trigger: state.status === "ok" && state.data.total_signals > 0 && Number.isFinite(state.data.win_rate).

**Render**:
```
┌────────────────────────────────────────┐
│ {pct(win_rate)}% win rate              │  ← big, bold, accent color
│ last 90 days · {M} signals             │  ← small, muted
└────────────────────────────────────────┘
```

`pct(x)` = `Math.round(x * 100)` — integer percent, no decimals. If win_rate is 0.6234 → "62%".

`{M}` = `state.data.total_signals.toLocaleString()` (formats thousands separator).

### Branch C — 0-data path (data but no signals yet)

Trigger: state.status === "ok" && state.data.total_signals === 0.

**Render**:
```
┌────────────────────────────────────────┐
│ Track record building                  │  ← regular weight, accent dim
│ first signals incoming · v2 live       │  ← small, muted
└────────────────────────────────────────┘
```

This is the **only** "win-rate-free" copy. Local dev hits this because the SQLite DB is empty (per Spec 49 smoke). Production should never hit this; if it does for 24+ hours, something is wrong with the alerts table.

### Branch D — Error path

Trigger: state.status === "error" (network failure, 5xx, parse error, schema validation fail).

**Render**:
```
┌────────────────────────────────────────┐
│ Track record unavailable right now     │  ← regular weight, text-muted
│ [Refresh] link                         │  ← accent text link, refetches
└────────────────────────────────────────┘
```

The Refresh link calls the same fetch again. No automatic retry — keep the implementation simple.

---

## Schema validation (the "valid JSON" gate)

Before transitioning to `{ status: "ok" }`, the fetch must verify:

```ts
function isValidTrackRecord(x: unknown): x is TrackRecord {
  if (typeof x !== "object" || x === null) return false;
  const r = x as Record<string, unknown>;
  return (
    typeof r.period_days === "number" &&
    typeof r.total_signals === "number" &&
    typeof r.wins === "number" &&
    typeof r.losses === "number" &&
    typeof r.win_rate === "number" &&
    Number.isFinite(r.win_rate)
  );
}
```

If validation fails → state goes to `{ status: "error" }`, NOT a half-rendered "ok" with missing fields.

---

## Why this matters

If we just write `{data.win_rate * 100}%` and data is null/undefined/has bad shape, we ship `NaN%` to the DOM. FR-202b says no, and SC-203 audits for it. The 3-state machine is the entire reason we don't fail.

The same pattern applies to the proof-section StatGrid (uses the same state). One hook, two consumers.

---

## Test cases (for QA, not automated unless added later)

| State | Triggered by | Expected render |
|-------|--------------|-----------------|
| Loading | `fetch` mocked to never resolve | "Track record loading…" |
| Happy path | `fetch` → `{win_rate: 0.62, total_signals: 47, ...}` | "62% win rate · last 90 days · 47 signals" |
| 0-data | `fetch` → `{win_rate: 0.0, total_signals: 0, ...}` | "Track record building · first signals incoming · v2 live" |
| Error 500 | `fetch` → status 500 | "Track record unavailable right now · Refresh" |
| Network fail | `fetch` rejects | Same as 500 |
| Bad JSON | `fetch` → `"not json"` | Same as 500 (parse fail) |
| Missing field | `fetch` → `{}` | Same as 500 (schema fail) |
| `NaN` win_rate | `fetch` → `{win_rate: NaN, ...}` | Same as 500 (`Number.isFinite` fails) |
