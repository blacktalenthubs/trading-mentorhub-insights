/** Settings — Account, Notifications & Alert Preferences.
 *
 *  Redesigned: two-column layout on desktop, clear visual hierarchy,
 *  Telegram linking is prominent (step 1 of getting alerts).
 */

import { useState } from "react";
import { useAuthStore } from "../stores/auth";
import { api } from "../api/client";
import {
  useUpdateProfile,
  useChangePassword,
  useNotificationPrefs,
  useUpdateNotificationPrefs,
  useAlertPrefs,
  useUpdateAlertPrefs,
  useTelegramStatus,
  useTelegramLink,
  useTelegramUnlink,
} from "../api/hooks";
import { useFeatureGate } from "../hooks/useFeatureGate";
import {
  Send, Bell, Shield, User, Key, ChevronRight, Check,
  Smartphone, Mail, ExternalLink, Loader2, DollarSign,
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
                await api.post("/settings/telegram-test");
                toast.success("Test alert sent to your Telegram");
              } catch {
                toast.error("Failed to send test alert");
              }
            }}
            className="text-xs text-accent hover:text-accent-hover transition-colors ml-3"
          >
            Send Test Alert
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
  const [emailOn, setEmailOn] = useState(false);
  const [pushOn, setPushOn] = useState(false);
  const [synced, setSynced] = useState(false);

  if (notifPrefs && !synced) {
    setTelegramOn(notifPrefs.telegram_enabled);
    setEmailOn(notifPrefs.email_enabled);
    setPushOn(notifPrefs.push_enabled);
    setSynced(true);
  }

  const dirty = synced && notifPrefs && (
    telegramOn !== notifPrefs.telegram_enabled ||
    emailOn !== notifPrefs.email_enabled ||
    pushOn !== notifPrefs.push_enabled
  );

  return (
    <Section title="Notification Channels" icon={<Bell className="h-4 w-4 text-text-muted" />}>
      <div className="space-y-3">
        {[
          { label: "Telegram", sub: "Real-time DM alerts with action buttons", icon: Send, checked: telegramOn, onChange: setTelegramOn },
          { label: "Email", sub: "Alert summaries to your inbox", icon: Mail, checked: emailOn, onChange: setEmailOn },
          { label: "Push", sub: "Mobile push notifications", icon: Smartphone, checked: pushOn, onChange: setPushOn },
        ].map((ch) => (
          <label key={ch.label} className="flex items-center gap-3 cursor-pointer group">
            <input
              type="checkbox"
              checked={ch.checked}
              onChange={(e) => ch.onChange(e.target.checked)}
              className="rounded border-border-subtle"
            />
            <ch.icon className="h-3.5 w-3.5 text-text-faint group-hover:text-text-muted" />
            <div className="flex-1">
              <span className="text-sm text-text-primary">{ch.label}</span>
              <p className="text-[10px] text-text-faint">{ch.sub}</p>
            </div>
          </label>
        ))}

        {dirty && (
          <button
            onClick={() => updateNotifs.mutate({
              telegram_enabled: telegramOn,
              email_enabled: emailOn,
              push_enabled: pushOn,
              quiet_hours_start: null,
              quiet_hours_end: null,
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

/* ── Alert Preferences ────────────────────────────────────────────── */

function AlertPreferences() {
  const { data: alertPrefs } = useAlertPrefs();
  const updateAlertPrefs = useUpdateAlertPrefs();
  const [catToggles, setCatToggles] = useState<Record<string, boolean>>({});
  const [minScore, setMinScore] = useState(0);
  const [synced, setSynced] = useState(false);

  if (alertPrefs && !synced) {
    const toggles: Record<string, boolean> = {};
    alertPrefs.categories.forEach((c) => { toggles[c.category_id] = c.enabled; });
    setCatToggles(toggles);
    setMinScore(alertPrefs.min_score);
    setSynced(true);
  }

  if (!alertPrefs) return null;

  return (
    <Section title="Trading Patterns" icon={<Shield className="h-4 w-4 text-text-muted" />}>
      <p className="text-xs text-text-faint mb-4">
        Choose which patterns trigger alerts. Disabled patterns still appear on the dashboard — just no push.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        {alertPrefs.categories.map((cat) => (
          <label key={cat.category_id} className="flex items-start gap-2.5 cursor-pointer p-2 rounded-md hover:bg-surface-2/50 transition-colors">
            <input
              type="checkbox"
              checked={catToggles[cat.category_id] ?? true}
              onChange={(e) => setCatToggles((prev) => ({ ...prev, [cat.category_id]: e.target.checked }))}
              className="mt-0.5 rounded border-border-subtle"
            />
            <div>
              <span className="text-xs font-medium text-text-primary">{cat.name}</span>
              <p className="text-[10px] text-text-faint leading-tight">{cat.description}</p>
            </div>
          </label>
        ))}
      </div>

      <div className="mt-4 pt-4 border-t border-border-subtle/50">
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-xs text-text-muted">Minimum Score</label>
          <span className="font-mono text-xs text-text-primary">{minScore}</span>
        </div>
        <input
          type="range" min={0} max={100} step={5}
          value={minScore}
          onChange={(e) => setMinScore(Number(e.target.value))}
          className="w-full accent-accent [&::-webkit-slider-runnable-track]:rounded-full [&::-webkit-slider-runnable-track]:bg-surface-3 [&::-webkit-slider-thumb]:bg-accent [&::-moz-range-track]:bg-surface-3 [&::-moz-range-thumb]:bg-accent"
        />
        <p className="text-[10px] text-text-faint mt-1">Exit alerts (T1/T2/Stop) always send regardless of score.</p>
      </div>

      <button
        onClick={() => updateAlertPrefs.mutate({ categories: catToggles, min_score: minScore })}
        disabled={updateAlertPrefs.isPending}
        className="mt-4 text-xs bg-accent hover:bg-accent-hover text-white px-4 py-1.5 rounded-md transition-colors disabled:opacity-50"
      >
        {updateAlertPrefs.isPending ? "Saving..." : "Save Alert Preferences"}
      </button>
      {updateAlertPrefs.isSuccess && (
        <span className="ml-2 text-[10px] text-bullish-text"><Check className="h-3 w-3 inline" /> Saved</span>
      )}
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
  const [portfolioSize, setPortfolioSize] = useState(
    () => Number(localStorage.getItem("ts_portfolio_size")) || 50000,
  );
  const [riskPct, setRiskPct] = useState(
    () => Number(localStorage.getItem("ts_risk_pct")) || 1,
  );

  function handleSave() {
    localStorage.setItem("ts_portfolio_size", String(portfolioSize));
    localStorage.setItem("ts_risk_pct", String(riskPct));
    toast.success("Trading settings saved");
  }

  return (
    <Section title="Position Sizing" icon={<DollarSign className="h-4 w-4 text-text-muted" />}>
      <p className="text-xs text-text-faint mb-4">
        Used to calculate share size on trade plans. Risk per trade = portfolio x risk%.
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
            step={0.5}
            min={0.25}
            max={5}
            onChange={(e) => setRiskPct(Number(e.target.value))}
            className="w-full rounded-md border border-border-subtle bg-surface-3 px-3 py-1.5 text-sm font-mono text-text-primary focus:border-accent focus:outline-none"
          />
        </div>
      </div>
      <p className="text-[10px] text-text-faint mt-2">
        Max risk per trade: <span className="font-mono text-text-primary">${((portfolioSize * riskPct) / 100).toFixed(0)}</span>
      </p>
      <button
        onClick={handleSave}
        className="mt-3 text-xs bg-accent hover:bg-accent-hover text-white px-4 py-1.5 rounded-md transition-colors"
      >
        Save
      </button>
    </Section>
  );
}

/* ── Main Settings Page ───────────────────────────────────────────── */

export default function SettingsPage() {
  return (
    <div className="h-full overflow-y-auto p-5">
      <div className="max-w-3xl mx-auto space-y-5">
        <h1 className="font-display text-xl font-bold text-text-primary">Settings</h1>

        {/* Two-column on desktop: alerts left, account right */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* Left column: Notifications (the stuff traders care about) */}
          <div className="space-y-5">
            <TelegramSetup />
            <NotificationChannels />
          </div>

          {/* Right column: Account */}
          <div className="space-y-5">
            <ProfileSection />
          </div>
        </div>

        {/* Trading settings */}
        <TradingSettings />

        {/* Full width: Alert preferences */}
        <AlertPreferences />
      </div>
    </div>
  );
}
