# Frontend & SaaS Stack Research for Trade Analytics Platform

**Date:** 2026-02-28
**Purpose:** Evaluate modern frontend frameworks, real-time data patterns, charting libraries, auth, billing, and migration strategy for taking trade-analytics from Streamlit prototype to production SaaS.

---

## 1. Frontend Framework Selection

### Recommendation: **Next.js 15+ (App Router)**

| Framework  | Ecosystem | Performance | Real-Time | Hiring Pool | Verdict |
|-----------|-----------|-------------|-----------|-------------|---------|
| Next.js 15+ | Massive (React) | Good (RSC reduces bundle) | Excellent | Largest | **Winner** |
| SvelteKit  | Growing | Best (no virtual DOM, 40% smaller bundles) | Good | Small | Strong alternative |
| Remix (React Router v7) | Medium | Good | Good | Medium | Good for form-heavy |

**Why Next.js wins for this use case:**

1. **Ecosystem depth** -- React has the most charting, UI component, and trading-specific libraries. TradingView Lightweight Charts has first-class React examples. shadcn/ui provides production-grade UI primitives.
2. **Clerk, Stripe, Vercel integrations** -- The entire SaaS toolchain (auth, billing, deployment) has first-party Next.js support.
3. **Hiring and community** -- If you ever bring on help, React/Next.js developers are 5-10x more available than Svelte developers.
4. **Server Components** -- React Server Components let you run Python-heavy data fetching on the server side, reducing client bundle and keeping API keys server-side.
5. **Incremental adoption** -- You can start with a few pages and add complexity over time. No all-or-nothing migration.

**When SvelteKit would be better:** If you are the sole developer forever and want the smallest, fastest possible bundle. SvelteKit compiles to vanilla JS with zero runtime, handles 1,200 RPS vs Next.js at 850 RPS, and ships 20-40% smaller bundles. But the ecosystem tradeoff is significant for a trading platform.

### Key Architecture Decisions

```
Next.js App Router (v15+)
├── /app                    # App Router pages
│   ├── /(marketing)        # Landing, pricing (static/SSG)
│   ├── /(dashboard)        # Authenticated dashboard (SSR + client)
│   │   ├── /signals        # Signal feed (SSE real-time)
│   │   ├── /charts         # TradingView charts (client component)
│   │   ├── /analytics      # Portfolio analytics (server component)
│   │   └── /alerts         # Alert management
│   └── /api                # API routes (proxy to FastAPI)
├── /components             # shadcn/ui + custom components
└── /lib                    # Utilities, hooks, API client
```

---

## 2. Real-Time Data Architecture

### Recommendation: **Hybrid SSE + WebSocket**

| Method    | Direction | Latency | Complexity | Browser Support | Reconnection |
|-----------|-----------|---------|------------|-----------------|--------------|
| SSE       | Server->Client | ~50ms | Low | Excellent | Built-in |
| WebSocket | Bidirectional | ~0.5ms | Medium | Excellent | Manual |
| Polling   | Client->Server | 1-30s | Lowest | Universal | N/A |

**Practical architecture for trade-analytics:**

```
┌─────────────────┐     SSE (read-only)      ┌──────────────┐
│  Price Feeds    │ ──────────────────────── │  Dashboard   │
│  Signal Alerts  │                           │  (Browser)   │
│  Market Status  │                           │              │
└─────────────────┘                           │              │
                                              │              │
┌─────────────────┐     WebSocket (if needed) │              │
│  Alert Config   │ ◄───────────────────────▶ │              │
│  Order Entry    │    (bidirectional)         │              │
└─────────────────┘                           └──────────────┘
```

**Why SSE for most of this platform:**

- Price feeds, signal alerts, and market regime updates are **unidirectional** (server to client). SSE is purpose-built for this.
- SSE runs on port 80/443 with no firewall issues, no proxy configuration needed.
- SSE has **built-in browser reconnection** -- if the connection drops, the browser automatically reconnects and picks up where it left off via `Last-Event-ID`.
- With HTTP/2, SSE multiplexes over a single TCP connection (no 6-connection limit from HTTP/1.1).
- FastAPI supports SSE natively via `StreamingResponse` or the `sse-starlette` package.

**When to add WebSocket:** Only if you add order entry or real-time collaborative features (shared watchlists, etc.). For a signal/analytics platform, SSE handles 95% of use cases.

**FastAPI SSE pattern:**
```python
from sse_starlette.sse import EventSourceResponse

@app.get("/api/signals/stream")
async def signal_stream(request: Request):
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            signal = await signal_queue.get()
            yield {"event": "signal", "data": signal.model_dump_json()}
    return EventSourceResponse(event_generator())
```

**Next.js client pattern:**
```typescript
useEffect(() => {
  const source = new EventSource('/api/signals/stream');
  source.addEventListener('signal', (e) => {
    const signal = JSON.parse(e.data);
    setSignals(prev => [signal, ...prev]);
  });
  return () => source.close();
}, []);
```

---

## 3. Charting Libraries

### Recommendation: **TradingView Lightweight Charts (primary) + Recharts (secondary)**

| Library | Size | Real-Time | Financial Charts | Learning Curve | License |
|---------|------|-----------|-----------------|----------------|---------|
| **TradingView Lightweight Charts** | 45 KB | Excellent | Purpose-built | Low (for trading) | Apache 2.0 |
| Apache ECharts | ~1 MB | Good | Supported | Steep | Apache 2.0 |
| Recharts | ~150 KB | Moderate | Basic | Low | MIT |
| Plotly.js | ~3 MB | Moderate | Supported | Medium | MIT |
| D3.js | ~250 KB | Manual | Manual | Very High | ISC |

**Why TradingView Lightweight Charts:**

1. **45 KB** -- Smaller than most images. Critical for dashboard load time.
2. **Canvas-based rendering** -- 60+ FPS with 10,000+ bars. No DOM manipulation, no layout thrashing.
3. **Purpose-built for trading** -- Candlestick, OHLC, line, area, histogram, and baseline series out of the box. Volume overlays, crosshairs, price scales all built-in.
4. **Real-time `series.update()`** -- First-class API for streaming data. No full re-render needed.
5. **React integration** -- Official examples and community wrappers available.
6. **Same tech as TradingView.com** -- The full TradingView platform uses their own charting engine. Lightweight Charts is the open-source version.

**Use Recharts for:** Non-financial charts (portfolio allocation pie charts, P&L bar charts, win rate histograms). Recharts is simple, declarative, and works well with React for standard business charts.

**Integration example:**
```typescript
import { createChart, CandlestickSeries } from 'lightweight-charts';

function TradingChart({ data, onCrosshairMove }) {
  const chartRef = useRef(null);

  useEffect(() => {
    const chart = createChart(chartRef.current, {
      width: 800, height: 400,
      layout: { background: { color: '#1a1a2e' }, textColor: '#e0e0e0' },
      grid: { vertLines: { color: '#2a2a3e' }, horzLines: { color: '#2a2a3e' } },
    });
    const series = chart.addSeries(CandlestickSeries);
    series.setData(data);

    // Real-time updates via SSE
    const source = new EventSource('/api/prices/stream');
    source.addEventListener('price', (e) => {
      series.update(JSON.parse(e.data));
    });

    return () => { source.close(); chart.remove(); };
  }, []);

  return <div ref={chartRef} />;
}
```

---

## 4. Backend API Architecture

### Recommendation: **FastAPI (keep existing) + OpenAPI-generated TypeScript client**

| Option | Language | Async | Auto Docs | Type Safety to Frontend | Fit |
|--------|----------|-------|-----------|------------------------|-----|
| **FastAPI** | Python | Native | OpenAPI | Via codegen | **Best** |
| Django REST | Python | Partial | Via drf-spectacular | Via codegen | Overkill |
| tRPC | TypeScript | Native | Built-in | End-to-end | Wrong language |
| GraphQL | Any | Varies | Introspection | Via codegen | Overengineered |

**Why FastAPI is the right choice:**

1. **You already have a Python analytics engine.** Your parsers, models, analytics modules are all Python. Rewriting to TypeScript (tRPC) would be insane.
2. **Pydantic models = OpenAPI schema = TypeScript types.** Use `openapi-typescript` or `orval` to auto-generate a fully typed TypeScript API client from your FastAPI OpenAPI spec. Zero manual type duplication.
3. **Async-native** -- Critical for SSE streams, concurrent data fetching, and WebSocket support.
4. **Production-proven** -- FastAPI is the standard Python API framework in 2026.

**Architecture pattern:**

```
┌──────────────────┐        ┌──────────────────┐        ┌──────────────────┐
│   Next.js        │        │   FastAPI         │        │   Data Layer     │
│   (Vercel/VPS)   │──API──▶│   (Docker/Cloud)  │───────▶│   SQLite/Postgres│
│                  │        │                   │        │   Redis (cache)  │
│   - React UI     │        │   - REST API      │        │   File storage   │
│   - SSR/RSC      │        │   - SSE streams   │        │                  │
│   - API proxy    │        │   - Analytics     │        │                  │
│                  │        │   - Signal engine  │        │                  │
└──────────────────┘        └──────────────────┘        └──────────────────┘
```

**Type-safe API client generation:**
```bash
# Generate TypeScript client from FastAPI's OpenAPI spec
npx openapi-typescript http://localhost:8000/openapi.json -o src/lib/api/schema.ts
# Or use orval for full client with react-query hooks
npx orval --input http://localhost:8000/openapi.json --output src/lib/api/
```

---

## 5. Authentication for SaaS

### Recommendation: **Clerk**

| Provider | Multi-Tenant | Pricing | Next.js DX | Pre-built UI | Stripe Integration |
|----------|-------------|---------|------------|-------------|-------------------|
| **Clerk** | Built-in orgs | $0.02/MAU (10K free) | Best | Full suite | Native billing |
| Auth0 | Organizations | $0.07/MAU (growth penalty) | Good | Limited | Manual |
| Supabase Auth | DIY with RLS | $0.00325/MAU (50K free) | Moderate | None | Manual |
| Custom (JWT) | Full control | Dev time only | N/A | None | Manual |

**Why Clerk for trade-analytics SaaS:**

1. **Pre-built UI components** -- `<SignIn />`, `<UserButton />`, `<OrganizationSwitcher />`, `<PricingTable />` are production-ready React components. Weeks of UI work eliminated.
2. **Native Stripe billing integration** -- Clerk Billing connects directly to Stripe. You define subscription plans in Clerk's dashboard, and it handles:
   - Subscription creation/upgrade/downgrade
   - Payment method management
   - Pricing table display
   - Entitlement checks (`user.subscription.plan === 'pro'`)
3. **Multi-tenant organizations** -- Built-in support for teams/organizations with member invitations, role management (admin/member/custom), and domain verification for auto-join.
4. **10,000 MAU free** -- Generous free tier for bootstrapping. At scale, $0.02/MAU is reasonable.
5. **Next.js middleware** -- Protect routes with a single `clerkMiddleware()` call. No custom auth logic.

**Warning about Auth0:** Multiple documented cases of 15x bill spikes from small user growth due to tier-based pricing. 34% of developers report migrating away from Auth0 citing pricing as the primary reason.

**Subscription tier model for trade-analytics:**

```
Free Tier ($0/mo):
  - Delayed signals (15-min delay)
  - Basic charts
  - 3 alerts

Pro Tier ($29-49/mo):
  - Real-time signals
  - Advanced analytics
  - Unlimited alerts
  - Market regime detection

Enterprise ($99-199/mo):
  - API access
  - Custom signal parameters
  - Priority support
  - Team/organization features
```

---

## 6. Billing & Subscriptions

### Recommendation: **Clerk Billing (wraps Stripe) or Direct Stripe**

**Option A: Clerk Billing (Simplest)**
- Same cost as Stripe Billing directly (0.7% per transaction + Stripe fees)
- No separate Stripe Billing setup needed
- Pre-built `<PricingTable />` and `<ManageSubscription />` components
- Entitlements tied directly to Clerk user/organization
- Sandbox mode works without Stripe account during development

**Option B: Direct Stripe Integration (More Control)**
- Use `stripe-node` SDK with Checkout Sessions (hosted payment page)
- Webhook-driven architecture for subscription lifecycle
- Use Vercel's `nextjs-subscription-payments` template as starter

**Key Stripe patterns for this SaaS:**

```
┌─────────────┐     Checkout Session      ┌─────────────┐
│  User clicks│ ─────────────────────────▶ │  Stripe     │
│  "Upgrade"  │                            │  Checkout   │
└─────────────┘                            └──────┬──────┘
                                                  │
                                                  │ Webhook
                                                  ▼
┌─────────────┐     Update entitlements    ┌──────────────┐
│  Dashboard  │ ◄──────────────────────── │  /api/webhook │
│  unlocked   │                            │  handler     │
└─────────────┘                            └──────────────┘
```

**Critical implementation details:**
- Always use `checkout.session.completed` webhook for fulfillment (not redirect callbacks)
- Use idempotency keys to prevent duplicate charges on retries
- Handle `customer.subscription.updated` and `customer.subscription.deleted` webhooks
- Stripe Smart Retries handle failed payment retries and dunning emails automatically

---

## 7. Real-World Platform Tech Stacks

### TradingView
- **Frontend:** Custom proprietary charting engine (Canvas-based), React for non-chart UI
- **Backend:** Python (full-stack teams include Python developers)
- **Infrastructure:** AWS (EC2, Route 53)
- **Charting:** Their own engine (Lightweight Charts is the open-source version)
- **Teams:** Named after space shuttles (Vostok, Firefly, Hope, X, Falcon)
- Source: [StackShare](https://stackshare.io/tradingview/tradingview), [Wappalyzer](https://www.wappalyzer.com/lookup/tradingview.com/)

### QuantConnect
- **Engine:** LEAN (open-source, C# + Python)
- **Frontend:** Custom web terminal
- **Infrastructure:** Kubernetes scaling, SOC 2 Type II certified, AES-256 encryption
- **Scale:** 15,000 backtests/day, $45B notional volume/month
- **Protocol:** FIX 5.0 SP2 for institutional clients
- Source: [QuantConnect](https://www.quantconnect.com/), [LEAN GitHub](https://github.com/QuantConnect/Lean)

### Common Pattern Across Fintech Platforms
- Canvas-based charting (not SVG/DOM) for performance
- Python for analytics/ML backend
- React for frontend shell
- WebSocket for real-time price data
- REST API for historical data and configuration
- Redis for caching and pub/sub
- PostgreSQL for persistent storage

---

## 8. Migration Path: Streamlit to Production SaaS

### Recommendation: **Strangler Fig Pattern -- Incremental Migration**

Do NOT rewrite everything at once. The smartest path is to extract your Python analytics into a FastAPI service first, then build the Next.js frontend incrementally while keeping Streamlit running.

### Phase 1: Extract API Layer (2-3 weeks)
**Keep Streamlit running. Add FastAPI alongside it.**

```
Current:
┌──────────────────────────────┐
│  Streamlit (monolith)        │
│  - UI + Analytics + Data     │
└──────────────────────────────┘

Phase 1:
┌──────────────────┐     ┌──────────────────┐
│  Streamlit       │────▶│  FastAPI          │
│  (UI only)       │     │  - Analytics API  │
└──────────────────┘     │  - Signal engine  │
                         │  - Data layer     │
                         └──────────────────┘
```

**What to do:**
1. Wrap existing analytics functions as FastAPI endpoints with Pydantic models
2. Add OpenAPI documentation (automatic with FastAPI)
3. Move database/data access into the API layer
4. Point Streamlit pages to call the API instead of direct function calls
5. Containerize both services with Docker Compose

**What you keep:** All your Python analytics code. It just gets proper API endpoints.

### Phase 2: Launch Next.js MVP (3-4 weeks)
**Build the most valuable pages first. Keep Streamlit for the rest.**

```
Phase 2:
┌──────────────────┐
│  Next.js         │────┐
│  - Signal feed   │    │     ┌──────────────────┐
│  - Charts        │    ├────▶│  FastAPI          │
│  - Auth/Billing  │    │     │  (same API)       │
└──────────────────┘    │     └──────────────────┘
                        │
┌──────────────────┐    │
│  Streamlit       │────┘
│  (admin/legacy)  │
└──────────────────┘
```

**Priority pages for Next.js:**
1. Landing page + pricing (static, SEO-important)
2. Signal dashboard with real-time feed (highest value feature)
3. Chart view with TradingView Lightweight Charts
4. Auth (Clerk) + billing (Stripe)
5. Alert management

**Keep in Streamlit (for now):**
- Admin tools
- Backtesting interface
- One-off analysis pages
- Anything only you use

### Phase 3: Complete Migration (4-6 weeks)
**Move remaining pages, sunset Streamlit for end users.**

```
Phase 3 (Production):
┌──────────────────┐           ┌──────────────────┐
│  Next.js         │───REST───▶│  FastAPI          │
│  (Vercel/VPS)    │◄──SSE────│  (Docker/Cloud)   │
│                  │           │                   │
│  - All UI        │           │  - Analytics API  │
│  - Clerk auth    │           │  - Signal engine  │
│  - Stripe billing│           │  - SSE streams    │
│  - TradingView   │           │  - Data pipeline  │
└──────────────────┘           └──────────────────┘
        │                              │
        │                              │
   ┌────▼────┐                  ┌──────▼──────┐
   │ Vercel  │                  │ PostgreSQL  │
   │ Edge    │                  │ Redis       │
   └─────────┘                  └─────────────┘
```

### Key Migration Principles

1. **API-first** -- Every feature gets an API endpoint before a UI. This means you can swap frontends without touching business logic.
2. **Feature flags** -- Use environment variables or a simple feature flag system to route users between Streamlit and Next.js during transition.
3. **Shared authentication** -- Clerk JWT tokens work with FastAPI via `python-jose` or `PyJWT` verification.
4. **Database migration** -- Move from SQLite to PostgreSQL early in Phase 1. Use Alembic for migrations.
5. **Keep Streamlit for internal tools** -- Streamlit is excellent for admin dashboards and data exploration. No need to migrate everything.

---

## Recommended Final Stack Summary

| Layer | Technology | Why |
|-------|-----------|-----|
| **Frontend Framework** | Next.js 15+ (App Router) | Ecosystem, integrations, hiring pool |
| **UI Components** | shadcn/ui + Tailwind CSS | Production-grade, customizable, accessible |
| **Financial Charts** | TradingView Lightweight Charts | 45KB, canvas-based, 60+ FPS, purpose-built |
| **Business Charts** | Recharts | Simple, declarative, React-native |
| **Real-Time Data** | SSE (primary), WebSocket (if needed) | Built-in reconnection, simpler than WS |
| **Backend API** | FastAPI (existing) | Already built, async, Pydantic, OpenAPI |
| **Type Safety** | openapi-typescript / orval | Auto-generated TS client from FastAPI spec |
| **Authentication** | Clerk | Pre-built UI, multi-tenant, Next.js native |
| **Billing** | Clerk Billing (wraps Stripe) | Zero-integration with auth, pre-built pricing table |
| **Database** | PostgreSQL + Redis | Production standard, caching + pub/sub |
| **Deployment** | Vercel (frontend) + Docker/Fly.io (API) | Optimized for Next.js + Python separation |
| **State Management** | React Query (TanStack Query) | Server state caching, refetching, SSE integration |

---

## Sources

- [Next.js vs Remix vs SvelteKit 2026 Comparison](https://www.nxcode.io/resources/news/nextjs-vs-remix-vs-sveltekit-2025-comparison)
- [SvelteKit vs Next.js 16: 2026 Performance Benchmarks](https://www.devmorph.dev/blogs/sveltekit-vs-nextjs-16-performance-benchmarks-2026)
- [TradingView Tech Stack - StackShare](https://stackshare.io/tradingview/tradingview)
- [TradingView Lightweight Charts](https://www.tradingview.com/lightweight-charts/)
- [Lightweight Charts React Tutorial](https://tradingview.github.io/lightweight-charts/tutorials/react/simple)
- [6 Best JavaScript Charting Libraries 2026](https://embeddable.com/blog/javascript-charting-libraries)
- [ECharts vs Lightweight Charts - StackShare](https://stackshare.io/stackups/echarts-vs-lightweight-charts)
- [Next.js FastAPI Template](https://www.vintasoftware.com/blog/next-js-fastapi-template)
- [Vercel Next.js FastAPI Starter](https://vercel.com/templates/next.js/nextjs-fastapi-starter)
- [Clerk vs Auth0 vs Supabase Auth Comparison](https://designrevision.com/blog/auth-providers-compared)
- [Clerk vs Supabase Auth](https://clerk.com/articles/clerk-vs-supabase-auth)
- [Auth Pricing Wars: Cognito vs Auth0 vs Firebase vs Supabase](https://zuplo.com/learning-center/api-authentication-pricing)
- [Clerk Billing for B2C SaaS](https://clerk.com/docs/nextjs/guides/billing/for-b2c)
- [Instant SaaS Billing with Clerk + Stripe](https://stripe.com/sessions/2025/instant-zero-integration-saas-billing-with-clerk-stripe)
- [Vercel nextjs-subscription-payments Template](https://github.com/vercel/nextjs-subscription-payments)
- [Best Next.js Subscription Templates 2026](https://designrevision.com/blog/best-nextjs-subscription-templates)
- [SSE vs WebSockets for Market Data](https://dev.to/donbagger/sse-vs-websockets-choosing-the-right-transport-for-market-data-56d4)
- [SSE Beat WebSockets for 95% of Real-Time Apps](https://dev.to/polliog/server-sent-events-beat-websockets-for-95-of-real-time-apps-heres-why-a4l)
- [SSE vs WebSockets Practical Guide 2026](https://www.nimbleway.com/blog/server-sent-events-vs-websockets-what-is-the-difference-2026-guide)
- [QuantConnect LEAN Engine](https://github.com/QuantConnect/Lean)
- [QuantConnect Platform](https://www.quantconnect.com/)
- [Deploying FastAPI and Next.js to Vercel (Feb 2026)](https://nemanjamitic.com/blog/2026-02-22-vercel-deploy-fastapi-nextjs)
- [Streamlit 2026 Release Notes](https://docs.streamlit.io/develop/quick-reference/release-notes/2026)
