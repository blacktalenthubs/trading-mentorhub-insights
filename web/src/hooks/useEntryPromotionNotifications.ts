/** In-app notification when a scanner setup PROMOTES from approaching → at entry.
 *
 * Watches the (already-polling, 60s) /scanner/scan query and fires an in-app toast
 * — plus a desktop notification when permission is granted — the moment a name's
 * action_label flips from "Watch" (approaching) to "Potential Entry" (price reached
 * the level). Mirrors useSignalNotifications. Mounted in AppLayout so it works on
 * any page while the app is open.
 *
 * Default ON (the user asked for it); opt out via localStorage
 * entry_promotion_notifications_enabled="false".
 */

import { useEffect, useRef } from "react";
import { useNavigate, type NavigateFunction } from "react-router-dom";
import { useScanner } from "../api/hooks";
import { toast } from "../components/Toast";
import type { SignalResult } from "../types";

const AT_ENTRY = "Potential Entry";
const LS_KEY = "entry_promotion_notifications_enabled";

export function entryPromotionEnabled(): boolean {
  try {
    return localStorage.getItem(LS_KEY) !== "false"; // default ON
  } catch {
    return true;
  }
}

export function setEntryPromotionEnabled(on: boolean): void {
  try {
    localStorage.setItem(LS_KEY, String(on));
  } catch {
    /* ignore */
  }
}

function fireEntryPromotion(s: SignalResult, navigate: NavigateFunction): void {
  const lvl = s.support_label || "its level";
  const bits: string[] = [];
  if (s.entry != null) bits.push(`Entry $${s.entry.toFixed(2)}`);
  if (s.stop != null) bits.push(`Stop $${s.stop.toFixed(2)}`);
  if (s.target_1 != null) bits.push(`T1 $${s.target_1.toFixed(2)}`);
  const body = bits.join("  ·  ");
  const title = `${s.symbol} reached entry — at ${lvl}`;

  toast.info(`${title}${body ? " · " + body : ""}`);

  if (typeof Notification !== "undefined" && Notification.permission === "granted") {
    try {
      const n = new Notification(title, {
        body,
        tag: `entry-${s.symbol}`, // collapse repeat promotions of the same name
        icon: "/logo-profile.svg",
      });
      n.onclick = () => {
        window.focus();
        navigate(`/trading?symbol=${encodeURIComponent(s.symbol)}`);
        n.close();
      };
    } catch {
      /* notification is best-effort */
    }
  }
}

export function useEntryPromotionNotifications(): void {
  const navigate = useNavigate();
  const { data: signals } = useScanner();
  const prevRef = useRef<Map<string, string> | null>(null);

  useEffect(() => {
    if (!signals) return;

    const curr = new Map<string, string>(signals.map((s) => [s.symbol, s.action_label]));

    // First load — record current state, notify for none (no burst on open).
    if (prevRef.current === null) {
      prevRef.current = curr;
      return;
    }
    const prev = prevRef.current;

    const promoted: SignalResult[] = [];
    for (const s of signals) {
      const was = prev.get(s.symbol);
      // Only a genuine transition: previously seen as NOT-at-entry, now at entry.
      if (s.action_label === AT_ENTRY && was !== undefined && was !== AT_ENTRY) {
        promoted.push(s);
      }
    }
    prevRef.current = curr; // advance the baseline even when disabled (no burst on re-enable)

    if (promoted.length === 0 || !entryPromotionEnabled()) return;
    for (const s of promoted) fireEntryPromotion(s, navigate);
  }, [signals, navigate]);
}
