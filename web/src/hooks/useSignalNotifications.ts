/** Browser notifications for new routed signals.
 *
 * Watches the (already-polling) today-alerts query; when a new routed signal
 * appears, fires a desktop notification + an in-app toast + a short sound.
 * Works while the web app is open in any browser tab. Opt-in via Settings.
 */

import { useEffect, useRef } from "react";
import { useNavigate, type NavigateFunction } from "react-router-dom";
import { useAlertsToday } from "../api/hooks";
import { formatSetup, isFeedSignal } from "../lib/alertFormat";
import { toast } from "../components/Toast";
import type { Alert } from "../types";

const LS_KEY = "signal_notifications_enabled";

export function signalNotificationsEnabled(): boolean {
  try {
    return localStorage.getItem(LS_KEY) === "true";
  } catch {
    return false;
  }
}

export function setSignalNotificationsEnabled(on: boolean): void {
  try {
    localStorage.setItem(LS_KEY, String(on));
  } catch {
    /* ignore */
  }
}

/** Short rising beep via the Web Audio API — no asset file needed. */
function playPing(): void {
  try {
    const Ctx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.setValueAtTime(660, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(990, ctx.currentTime + 0.12);
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.18, ctx.currentTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.3);
    osc.start();
    osc.stop(ctx.currentTime + 0.31);
    osc.onended = () => ctx.close();
  } catch {
    /* audio is best-effort */
  }
}

function fireNotification(a: Alert, navigate: NavigateFunction): void {
  const dir =
    a.direction === "BUY" ? "LONG"
    : a.direction === "SHORT" ? "SHORT"
    : a.direction || "";
  const title = `${a.symbol} ${dir} · ${formatSetup(a.alert_type)}`.trim();
  const parts: string[] = [];
  if (a.entry != null) parts.push(`Entry $${a.entry.toFixed(2)}`);
  if (a.stop != null) parts.push(`Stop $${a.stop.toFixed(2)}`);
  if (a.target_1 != null) parts.push(`T1 $${a.target_1.toFixed(2)}`);
  const body = parts.join("  ·  ") || a.message || "";

  toast.info(`${title}${body ? " — " + body : ""}`);

  if (typeof Notification !== "undefined" && Notification.permission === "granted") {
    try {
      const n = new Notification(title, {
        body,
        tag: `signal-${a.id}`,
        icon: "/logo-profile.svg",
      });
      n.onclick = () => {
        window.focus();
        navigate(`/trading?symbol=${encodeURIComponent(a.symbol)}`);
        n.close();
      };
    } catch {
      /* notification is best-effort */
    }
  }
}

export function useSignalNotifications(): void {
  const navigate = useNavigate();
  const { data: alerts } = useAlertsToday();
  const seenRef = useRef<Set<number> | null>(null);

  useEffect(() => {
    if (!alerts) return;

    // First load — record everything, notify for none (no burst on open).
    if (seenRef.current === null) {
      seenRef.current = new Set(alerts.map((a) => a.id));
      return;
    }
    const seen = seenRef.current;

    const fresh: Alert[] = [];
    for (const a of alerts) {
      if (seen.has(a.id)) continue;
      seen.add(a.id);
      // Only routed feed signals — disabled/non-routed types stay silent.
      if (!isFeedSignal(a.alert_type)) continue;
      if (a.suppressed_reason === "type_not_enabled") continue;
      fresh.push(a);
    }

    if (fresh.length === 0 || !signalNotificationsEnabled()) return;

    playPing(); // one ping per batch
    for (const a of fresh) fireNotification(a, navigate);
  }, [alerts, navigate]);
}
