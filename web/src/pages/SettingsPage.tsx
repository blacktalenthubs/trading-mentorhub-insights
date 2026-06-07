/** Settings — Account, Notifications & Alert Preferences.
 *
 *  Redesigned: two-column layout on desktop, clear visual hierarchy,
 *  Telegram linking is prominent (step 1 of getting alerts).
 */

import { useEffect, useState } from "react";
import { useAuthStore } from "../stores/auth";
import { api } from "../api/client";
import {
  useUpdateProfile,
  useChangePassword,
  useNotificationPrefs,
  useUpdateNotificationPrefs,
  useNotificationRouting,
  useUpdateNotificationRouting,
  useTelegramStatus,
  useTelegramLink,
  useTelegramUnlink,
  useAlertConfig,
  useToggleAlertConfig,
  useRegimeConfig,
  useUpdateRegimeConfig,
  type AlertTypeConfigItem,
} from "../api/hooks";
import { useFeatureGate } from "../hooks/useFeatureGate";
import {
  signalNotificationsEnabled,
  setSignalNotificationsEnabled,
} from "../hooks/useSignalNotifications";
import type { NotificationPrefs, NotificationRouting, AlertChannel } from "../types";
import {
  Send, Bell, User, Key, ChevronRight, Check,
  ExternalLink, Loader2, DollarSign, Gift,
  Sun, Moon, Filter, Zap, Award,
} from "lucide-react";
import { toast } from "../components/Toast";

/* ── Section wrapper ──────────────────────────────────────────────── */

function Section({ title, icon, children, accent }: {
  title: string; icon: React.ReactNode; children: React.ReactNode; accent?: boolean;
}) {
  return (
    <div className={`rounded-xl border p-5 ${accent ? "border-accent/30 bg-accent/[0.03]" : "border-border-subtle bg-surface-1"}`}>
      <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2 mb-4">
        {icon}
        {title}
      </h3>
      {children}
    </div>
  );
}

/* ── Telegram Setup (the most important section) ──────────────────── */

function TelegramSetup() {
  const { data: status, isLoading } = useTelegramStatus();
  const linkTelegram = useTelegramLink();
  const unlinkTelegram = useTelegramUnlink();

  if (isLoading) return null;

  const linked = status?.linked;

  return (
    <Section
      title="Telegram Alerts"
      icon={<Send className="h-4 w-4 text-accent" />}
      accent={!linked}
    >
      {linked ? (
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-1.5 bg-bullish/10 border border-bullish/20 text-bullish-text text-xs font-semibold px-2.5 py-1 rounded-md">
              <span className="h-1.5 w-1.5 rounded-full bg-bullish animate-pulse" />
              Connected
            </span>
            <span className="text-sm text-text-secondary">Alerts deliver to your Telegram DMs</span>
          </div>
          <p className="text-xs text-text-faint">
            Trade alerts arrive with inline Took/Skip buttons — act from your phone without opening the app.
          </p>
          <button
            onClick={() => unlinkTelegram.mutate()}
            disabled={unlinkTelegram.isPending}
            className="text-xs text-text-faint hover:text-bearish-text transition-colors"
          >
            Disconnect Telegram
          </button>
          <button
            onClick={async () => {
              try {
                const res = await api.post<{ telegram: boolean; apns: boolean; telegram_error: string | null; apns_error: string | null }>(
                  "/settings/test-notification"
                );
                const parts = [];
                if (res.telegram) parts.push("✓ Telegram");
                else if (res.telegram_error) parts.push(`✗ Telegram: ${res.telegram_error}`);
                if (res.apns) parts.push("✓ iOS push");
                else if (res.apns_error) parts.push(`✗ iOS push: ${res.apns_error}`);
                const ok = res.telegram || res.apns;
                (ok ? toast.success : toast.error)(parts.join(" · ") || "No channels configured");
              } catch {
                toast.error("Failed to send test alert");
              }
            }}
            className="text-xs text-accent hover:text-accent-hover transition-colors ml-3"
          >
            Send Test (all channels)
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="bg-surface-2 rounded-lg p-4 border border-border-subtle">
            <p className="text-sm text-text-secondary mb-3">
              Connect Telegram to receive trade alerts directly on your phone — with inline Took/Skip buttons.
            </p>
            <div className="flex flex-col gap-2 text-xs text-text-muted">
              <div className="flex items-center gap-2">
                <span className="w-5 h-5 rounded-full bg-accent/10 text-accent flex items-center justify-center text-[10px] font-bold shrink-0">1</span>
                Click the button below — it opens our bot in Telegram
              </div>
              <div className="flex items-center gap-2">
                <span className="w-5 h-5 rounded-full bg-accent/10 text-accent flex items-center justify-center text-[10px] font-bold shrink-0">2</span>
                Tap <span className="font-semibold text-text-primary">Start</span> in Telegram
              </div>
              <div className="flex items-center gap-2">
                <span className="w-5 h-5 rounded-full bg-accent/10 text-accent flex items-center justify-center text-[10px] font-bold shrink-0">3</span>
                Done — alerts start flowing to your DMs
              </div>
            </div>
          </div>

          {linkTelegram.data ? (
            <>
              <a
                href={linkTelegram.data.deep_link}
                target="_blank"
                rel="noopener noreferrer"
                className="w-full flex items-center justify-center gap-2 bg-bullish hover:bg-bullish/90 text-surface-0 font-bold py-3 px-4 rounded-lg transition-colors shadow-[0_0_15px_rgba(34,197,94,0.15)]"
              >
                <Send className="h-4 w-4" />
                Open in Telegram & Tap Start
                <ExternalLink className="h-3 w-3" />
              </a>
              <p className="text-[10px] text-text-faint text-center">Link expires in 10 minutes. Come back here after tapping Start.</p>
            </>
          ) : (
            <button
              onClick={() => linkTelegram.mutate()}
              disabled={linkTelegram.isPending || isLoading}
              className="w-full flex items-center justify-center gap-2 bg-accent hover:bg-accent-hover text-white font-semibold py-3 px-4 rounded-lg transition-colors disabled:opacity-50"
            >
              {linkTelegram.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
              Connect Telegram
            </button>
          )}
        </div>
      )}
    </Section>
  );
}

/* ── Notification Channels ────────────────────────────────────────── */

function NotificationChannels() {
  const { data: notifPrefs } = useNotificationPrefs();
  const updateNotifs = useUpdateNotificationPrefs();
  const [telegramOn, setTelegramOn] = useState(true);
  const [synced, setSynced] = useState(false);

  if (notifPrefs && !synced) {
    setTelegramOn(notifPrefs.telegram_enabled);
    setSynced(true);
  }

  const dirty = synced && notifPrefs && telegramOn !== notifPrefs.telegram_enabled;

  return (
    <Section title="Notifications" icon={<Bell className="h-4 w-4 text-text-muted" />}>
      <div className="space-y-3">
        <label className="flex items-center gap-3 cursor-pointer group">
          <input
            type="checkbox"
            checked={telegramOn}
            onChange={(e) => setTelegramOn(e.target.checked)}
            className="rounded border-border-subtle"
          />
          <Send className="h-3.5 w-3.5 text-text-faint group-hover:text-text-muted" />
          <div className="flex-1">
            <span className="text-sm text-text-primary">Telegram alerts</span>
            <p className="text-[10px] text-text-faint">Master switch — turn all Telegram alerts on or off.</p>
          </div>
        </label>
        <p className="text-[10px] text-text-faint italic">
          Email &amp; push notifications coming soon.
        </p>

        {dirty && (
          <button
            onClick={() => updateNotifs.mutate({
              ...(notifPrefs as NotificationPrefs),
              telegram_enabled: telegramOn,
            })}
            disabled={updateNotifs.isPending}
            className="text-xs bg-accent hover:bg-accent-hover text-white px-4 py-1.5 rounded-md transition-colors disabled:opacity-50"
          >
            {updateNotifs.isPending ? "Saving..." : "Save"}
          </button>
        )}
        {updateNotifs.isSuccess && !dirty && (
          <span className="text-[10px] text-bullish-text flex items-center gap-1"><Check className="h-3 w-3" /> Saved</span>
        )}
      </div>
    </Section>
  );
}

/* ── Channel Routing (per alert type) ─────────────────────────────
 *  Pick where each AI alert type goes: Telegram, Email, Both, or Off.
 *  Default for new users is Telegram for every type (legacy behavior).
 */

const CHANNEL_OPTIONS: AlertChannel[] = ["telegram", "email", "both", "off"];

const ROUTING_ROWS: { key: keyof NotificationRouting; label: string; sub: string }[] = [
  { key: "ai_update",     label: "AI Updates",        sub: "Context / WAIT commentary" },
  { key: "ai_long",       label: "LONG Entries",      sub: "New long setups" },
  { key: "ai_short",      label: "SHORT Entries",     sub: "SPY structural rejections" },
  { key: "ai_resistance", label: "Resistance Notices", sub: "Tighten-stop warnings" },
  { key: "ai_exit",       label: "Exit Signals",      sub: "EXIT_NOW / TAKE_PROFITS" },
];

function channelLabel(c: AlertChannel): string {
  switch (c) {
    case "telegram": return "Telegram";
    case "email":    return "Email";
    case "both":     return "Both";
    case "off":      return "Off";
  }
}

// @ts-expect-error — kept for rollback; removed from render per 2026-05-27 cleanup
function ChannelRouting() {
  const { data } = useNotificationRouting();
  const update = useUpdateNotificationRouting();
  const [routing, setRouting] = useState<NotificationRouting | null>(null);
  const [synced, setSynced] = useState(false);

  useEffect(() => {
    if (data && !synced) {
      setRouting(data);
      setSynced(true);
    }
  }, [data, synced]);

  if (!routing) return null;

  const dirty = data && (
    ROUTING_ROWS.some(({ key }) => routing[key] !== data[key]) ||
    (routing.telegram_update_symbols || "") !== (data.telegram_update_symbols || "")
  );

  function setChannel(key: keyof NotificationRouting, c: AlertChannel) {
    setRouting((prev) => (prev ? { ...prev, [key]: c } : prev));
  }

  function save() {
    if (!routing) return;
    update.mutate(routing, {
      onSuccess: (saved) => {
        setRouting(saved);
        toast.success("Alert routing saved");
      },
    });
  }

  return (
    <Section title="Alert Channel Routing" icon={<Send className="h-4 w-4 text-accent" />}>
      <p className="text-xs text-text-faint mb-4">
        Choose where each AI alert type is delivered. Email uses your account address ({/* read-only */}).
      </p>

      <div className="space-y-3">
        {ROUTING_ROWS.map(({ key, label, sub }) => (
          <div key={key} className="flex items-center justify-between gap-3">
            <div className="flex-1 min-w-0">
              <div className="text-xs font-semibold text-text-primary">{label}</div>
              <div className="text-[10px] text-text-faint leading-tight">{sub}</div>
            </div>
            <select
              value={routing[key]}
              onChange={(e) => setChannel(key, e.target.value as AlertChannel)}
              className="text-xs bg-surface-3 border border-border-subtle rounded-md px-2 py-1 text-text-primary focus:border-accent focus:outline-none"
            >
              {CHANNEL_OPTIONS.map((c) => (
                <option key={c} value={c}>{channelLabel(c)}</option>
              ))}
            </select>
          </div>
        ))}
      </div>

      {/* Per-symbol Telegram override for AI Updates */}
      <div className="mt-4 pt-4 border-t border-border-subtle/50">
        <label className="text-xs font-semibold text-text-primary block mb-1">
          Always send AI Updates to Telegram for
        </label>
        <input
          type="text"
          value={routing.telegram_update_symbols || ""}
          onChange={(e) =>
            setRouting((prev) =>
              prev ? { ...prev, telegram_update_symbols: e.target.value.toUpperCase() } : prev
            )
          }
          placeholder="SPY, NVDA, QQQ"
          className="w-full rounded-md border border-border-subtle bg-surface-3 px-3 py-1.5 text-sm font-mono text-text-primary focus:border-accent focus:outline-none"
        />
        <p className="text-[10px] text-text-faint mt-1">
          Comma-separated symbols. These symbols always get Telegram delivery for
          AI Updates, even when the general AI Updates routing is set to Email or Off.
        </p>
      </div>

      <div className="flex items-center gap-3 mt-4">
        <button
          onClick={save}
          disabled={!dirty || update.isPending}
          className="text-xs bg-accent hover:bg-accent-hover text-white px-4 py-1.5 rounded-md transition-colors disabled:opacity-50"
        >
          {update.isPending ? "Saving..." : "Save Routing"}
        </button>
        {update.isSuccess && !dirty && (
          <span className="text-[10px] text-bullish-text flex items-center gap-1">
            <Check className="h-3 w-3" /> Saved
          </span>
        )}
      </div>
    </Section>
  );
}

/* ── AI Alert Filters (Spec 36) ────────────────────────────────────
 *  User-controlled alert volume. Replaces deprecated rule-engine
 *  pattern toggles.
 */

const ALL_DIRECTIONS = ["LONG", "SHORT", "RESISTANCE", "EXIT"] as const;
type Direction = (typeof ALL_DIRECTIONS)[number];

// @ts-expect-error — kept for rollback; removed from render per 2026-05-27 cleanup
function AIAlertFilters() {
  const { data: prefs } = useNotificationPrefs();
  const update = useUpdateNotificationPrefs();

  const [minConviction, setMinConviction] = useState<"low" | "medium" | "high">("medium");
  const [waitEnabled, setWaitEnabled] = useState(false);
  const [directions, setDirections] = useState<Set<Direction>>(new Set(ALL_DIRECTIONS));
  const [synced, setSynced] = useState(false);

  if (prefs && !synced) {
    setMinConviction((prefs.min_conviction as "low" | "medium" | "high") || "medium");
    setWaitEnabled(!!prefs.wait_alerts_enabled);
    const dirStr = prefs.alert_directions || "LONG,SHORT,RESISTANCE,EXIT";
    setDirections(new Set(
      dirStr.split(",").map((d) => d.trim().toUpperCase()).filter(Boolean) as Direction[]
    ));
    setSynced(true);
  }

  function toggleDirection(d: Direction) {
    const next = new Set(directions);
    if (next.has(d)) next.delete(d);
    else next.add(d);
    setDirections(next);
  }

  const dirty = synced && prefs && (
    minConviction !== (prefs.min_conviction || "medium") ||
    waitEnabled !== !!prefs.wait_alerts_enabled ||
    Array.from(directions).sort().join(",") !==
      (prefs.alert_directions || "LONG,SHORT,RESISTANCE,EXIT").split(",").map((s) => s.trim().toUpperCase()).sort().join(",")
  );

  const noDirections = directions.size === 0;

  function save() {
    if (!prefs) return;
    update.mutate({
      ...(prefs as NotificationPrefs),
      min_conviction: minConviction,
      wait_alerts_enabled: waitEnabled,
      alert_directions: Array.from(directions).join(","),
    });
  }

  if (!prefs) return null;

  return (
    <Section title="AI Alert Filters" icon={<Filter className="h-4 w-4 text-accent" />}>
      <p className="text-xs text-text-faint mb-4">
        Control which AI alerts reach your Telegram. These apply on top of your tier's daily limit.
      </p>

      {/* Minimum conviction */}
      <div className="mb-5">
        <label className="text-xs font-semibold text-text-primary block mb-2">Minimum conviction</label>
        <div className="grid grid-cols-3 gap-2">
          {(["high", "medium", "low"] as const).map((level) => (
            <button
              key={level}
              onClick={() => setMinConviction(level)}
              className={`text-xs font-medium px-3 py-2 rounded-md border transition-colors ${
                minConviction === level
                  ? "bg-accent/15 border-accent/40 text-accent"
                  : "bg-surface-2/40 border-border-subtle text-text-muted hover:bg-surface-2"
              }`}
            >
              {level === "high" ? "High only" : level === "medium" ? "Medium+" : "All (Low+)"}
            </button>
          ))}
        </div>
        <p className="text-[10px] text-text-faint mt-1.5">
          {minConviction === "high" && "Tightest filter — only the highest-probability AI signals."}
          {minConviction === "medium" && "Balanced — skip low conviction, deliver medium and high."}
          {minConviction === "low" && "Full firehose — every AI signal, including low conviction."}
        </p>
      </div>

      {/* AI Updates */}
      <div className="mb-5 pb-5 border-b border-border-subtle/50">
        <label className="flex items-start gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={waitEnabled}
            onChange={(e) => setWaitEnabled(e.target.checked)}
            className="mt-0.5 rounded border-border-subtle"
          />
          <div className="flex-1">
            <span className="text-xs font-semibold text-text-primary">Send AI Updates</span>
            <p className="text-[10px] text-text-faint leading-tight mt-0.5">
              Context between trades — what the AI is watching and why it's staying out of chop.
              Chatty during sideways markets. Updates always appear in the dashboard regardless of this setting.
            </p>
          </div>
        </label>
      </div>

      {/* Direction filters */}
      <div className="mb-4">
        <label className="text-xs font-semibold text-text-primary block mb-2">Alert me on</label>
        <div className="grid grid-cols-2 gap-2">
          {ALL_DIRECTIONS.map((d) => {
            const on = directions.has(d);
            const label =
              d === "LONG" ? "LONG entries" :
              d === "SHORT" ? "SHORT entries" :
              d === "RESISTANCE" ? "Resistance notices" :
              "Exit signals";
            return (
              <label key={d} className="flex items-center gap-2 cursor-pointer p-2 rounded-md hover:bg-surface-2/50 transition-colors">
                <input
                  type="checkbox"
                  checked={on}
                  onChange={() => toggleDirection(d)}
                  className="rounded border-border-subtle"
                />
                <span className={`text-xs ${on ? "text-text-primary" : "text-text-muted"}`}>{label}</span>
              </label>
            );
          })}
        </div>
        {noDirections && (
          <p className="text-[10px] text-warning-text mt-1.5">
            ⚠︎ You've disabled all alert directions. You won't receive any AI Telegram alerts.
          </p>
        )}
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={save}
          disabled={!dirty || update.isPending}
          className="text-xs bg-accent hover:bg-accent-hover text-white px-4 py-1.5 rounded-md transition-colors disabled:opacity-50"
        >
          {update.isPending ? "Saving..." : "Save Filters"}
        </button>
        {update.isSuccess && !dirty && (
          <span className="text-[10px] text-bullish-text flex items-center gap-1">
            <Check className="h-3 w-3" /> Saved
          </span>
        )}
      </div>
    </Section>
  );
}

/* ── Profile & Account ────────────────────────────────────────────── */

function ProfileSection() {
  const user = useAuthStore((s) => s.user);
  const { isPro, tier } = useFeatureGate();
  const [displayName, setDisplayName] = useState(user?.display_name ?? "");
  const updateProfile = useUpdateProfile();

  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [pwMsg, setPwMsg] = useState("");
  const [showPw, setShowPw] = useState(false);
  const changePassword = useChangePassword();

  return (
    <Section title="Account" icon={<User className="h-4 w-4 text-text-muted" />}>
      <div className="space-y-4">
        {/* Email + Tier */}
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-text-primary">{user?.email}</p>
            <span className="text-[10px] text-text-faint">Account email</span>
          </div>
          <div className="flex items-center gap-2">
            <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${
              isPro ? "bg-accent/10 text-accent border border-accent/20" : "bg-surface-3 text-text-faint"
            }`}>
              {tier.toUpperCase()}
            </span>
            <a href="/billing" className="text-[10px] text-accent hover:text-accent-hover">
              {isPro ? "Manage" : "Upgrade"}
            </a>
          </div>
        </div>

        {/* Display Name */}
        <form onSubmit={(e) => { e.preventDefault(); updateProfile.mutate({ display_name: displayName }); }} className="flex gap-2">
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="Display name"
            className="flex-1 rounded-md border border-border-subtle bg-surface-3 px-3 py-2 text-sm text-text-primary focus:border-accent focus:ring-1 focus:ring-accent/30 focus:outline-none"
          />
          <button
            type="submit"
            disabled={updateProfile.isPending}
            className="text-xs bg-surface-3 hover:bg-surface-4 border border-border-subtle text-text-primary px-3 py-1.5 rounded-md transition-colors disabled:opacity-50"
          >
            {updateProfile.isSuccess ? <Check className="h-3 w-3 text-bullish-text" /> : "Save"}
          </button>
        </form>

        {/* Change Password (collapsible) */}
        <div className="border-t border-border-subtle/50 pt-3">
          <button
            onClick={() => setShowPw(!showPw)}
            className="text-xs text-text-muted hover:text-text-secondary flex items-center gap-1 transition-colors"
          >
            <Key className="h-3 w-3" />
            Change password
            <ChevronRight className={`h-3 w-3 transition-transform ${showPw ? "rotate-90" : ""}`} />
          </button>

          {showPw && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                setPwMsg("");
                changePassword.mutate(
                  { current_password: currentPw, new_password: newPw },
                  {
                    onSuccess: () => { setPwMsg("Updated"); setCurrentPw(""); setNewPw(""); },
                    onError: (err) => { setPwMsg(err instanceof Error ? err.message : "Failed"); },
                  },
                );
              }}
              className="mt-3 space-y-2"
            >
              <input type="password" value={currentPw} onChange={(e) => setCurrentPw(e.target.value)}
                placeholder="Current password" required
                className="w-full rounded-md border border-border-subtle bg-surface-3 px-3 py-2 text-sm text-text-primary focus:border-accent focus:ring-1 focus:ring-accent/30 focus:outline-none" />
              <input type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)}
                placeholder="New password (min 6)" required minLength={6}
                className="w-full rounded-md border border-border-subtle bg-surface-3 px-3 py-2 text-sm text-text-primary focus:border-accent focus:ring-1 focus:ring-accent/30 focus:outline-none" />
              <div className="flex items-center gap-2">
                <button type="submit" disabled={changePassword.isPending}
                  className="text-xs bg-accent text-white px-3 py-1.5 rounded-md disabled:opacity-50">
                  Update
                </button>
                {pwMsg && (
                  <span className={`text-[10px] ${pwMsg === "Updated" ? "text-bullish-text" : "text-bearish-text"}`}>{pwMsg}</span>
                )}
              </div>
            </form>
          )}
        </div>
      </div>
    </Section>
  );
}

/* ── Trading Settings (portfolio size, risk) ──────────────────────── */

function TradingSettings() {
  const { data: prefs } = useNotificationPrefs();
  const update = useUpdateNotificationPrefs();
  const [portfolioSize, setPortfolioSize] = useState(50000);
  const [riskPct, setRiskPct] = useState(1);
  const [synced, setSynced] = useState(false);

  if (prefs && !synced) {
    setPortfolioSize(prefs.default_portfolio_size ?? 50000);
    setRiskPct(prefs.default_risk_pct ?? 1);
    setSynced(true);
  }

  const dirty = synced && prefs && (
    portfolioSize !== (prefs.default_portfolio_size ?? 50000) ||
    riskPct !== (prefs.default_risk_pct ?? 1)
  );

  function save() {
    if (!prefs) return;
    update.mutate({
      ...(prefs as NotificationPrefs),
      default_portfolio_size: portfolioSize,
      default_risk_pct: riskPct,
    });
    toast.success("Position sizing saved");
  }

  return (
    <Section title="Position Sizing" icon={<DollarSign className="h-4 w-4 text-text-muted" />}>
      <p className="text-xs text-text-faint mb-4">
        Used when you tap "Took It" on an AI alert — shares = (portfolio × risk%) / (entry − stop).
      </p>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="text-xs text-text-muted mb-1 block">Portfolio Size ($)</label>
          <input
            type="number"
            value={portfolioSize}
            onChange={(e) => setPortfolioSize(Number(e.target.value))}
            className="w-full rounded-md border border-border-subtle bg-surface-3 px-3 py-1.5 text-sm font-mono text-text-primary focus:border-accent focus:outline-none"
          />
        </div>
        <div>
          <label className="text-xs text-text-muted mb-1 block">Risk per Trade (%)</label>
          <input
            type="number"
            value={riskPct}
            step={0.25}
            min={0.25}
            max={5}
            onChange={(e) => setRiskPct(Number(e.target.value))}
            className="w-full rounded-md border border-border-subtle bg-surface-3 px-3 py-1.5 text-sm font-mono text-text-primary focus:border-accent focus:outline-none"
          />
        </div>
      </div>
      <p className="text-[10px] text-text-faint mt-2">
        Max $ risk per trade: <span className="font-mono text-text-primary">${((portfolioSize * riskPct) / 100).toFixed(0)}</span>
      </p>
      <div className="flex items-center gap-3 mt-3">
        <button
          onClick={save}
          disabled={!dirty || update.isPending}
          className="text-xs bg-accent hover:bg-accent-hover text-white px-4 py-1.5 rounded-md transition-colors disabled:opacity-50"
        >
          {update.isPending ? "Saving..." : "Save"}
        </button>
        {update.isSuccess && !dirty && (
          <span className="text-[10px] text-bullish-text flex items-center gap-1">
            <Check className="h-3 w-3" /> Saved
          </span>
        )}
      </div>
    </Section>
  );
}

/* ── Theme Toggle ────────────────────────────────────────────────── */

function ThemeToggle() {
  const [isDark, setIsDark] = useState(() => !document.documentElement.classList.contains("light"));

  function toggle() {
    const next = !isDark;
    setIsDark(next);
    if (next) {
      document.documentElement.classList.remove("light");
      localStorage.setItem("theme", "dark");
    } else {
      document.documentElement.classList.add("light");
      localStorage.setItem("theme", "light");
    }
  }

  return (
    <Section title="Appearance" icon={isDark ? <Moon className="h-4 w-4 text-text-muted" /> : <Sun className="h-4 w-4 text-text-muted" />}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-text-primary">{isDark ? "Dark Mode" : "Light Mode"}</p>
          <p className="text-xs text-text-muted">Switch between dark and light themes</p>
        </div>
        <button
          onClick={toggle}
          className={`relative w-12 h-6 rounded-full transition-colors ${isDark ? "bg-accent" : "bg-surface-4"}`}
        >
          <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${isDark ? "" : "translate-x-6"}`} />
        </button>
      </div>
    </Section>
  );
}

/* ── Alert Types (per-type enable/disable) ────────────────────────── */

function AlertTypesSection() {
  const { data: types, isLoading } = useAlertConfig();
  const toggle = useToggleAlertConfig();

  const grouped: Record<string, AlertTypeConfigItem[]> = {};
  for (const t of types ?? []) {
    (grouped[t.category] ??= []).push(t);
  }
  const enabledCount = (types ?? []).filter((t) => t.enabled).length;

  return (
    <Section title="Alert Types" icon={<Zap className="h-4 w-4 text-accent" />}>
      <p className="text-xs text-text-muted mb-4">
        Tap a card to route that alert type to Telegram + your Signals feed.
        Disabled types still fire and record silently for review. Changes take
        effect on the next alert.
        {types && (
          <span className="text-text-faint">
            {" "}· {enabledCount} of {types.length} on
          </span>
        )}
      </p>

      {isLoading && <p className="text-xs text-text-faint">Loading…</p>}

      <div className="space-y-5">
        {Object.entries(grouped).map(([category, items]) => {
          const onCount = items.filter((i) => i.enabled).length;
          return (
            <div key={category}>
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] font-bold uppercase tracking-wide text-text-secondary">
                  {category}
                </span>
                <span
                  className={`text-[10px] font-semibold ${
                    onCount > 0 ? "text-accent" : "text-text-faint"
                  }`}
                >
                  {onCount}/{items.length} on
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {items.map((t) => (
                  <button
                    key={t.alert_type}
                    onClick={() =>
                      toggle.mutate({ alert_type: t.alert_type, enabled: !t.enabled })
                    }
                    disabled={toggle.isPending}
                    role="switch"
                    aria-checked={t.enabled}
                    className={`flex items-start gap-2 rounded-lg border px-3 py-2.5 text-left transition-colors disabled:opacity-60 ${
                      t.enabled
                        ? "border-accent/50 bg-accent/10"
                        : "border-border-subtle bg-surface-1 hover:bg-surface-2"
                    }`}
                  >
                    <span
                      className={`mt-0.5 shrink-0 h-4 w-4 rounded flex items-center justify-center ${
                        t.enabled
                          ? "bg-accent"
                          : "bg-surface-3 border border-border-subtle"
                      }`}
                    >
                      {t.enabled && <Check className="h-3 w-3 text-white" />}
                    </span>
                    <span
                      className={`text-[11px] leading-snug ${
                        t.enabled
                          ? "text-text-primary font-medium"
                          : "text-text-muted"
                      }`}
                    >
                      {t.label}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </Section>
  );
}

/* ── Setup Grade Filter — spec 61 follow-up ───────────────────────── */

function SetupGradeFilter() {
  const { data: prefs } = useNotificationPrefs();
  const update = useUpdateNotificationPrefs();
  const [grade, setGrade] = useState<"A" | "B" | "C">("C");
  const [synced, setSynced] = useState(false);

  if (prefs && !synced) {
    setGrade((prefs.min_alert_grade as "A" | "B" | "C") || "C");
    setSynced(true);
  }

  const dirty = synced && prefs && grade !== ((prefs.min_alert_grade as "A" | "B" | "C") || "C");

  if (!prefs) return null;

  const LEVELS: { id: "A" | "B" | "C"; title: string; subtitle: string }[] = [
    { id: "A", title: "A only",  subtitle: "High conviction — vol ≥ 2× AND slope ≥ +0.05%" },
    { id: "B", title: "A + B",   subtitle: "Either gate passed — moderate filter" },
    { id: "C", title: "All",     subtitle: "No filter — every alert reaches you" },
  ];

  return (
    <Section title="Setup Grade Filter" icon={<Award className="h-4 w-4 text-accent" />}>
      <p className="text-xs text-text-faint mb-3">
        Filter your alert feed by setup grade. Computed per-alert from volume + VWAP slope —
        the same gates the v2 quality pipeline uses.
      </p>
      <div className="space-y-2">
        {LEVELS.map((lvl) => (
          <button
            key={lvl.id}
            onClick={() => setGrade(lvl.id)}
            className={`w-full flex items-start gap-3 px-3 py-2.5 rounded-md border text-left transition-colors ${
              grade === lvl.id
                ? "bg-accent/15 border-accent/40"
                : "bg-surface-2/40 border-border-subtle hover:bg-surface-2"
            }`}
          >
            <span className={`text-sm font-bold w-6 text-center ${
              grade === lvl.id ? "text-accent" : "text-text-muted"
            }`}>
              {lvl.id}
            </span>
            <div className="flex-1">
              <div className={`text-xs font-semibold ${
                grade === lvl.id ? "text-accent" : "text-text-primary"
              }`}>
                {lvl.title}
              </div>
              <div className="text-[10px] text-text-faint mt-0.5">{lvl.subtitle}</div>
            </div>
          </button>
        ))}
      </div>
      {dirty && (
        <button
          onClick={() => update.mutate({
            ...(prefs as NotificationPrefs),
            min_alert_grade: grade,
          })}
          disabled={update.isPending}
          className="mt-3 text-xs bg-accent hover:bg-accent-hover text-white px-4 py-1.5 rounded-md transition-colors disabled:opacity-50"
        >
          {update.isPending ? "Saving..." : "Save filter"}
        </button>
      )}
      {update.isSuccess && !dirty && (
        <span className="mt-2 text-[10px] text-bullish-text flex items-center gap-1">
          <Check className="h-3 w-3" /> Saved
        </span>
      )}
    </Section>
  );
}

/* ── Signal Notifications (browser alerts) ────────────────────────── */

function SignalNotifications() {
  const [enabled, setEnabled] = useState(() => signalNotificationsEnabled());
  const [perm, setPerm] = useState<string>(
    typeof Notification !== "undefined" ? Notification.permission : "unsupported",
  );

  async function requestPerm(): Promise<boolean> {
    if (typeof Notification === "undefined") {
      toast.error("This browser doesn't support notifications.");
      return false;
    }
    let p = Notification.permission;
    if (p === "default") p = await Notification.requestPermission();
    setPerm(p);
    return p === "granted";
  }

  async function handleToggle() {
    if (!enabled && !(await requestPerm())) {
      toast.error("Allow notifications for this site, then try again.");
      return;
    }
    const next = !enabled;
    setEnabled(next);
    setSignalNotificationsEnabled(next);
    toast.success(next ? "Signal notifications on" : "Signal notifications off");
  }

  async function sendTest() {
    if (!(await requestPerm())) {
      toast.error("Permission not granted — allow notifications in your browser.");
      return;
    }
    toast.info("Test — BusyTradersDesk signal notification");
    try {
      const n = new Notification("BusyTradersDesk · test signal", {
        body: "If you see this, signal notifications are working.",
        icon: "/logo-profile.svg",
      });
      n.onclick = () => {
        window.focus();
        n.close();
      };
    } catch {
      toast.error(
        "Couldn't show the popup — check macOS System Settings → Notifications for your browser.",
      );
    }
  }

  const permLabel = perm === "granted" ? "granted"
    : perm === "denied" ? "blocked"
    : perm === "unsupported" ? "unsupported"
    : "not asked yet";

  return (
    <Section title="Signal Notifications" icon={<Bell className="h-4 w-4 text-accent" />}>
      <div className="flex items-start justify-between gap-4 mb-3">
        <p className="text-xs text-text-muted">
          Pop a desktop notification, with a sound, when a new routed signal
          lands — works while this app is open in any browser tab (even a
          background tab). Telegram still covers you when the browser is closed.
        </p>
        <button
          onClick={handleToggle}
          role="switch"
          aria-checked={enabled}
          className={`shrink-0 relative w-11 h-6 rounded-full transition-colors ${
            enabled ? "bg-accent" : "bg-surface-3"
          }`}
        >
          <span
            className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all ${
              enabled ? "left-[22px]" : "left-0.5"
            }`}
          />
        </button>
      </div>

      <div className="flex items-center justify-between gap-3 rounded-lg bg-surface-2 border border-border-subtle px-3 py-2">
        <span className="text-[11px] text-text-muted">
          Browser permission:{" "}
          <span
            className={`font-semibold ${
              perm === "granted"
                ? "text-bullish-text"
                : perm === "denied"
                ? "text-bearish-text"
                : "text-text-secondary"
            }`}
          >
            {permLabel}
          </span>
        </span>
        <button
          onClick={sendTest}
          className="text-[11px] px-3 py-1 rounded-md bg-accent/15 text-accent hover:bg-accent/25 transition-colors font-medium"
        >
          Send test
        </button>
      </div>

      {perm === "denied" && (
        <p className="text-[10px] text-bearish-text/80 mt-2">
          Notifications are blocked. Re-allow them for this site in your
          browser's site settings, and make sure your browser is allowed in
          macOS System Settings → Notifications.
        </p>
      )}
    </Section>
  );
}

/* ── Market gate — exempt symbols ─────────────────────────────────── */

function ExemptListEditor({ label, hint, list, onSave }: {
  label: string;
  hint: string;
  list: string[];
  onSave: (next: string[]) => void;
}) {
  const [input, setInput] = useState("");
  const add = () => {
    const sym = input.trim().toUpperCase();
    if (sym && !list.includes(sym)) onSave([...list, sym]);
    setInput("");
  };
  return (
    <div>
      <div className="text-xs font-semibold text-text-secondary mb-0.5">{label}</div>
      <div className="text-[11px] text-text-muted mb-2">{hint}</div>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {list.length === 0 && <span className="text-xs text-text-faint">none</span>}
        {list.map((sym) => (
          <span key={sym} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-accent/10 border border-accent/30 text-[11px] font-semibold text-accent">
            {sym}
            <button
              onClick={() => onSave(list.filter((s) => s !== sym))}
              className="text-accent/60 hover:text-bearish-text"
              aria-label={`Remove ${sym}`}
            >
              ×
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-1.5">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          placeholder="Add symbol…"
          className="flex-1 bg-surface-1 border border-border-subtle rounded px-2 py-1 text-[11px] text-text-secondary placeholder:text-text-faint focus:outline-none focus:border-accent/40"
        />
        <button
          onClick={add}
          className="shrink-0 text-[11px] px-3 py-1 rounded bg-accent/15 text-accent border border-accent/40 hover:bg-accent/20"
        >
          Add
        </button>
      </div>
    </div>
  );
}

function MarketGateSection() {
  const { data, isLoading } = useRegimeConfig();
  const update = useUpdateRegimeConfig();
  const toList = (s?: string) =>
    s ? s.split(",").map((x) => x.trim().toUpperCase()).filter(Boolean) : [];

  return (
    <Section title="Market gate — exempt symbols" icon={<Filter className="h-4 w-4 text-accent" />}>
      <p className="text-xs text-text-muted mb-4">
        These symbols are <strong>never blocked</strong> by the regime gate — their
        buys deliver even when SPY (stocks) or BTC (crypto) is below its prior-day
        low. Add genuine relative-strength names you'd still trade in a downtrend
        (e.g. AAPL). Takes effect on the next alert — no redeploy.
      </p>
      {isLoading ? (
        <div className="text-xs text-text-faint">Loading…</div>
      ) : (
        <div className="space-y-4">
          <ExemptListEditor
            label="Stocks — SPY gate"
            hint="Exempt from the SPY-below-PDL block."
            list={toList(data?.index_exempt)}
            onSave={(l) => update.mutate({ index_exempt: l.join(",") })}
          />
          <ExemptListEditor
            label="Crypto — BTC gate"
            hint="Exempt from the BTC-below-PDL block (BTC-USD is the index)."
            list={toList(data?.crypto_exempt)}
            onSave={(l) => update.mutate({ crypto_exempt: l.join(",") })}
          />
        </div>
      )}
    </Section>
  );
}

function InfoAlertSymbolsSection() {
  const { data, isLoading } = useRegimeConfig();
  const update = useUpdateRegimeConfig();
  const toList = (s?: string) =>
    s ? s.split(",").map((x) => x.trim().toUpperCase()).filter(Boolean) : [];

  return (
    <Section title="Info-alert symbols" icon={<Zap className="h-4 w-4 text-accent" />}>
      <p className="text-xs text-text-muted mb-4">
        Which symbols fire the <strong>informational</strong> alerts — multi-touch
        level crosses and gap entered/filled. The indicators fire broadly; only
        these symbols are kept. Add a stock here to start watching it — no need to
        edit the Pine. Toggle the alerts themselves on/off in <strong>Alert Types</strong> above.
      </p>
      {isLoading ? (
        <div className="text-xs text-text-faint">Loading…</div>
      ) : (
        <ExemptListEditor
          label="Symbols that fire multi-touch & gap alerts"
          hint="e.g. SPY, NBIS, QQQ. Applies to both the level-cross and gap alerts."
          list={toList(data?.alert_symbols)}
          onSave={(l) => update.mutate({ alert_symbols: l.join(",") })}
        />
      )}
    </Section>
  );
}

export default function SettingsPage() {
  return (
    <div className="h-full overflow-y-auto p-5">
      <div className="max-w-3xl mx-auto space-y-5">
        <h1 className="font-display text-xl font-bold text-text-primary">Settings</h1>

        {/* Two-column on desktop: alerts left, account right */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* Left column: Alerts + preferences */}
          {/* Removed 2026-05-27 per user — focus on essential settings:
             - ChannelRouting: redundant with TelegramSetup + AlertTypesSection
             - AIAlertFilters: AI Updates not actively used; clutters UI */}
          <div className="space-y-5">
            <TelegramSetup />
            <NotificationChannels />
            <SetupGradeFilter />
            <SignalNotifications />
            <ThemeToggle />
          </div>

          {/* Right column: Account + trading */}
          <div className="space-y-5">
            <ProfileSection />
            <TradingSettings />
          </div>
        </div>

        {/* Per-alert-type enable/disable */}
        <AlertTypesSection />

        {/* Regime-gate exempt symbols */}
        <MarketGateSection />

        {/* Which symbols fire the info alerts (multi-touch / gap) */}
        <InfoAlertSymbolsSection />

        {/* Referral program */}
        <ReferralSection />
      </div>
    </div>
  );
}


/* ── Referral Section ────────────────────────────────────────────── */

function ReferralSection() {
  const [data, setData] = useState<any>(null);
  const [copied, setCopied] = useState(false);
  const [refCode, setRefCode] = useState("");
  const [applying, setApplying] = useState(false);
  const [applyMsg, setApplyMsg] = useState("");

  useEffect(() => {
    api.get("/referral/code").then(setData).catch(() => {});
  }, []);

  function copyLink() {
    if (!data?.share_url) return;
    navigator.clipboard.writeText(data.share_url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function applyCode() {
    if (!refCode.trim()) return;
    setApplying(true);
    setApplyMsg("");
    try {
      const res = await api.post<{ message: string }>("/referral/apply", { code: refCode.trim() });
      setApplyMsg(res.message || "Referral applied!");
    } catch (err: any) {
      setApplyMsg(err?.message || "Invalid code");
    } finally {
      setApplying(false);
    }
  }

  return (
    <div className="bg-surface-1 border border-border-subtle rounded-xl p-5">
      <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
        <Gift className="h-4 w-4 text-accent" />
        Referral Program
      </h3>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* Share your code */}
        <div>
          <p className="text-xs text-text-muted mb-2">Share your link — both you and your friend get 30 days free Pro</p>
          {data && (
            <div className="flex items-center gap-2">
              <input
                readOnly
                value={data.share_url || ""}
                className="flex-1 bg-surface-3 border border-border-subtle rounded px-3 py-2 text-xs font-mono text-text-secondary"
              />
              <button
                onClick={copyLink}
                className="text-xs font-bold text-accent bg-accent/10 hover:bg-accent/20 border border-accent/20 px-3 py-2 rounded transition-colors"
              >
                {copied ? "Copied!" : "Copy"}
              </button>
            </div>
          )}
          {data && (
            <div className="flex items-center gap-4 mt-3 text-xs text-text-faint">
              <span>Referrals: <span className="text-text-primary font-bold">{data.total_referrals}</span></span>
              <span>Rewarded: <span className="text-bullish-text font-bold">{data.rewarded}</span></span>
            </div>
          )}
        </div>

        {/* Apply a code */}
        <div>
          <p className="text-xs text-text-muted mb-2">Have a referral code? Enter it below</p>
          <div className="flex items-center gap-2">
            <input
              value={refCode}
              onChange={(e) => setRefCode(e.target.value.toUpperCase())}
              placeholder="Enter code"
              className="flex-1 bg-surface-3 border border-border-subtle rounded px-3 py-2 text-xs font-mono text-text-primary uppercase focus:border-accent focus:ring-1 focus:ring-accent/30"
              maxLength={8}
            />
            <button
              onClick={applyCode}
              disabled={applying || !refCode.trim()}
              className="text-xs font-bold text-white bg-bullish hover:bg-bullish/80 px-3 py-2 rounded transition-colors disabled:opacity-40"
            >
              {applying ? "..." : "Apply"}
            </button>
          </div>
          {applyMsg && (
            <p className={`text-xs mt-2 ${applyMsg.includes("applied") ? "text-bullish-text" : "text-bearish-text"}`}>
              {applyMsg}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
