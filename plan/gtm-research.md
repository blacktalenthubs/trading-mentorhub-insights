# Go-To-Market Research — TradeCoPilot

**Date:** April 2026
**Goal:** How to acquire first 500 paying users in 3 months

---

## 1. How Does a New Trading Platform Get Reach?

### The Playbook (Priority Order)

**Phase 1 — Organic Content (Week 1-4): $0 cost**
- **Short-form video** is the #1 discovery channel for trading tools in 2026
  - TikTok: #FinTok views up 275% YoY — traders actively discover tools here
  - YouTube Shorts: long-tail discoverability (videos rank for years)
  - Instagram Reels: cross-post TikTok content
  - **Content format:** 40-60 second chart replay videos showing real alerts
    - "How TradeCoPilot caught the ETH double bottom at $2024"
    - Show: alert fires → entry/stop/T1 → chart plays out → outcome
    - Faceless format works (screen recording + voiceover)
  - **Cadence:** 3-5 videos/week across all platforms

- **Reddit** — where day traders actually hang out
  - r/daytrading (1.5M members), r/stockmarket (2.5M), r/options (1.2M)
  - **Strategy:** Value posts, not spam. Share weekly track record transparency
  - "Our alert system caught 433 wins out of 726 signals (79.9% WR) — here's the breakdown"
  - Link to Signal Library pages (SEO + traffic)

- **SEO via Signal Library** — 29 pages now live, targeting long-tail keywords
  - "prior day low reclaim trading strategy"
  - "what is a consolidation breakout"
  - "200 MA bounce swing trade"
  - Each page ends with register CTA
  - **Timeline:** 2-4 months for Google indexing and traffic

- **Twitter/X** — daily pre-market briefs + alert screenshots
  - Post the AI Battle Plan every morning (free content)
  - Share alert outcomes with charts
  - Build authority through transparency (weekly scorecards)

**Phase 2 — Paid Ads (Week 4-12): $1,500-3,000/mo**
- **Google Ads** — capture high-intent searchers
  - Target: "stock alert app", "day trading alerts", "AI trading signals"
  - Finance CPC: $3-6 per click (some keywords up to $50)
  - Realistic budget: $1,500/mo = ~300-500 clicks
  - At 5% conversion rate = 15-25 signups/mo from Google
  - Focus on long-tail, lower-CPC keywords first

- **YouTube Ads** — pre-roll on trading content
  - 15-30 sec video ad showing a real alert → outcome
  - Target: viewers of trading education channels
  - CPC lower than Google Search ($0.50-2.00)
  - Budget: $500/mo

- **Meta Ads** — awareness + retargeting
  - Carousel showing alert flow: signal → Telegram → took → P&L
  - Retarget website visitors who didn't register
  - Budget: $500/mo

**Phase 3 — Community & Referral (Week 8+): $0 + incentive cost**
- **Referral program:** refer → both get 1 month free Pro
  - CAC for referral = $0 (just deferred revenue)
  - Referral users have 37% higher retention
- **Discord community** — free tier users discuss setups
  - Builds engagement, reduces churn
  - Power users become advocates
- **Creator partnerships** — give Pro access to trading YouTubers/TikTokers
  - They create content about their experience
  - Authentic > paid ads

---

## 2. Budget for 3 Months

### Conservative Budget ($3,000 total)

| Month | Channel | Budget | Expected Signups |
|-------|---------|--------|-----------------|
| Month 1 | Organic only (content + Reddit + SEO) | $0 | 20-40 |
| Month 2 | Google Ads + organic | $1,000 | 40-60 |
| Month 3 | Google + YouTube + Meta + organic | $2,000 | 60-100 |
| **Total** | | **$3,000** | **120-200 signups** |

At 10% free→Pro conversion: **12-20 paying users**
At $29/mo Pro: **$348-580/mo revenue**

### Moderate Budget ($7,500 total)

| Month | Channel | Budget | Expected Signups |
|-------|---------|--------|-----------------|
| Month 1 | Organic + Google Ads ($1,000) | $1,000 | 40-60 |
| Month 2 | Google ($1,500) + YouTube ($500) + Meta ($500) | $2,500 | 80-120 |
| Month 3 | All channels + referral program | $4,000 | 120-200 |
| **Total** | | **$7,500** | **240-380 signups** |

At 15% conversion (with trial): **36-57 paying users**
Revenue: **$1,044-1,653/mo**

### Aggressive Budget ($15,000 total)

| Month | Channel | Budget | Expected Signups |
|-------|---------|--------|-----------------|
| Month 1 | Google ($2K) + YouTube ($1K) + Meta ($1K) + creator partnerships ($1K) | $5,000 | 100-150 |
| Month 2 | All channels optimized | $5,000 | 150-250 |
| Month 3 | Scale winners + referral | $5,000 | 200-350 |
| **Total** | | **$15,000** | **450-750 signups** |

At 15% conversion: **67-112 paying users**
Revenue: **$1,943-3,248/mo**

### Recommendation: Start with $3,000 (Conservative)
- Month 1 is FREE (organic content only)
- Test Google Ads in Month 2 to find CPC and conversion rate
- Scale what works in Month 3
- The 3-day Pro trial is the key conversion lever — users taste value, then hit limits

---

## 3. Is Current Infrastructure Ready for Users?

### Capacity Assessment

| Component | Current | Limit | Status |
|-----------|---------|-------|--------|
| **Railway Worker** | 1 instance | Auto-scales to 32 vCPU | OK for 500+ users |
| **Postgres** | Railway managed | 100 connections default | Need PgBouncer at ~100 concurrent users |
| **yfinance API** | 20 req/min rate limit | Shared across all users | Bottleneck at ~50 users with 10 symbols each |
| **Anthropic API** | Pay-per-use | No hard limit | Cost scales with usage ($0.003/query Haiku, $0.015/query Sonnet) |
| **Telegram Bot** | Single polling thread | ~1000 messages/sec | OK for 500+ users |
| **Alert Monitor** | 3-min poll cycle | Single thread | ~30 users × 10 symbols = 300 evaluations/cycle (OK) |

### Known Bottlenecks

**1. yfinance Rate Limiting (CRITICAL at 50+ users)**
- Currently fetches data per-user per-symbol
- Already deduplicates: same symbol across users = one fetch
- With 50 users × 10 symbols = ~100 unique symbols
- yfinance rate limit: 20 req/min → need 5 minutes per cycle
- **Fix needed:** Batch symbol fetching, cache aggressively (5-min TTL)

**2. Postgres Connections (at 100+ concurrent users)**
- Default 100 connections
- The V2 API uses async connections, V1 db.py uses sync
- **Fix needed:** Add PgBouncer or increase max_connections

**3. AI API Costs (scales with users)**
- AI Coach: ~$0.015/query (Sonnet) × 20 queries/day × users
- 100 Pro users × 20 queries = $30/day AI costs
- Daily battle plan: ~$0.03/user × 100 = $3/day
- Weekly review: ~$0.03/user × 100 = $3/week
- **Total AI cost at 100 users: ~$1,000/mo** (covered by Pro revenue)

### Infrastructure Readiness Score: 7/10

**Ready now (0-50 users):**
- App deployed, alerts working, Telegram bot running
- Database handles current load fine
- AI services operational

**Need before 50-100 users:**
- yfinance caching layer (Redis or in-memory with TTL)
- Connection pooling (PgBouncer)
- Alert monitor optimization (batch fetches)

**Need before 100-500 users:**
- Dedicated yfinance data service (or switch to paid data provider)
- Database read replicas or connection pooling
- CDN for static assets (currently served by Railway)
- Monitoring & alerting (uptime, error rates, latency)

---

## 4. Key Metrics to Track

| Metric | Target | How to Measure |
|--------|--------|----------------|
| **Signup rate** | 5-10/day from organic | Registration count |
| **Trial → Pro conversion** | 15-20% | Subscriptions within 3 days |
| **Day 7 retention** | 40%+ | Users who return after first week |
| **CAC (paid)** | < $50/signup | Ad spend / signups |
| **LTV** | > $150 (5+ months at $29) | Average subscription duration × price |
| **LTV:CAC ratio** | > 3:1 | LTV / CAC |
| **Churn rate** | < 8%/month | Cancellations / active subscribers |

---

## 5. Quick Wins Before Ads

Before spending on ads, optimize conversion on what's free:

1. **Signal Library is live (29 pages)** — submit sitemap to Google Search Console
2. **Start posting on Twitter/X** — daily pre-market briefs + alert outcomes
3. **Record 5 chart replay videos** — use the replay feature, screen record, add voiceover
4. **Post on Reddit** — 1 value post/week on r/daytrading with track record
5. **Referral program** — implement the refer-a-friend flow in settings
6. **Google Search Console** — submit tradingwithai.ai for indexing

---

## Sources

- [Fintech Marketing Trends 2026](https://www.brighterclick.com/blog-post/fintech-marketing-trends)
- [Customer Acquisition Cost Statistics 2026](https://www.amraandelma.com/customer-acquisition-cost-statistics/)
- [Paid Marketing for Fintech](https://upgrowth.in/paid-marketing-for-fintech-companies/)
- [Google Ads Benchmarks 2026](https://www.whitelabelagency.co/post/google-ads-benchmarks-in-2026-ctr-cpc-conversion-rates-by-industry)
- [Google Ads CPC by Industry](https://www.uproas.io/blog/google-ads-benchmarks)
- [Railway Scaling Docs](https://docs.railway.com/reference/scaling)
- [FinTok Growth Strategy](https://www.houseofmarketers.com/fintok-fintech-growth-strategy/)
- [Fintech Marketing Strategies](https://ninjapromo.io/fintech-marketing-strategies)
- [Startup Marketing Budget Guide](https://www.theknowledgeacademy.com/blog/startup-marketing-budget/)
