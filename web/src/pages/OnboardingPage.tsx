/** Onboarding Wizard — guides new users from registration to first alert.
 *
 *  Steps:
 *    1. Pick symbols (watchlist setup)
 *    2. Connect Telegram
 *    3. Choose alert patterns
 *    4. Done → redirect to Trading
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useWatchlist, useAddSymbol, useRemoveSymbol,
  useTelegramStatus, useTelegramLink,
  useUpdateAlertPrefs,
} from "../api/hooks";
import {
  Crosshair, Check, ChevronRight, Send, Plus,
  ExternalLink, Loader2, Search,
} from "lucide-react";

/* ── Popular symbols for quick-add ────────────────────────────────── */

const POPULAR_SYMBOLS = [
  { symbol: "SPY", label: "S&P 500" },
  { symbol: "QQQ", label: "Nasdaq 100" },
  { symbol: "AAPL", label: "Apple" },
  { symbol: "NVDA", label: "Nvidia" },
  { symbol: "TSLA", label: "Tesla" },
  { symbol: "META", label: "Meta" },
  { symbol: "MSFT", label: "Microsoft" },
  { symbol: "AMZN", label: "Amazon" },
  { symbol: "GOOGL", label: "Google" },
  { symbol: "BTC-USD", label: "Bitcoin" },
  { symbol: "ETH-USD", label: "Ethereum" },
  { symbol: "AMD", label: "AMD" },
];

/* ── Step indicator ───────────────────────────────────────────────── */

function StepIndicator({ current, total }: { current: number; total: number }) {
  return (
    <div className="flex items-center gap-2 mb-8">
      {Array.from({ length: total }).map((_, i) => (
        <div key={i} className="flex items-center gap-2">
          <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-colors ${
            i < current ? "bg-bullish text-surface-0"
              : i === current ? "bg-accent text-white"
              : "bg-surface-3 text-text-faint"
          }`}>
            {i < current ? <Check className="h-4 w-4" /> : i + 1}
          </div>
          {i < total - 1 && (
            <div className={`w-8 h-0.5 ${i < current ? "bg-bullish" : "bg-surface-3"}`} />
          )}
        </div>
      ))}
    </div>
  );
}

/* ── Step 1: Pick Symbols ─────────────────────────────────────────── */

function StepSymbols({ onNext }: { onNext: () => void; onBack?: () => void }) {
  const { data: watchlist } = useWatchlist();
  const addSymbol = useAddSymbol();
  const removeSymbol = useRemoveSymbol();
  const [customInput, setCustomInput] = useState("");

  const watchlistSet = new Set(watchlist?.map((w) => w.symbol) ?? []);
  const count = watchlist?.length ?? 0;

  function handleToggle(symbol: string) {
    if (watchlistSet.has(symbol)) {
      removeSymbol.mutate(symbol);
    } else {
      addSymbol.mutate(symbol);
    }
  }

  function handleAddCustom(e: React.FormEvent) {
    e.preventDefault();
    const sym = customInput.trim().toUpperCase();
    if (sym && !watchlistSet.has(sym)) {
      addSymbol.mutate(sym, { onSuccess: () => setCustomInput("") });
    }
  }

  return (
    <div>
      <h2 className="text-2xl font-bold text-text-primary mb-2">Pick your symbols</h2>
      <p className="text-text-muted text-sm mb-6">
        Choose the stocks and crypto you want to monitor. We'll scan them every 3 minutes
        and alert you when trade setups appear.
      </p>

      {/* Popular symbols grid */}
      <div className="grid grid-cols-3 sm:grid-cols-4 gap-2 mb-5">
        {POPULAR_SYMBOLS.map((s) => {
          const active = watchlistSet.has(s.symbol);
          return (
            <button
              key={s.symbol}
              onClick={() => handleToggle(s.symbol)}
              className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border text-left transition-all ${
                active
                  ? "bg-accent/10 border-accent/30 text-text-primary"
                  : "bg-surface-2 border-border-subtle text-text-muted hover:border-border-default"
              }`}
            >
              {active ? (
                <Check className="h-3.5 w-3.5 text-accent shrink-0" />
              ) : (
                <Plus className="h-3.5 w-3.5 text-text-faint shrink-0" />
              )}
              <div className="min-w-0">
                <div className="text-sm font-bold truncate">{s.symbol}</div>
                <div className="text-[10px] text-text-faint truncate">{s.label}</div>
              </div>
            </button>
          );
        })}
      </div>

      {/* Custom symbol input */}
      <form onSubmit={handleAddCustom} className="flex gap-2 mb-6">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-text-faint" />
          <input
            type="text"
            value={customInput}
            onChange={(e) => setCustomInput(e.target.value.toUpperCase())}
            placeholder="Add another symbol..."
            className="w-full bg-surface-2 border border-border-subtle rounded-lg py-2 pl-8 pr-3 text-sm text-text-primary placeholder:text-text-faint focus:border-accent focus:outline-none"
          />
        </div>
        {customInput.trim() && (
          <button
            type="submit"
            disabled={addSymbol.isPending}
            className="bg-accent hover:bg-accent-hover text-white text-sm font-medium px-4 rounded-lg transition-colors disabled:opacity-50"
          >
            Add
          </button>
        )}
      </form>

      {/* Selected count + next */}
      <div className="flex items-center justify-between">
        <span className="text-sm text-text-muted">
          <span className="font-mono text-text-primary">{count}</span> symbol{count !== 1 ? "s" : ""} selected
        </span>
        <button
          onClick={onNext}
          disabled={count === 0}
          className="flex items-center gap-2 bg-accent hover:bg-accent-hover text-white font-semibold py-2.5 px-6 rounded-lg transition-colors disabled:opacity-30"
        >
          Continue
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

/* ── Step 2: Connect Telegram ─────────────────────────────────────── */

function StepTelegram({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const { data: status, isLoading } = useTelegramStatus();
  const linkTelegram = useTelegramLink();

  const linked = status?.linked;

  return (
    <div>
      <h2 className="text-2xl font-bold text-text-primary mb-2">Connect Telegram</h2>
      <p className="text-text-muted text-sm mb-6">
        Get trade alerts delivered to your phone with Took/Skip action buttons.
        This is how most traders interact with BusyTradersDesk.
      </p>

      {linked ? (
        <div className="bg-bullish/5 border border-bullish/20 rounded-xl p-6 mb-6 text-center">
          <div className="w-12 h-12 rounded-full bg-bullish/10 flex items-center justify-center mx-auto mb-3">
            <Check className="h-6 w-6 text-bullish-text" />
          </div>
          <h3 className="text-lg font-bold text-bullish-text mb-1">Telegram Connected</h3>
          <p className="text-sm text-text-muted">Alerts will be delivered to your Telegram DMs.</p>
        </div>
      ) : (
        <div className="bg-surface-2 border border-border-subtle rounded-xl p-6 mb-6">
          <div className="flex flex-col gap-3 mb-5">
            <div className="flex items-center gap-3">
              <span className="w-6 h-6 rounded-full bg-accent/10 text-accent flex items-center justify-center text-xs font-bold shrink-0">1</span>
              <span className="text-sm text-text-secondary">Click the button below — it opens our bot in Telegram</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="w-6 h-6 rounded-full bg-accent/10 text-accent flex items-center justify-center text-xs font-bold shrink-0">2</span>
              <span className="text-sm text-text-secondary">Tap <span className="font-semibold text-text-primary">Start</span> in Telegram</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="w-6 h-6 rounded-full bg-accent/10 text-accent flex items-center justify-center text-xs font-bold shrink-0">3</span>
              <span className="text-sm text-text-secondary">Come back here — we'll detect the connection automatically</span>
            </div>
          </div>

          {linkTelegram.data ? (
            <a
              href={linkTelegram.data.deep_link}
              target="_blank"
              rel="noopener noreferrer"
              className="w-full flex items-center justify-center gap-2 bg-accent hover:bg-accent-hover text-white font-semibold py-3 px-4 rounded-lg transition-colors"
            >
              <Send className="h-4 w-4" />
              Open in Telegram
              <ExternalLink className="h-3 w-3" />
            </a>
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

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="text-sm text-text-faint hover:text-text-muted transition-colors">
            Back
          </button>
          {!linked && (
            <button onClick={onNext} className="text-sm text-text-faint hover:text-text-muted transition-colors">
              Skip for now
            </button>
          )}
        </div>
        <button
          onClick={onNext}
          className="flex items-center gap-2 bg-accent hover:bg-accent-hover text-white font-semibold py-2.5 px-6 rounded-lg transition-colors"
        >
          {linked ? "Continue" : "Next"}
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

/* ── Step 3: Alert Preferences ────────────────────────────────────── */

/* Trader profile presets — maps "I'm a ___" to the right alert categories.
 * Removes the 8-toggle paralysis the old StepPreferences caused. */
type TraderProfile = "day" | "swing" | "both";

const PROFILE_PRESETS: Record<TraderProfile, {
  title: string;
  subtitle: string;
  bullets: string[];
  categories: Record<string, boolean>;
}> = {
  day: {
    title: "Busy Day Trader",
    subtitle: "Intraday setups, scan in 5 min before/during work hours",
    bullets: [
      "PDH/PDL breaks + holds",
      "MA bounces (intraday)",
      "Gap-up continuation",
      "Exit alerts on positions",
    ],
    categories: {
      entry_signals: true,
      breakout_signals: true,
      exit_alerts: true,
      resistance_warnings: true,
      short_signals: false,
      support_warnings: false,
      swing_trade: false,
      informational: false,
    },
  },
  swing: {
    title: "Swing Trader",
    subtitle: "Daily-bar setups, 1-2 weeks holding period",
    bullets: [
      "Daily EMA bounces (8/21/50/200)",
      "Anchored VWAP defenses",
      "52-week-high retests",
      "RSI-30 recoveries",
    ],
    categories: {
      entry_signals: false,
      breakout_signals: false,
      exit_alerts: false,
      resistance_warnings: false,
      short_signals: false,
      support_warnings: false,
      swing_trade: true,
      informational: true,
    },
  },
  both: {
    title: "Both",
    subtitle: "I trade intraday AND swing — give me everything",
    bullets: [
      "All day-trade categories",
      "All swing categories",
      "Exit alerts on every position",
      "Tune more in Settings later",
    ],
    categories: {
      entry_signals: true,
      breakout_signals: true,
      exit_alerts: true,
      resistance_warnings: true,
      short_signals: false,
      support_warnings: false,
      swing_trade: true,
      informational: false,
    },
  },
};

function StepPreferences({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const updateAlertPrefs = useUpdateAlertPrefs();
  const [selected, setSelected] = useState<TraderProfile | null>(null);

  function handlePick(profile: TraderProfile) {
    setSelected(profile);
    updateAlertPrefs.mutate(
      { categories: PROFILE_PRESETS[profile].categories, min_score: 0 },
      { onSuccess: () => onNext() },
    );
  }

  return (
    <div>
      <h2 className="text-2xl font-bold text-text-primary mb-2">How do you trade?</h2>
      <p className="text-text-muted text-sm mb-6">
        Pick one to auto-enable the right alert patterns. You can tune individual
        patterns in Settings → Alert Types later.
      </p>

      <div className="space-y-3 mb-6">
        {(["day", "swing", "both"] as TraderProfile[]).map((id) => {
          const p = PROFILE_PRESETS[id];
          const isSelected = selected === id;
          const isLoading = isSelected && updateAlertPrefs.isPending;
          return (
            <button
              key={id}
              onClick={() => handlePick(id)}
              disabled={updateAlertPrefs.isPending}
              className={`w-full text-left flex items-start gap-3 p-4 rounded-lg border transition-colors ${
                isSelected
                  ? "border-accent bg-accent/10"
                  : "border-border-subtle hover:bg-surface-2/50"
              } disabled:opacity-60`}
            >
              <div className={`mt-0.5 w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0 ${
                isSelected ? "border-accent" : "border-border-subtle"
              }`}>
                {isLoading ? (
                  <Loader2 className="h-3 w-3 animate-spin text-accent" />
                ) : isSelected ? (
                  <div className="w-2.5 h-2.5 rounded-full bg-accent" />
                ) : null}
              </div>
              <div className="flex-1">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-base font-bold text-text-primary">{p.title}</span>
                </div>
                <p className="text-xs text-text-muted mb-2">{p.subtitle}</p>
                <ul className="space-y-0.5">
                  {p.bullets.map((b) => (
                    <li key={b} className="text-[11px] text-text-secondary flex items-center gap-1.5">
                      <Check className="h-3 w-3 text-bullish-text shrink-0" />
                      {b}
                    </li>
                  ))}
                </ul>
              </div>
            </button>
          );
        })}
      </div>

      <div className="flex items-center justify-between">
        <button onClick={onBack} className="text-sm text-text-faint hover:text-text-muted transition-colors">
          Back
        </button>
        <span className="text-[11px] text-text-faint italic">
          Pick one to continue — auto-saves
        </span>
      </div>
    </div>
  );
}

/* ── Step 4: Done ─────────────────────────────────────────────────── */

function StepDone() {
  const navigate = useNavigate();
  const { data: watchlist } = useWatchlist();
  const { data: tgStatus } = useTelegramStatus();

  return (
    <div className="text-center">
      {/* Celebration keyframes */}
      <style>{`
        @keyframes celebrate-bounce {
          0% { transform: scale(0); opacity: 0; }
          50% { transform: scale(1.2); }
          100% { transform: scale(1); opacity: 1; }
        }
        @keyframes celebrate-check {
          0% { transform: scale(0) rotate(-45deg); opacity: 0; }
          100% { transform: scale(1) rotate(0deg); opacity: 1; }
        }
        @keyframes celebrate-fade-up {
          0% { transform: translateY(10px); opacity: 0; }
          100% { transform: translateY(0); opacity: 1; }
        }
      `}</style>
      {/* Animated checkmark circle */}
      <div className="w-16 h-16 rounded-full bg-bullish/10 flex items-center justify-center mx-auto mb-4 animate-[celebrate-bounce_0.6s_ease-out]">
        <Check className="h-8 w-8 text-bullish-text animate-[celebrate-check_0.4s_ease-out_0.2s_both]" />
      </div>
      <h2 className="text-2xl font-bold text-text-primary mb-2 animate-[celebrate-fade-up_0.5s_ease-out_0.3s_both]">You're all set!</h2>
      <p className="text-text-muted text-sm mb-8 max-w-md mx-auto animate-[celebrate-fade-up_0.5s_ease-out_0.45s_both]">
        We're now scanning {watchlist?.length ?? 0} symbol{(watchlist?.length ?? 0) !== 1 ? "s" : ""} every
        3 minutes during market hours.
        {tgStatus?.linked
          ? " Alerts will be delivered to your Telegram."
          : " Connect Telegram in Settings to get alerts on your phone."}
      </p>

      <div className="flex flex-col sm:flex-row gap-3 justify-center">
        <button
          onClick={() => navigate("/trading", { replace: true })}
          className="flex items-center justify-center gap-2 bg-bullish hover:bg-bullish/90 text-surface-0 font-bold py-3 px-8 rounded-xl transition-all shadow-[0_0_20px_rgba(34,197,94,0.2)]"
        >
          <Crosshair className="h-4 w-4" />
          Open Trading
        </button>
        <button
          onClick={() => navigate("/trade-ideas", { replace: true })}
          className="flex items-center justify-center gap-2 bg-surface-3 hover:bg-surface-4 text-text-primary font-medium py-3 px-8 rounded-xl border border-border-subtle transition-colors"
        >
          See Trade Ideas
        </button>
      </div>
    </div>
  );
}

/* ── Main Onboarding Page ─────────────────────────────────────────── */

export default function OnboardingPage() {
  const [step, setStep] = useState(0);
  const totalSteps = 4;

  return (
    <div className="min-h-screen bg-surface-0 flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-xl">
        {/* Logo */}
        <div className="flex items-center gap-2.5 mb-8">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-accent to-purple flex items-center justify-center">
            <Crosshair className="h-4 w-4 text-white" />
          </div>
          <span className="font-bold text-lg text-text-primary">
            <span className="text-accent">Busy</span>TradersDesk
          </span>
        </div>

        <StepIndicator current={step} total={totalSteps} />

        <div className="bg-surface-1 border border-border-subtle rounded-xl p-6 sm:p-8">
          {step === 0 && <StepSymbols onNext={() => setStep(1)} />}
          {step === 1 && <StepTelegram onNext={() => setStep(2)} onBack={() => setStep(0)} />}
          {step === 2 && <StepPreferences onNext={() => setStep(3)} onBack={() => setStep(1)} />}
          {step === 3 && <StepDone />}
        </div>
      </div>
    </div>
  );
}
