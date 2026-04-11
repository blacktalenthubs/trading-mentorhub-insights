/** Pattern Library — grid of all trading patterns with difficulty badges.
 *  Clicking a pattern fetches deep-dive education from the learn API. */

import { useState } from "react";
import { Capacitor } from "@capacitor/core";
import { BookOpen, CheckCircle, XCircle, ChevronLeft, Loader2 } from "lucide-react";

const API_HOST = Capacitor.isNativePlatform()
  ? String(import.meta.env.VITE_API_URL || "https://api.aicopilottrader.com")
  : "";

/* ── Pattern definitions ─────────────────────────────────────────── */

const PATTERNS = [
  { key: "pdl_bounce", name: "PDL Bounce", category: "Support", difficulty: "Beginner", desc: "Price tests yesterday's low and holds", icon: "🟢", learnId: "prior_day_low_bounce" },
  { key: "pdl_reclaim", name: "PDL Reclaim", category: "Support", difficulty: "Beginner", desc: "Price dips below PDL then recovers", icon: "🟢", learnId: "prior_day_low_reclaim" },
  { key: "vwap_hold", name: "VWAP Hold", category: "Support", difficulty: "Beginner", desc: "Pullback to VWAP that holds", icon: "🟢", learnId: "vwap_bounce" },
  { key: "vwap_reclaim", name: "VWAP Reclaim", category: "Reversal", difficulty: "Intermediate", desc: "Crosses above VWAP — momentum shift", icon: "🔄", learnId: "vwap_reclaim" },
  { key: "session_low_double_bottom", name: "Double Bottom", category: "Support", difficulty: "Beginner", desc: "Two tests of same low, holds", icon: "🟢", learnId: "session_low_double_bottom" },
  { key: "ma_bounce", name: "MA Bounce", category: "Support", difficulty: "Intermediate", desc: "Bounces off 50/100/200 MA", icon: "🟢", learnId: "ma_bounce_50" },
  { key: "pdh_breakout", name: "PDH Breakout", category: "Breakout", difficulty: "Intermediate", desc: "Breaks above yesterday's high", icon: "🔵", learnId: "prior_day_high_breakout" },
  { key: "pdh_rejection", name: "PDH Rejection", category: "Resistance", difficulty: "Beginner", desc: "Fails at yesterday's high", icon: "🔴", learnId: "pdh_failed_breakout" },
  { key: "session_high_double_top", name: "Double Top", category: "Resistance", difficulty: "Intermediate", desc: "Tests session high twice, fails", icon: "🔴", learnId: "session_high_double_top" },
  { key: "vwap_loss", name: "VWAP Loss", category: "Reversal", difficulty: "Beginner", desc: "Drops below VWAP — bearish", icon: "🔴", learnId: "vwap_loss" },
  { key: "inside_day_breakout", name: "Inside Day", category: "Breakout", difficulty: "Advanced", desc: "Tight range → expansion", icon: "🔵", learnId: "inside_day_breakout" },
  { key: "fib_bounce", name: "Fib Bounce", category: "Support", difficulty: "Advanced", desc: "Bounce at 50%/61.8% level", icon: "🟢", learnId: "intraday_support_bounce" },
  { key: "gap_and_go", name: "Gap & Go", category: "Momentum", difficulty: "Advanced", desc: "Gap up + holds VWAP", icon: "🔵", learnId: "gap_fill" },
  { key: "ema_rejection", name: "EMA Rejection", category: "Resistance", difficulty: "Intermediate", desc: "Rejected at falling EMA", icon: "🔴", learnId: "ema_rejection_short" },
];

const DIFFICULTY_COLORS: Record<string, string> = {
  Beginner: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  Intermediate: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  Advanced: "bg-purple-500/10 text-purple-400 border-purple-500/20",
};

const CATEGORY_COLORS: Record<string, string> = {
  Support: "text-emerald-400",
  Resistance: "text-red-400",
  Breakout: "text-blue-400",
  Reversal: "text-yellow-400",
  Momentum: "text-purple-400",
};

/* ── Education detail type ───────────────────────────────────────── */

interface PatternDetail {
  name: string;
  tagline: string;
  difficulty: string;
  what_it_is: string;
  how_to_identify: string[];
  why_it_works: string;
  when_it_fails: string;
  common_mistakes: string[];
  pro_tips: string[];
}

/* ── Component ───────────────────────────────────────────────────── */

interface Props {
  onSelect?: (patternKey: string) => void;
}

export default function PatternLibrary({ onSelect }: Props) {
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<PatternDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSelect = async (patternKey: string, learnId: string) => {
    onSelect?.(patternKey);

    if (selected === patternKey) {
      setSelected(null);
      setDetail(null);
      return;
    }

    setSelected(patternKey);
    setDetail(null);
    setError("");
    setLoading(true);

    try {
      const res = await fetch(`${API_HOST}/api/v1/learn/patterns/${learnId}`);
      if (!res.ok) throw new Error("Pattern not found");
      const data = await res.json();
      setDetail(data);
    } catch {
      setError("Could not load pattern details");
    } finally {
      setLoading(false);
    }
  };

  const selectedPattern = PATTERNS.find((p) => p.key === selected);

  return (
    <div className="rounded-xl border border-border-subtle bg-surface-1 p-5">
      <h3 className="text-sm font-bold text-text-primary mb-3">Pattern Library</h3>
      <p className="text-xs text-text-muted mb-4">
        Learn to recognize these setups. Click any pattern for a detailed explanation.
      </p>

      {/* ── Grid ── */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
        {PATTERNS.map((p) => (
          <button
            key={p.key}
            onClick={() => handleSelect(p.key, p.learnId)}
            className={`text-left bg-surface-2/40 border rounded-lg p-3 transition-colors ${
              selected === p.key
                ? "border-accent/50 bg-accent/5"
                : "border-border-subtle/60 hover:border-accent/20"
            }`}
          >
            <div className="flex items-center gap-1.5 mb-1">
              <span className="text-sm">{p.icon}</span>
              <span className="text-[11px] font-bold text-text-primary truncate">{p.name}</span>
            </div>
            <div className="flex items-center gap-1.5 mb-1.5">
              <span className={`text-[9px] ${CATEGORY_COLORS[p.category] || "text-text-muted"}`}>
                {p.category}
              </span>
              <span className={`text-[8px] font-semibold px-1.5 py-0.5 rounded border ${DIFFICULTY_COLORS[p.difficulty]}`}>
                {p.difficulty}
              </span>
            </div>
            <p className="text-[10px] text-text-muted leading-tight line-clamp-2">{p.desc}</p>
          </button>
        ))}
      </div>

      {/* ── Education Detail Panel ── */}
      {selected && (
        <div className="mt-4 rounded-xl border border-accent/20 bg-surface-2/40 p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <BookOpen className="h-4 w-4 text-accent" />
              <h3 className="text-sm font-bold text-text-primary">
                {selectedPattern?.icon} {selectedPattern?.name}
              </h3>
            </div>
            <button
              onClick={() => { setSelected(null); setDetail(null); }}
              className="flex items-center gap-1 text-xs text-text-muted hover:text-text-secondary transition-colors"
            >
              <ChevronLeft className="h-3 w-3" />
              Close
            </button>
          </div>

          {loading && (
            <div className="flex items-center gap-2 text-xs text-text-muted py-4">
              <Loader2 className="h-4 w-4 animate-spin text-accent" />
              Loading pattern details...
            </div>
          )}

          {error && (
            <p className="text-xs text-red-400">{error}</p>
          )}

          {detail && (
            <div className="space-y-4">
              {/* Tagline */}
              <p className="text-[13px] text-text-secondary italic">{detail.tagline}</p>

              {/* What It Is */}
              <div className="space-y-1.5">
                <h4 className="text-[10px] font-bold uppercase tracking-wider text-accent">What Is It?</h4>
                <p className="text-[13px] text-text-secondary leading-relaxed">{detail.what_it_is}</p>
              </div>

              {/* How to Identify */}
              {detail.how_to_identify.length > 0 && (
                <div className="space-y-1.5">
                  <h4 className="text-[10px] font-bold uppercase tracking-wider text-emerald-400">How to Identify</h4>
                  <div className="space-y-1">
                    {detail.how_to_identify.map((item, i) => (
                      <div key={i} className="flex items-start gap-2">
                        <CheckCircle className="h-3.5 w-3.5 text-emerald-400 mt-0.5 shrink-0" />
                        <span className="text-[13px] text-text-secondary">{item}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Why It Works */}
              <div className="space-y-1.5">
                <h4 className="text-[10px] font-bold uppercase tracking-wider text-yellow-400">Why It Works</h4>
                <p className="text-[13px] text-text-secondary leading-relaxed whitespace-pre-line">{detail.why_it_works}</p>
              </div>

              {/* When It Fails */}
              <div className="space-y-1.5">
                <h4 className="text-[10px] font-bold uppercase tracking-wider text-red-400">When It Fails</h4>
                <div className="flex items-start gap-2">
                  <XCircle className="h-3.5 w-3.5 text-red-400 mt-0.5 shrink-0" />
                  <span className="text-[13px] text-text-secondary">{detail.when_it_fails}</span>
                </div>
              </div>

              {/* Common Mistakes */}
              {detail.common_mistakes.length > 0 && (
                <div className="space-y-1.5">
                  <h4 className="text-[10px] font-bold uppercase tracking-wider text-orange-400">Common Mistakes</h4>
                  <ul className="space-y-1">
                    {detail.common_mistakes.map((m, i) => (
                      <li key={i} className="text-[12px] text-text-muted flex items-start gap-1.5">
                        <span className="text-orange-400 mt-0.5">•</span>
                        {m}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Pro Tips */}
              {detail.pro_tips.length > 0 && (
                <div className="space-y-1.5">
                  <h4 className="text-[10px] font-bold uppercase tracking-wider text-blue-400">Pro Tips</h4>
                  <ul className="space-y-1">
                    {detail.pro_tips.map((t, i) => (
                      <li key={i} className="text-[12px] text-text-muted flex items-start gap-1.5">
                        <span className="text-blue-400 mt-0.5">★</span>
                        {t}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
