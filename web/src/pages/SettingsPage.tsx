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
  useTelegramStatus,
  useTelegramLink,
  useTelegramUnlink,
  useAlertConfig,
  useToggleAlertConfig,
  useToggleAllAlertConfig,
  useMarketGate,
  useUpdateMarketGate,
  useWatchlist,
  type AlertTypeConfigItem,
} from "../api/hooks";
import { useFeatureGate } from "../hooks/useFeatureGate";
import type { NotificationPrefs } from "../types";
import {
  Send, Bell, User, Key, ChevronRight, Check,
  ExternalLink, Loader2, DollarSign, Gift,
  Sun, Moon, Zap, ShieldCheck, X, Plus,
} from "lucide-react";
import { toast } from "../components/Toast";
import { signalNotificationsEnabled, setSignalNotificationsEnabled } from "../hooks/useSignalNotifications";

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
  const [desktopOn, setDesktopOn] = useState(signalNotificationsEnabled);

  // Desktop (browser/Electron) alerts need BOTH the opt-in AND the OS notification
  // permission. Requesting permission was the missing piece — without it the
  // Notification.permission stays "default" and signals never popped on desktop.
  async function toggleDesktop(on: boolean) {
    if (on && typeof Notification !== "undefined" && Notification.permission !== "granted") {
      const perm = await Notification.requestPermission();
      if (perm !== "granted") {
        toast.info("Allow notifications for this app in your system settings to get desktop alerts.");
        setDesktopOn(false);
        setSignalNotificationsEnabled(false);
        return;
      }
    }
    setDesktopOn(on);
    setSignalNotificationsEnabled(on);
    if (on) toast.info("Desktop alerts on — new signals will pop up; click one to open its chart.");
  }

  if (notifPrefs && !synced) {
    setTelegramOn(notifPrefs.telegram_enabled);
    setSynced(true);
  }

  return (
    <Section title="Notifications" icon={<Bell className="h-4 w-4 text-text-muted" />}>
      <div className="divide-y divide-border-subtle/40">
        <div className="flex items-center gap-3 py-3">
          <Send className="h-4 w-4 shrink-0 text-text-faint" />
          <div className="min-w-0 flex-1">
            <div className="text-sm text-text-primary">Telegram alerts</div>
            <p className="text-[11px] text-text-faint">Master switch — turn all Telegram alerts on or off.</p>
          </div>
          <Toggle
            on={telegramOn}
            disabled={!notifPrefs || updateNotifs.isPending}
            onClick={() => { const n = !telegramOn; setTelegramOn(n); if (notifPrefs) updateNotifs.mutate({ ...notifPrefs, telegram_enabled: n }); }}
          />
        </div>

        <div className="flex items-center gap-3 py-3">
          <Bell className="h-4 w-4 shrink-0 text-text-faint" />
          <div className="min-w-0 flex-1">
            <div className="text-sm text-text-primary">Desktop alerts</div>
            <p className="text-[11px] text-text-faint">Pop up new signals on this device — click one to jump to its chart.</p>
          </div>
          <Toggle on={desktopOn} onClick={() => toggleDesktop(!desktopOn)} />
        </div>

        <div className="flex items-center gap-3 py-3">
          <ShieldCheck className="h-4 w-4 shrink-0 text-text-faint" />
          <div className="min-w-0 flex-1">
            <div className="text-sm text-text-primary">Day-trade alerts: my Focus list only</div>
            <p className="text-[11px] text-text-faint">Off = your whole watchlist (default). On = push day-trade alerts only for symbols on your Focus tab — the rest are still tracked in the feed, marked “not in Focus.” Swing &amp; long-term always cover your whole watchlist.</p>
          </div>
          <Toggle
            on={!!notifPrefs?.daytrade_focus_only}
            disabled={!notifPrefs}
            onClick={() => notifPrefs && updateNotifs.mutate({ ...(notifPrefs as NotificationPrefs), daytrade_focus_only: !notifPrefs.daytrade_focus_only })}
          />
        </div>
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
  const [scale, setScale] = useState(() => localStorage.getItem("ui_scale") || "1");

  function applyScale(v: string) {
    localStorage.setItem("ui_scale", v);
    // `zoom` scales everything — px-hardcoded text, prices, AND the chart canvas — in
    // Chromium (the desktop app + most browsers). One knob for "make it all bigger".
    (document.documentElement.style as unknown as Record<string, string>).zoom = v;
    setScale(v);
  }

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
        <Toggle on={isDark} onClick={toggle} />
      </div>

      <div className="flex items-center justify-between mt-4 pt-4 border-t border-border-subtle">
        <div>
          <p className="text-sm font-medium text-text-primary">Text size</p>
          <p className="text-xs text-text-muted">Make all text, prices &amp; charts bigger</p>
        </div>
        <div className="flex gap-1.5">
          {([["1", "Normal"], ["1.15", "Large"], ["1.3", "XL"]] as const).map(([v, label]) => (
            <button
              key={v}
              onClick={() => applyScale(v)}
              className={`px-3 py-1.5 rounded-lg text-[13px] font-semibold transition-colors ${scale === v ? "bg-accent text-white" : "bg-surface-3 text-text-secondary hover:bg-surface-4"}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </Section>
  );
}

/* ── Market gate (SPY 8/21) — MANAGED, ON by default, per-user override ──────────
   We run this for everyone: when SPY closes below its daily 8 or 21 EMA, DAY-TRADE
   LONGS are suppressed automatically — except a user's exempt symbols (+ the
   always-flow bypass: monthly RC, 30-RSI, 200-MA bounce). Shorts never gated. The
   toggle is an OVERRIDE — turn it OFF to keep getting longs in a weak tape.
   Saves immediately on every change. */
function MarketGateSection() {
  const { data, isError } = useMarketGate();
  const { data: watchlist } = useWatchlist();
  const update = useUpdateMarketGate();
  const [input, setInput] = useState("");

  if (isError) return null;

  const enabled = !!data?.enabled;
  const symbols = (data?.exempt || "").split(",").map((s) => s.trim().toUpperCase()).filter(Boolean);
  // Autocomplete the allow-list from the user's watchlist (names not already added).
  const wlSuggestions = (watchlist ?? []).map((w) => w.symbol.toUpperCase()).filter((s) => !symbols.includes(s));

  const setEnabled = (on: boolean) => update.mutate({ enabled: on });
  const addSymbol = () => {
    const s = input.trim().toUpperCase();
    setInput("");
    if (!s || symbols.includes(s)) return;
    update.mutate({ exempt: [...symbols, s].join(",") });
  };
  const removeSymbol = (s: string) =>
    update.mutate({ exempt: symbols.filter((x) => x !== s).join(",") });

  return (
    <Section title="Market gate — SPY 8/21" icon={<ShieldCheck className="h-4 w-4 text-accent" />}>
      <p className="text-[12px] leading-relaxed text-text-muted mb-3">
        Protection is <b>on by default</b> — we run it for you. When SPY closes below <b>either</b> its
        daily 8 <b>or</b> 21 EMA the tape isn't trending and day-trade longs get bitten, so we
        automatically hold them back. Shorts still flow; <b>monthly RC, the 30-RSI buy, and 200-MA
        bounces</b> always fire; and your allow-list below alerts in any tape. Turn this <b>off to
        override</b> and keep receiving longs in a weak tape — it only changes your own feed.
      </p>

      {/* master toggle — shared green pill, consistent with Alert Types */}
      <div className="flex items-center justify-between gap-3 border-t border-border-subtle/60 py-3">
        <span className="text-[13px] text-text-secondary">Protect my day-trade longs when SPY is weak (below its 8/21)</span>
        <Toggle on={enabled} onClick={() => setEnabled(!enabled)} disabled={update.isPending} />
      </div>

      {/* allow-list — even in a weak tape */}
      <div className="mt-1">
        <div className="mb-1.5 flex items-baseline justify-between">
          <label className="text-[11px] font-semibold uppercase tracking-wide text-text-faint">Always alert me on these — even in a weak tape</label>
          {symbols.length > 0 && <span className="text-[10px] text-text-faint">{symbols.length}</span>}
        </div>
        {symbols.length > 0 ? (
          <div className="mb-2 flex flex-wrap gap-1.5 rounded-lg border border-border-subtle bg-surface-2/40 p-2.5">
            {symbols.map((s) => (
              <span key={s} className="inline-flex items-center gap-1 rounded-md border border-border-subtle bg-surface-1 px-2 py-0.5 font-mono text-[11px] font-semibold text-text-secondary">
                {s}
                <button type="button" onClick={() => removeSymbol(s)} className="text-text-faint transition-colors hover:text-bearish-text" aria-label={`Remove ${s}`}>
                  <X className="h-2.5 w-2.5" />
                </button>
              </span>
            ))}
          </div>
        ) : (
          <p className="mb-2 text-[11px] text-text-faint">No symbols yet — add the names you'll day-trade even when the market is flat.</p>
        )}
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value.toUpperCase())}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addSymbol(); } }}
            placeholder="Add a symbol — type or pick from your watchlist"
            list="mg-watchlist"
            className="flex-1 rounded-lg border border-border-subtle bg-surface-2 px-3 py-2 text-[13px] text-text-primary placeholder:text-text-faint outline-none focus:border-accent"
          />
          <datalist id="mg-watchlist">
            {wlSuggestions.map((s) => <option key={s} value={s} />)}
          </datalist>
          <button
            type="button"
            onClick={addSymbol}
            disabled={!input.trim() || update.isPending}
            className="inline-flex items-center gap-1 rounded-lg border border-accent/40 bg-accent/10 px-3 py-2 text-[13px] font-semibold text-accent transition-colors hover:bg-accent/20 disabled:opacity-50"
          >
            {update.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            Add
          </button>
        </div>
      </div>
    </Section>
  );
}


/* ── Alert Types (per-type enable/disable) ────────────────────────── */

/* iOS-style pill toggle — the mock's on/off control (green when on). */
function Toggle({ on, onClick, disabled }: { on: boolean; onClick: () => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={onClick}
      disabled={disabled}
      className={`relative h-5 w-9 shrink-0 rounded-full transition-colors disabled:opacity-50 ${on ? "bg-bullish-text" : "bg-surface-3"}`}
    >
      <span className={`absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white transition-transform ${on ? "translate-x-4" : ""}`} />
    </button>
  );
}

function AlertTypesSection() {
  const { data: types, isLoading } = useAlertConfig();
  const toggle = useToggleAlertConfig();
  const toggleAll = useToggleAllAlertConfig();

  // Group by the trade-style bucket (Day / Swing / Long-term) so users enable a
  // whole style in one shot, not 45 toggles (2026-06-20).
  const GROUP_ORDER = ["Day Trade", "Swing Trade", "Long Term", "Notice", "Other"];
  const grouped: Record<string, AlertTypeConfigItem[]> = {};
  for (const t of types ?? []) {
    (grouped[t.trade_group ?? "Other"] ??= []).push(t);
  }
  const orderedGroups = GROUP_ORDER.filter((g) => (grouped[g]?.length ?? 0) > 0);
  const enabledCount = (types ?? []).filter((t) => t.enabled).length;
  const total = types?.length ?? 0;
  const busy = toggle.isPending || toggleAll.isPending;

  return (
    <Section title="Alert Types" icon={<Zap className="h-4 w-4 text-accent" />}>
      <div className="mb-4 rounded-lg border border-border-subtle bg-surface-1 px-3 py-2 text-[11px] leading-relaxed text-text-muted">
        <b className="text-bullish-text">ON</b> = delivered to Telegram + your Signals feed ·{" "}
        <b className="text-text-secondary">OFF</b> = still fires &amp; records silently for review ·
        each <b className="text-text-secondary">family</b> toggles as a group.
        {types && <span className="text-text-faint"> · {enabledCount} of {total} on</span>}
      </div>

      {isLoading && <p className="text-xs text-text-faint">Loading…</p>}

      <div className="space-y-6">
        {orderedGroups.map((group) => {
          const items = grouped[group];
          const onCount = items.filter((i) => i.enabled).length;
          const clusters = Object.entries(
            items.reduce((acc, t) => { (acc[t.category] ??= []).push(t); return acc; }, {} as Record<string, AlertTypeConfigItem[]>),
          );
          return (
            <div key={group}>
              {/* Group header + master toggle */}
              <div className="mb-3 flex items-center justify-between">
                <div className="flex items-baseline gap-2">
                  <span className="text-[13px] font-bold uppercase tracking-wide text-text-secondary">{group}</span>
                  <span className="text-[10px] text-text-faint">{onCount} of {items.length} on · group</span>
                </div>
                <Toggle on={onCount === items.length} disabled={busy} onClick={() => toggleAll.mutate({ enabled: onCount < items.length, trade_group: group })} />
              </div>
              <div className="space-y-4">
                {clusters.map(([cluster, rows]) => (
                  <div key={cluster}>
                    <div className="mb-1 font-mono text-[10px] uppercase tracking-wider text-text-faint">{cluster}</div>
                    <div className="divide-y divide-border-subtle/40 rounded-lg border border-border-subtle bg-surface-1 px-3">
                      {rows.map((t) => {
                        const isShort = /\bshort\b/i.test(t.label);
                        const [name, ...rest] = t.label.split(" — ");
                        const desc = rest.join(" — ");
                        return (
                          <div key={t.alert_type} className="flex items-center gap-2.5 py-2.5">
                            <span className={`shrink-0 rounded px-1.5 py-0.5 text-[8.5px] font-bold uppercase ${isShort ? "bg-bearish-subtle text-bearish-text" : "bg-bullish-subtle text-bullish-text"}`}>{isShort ? "short" : "long"}</span>
                            <div className="min-w-0 flex-1">
                              <span className={`text-[12px] font-semibold ${t.enabled ? "text-text-primary" : "text-text-secondary"}`}>{name}</span>
                              {desc && <span className="ml-2 text-[11px] text-text-faint">{desc}</span>}
                            </div>
                            <Toggle on={t.enabled} disabled={busy} onClick={() => toggle.mutate({ alert_type: t.alert_type, enabled: !t.enabled })} />
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </Section>
  );
}

/* Alert symbol lists REMOVED 2026-06-23 — alert rules now apply uniformly to the
   user's WATCHLIST, gated only by the per-type toggle (Alert Types) + the pine rule
   logic (e.g. MA bounce's in-pine regime gate). No per-symbol exceptions/allowlists. */

/* ── Redesign: left nav + one pane at a time (settings_redesign_mockup.html).
   Consolidates the old 9 sections into 5 panes. The ORL-scope section was dropped
   (staged_orl_held retired). Everything still saves instantly — no Save buttons. ── */
type SettingsPane = "alerts" | "delivery" | "risk" | "appearance" | "account";
const SETTINGS_NAV: { id: SettingsPane; label: string; icon: typeof Zap }[] = [
  { id: "alerts", label: "Alerts", icon: Zap },
  { id: "delivery", label: "Delivery", icon: Send },
  { id: "risk", label: "Risk & Sizing", icon: DollarSign },
  { id: "appearance", label: "Appearance", icon: Sun },
  { id: "account", label: "Account", icon: User },
];

export default function SettingsPage() {
  const [pane, setPane] = useState<SettingsPane>(() => {
    if (typeof window === "undefined") return "alerts";
    const saved = localStorage.getItem("settings_pane") as SettingsPane | null;
    return saved && SETTINGS_NAV.some((n) => n.id === saved) ? saved : "alerts";
  });
  const pick = (p: SettingsPane) => { setPane(p); try { localStorage.setItem("settings_pane", p); } catch { /* ignore */ } };

  return (
    <div className="h-full overflow-y-auto overflow-x-hidden p-5">
      <div className="max-w-5xl mx-auto space-y-4">
        <div>
          <h1 className="font-display text-xl font-bold text-text-primary">Settings</h1>
          <p className="text-[11px] text-text-muted">Everything saves instantly — no Save buttons.</p>
        </div>

        <div className="flex flex-col gap-5 md:flex-row md:items-start">
          {/* Left nav — a horizontal scroller on mobile, a rail on desktop */}
          <nav className="flex gap-1 overflow-x-auto pb-1 md:w-48 md:shrink-0 md:flex-col md:gap-0.5 md:overflow-visible md:pb-0">
            {SETTINGS_NAV.map((n) => {
              const Icon = n.icon;
              return (
                <button
                  key={n.id}
                  onClick={() => pick(n.id)}
                  className={`flex items-center gap-2 whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium transition-colors ${pane === n.id ? "bg-accent/10 text-accent" : "text-text-muted hover:bg-surface-2 hover:text-text-secondary"}`}
                >
                  <Icon className="h-4 w-4" /> {n.label}
                </button>
              );
            })}
          </nav>

          {/* Active pane */}
          <div className="min-w-0 flex-1 space-y-5">
            {pane === "alerts" && (<><MarketGateSection /><AlertTypesSection /></>)}
            {pane === "delivery" && (<><TelegramSetup /><NotificationChannels /></>)}
            {pane === "risk" && <TradingSettings />}
            {pane === "appearance" && <ThemeToggle />}
            {pane === "account" && (<><ProfileSection /><ReferralSection /></>)}
          </div>
        </div>
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
