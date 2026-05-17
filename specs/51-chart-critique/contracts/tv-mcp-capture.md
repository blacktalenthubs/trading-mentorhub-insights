# Contract — TradingView MCP capture integration

**Phase**: C (after Phase A image upload is shipped)
**Affected files**: `web/src/pages/AICoPilotPage.tsx`, optionally `api/app/routers/intel.py` (depending on transport choice)

## What this is

TradingView MCP exposes `mcp__tradingview__capture_screenshot` (per the connected MCP server's tool list). It captures the user's currently-open TradingView Desktop chart and returns a PNG. FR-309 wants this wired so the candidate can hit "Capture from TradingView" instead of pasting.

## Transport choice (two options)

### Option A — Browser → MCP via local bridge (preferred if possible)

The MCP server runs on the user's machine (TradingView Desktop is local). The browser cannot directly call MCP. Options:
- A local bridge service (e.g., a small WebSocket the user runs alongside the dev/desktop app)
- A Capacitor plugin in the iOS/desktop bundle that talks to MCP natively
- (Not practical for web in this revamp.)

This is **out of scope** for Phase C as a pure web feature. The Phase C web implementation falls back to Option B.

### Option B — Backend invokes MCP

The backend has its own MCP client (already used by triage agent indirectly for tools). Workflow:
1. Frontend clicks "Capture from TradingView."
2. Frontend POSTs `{kind: "tv_capture", hint_symbol?}` to a NEW endpoint `POST /api/v1/intel/analyze-chart/tv-capture`.
3. Backend calls `mcp__tradingview__capture_screenshot` via its MCP client.
4. Backend feeds the returned image bytes into the existing image-input pipeline.
5. SSE stream returns to the frontend.

**Problem**: The MCP server is the *user's* TradingView, not a shared one. The backend can't trigger the user's local TradingView. So Option B only works if:
- The user is running their own backend (self-hosted), OR
- There's a shared TradingView account the platform uses to capture on the user's behalf (operationally weird)

### Realistic Phase C scope

Given the above, **Phase C as written in spec 51 (FR-309) needs operator review**. The likely workable shapes:

1. **Defer**: skip Phase C entirely. Paste/upload (Phase A) is the v1 web flow. TV MCP is a fast-follow.
2. **Capacitor-only**: Phase C ships only in the iOS/desktop Capacitor build (which CAN talk to a local MCP server on the same device). Web stays paste/upload-only.
3. **Browser extension**: build a Chrome extension that calls TV's web UI's "Take Snapshot" feature and POSTs to the backend. Different scope; not what spec 51 implies.

**Recommendation**: Phase C deferred until after Phase A ships and the operator confirms which transport is wanted. Spec 51's FR-310 ("TV MCP unavailable → paste fallback") effectively means Phase A is enough on its own.

## What to do in this contract

Document the gap. Don't write code yet. Phase A (paste/upload) is the entire Phase 0–1 work for spec 51 as currently scoped.

## If Phase C does happen later

API endpoint (Option B variant):
```
POST /api/v1/intel/analyze-chart/tv-capture
Body: { hint_symbol?: string, hint_timeframe?: string }
Response: SSE stream identical to /analyze-chart
```

The endpoint invokes the MCP `capture_screenshot` tool, receives bytes, then runs through the existing vision pipeline from Phase A. No new engine work.

Frontend addition (Option B variant):
```tsx
async function captureFromTV() {
  setStreaming(true);
  const res = await fetch(`${API_HOST}/api/v1/intel/analyze-chart/tv-capture`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ hint_symbol: activeSymbol, hint_timeframe: timeframe }),
  });
  // process SSE the same way
}
```

A "Capture from TradingView" button sits next to the "Paste/Upload chart" button. If the backend returns `error: "tv_mcp_unavailable"`, the button shows a graceful "TradingView Desktop not reachable — try paste instead" message (FR-310).
