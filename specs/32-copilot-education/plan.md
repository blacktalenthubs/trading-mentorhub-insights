# Implementation Plan: AI CoPilot Education Platform

**Spec**: [spec.md](spec.md)
**Created**: 2026-04-11

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    AICoPilotPage.tsx                  │
│                                                      │
│  ┌──────────────┐  ┌─────────────────────────────┐  │
│  │ Chart with    │  │ Education Panel              │  │
│  │ annotations   │  │                              │  │
│  │               │  │ ┌──────────────────────────┐ │  │
│  │               │  │ │ WHAT IS IT?              │ │  │
│  │               │  │ │ WHY IT WORKS             │ │  │
│  │               │  │ │ HOW TO CONFIRM           │ │  │
│  │               │  │ │ RISK MANAGEMENT          │ │  │
│  │               │  │ └──────────────────────────┘ │  │
│  │               │  │                              │  │
│  └──────────────┘  │ ┌──────────────────────────┐ │  │
│                     │ │ Trade Plan (existing)    │ │  │
│                     │ │ LONG/SHORT/WAIT          │ │  │
│                     │ │ Entry/Stop/T1/T2         │ │  │
│                     │ └──────────────────────────┘ │  │
│                     └─────────────────────────────┘  │
│                                                      │
│  ┌───────────────────────────────────────────────┐   │
│  │ Pattern Library                                │   │
│  │ [PDL Bounce] [VWAP Hold] [MA Bounce] [more]   │   │
│  └───────────────────────────────────────────────┘   │
│                                                      │
│  ┌───────────────────────────────────────────────┐   │
│  │ Your Pattern Stats (personal win rates)        │   │
│  └───────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

## Files to Modify/Create

| File | Action | What |
|------|--------|------|
| `analytics/chart_analyzer.py` | MODIFY | Add education prompt alongside trade plan prompt |
| `api/app/routers/intel.py` | MODIFY | Add `/pattern-education/{type}` endpoint |
| `web/src/pages/AICoPilotPage.tsx` | MODIFY | Redesign layout: education panel + pattern library |
| `web/src/components/ai/PatternEducation.tsx` | CREATE | Education panel component |
| `web/src/components/ai/PatternLibrary.tsx` | CREATE | Pattern grid + detail cards |
| `web/src/components/ai/PatternStats.tsx` | CREATE | Personal win rate per pattern |
| `tests/test_copilot_education.py` | CREATE | Tests for education content |

## Implementation Phases

### Phase 1: Education Prompt + API

1. Add education prompt to `chart_analyzer.py`:
   - New function: `build_education_prompt(setup_type, symbol, prior_day, bars)`
   - Returns structured education: WHAT/WHY/CONFIRM/RISK
   - Uses actual prices from the data
   
2. Add API endpoint in `intel.py`:
   - `GET /api/v1/intel/pattern-education/{pattern_type}?symbol={sym}`
   - Returns education content for the given pattern
   - Calls Claude with education prompt
   
3. Modify existing analyze-chart to include education in response:
   - After parsing trade plan, also generate education for the detected setup
   - Return both in the streaming response

### Phase 2: Frontend — Education Panel

4. Create `PatternEducation.tsx`:
   - Renders WHAT/WHY/CONFIRM/RISK sections
   - Color-coded: green checkmarks for confirm, red X for invalidation
   - Collapsible sections

5. Create `PatternLibrary.tsx`:
   - Grid of 14 pattern cards
   - Each card: name, category, difficulty badge, 1-line description
   - Click → opens education detail

6. Modify `AICoPilotPage.tsx`:
   - Split right panel: trade plan (top) + education (bottom)
   - Add Pattern Library section below chart
   - Rename header: "Learn Trading Patterns"

### Phase 3: Pattern Stats

7. Create `PatternStats.tsx`:
   - Fetch win rates from existing `/api/v1/intel/win-rates`
   - Group by pattern type
   - Show: times seen, won/lost, your took/skipped, avg gain

## Data Flow

```
User clicks "Analyze" on CoPilot page
  │
  ▼
Frontend calls /api/v1/intel/analyze-chart (existing)
  │
  ▼
Backend: build_analysis_prompt() → Claude → parse trade plan
  │
  ▼
Backend: build_education_prompt(setup_type) → Claude → parse education
  │
  ▼
Frontend receives: { plan, education, reasoning }
  │
  ├── TradePlanCard: shows entry/stop/T1/T2
  └── PatternEducation: shows WHAT/WHY/CONFIRM/RISK
```

## Education Prompt

```python
def build_education_prompt(setup_type: str, symbol: str, entry: float, 
                           stop: float, t1: float, prior_day: dict) -> str:
    return f"""
You are a trading educator explaining the "{setup_type}" pattern to a 
beginner trader looking at {symbol}.

Use these ACTUAL prices from the chart:
Entry: ${entry}
Stop: ${stop}  
Target: ${t1}

Explain in 4 sections:

WHAT IS IT: 2 sentences — name the pattern, describe what happened 
on the chart in simple language a beginner understands.

WHY IT WORKS: 3 bullet points — the market logic (institutional orders,
supply/demand, why this level matters).

HOW TO CONFIRM:
✓ 3-4 checkmarks — what to verify before entering
✗ 1 item — what invalidates the setup

RISK MANAGEMENT:
Entry: ${entry} (the level)
Stop: ${stop} (where thesis breaks)
Target: ${t1} (next resistance/support)
R:R: calculate from the prices

Keep it under 150 words. Plain text. No markdown.
Speak simply — assume the reader is new to trading.
"""
```

## Pattern Library Content (Static)

```python
PATTERN_LIBRARY = {
    "pdl_bounce": {
        "name": "Prior Day Low Bounce",
        "category": "Support",
        "difficulty": "Beginner",
        "description": "Price tests yesterday's low and holds above it",
        "icon": "🟢",
    },
    "vwap_hold": {
        "name": "VWAP Hold",
        "category": "Support", 
        "difficulty": "Beginner",
        "description": "Price pulls back to VWAP and bounces",
        "icon": "🟢",
    },
    "pdh_breakout": {
        "name": "PDH Breakout",
        "category": "Breakout",
        "difficulty": "Intermediate",
        "description": "Price breaks above yesterday's high on volume",
        "icon": "🔵",
    },
    "session_low_double_bottom": {
        "name": "Session Low Double Bottom",
        "category": "Support",
        "difficulty": "Beginner",
        "description": "Price tests the same low twice and holds",
        "icon": "🟢",
    },
    "ma_bounce": {
        "name": "Moving Average Bounce",
        "category": "Support",
        "difficulty": "Intermediate",
        "description": "Price bounces off a key moving average (50/100/200)",
        "icon": "🟢",
    },
    "vwap_reclaim": {
        "name": "VWAP Reclaim",
        "category": "Reversal",
        "difficulty": "Intermediate",
        "description": "Price crosses above VWAP from below — momentum shift",
        "icon": "🔄",
    },
    "pdh_rejection": {
        "name": "PDH Rejection",
        "category": "Resistance",
        "difficulty": "Beginner",
        "description": "Price fails at yesterday's high — sellers defend",
        "icon": "🔴",
    },
    "session_high_double_top": {
        "name": "Session High Double Top",
        "category": "Resistance",
        "difficulty": "Intermediate",
        "description": "Price tests session high twice and fails",
        "icon": "🔴",
    },
    "vwap_loss": {
        "name": "VWAP Loss",
        "category": "Reversal",
        "difficulty": "Beginner",
        "description": "Price drops below VWAP — bearish shift",
        "icon": "🔴",
    },
    "inside_day_breakout": {
        "name": "Inside Day Breakout",
        "category": "Breakout",
        "difficulty": "Advanced",
        "description": "Tight range day followed by expansion",
        "icon": "🔵",
    },
    "fib_bounce": {
        "name": "Fibonacci Retracement Bounce",
        "category": "Support",
        "difficulty": "Advanced",
        "description": "Price bounces at 50% or 61.8% fib level",
        "icon": "🟢",
    },
    "gap_and_go": {
        "name": "Gap & Go",
        "category": "Momentum",
        "difficulty": "Advanced",
        "description": "Stock gaps up and holds above VWAP with volume",
        "icon": "🔵",
    },
    "pdl_reclaim": {
        "name": "Prior Day Low Reclaim",
        "category": "Support",
        "difficulty": "Beginner",
        "description": "Price dips below PDL then recovers above it",
        "icon": "🟢",
    },
    "ema_rejection": {
        "name": "EMA Rejection",
        "category": "Resistance",
        "difficulty": "Intermediate",
        "description": "Price rallies into falling EMA and gets rejected",
        "icon": "🔴",
    },
}
```

## Test Plan

See [qa.md](qa.md)
