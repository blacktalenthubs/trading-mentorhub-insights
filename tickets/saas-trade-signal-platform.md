# SaaS Trade Signal Platform

## Status: Weekend — Business Requirements & System Design

## Vision

Self-service trade signal platform where users bring their own watchlist and receive scored alerts based on technical rules. Users own their data, we provide the engine. No financial advice — pure tooling.

## Weekend Deliverables

### 1. Business Requirements
- Target user persona (serious retail traders, $30-50/mo budget)
- Feature tiers (free vs paid)
- Pricing model
- Legal/compliance requirements (disclaimers, terms of service)
- Go-to-market strategy

### 2. System Architecture Design
- Multi-tenant data model (per-user watchlists, alerts, trades, settings)
- Infrastructure (move off Streamlit Cloud to proper backend)
- API design (separate backend from frontend)
- Real-time alert delivery (Telegram, email, push)
- Database (persistent, scalable — Postgres/Supabase)
- Authentication & billing (Stripe integration)
- Deployment & CI/CD

### 3. MVP Scope Definition
- What's in v1 vs backlog
- User onboarding flow
- Core loop: watchlist → scan → score → alert → track → review

## Existing Assets (Already Built)
- Signal scanner with 10+ rule types (MA bounce, support, VWAP, etc.)
- Scoring engine (0-100 with confidence levels)
- Multi-channel notifications (Telegram, email, SMS)
- Real trade tracking with P&L dashboard
- Options trade tracking
- AI trade narrator
- User auth with per-user watchlists
- Paper trading with Alpaca integration
- Swing trade scanner (EOD)
- Trade journal with notes

## Key Design Principle

Self-service = legal safety. Users choose symbols, configure alerts, track their own trades. Platform provides technical analysis tools, not recommendations.
