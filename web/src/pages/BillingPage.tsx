/** Billing — Subscription management with Square payments.
 *
 *  Shows current tier, upgrade/downgrade options, and payment form.
 *  Uses Square Web Payments SDK for card tokenization.
 */

import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import {
  Check, Crown, ChevronRight, Loader2, X,
  CreditCard, AlertTriangle, Sparkles, Clock,
} from "lucide-react";

/* ── Types ────────────────────────────────────────────────────────── */

interface BillingStatus {
  tier: string;
  status: string;
  square_subscription_id: string | null;
  trial_active?: boolean;
  trial_days_left?: number;
}

/* ── Plan definitions ─────────────────────────────────────────────── */

const PLANS = [
  {
    id: "free",
    name: "Free",
    price: "$0",
    period: "forever",
    features: [
      "3 symbols on watchlist",
      "3 alerts visible per session",
      "AI Coach (2 queries/day)",
      "Signal Library access",
      "Today's alerts only",
    ],
    cta: "Current Plan",
  },
  {
    id: "pro",
    name: "Pro",
    price: "$49",
    period: "/month",
    popular: true,
    features: [
      "10 symbols on watchlist",
      "Real-time Telegram alerts",
      "AI Coach (20 queries/day)",
      "Full alert history (30 days)",
      "Pre-trade checklist",
      "Daily EOD review",
      "Pre-market brief",
      "Performance analytics",
    ],
    cta: "Upgrade to Pro",
  },
  {
    id: "premium",
    name: "Premium",
    price: "$99",
    period: "/month",
    features: [
      "Everything in Pro",
      "25 symbols on watchlist",
      "Unlimited AI Coach",
      "Full alert history",
      "Weekly AI review",
      "Paper trading simulator",
      "Backtesting engine",
    ],
    cta: "Upgrade to Premium",
  },
];

/* ── Square Card Form ─────────────────────────────────────────────── */

function CardForm({ plan, onSuccess, onCancel }: {
  plan: string;
  onSuccess: () => void;
  onCancel: () => void;
}) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [cardInstance, setCardInstance] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sdkReady, setSdkReady] = useState(false);

  // Load Square Web Payments SDK
  useEffect(() => {
    const appId = (window as any).__SQUARE_APP_ID__;
    const locationId = (window as any).__SQUARE_LOCATION_ID__;

    if (!appId || !locationId) {
      setError("Billing not configured. Contact support.");
      return;
    }

    async function initSquare() {
      try {
        const payments = (window as any).Square.payments(appId, locationId);
        const card = await payments.card();
        await card.attach(cardRef.current!);
        setCardInstance(card);
        setSdkReady(true);
      } catch (err) {
        setError("Failed to load payment form. Please refresh.");
      }
    }

    // Check if Square SDK is loaded
    if ((window as any).Square) {
      initSquare();
    } else {
      // Load the SDK script
      const script = document.createElement("script");
      script.src = "https://sandbox.web.squarecdn.com/v1/square.js";
      script.onload = initSquare;
      script.onerror = () => setError("Failed to load payment SDK");
      document.head.appendChild(script);
    }
  }, []);

  async function handlePay() {
    if (!cardInstance) return;
    setLoading(true);
    setError("");

    try {
      const result = await cardInstance.tokenize();
      if (result.status !== "OK") {
        setError(result.errors?.[0]?.message || "Card tokenization failed");
        setLoading(false);
        return;
      }

      // Send nonce to backend
      await api.post("/billing/subscribe", { nonce: result.token, plan });
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Payment failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="bg-surface-1 border border-border-subtle rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <CreditCard className="h-4 w-4 text-accent" />
          Payment Details
        </h3>
        <button onClick={onCancel} className="text-text-faint hover:text-text-muted">
          <X className="h-4 w-4" />
        </button>
      </div>

      {error && (
        <div className="mb-4 bg-bearish/10 border border-bearish/20 rounded-lg px-3 py-2.5">
          <div className="flex items-center gap-2 text-xs text-bearish-text font-medium">
            <AlertTriangle className="h-3 w-3 shrink-0" />
            {error}
          </div>
          <p className="text-[10px] text-text-faint mt-1 pl-5">
            {error.includes("declined") || error.includes("Declined")
              ? "Try a different card or check with your bank."
              : error.includes("expired")
              ? "Your card has expired. Please use a different card."
              : "Please try again. If the issue persists, contact support."}
          </p>
        </div>
      )}

      {/* Square card form mounts here */}
      <div ref={cardRef} className="mb-4 min-h-[50px]" />

      <button
        onClick={handlePay}
        disabled={loading || !sdkReady}
        className="w-full flex items-center justify-center gap-2 bg-bullish hover:bg-bullish/90 text-surface-0 font-bold py-3 px-4 rounded-lg transition-all disabled:opacity-50"
      >
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <>
            Subscribe to {plan === "pro" ? "Pro" : "Premium"}
            <ChevronRight className="h-4 w-4" />
          </>
        )}
      </button>

      <p className="mt-3 text-[10px] text-text-faint text-center">
        Secure payment via Square. Cancel anytime.
      </p>
    </div>
  );
}

/* ── Main Billing Page ────────────────────────────────────────────── */

export default function BillingPage() {
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [selectedPlan, setSelectedPlan] = useState<string | null>(null);
  const [canceling, setCanceling] = useState(false);

  useEffect(() => {
    api.get<BillingStatus>("/billing/status").then(setStatus).catch(() => {});
  }, []);

  const currentTier = status?.tier || "free";

  async function handleCancel() {
    if (!confirm("Cancel your subscription? You'll keep access until the end of your billing period.")) return;
    setCanceling(true);
    try {
      await api.post("/billing/cancel");
      setStatus({ tier: "free", status: "canceled", square_subscription_id: null });
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to cancel");
    } finally {
      setCanceling(false);
    }
  }

  return (
    <div className="h-full overflow-y-auto p-5">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-xl font-bold text-text-primary mb-4">Billing & Subscription</h1>

        {/* Trial banner */}
        {status?.trial_active && (
          <div className="mb-6 p-4 bg-amber-500/10 border border-amber-500/20 rounded-xl flex items-center gap-3">
            <div className="w-10 h-10 bg-amber-500/20 rounded-full flex items-center justify-center shrink-0">
              <Sparkles className="h-5 w-5 text-amber-400" />
            </div>
            <div className="flex-1">
              <p className="text-sm font-semibold text-amber-200">
                Pro Trial — {status.trial_days_left} day{status.trial_days_left !== 1 ? "s" : ""} remaining
              </p>
              <p className="text-xs text-text-muted mt-0.5">
                You have full Pro access. Subscribe to keep everything unlocked.
              </p>
            </div>
            <Clock className="h-5 w-5 text-amber-400/50 shrink-0" />
          </div>
        )}

        {/* Plan cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
          {PLANS.map((plan) => {
            const isCurrent = currentTier === plan.id;
            const isUpgrade = !isCurrent && (
              (currentTier === "free") ||
              (currentTier === "pro" && plan.id === "premium")
            );

            return (
              <div
                key={plan.id}
                className={`rounded-xl p-5 flex flex-col ${
                  plan.popular
                    ? "bg-surface-1 border-2 border-bullish/30 relative"
                    : "bg-surface-1 border border-border-subtle"
                } ${isCurrent ? "ring-2 ring-accent/30" : ""}`}
              >
                {plan.popular && (
                  <span className="absolute -top-2.5 left-1/2 -translate-x-1/2 bg-bullish text-surface-0 text-[10px] font-bold px-3 py-0.5 rounded-full">
                    Most Popular
                  </span>
                )}

                <div className="mb-4">
                  <h3 className="text-base font-bold text-text-primary flex items-center gap-2">
                    {plan.id === "premium" && <Crown className="h-4 w-4 text-warning" />}
                    {plan.name}
                  </h3>
                  <div className="flex items-baseline gap-1 mt-1">
                    <span className="font-mono text-3xl font-bold text-text-primary">{plan.price}</span>
                    <span className="text-text-muted text-sm">{plan.period}</span>
                  </div>
                </div>

                <ul className="space-y-2 mb-5 flex-1">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-xs text-text-secondary">
                      <Check className="h-3.5 w-3.5 text-bullish-text shrink-0 mt-0.5" />
                      {f}
                    </li>
                  ))}
                </ul>

                {isCurrent ? (
                  <div className="text-center">
                    <span className="text-xs font-medium text-accent bg-accent/10 px-3 py-1.5 rounded-md">
                      Current Plan
                    </span>
                    {currentTier !== "free" && (
                      <button
                        onClick={handleCancel}
                        disabled={canceling}
                        className="block mx-auto mt-2 text-[10px] text-text-faint hover:text-bearish-text transition-colors"
                      >
                        {canceling ? "Canceling..." : "Cancel subscription"}
                      </button>
                    )}
                  </div>
                ) : isUpgrade ? (
                  <button
                    onClick={() => setSelectedPlan(plan.id)}
                    className={`w-full text-center py-2.5 rounded-lg font-semibold text-sm transition-all ${
                      plan.popular
                        ? "bg-bullish hover:bg-bullish/90 text-surface-0"
                        : "bg-surface-3 hover:bg-surface-4 text-text-primary border border-border-subtle"
                    }`}
                  >
                    {plan.cta}
                  </button>
                ) : (
                  <span className="text-center text-xs text-text-faint py-2.5">
                    {plan.id === "free" ? "Downgrade via cancel" : ""}
                  </span>
                )}
              </div>
            );
          })}
        </div>

        {/* Payment form (shown when user picks a plan) */}
        {selectedPlan && (
          <CardForm
            plan={selectedPlan}
            onSuccess={() => {
              setSelectedPlan(null);
              api.get<BillingStatus>("/billing/status").then(setStatus);
            }}
            onCancel={() => setSelectedPlan(null)}
          />
        )}
      </div>
    </div>
  );
}
