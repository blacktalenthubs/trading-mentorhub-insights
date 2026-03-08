# Learning: AI Trade Narrator

## Codebase Analysis

### AlertSignal Dataclass (`analytics/intraday_rules.py:101-126`)
Full context available per signal:
- **Price**: `price`, `entry`, `stop`, `target_1`, `target_2`
- **Technical**: `volume_label`, `vwap_position`, `spy_trend`, `rs_ratio`
- **Market**: `session_phase`, `gap_info`, `confluence`, `confluence_ma`
- **Quality**: `score` (0-100), `score_label` (A+/A/B/C), `confidence`, `mtf_aligned`
- **Identity**: `symbol`, `alert_type` (23+ types), `direction`, `message`

This is sufficient context for a rich narrative — no additional data fetch needed.

### Alert Flow
```
evaluate_rules() → AlertSignal
  → monitor.py poll_cycle() → for each signal:
      → record_alert() (DB)
      → notify_user() (Telegram/email)
  → Scanner page reads from DB + live scan
```

### Scanner Detail Cards (`pages/1_Scanner.py:551-665`)
Each symbol gets an expander with sections: Header → Live Plan → Pre-Market → Key Levels → Live Status → Trade Plan → Re-entry → Position Sizing → MA Context → Chart.

**Best injection point**: After Trade Plan section (line ~665), before Re-entry. This is where traders look for the thesis before deciding.

### Notification Format (`alerting/notifier.py`)
- Email: Multi-line plain text, can append narrative section
- Telegram: Compact ≤320 chars with `|` delimiters — narrative needs to be abbreviated (first sentence only)

### Caching (`analytics/_cache.py`)
Dual-mode cache: uses `st.cache_data` in Streamlit, no-op in monitor/scripts. Narrative should use its own cache keyed on `(symbol, alert_type, session_date)`.

### Config Pattern (`alert_config.py:14-23`)
`_get_secret(key)` reads env vars first, falls back to `st.secrets` for Streamlit Cloud. Claude API key follows same pattern.

### Database (`db.py:157-174`)
Alerts table has `message TEXT` column but no `narrative` column. Need migration to add `narrative TEXT`.

### Dependencies
`anthropic` SDK not yet in `requirements.txt`. Need to add it.

## Technical Decisions

1. **New module**: `alerting/narrator.py` — keeps AI logic separate from rule engine
2. **Haiku model**: Use `claude-haiku-4-5-20251001` for speed + cost (narratives are short, context is structured)
3. **Cache per session**: Key on `(symbol, alert_type, session_date)` — same alert doesn't re-call API
4. **Graceful fallback**: If API fails or key missing, alert works normally without narrative
5. **DB storage**: Add `narrative TEXT` column to alerts table — persists for history/review
6. **Prompt engineering**: Structured system prompt with all context fields, constrained to 2-3 sentences
