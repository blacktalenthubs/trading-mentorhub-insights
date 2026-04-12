# URGENT: Alert Engine Needs Full Clean Revert

**Priority**: P0
**Created**: 2026-04-10 (late night)

## Problem
Alert engine is in a broken hybrid state. intraday_rules.py and alert_config.py were reverted to April 2, but monitor.py and notifier.py still have April 10 changes. This creates mismatched behavior:
- Gates are back (April 2 rules) but monitor has global signal cache and suppress_telegram logic
- BUY alerts not firing for session low bounces, MA bounces at support
- Wrong alerts firing (morning low breakdown when morning low wasn't broken)
- RESISTANCE format works but rest of notification pipeline is unstable

## Root Cause
20+ commits in one day to core alert engine files. Each change introduced side effects. Partial revert left mixed state.

## Fix (Morning, before market open)
1. Revert monitor.py to pre-April 10 state (keep only IndentationError fix for T1 block)
2. Revert notifier.py to pre-April 10 state (keep RESISTANCE format change only)
3. Keep alert_config.py as-is (April 2 + VWAP enabled)
4. Keep intraday_rules.py as-is (April 2)
5. Test: verify session_low_bounce, MA bounce, PDL bounce all fire
6. ONE change at a time after that

## Files affected
- api/app/background/monitor.py — revert global signal cache, suppress_telegram, stop notification gating
- alerting/notifier.py — keep RESISTANCE format, revert everything else
