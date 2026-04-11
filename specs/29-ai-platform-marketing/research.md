# Research Notes: AI Platform Marketing

## Decision 1: Evidence Board Data Source
- **Decision**: Use existing alerts + trade_journal tables
- **Rationale**: Alert → Took → T1/T2/Stop outcome → trade_journal with replay_text already exists
- **Alternatives**: New table (duplication), external analytics (overkill)

## Decision 2: Chart in Evidence Cards
- **Decision**: AI replay text + price data only (no chart animation initially)
- **Rationale**: Chart replay component needs auth. AI text + verified prices is sufficient proof. Chart can be added later.
- **Alternatives**: Static screenshots (headless rendering needed), full replay (auth bypass needed)

## Decision 3: Public API Security
- **Decision**: Fully public endpoint, anonymized (no user IDs or personal data)
- **Rationale**: Public proof is the point. Only alert metadata + outcomes shown.
- **Alternatives**: Auth + share links (friction), rate limiting (premature)

## Decision 4: Landing Page Scope
- **Decision**: Update existing LandingPage.tsx (not full redesign)
- **Rationale**: Surgical changes: update headline, remove 3 features, add values section, add evidence preview. Full redesign is a separate effort.
- **Alternatives**: Complete landing page rebuild (too large for this spec)
