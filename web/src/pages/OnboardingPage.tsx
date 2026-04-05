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
  useAlertPrefs, useUpdateAlertPrefs,
} from "../api/hooks";
import {
  Crosshair, Check, ChevronRight, Send, Plus,
  ExternalLink, Loader2, Search, Zap,
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
        This is how most traders interact with TradeCoPilot.
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

function StepPreferences({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const { data: alertPrefs } = useAlertPrefs();
  const updateAlertPrefs = useUpdateAlertPrefs();
  const [catToggles, setCatToggles] = useState<Record<string, boolean>>({});
  const [synced, setSynced] = useState(false);

  if (alertPrefs && !synced) {
    const toggles: Record<string, boolean> = {};
    alertPrefs.categories.forEach((c) => { toggles[c.category_id] = c.enabled; });
    setCatToggles(toggles);
    setSynced(true);
  }

  function handleSaveAndContinue() {
    updateAlertPrefs.mutate(
      { categories: catToggles, min_score: 0 },
      { onSuccess: () => onNext() },
    );
  }

  return (
    <div>
      <h2 className="text-2xl font-bold text-text-primary mb-2">Choose your alert patterns</h2>
      <p className="text-text-muted text-sm mb-6">
        Pick which trading patterns you want alerts for. You can change these anytime in Settings.
        We recommend keeping all enabled to start — you'll learn which ones work best for you.
      </p>

      {alertPrefs ? (
        <div className="space-y-2 mb-6">
          {alertPrefs.categories.map((cat) => (
            <label
              key={cat.category_id}
              className="flex items-start gap-3 p-3 rounded-lg border border-border-subtle hover:bg-surface-2/50 cursor-pointer transition-colors"
            >
              <input
                type="checkbox"
                checked={catToggles[cat.category_id] ?? true}
                onChange={(e) => setCatToggles((prev) => ({ ...prev, [cat.category_id]: e.target.checked }))}
                className="mt-0.5 rounded border-border-subtle"
              />
              <div className="flex-1">
                <span className="text-sm font-medium text-text-primary">{cat.name}</span>
                <p className="text-[10px] text-text-faint leading-tight mt-0.5">{cat.description}</p>
              </div>
            </label>
          ))}
        </div>
      ) : (
        <div className="h-40 flex items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin text-text-faint" />
        </div>
      )}

      <div className="flex items-center justify-between">
        <button onClick={onBack} className="text-sm text-text-faint hover:text-text-muted transition-colors">
          Back
        </button>
        <button
          onClick={handleSaveAndContinue}
          disabled={updateAlertPrefs.isPending}
          className="flex items-center gap-2 bg-accent hover:bg-accent-hover text-white font-semibold py-2.5 px-6 rounded-lg transition-colors disabled:opacity-50"
        >
          {updateAlertPrefs.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            "Save & Continue"
          )}
          <ChevronRight className="h-4 w-4" />
        </button>
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
      <div className="w-16 h-16 rounded-full bg-bullish/10 flex items-center justify-center mx-auto mb-4">
        <Zap className="h-8 w-8 text-bullish-text" />
      </div>
      <h2 className="text-2xl font-bold text-text-primary mb-2">You're all set!</h2>
      <p className="text-text-muted text-sm mb-8 max-w-md mx-auto">
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
          onClick={() => navigate("/dashboard", { replace: true })}
          className="flex items-center justify-center gap-2 bg-surface-3 hover:bg-surface-4 text-text-primary font-medium py-3 px-8 rounded-xl border border-border-subtle transition-colors"
        >
          Go to Dashboard
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
            <span className="text-accent">Trade</span>Signal
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
