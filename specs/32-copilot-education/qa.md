# QA Test Plan: AI CoPilot Education

## Unit Tests (automated)

### 1. Education Prompt Tests
```
test_education_prompt_includes_setup_type
  → build_education_prompt("PDL Bounce", "ETH-USD", 2230, 2220, 2246, {})
  → prompt contains "PDL Bounce"
  → prompt contains "$2230" (entry)
  → prompt contains "$2220" (stop)
  → prompt contains "WHAT IS IT"
  → prompt contains "WHY IT WORKS"
  → prompt contains "HOW TO CONFIRM"
  → prompt contains "RISK MANAGEMENT"

test_education_prompt_handles_missing_prices
  → build_education_prompt("VWAP Hold", "SPY", 0, 0, 0, {})
  → does not crash
  → returns valid prompt string

test_education_prompt_all_pattern_types
  → for each pattern in PATTERN_LIBRARY:
    → build_education_prompt(pattern, "ETH-USD", 100, 99, 102, {})
    → returns non-empty prompt
```

### 2. Pattern Library Tests
```
test_pattern_library_has_14_entries
  → len(PATTERN_LIBRARY) == 14

test_every_pattern_has_required_fields
  → for each pattern:
    → has "name" (string, non-empty)
    → has "category" (one of: Support, Resistance, Breakout, Reversal, Momentum)
    → has "difficulty" (one of: Beginner, Intermediate, Advanced)
    → has "description" (string, non-empty)

test_pattern_categories_balanced
  → at least 4 Support patterns
  → at least 2 Resistance patterns
  → at least 2 Breakout patterns

test_difficulty_levels_balanced
  → at least 4 Beginner patterns
  → at least 4 Intermediate patterns
  → at least 2 Advanced patterns
```

### 3. Education Response Parsing Tests
```
test_parse_education_response_all_sections
  → given AI response with WHAT/WHY/CONFIRM/RISK sections
  → parser extracts each section correctly
  → no section is None

test_parse_education_response_missing_section
  → given AI response missing "WHY IT WORKS"
  → parser returns None for that section
  → other sections still parsed

test_parse_education_response_with_checkmarks
  → given response with ✓ and ✗ items
  → parser extracts confirm_items (list) and invalidation (string)
```

### 4. API Endpoint Tests
```
test_pattern_education_endpoint_returns_200
  → GET /api/v1/intel/pattern-education/pdl_bounce?symbol=ETH-USD
  → status 200
  → response has "education" key with content

test_pattern_education_endpoint_invalid_pattern
  → GET /api/v1/intel/pattern-education/invalid_xyz
  → status 404 or returns generic education

test_pattern_education_endpoint_requires_auth
  → GET without token
  → status 401
```

## Integration Tests (manual)

### 5. CoPilot Page Flow
```
GIVEN: user opens CoPilot page
WHEN: selects ETH-USD, clicks Analyze
THEN: 
  - Chart shows with annotations
  - Trade plan card appears (LONG/SHORT/WAIT)
  - Education panel appears below with WHAT/WHY/CONFIRM/RISK
  - Education uses actual prices from the analysis
  - Pattern Library grid visible at bottom

GIVEN: AI detects "PDL Bounce" setup
THEN:
  - Education panel title shows "PDL Bounce"
  - WHAT section explains in 2 sentences
  - WHY section has 3 bullet points about institutional logic
  - CONFIRM section has 3-4 ✓ checkmarks
  - CONFIRM section has 1 ✗ invalidation
  - RISK section shows entry/stop/target with actual prices
```

### 6. Pattern Library
```
GIVEN: user views Pattern Library section
THEN:
  - 14 pattern cards visible
  - Each card shows: name, category badge, difficulty badge, description
  - Cards organized by category (Support, Resistance, Breakout)
  
GIVEN: user clicks a pattern card
THEN:
  - Education detail expands/opens
  - Shows full WHAT/WHY/CONFIRM/RISK for that pattern
  - Uses generic example prices (not live data)
```

### 7. Pattern Stats
```
GIVEN: user has traded for 1+ weeks
THEN:
  - "Your Pattern Stats" section shows
  - Per-pattern: times seen, won/lost, took/skipped
  - Highlights strongest pattern ("Your edge")
  
GIVEN: user is new (no trade history)
THEN:
  - Stats section shows "Start taking trades to build your stats"
```

### 8. Navigation from AI Scan
```
GIVEN: user sees AI Scan alert "LONG ETH — PDL Bounce"
WHEN: clicks "Learn more" or navigates to CoPilot
THEN:
  - CoPilot opens with ETH-USD selected
  - Education panel pre-loaded with "PDL Bounce" content
```

## Acceptance Criteria

- [ ] Every AI analysis includes education content (WHAT/WHY/CONFIRM/RISK)
- [ ] Education uses actual prices from the chart, not generic examples
- [ ] Pattern Library has all 14 patterns documented
- [ ] Each pattern has difficulty badge (Beginner/Intermediate/Advanced)
- [ ] A beginner can understand the WHAT and WHY sections without prior knowledge
- [ ] RISK section always shows specific entry/stop/target prices
- [ ] HOW TO CONFIRM has actionable checkmarks they can verify
- [ ] Page loads in <3 seconds
- [ ] Education content generates in <5 seconds (Claude call)
