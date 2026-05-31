/** Standalone /pricing page — spec 63 Week 1.
 *
 *  Same plan data as the Pricing section on the landing page, but on
 *  its own route so paid ads + content links can deep-link without
 *  scrolling the marketing site. Adds a small FAQ section below since
 *  that's typical follow-up content when someone lands here cold.
 */

import { Link, Navigate } from "react-router-dom";
import { Check, ArrowLeft } from "lucide-react";
import { useMe } from "../api/hooks";

const PLANS = [
  {
    name: "Free",
    price: "$0",
    period: "forever",
    desc: "3-day full-access trial, then limited",
    cta: "Try free for 3 days",
    features: [
      "5 symbols on watchlist",
      "Top setups preview (Swing & In-Play)",
      "1 setup scan/day",
      "A-grade observations only",
      "Today's observations only",
      "1 setup replay/day",
      "Pattern Library access",
    ],
    highlight: false,
  },
  {
    name: "Pro",
    price: "$49",
    period: "/month",
    desc: "For active self-directed investors",
    cta: "Try free for 3 days",
    features: [
      "Unlimited watchlist",
      "Full Swing & In-Play screeners",
      "Every observation, real-time — all grades",
      "50 setup scans/day",
      "Pre-market brief + daily EOD review",
      "Personal Took/Skipped analytics",
      "Setup Grade A/B/C filter",
      "Weekly AI retrospective",
      "Live SPY regime gauge",
      "Full observation history",
    ],
    highlight: true,
  },
] as const;

const FAQ = [
  {
    q: "Do I need a credit card to start?",
    a: "No. The 3-day Pro trial requires only an email. You're never auto-charged at the end of the trial — you drop to the Free tier unless you choose to upgrade.",
  },
  {
    q: "Can I cancel anytime?",
    a: "Yes. One click in Settings → Billing. No questions, no retention call. You keep Pro access until the end of the current billing period.",
  },
  {
    q: "What are 'observations'?",
    a: "We never publish 'buy this' commands. An observation is the platform flagging that a stock has interacted with a key structural level (prior day high, EMA, VWAP, etc.) with the volume and slope context attached. You decide whether to act.",
  },
  {
    q: "Is this financial advice?",
    a: "No. BusyTradersDesk is a research toolkit, not an investment advisor. We do not manage your money, do not take account-linked actions, and do not make personalized recommendations. Educational purposes only.",
  },
  {
    q: "What's the difference between Free and Pro?",
    a: "Free lets you experience everything — chart anything, preview the top setups, run a scan a day, and get the highest-conviction (A-grade) observations. Pro lifts the caps: the full Swing & In-Play screeners, every observation in real-time across all grades, an unlimited watchlist, full history, and personal performance analytics. One simple paid tier — no upsell maze.",
  },
  {
    q: "Does the AI replace my judgment?",
    a: "No. The AI Best Setups feature pre-filters which symbols deserve your attention; the Weekly Retrospective summarizes what worked or didn't from last week's data. Every actual entry decision is yours.",
  },
] as const;

export default function PricingPage() {
  // If user is already logged in, send them to /settings/billing
  // (their existing context — they don't need the cold pricing pitch).
  const { data: user } = useMe();
  if (user) return <Navigate to="/settings" replace />;

  return (
    <div className="min-h-screen bg-surface-0">
      {/* Minimal header — back link + brand */}
      <header className="border-b border-border-subtle">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 text-sm text-text-muted hover:text-text-primary transition-colors">
            <ArrowLeft className="h-4 w-4" />
            Back to home
          </Link>
          <Link to="/" className="font-bold text-text-primary">
            BusyTradersDesk
          </Link>
        </div>
      </header>

      {/* Pricing grid */}
      <section className="py-20 px-6">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <h1 className="text-4xl sm:text-5xl font-bold text-text-primary">
              Simple pricing. Cancel anytime.
            </h1>
            <p className="mt-4 text-lg text-text-secondary">
              No credit card required to start. Free tier available forever.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-3xl mx-auto">
            {PLANS.map((plan) => (
              <div
                key={plan.name}
                className={`rounded-2xl p-6 flex flex-col ${
                  plan.highlight
                    ? "bg-surface-1 border-2 border-bullish/30 shadow-[0_0_40px_rgba(34,197,94,0.08)] relative"
                    : "bg-surface-1 border border-border-subtle"
                }`}
              >
                {plan.highlight && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                    <span className="bg-bullish text-surface-0 text-xs font-bold px-4 py-1 rounded-full">Most Popular</span>
                  </div>
                )}

                <div className="mb-6">
                  <h3 className="text-lg font-bold text-text-primary">{plan.name}</h3>
                  <div className="flex items-baseline gap-1 mt-2">
                    <span className="font-mono text-4xl font-bold text-text-primary">{plan.price}</span>
                    <span className="text-text-muted text-sm">{plan.period}</span>
                  </div>
                  <p className="text-sm text-text-muted mt-2">{plan.desc}</p>
                </div>

                <ul className="space-y-3 mb-8 flex-1">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-start gap-2.5 text-sm text-text-secondary">
                      <Check className="h-4 w-4 text-bullish-text shrink-0 mt-0.5" />
                      {f}
                    </li>
                  ))}
                </ul>

                <Link
                  to="/register"
                  className={`w-full text-center py-3 rounded-xl font-semibold text-sm transition-all ${
                    plan.highlight
                      ? "bg-bullish hover:bg-bullish/90 text-surface-0 shadow-[0_0_20px_rgba(34,197,94,0.2)]"
                      : "bg-surface-3 hover:bg-surface-4 text-text-primary border border-border-subtle"
                  }`}
                >
                  {plan.cta}
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="py-16 px-6 border-t border-border-subtle">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-2xl sm:text-3xl font-bold text-text-primary text-center mb-12">
            Frequently asked
          </h2>
          <div className="space-y-6">
            {FAQ.map((item) => (
              <div key={item.q} className="border-b border-border-subtle/50 pb-6 last:border-b-0">
                <h3 className="text-base font-semibold text-text-primary mb-2">{item.q}</h3>
                <p className="text-sm text-text-secondary leading-relaxed">{item.a}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer CTA */}
      <section className="py-16 px-6 bg-surface-1">
        <div className="max-w-3xl mx-auto text-center">
          <h2 className="text-2xl font-bold text-text-primary mb-4">
            Start with a 3-day Pro trial
          </h2>
          <p className="text-text-secondary mb-8">
            No card required. Cancel any time — drop to Free if you don't upgrade.
          </p>
          <Link
            to="/register"
            className="inline-block bg-bullish hover:bg-bullish/90 text-surface-0 font-semibold px-8 py-3 rounded-xl text-sm transition-all shadow-[0_0_20px_rgba(34,197,94,0.2)]"
          >
            Try free for 3 days
          </Link>
        </div>
      </section>
    </div>
  );
}
