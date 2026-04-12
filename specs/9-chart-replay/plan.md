# Implementation Plan: [FEATURE_NAME]

**Spec**: [Link to spec.md]
**Branch**: [BRANCH_NAME]
**Created**: [DATE]

## Technical Context

| Item | Value |
|------|-------|
| Language | Python 3.9+ |
| Framework | Streamlit (dashboard), APScheduler (worker) |
| Database | SQLite (local) / Postgres (production) |
| Notifications | Telegram Bot API |
| Market Data | yfinance |
| AI | Anthropic API |
| Deployment | Railway (worker + Streamlit) |

### Dependencies
- [New dependencies needed]

### Integration Points
- [External systems this touches]

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| Protect Business Logic | [PASS/FAIL] | [Impact analysis if touching protected files] |
| Test-Driven Development | [PASS/FAIL] | [Test plan] |
| Local First | [PASS/FAIL] | [Verification steps] |
| Database Compatibility | [PASS/FAIL] | [SQLite + Postgres handling] |
| Alert Quality | [PASS/FAIL] | [If touching alert logic] |
| Single Notification Channel | [PASS/FAIL] | [If touching notifications] |

## Solution Architecture

```
[ASCII diagram of component interactions]
```

### Data Flow
[How data moves through the system]

### Files to Modify

| File | Change | Risk |
|------|--------|------|
| [path] | [What changes] | [Low/Med/High] |

### Files to Add

| File | Purpose |
|------|---------|
| [path] | [What it does] |

## Implementation Approach

### Phase 1: [Foundation]
1. [Step with file path]
2. [Step with file path]

### Phase 2: [Core Logic]
1. [Step with file path]
2. [Step with file path]

### Phase 3: [Integration & Polish]
1. [Step with file path]

## Test Plan

### Unit Tests
- [ ] [Test case — what it validates]

### Integration Tests
- [ ] [Test case — what it validates]

### E2E Validation
1. **Setup**: [Prerequisites]
2. **Action**: [What to do]
3. **Verify**: [Expected outcome]
4. **Cleanup**: [Reset steps]

## Out of Scope

- [Excluded item and reason]

## Research Notes

_Populated during Phase 0 research — see research.md_
