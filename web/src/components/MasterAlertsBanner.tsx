/**
 * Master Alerts discoverability banner.
 *
 * Shows to users who haven't opted into Master Alerts — the platform's whole
 * deduped master-watchlist feed. One tap turns it on; the banner auto-hides the
 * moment master_alerts is true. Dismiss = SNOOZE 1 hour (not forever) — it comes
 * back next session/hour so users who skipped it still get reminded, without
 * nagging on every render. Auto-re-appears when the snooze lapses (timer).
 */

import { useEffect, useState } from "react";
import { Zap, X } from "lucide-react";
import { useNotificationPrefs, useUpdateNotificationPrefs } from "../api/hooks";
import type { NotificationPrefs } from "../types";

const SNOOZE_KEY = "master_alerts_banner_snoozed_until";
const SNOOZE_MS = 60 * 60 * 1000; // 1 hour

function snoozedUntil(): number {
  return parseInt(localStorage.getItem(SNOOZE_KEY) || "0", 10) || 0;
}

export default function MasterAlertsBanner() {
  const { data: prefs } = useNotificationPrefs();
  const update = useUpdateNotificationPrefs();
  const [now, setNow] = useState(() => Date.now());

  // Re-evaluate every 5 min so the banner re-appears after the 1h snooze lapses
  // even if the user never navigates away.
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 5 * 60 * 1000);
    return () => clearInterval(id);
  }, []);

  // Only for users who haven't opted in, and not currently snoozed.
  if (!prefs || prefs.master_alerts || now < snoozedUntil()) return null;

  function enable() {
    update.mutate({ ...(prefs as NotificationPrefs), master_alerts: true });
    // onSuccess invalidates the prefs query → master_alerts:true → the banner
    // unmounts on its own. No manual hide needed.
  }
  function dismiss() {
    try { localStorage.setItem(SNOOZE_KEY, String(Date.now() + SNOOZE_MS)); } catch { /* ignore */ }
    setNow(Date.now());   // re-render → hidden until the snooze lapses
  }

  return (
    <div className="mb-4 flex items-center gap-3 rounded-xl border border-accent/30 bg-accent/10 px-3.5 py-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent/20">
        <Zap className="h-4 w-4 text-accent" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-semibold text-text-primary">
          Get the whole platform’s signal feed
        </p>
        <p className="text-[11px] leading-snug text-text-muted">
          One tap — every deduped quality signal across the master watchlist, not just your list.
        </p>
      </div>
      <button
        onClick={enable}
        disabled={update.isPending}
        className="shrink-0 rounded-lg bg-accent px-3 py-1.5 text-[12px] font-semibold text-bg-base transition-colors hover:bg-accent-hover disabled:opacity-60"
      >
        {update.isPending ? "Turning on…" : "Turn on"}
      </button>
      <button
        onClick={dismiss}
        aria-label="Dismiss"
        className="shrink-0 rounded p-1 text-text-faint transition-colors hover:text-text-secondary"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
