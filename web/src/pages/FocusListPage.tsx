/** Trade Ideas — forward-looking ideas across three boards: Conviction (high-conviction
 *  names), Emerging (early momentum turns), and Long Term (growth leaders). Old
 *  /focus-list · /conviction · /dashboard routes redirect here (App.tsx).
 *
 *  AI Scans + Social Buzz were REMOVED (no longer part of the product) — this file used
 *  to host both as tabs; it's now a thin shell over the three remaining boards, each a
 *  TabView imported from its own page.
 */

import { useState } from "react";
import { Target, Gem, Compass, TrendingUp } from "lucide-react";
import { ConvictionTabView } from "./ConvictionPage";
import { GrowthLeadersTabView } from "./GrowthLeadersPage";
import { EmergingTabView } from "./EmergingLeadersPage";

type IdeasTab = "conviction" | "emerging" | "long_term";

const IDEAS_TABS: { id: IdeasTab; label: string; icon: typeof Target }[] = [
  { id: "conviction", label: "Conviction", icon: Gem },
  { id: "emerging", label: "Emerging", icon: Compass },
  { id: "long_term", label: "Long Term", icon: TrendingUp },
];

export default function FocusListPage() {
  const [tab, setTab] = useState<IdeasTab>(() => {
    if (typeof window === "undefined") return "conviction";
    // Deep-link from a notification tap: ?tab=emerging (or any valid Ideas tab).
    const valid: IdeasTab[] = ["conviction", "emerging", "long_term"];
    const q = new URLSearchParams(window.location.search).get("tab");
    if (q && valid.includes(q as IdeasTab)) return q as IdeasTab;
    const saved = localStorage.getItem("ideas_active_tab");
    return valid.includes(saved as IdeasTab) ? (saved as IdeasTab) : "conviction";  // drop legacy social/ai/day/swing
  });
  function pickTab(t: IdeasTab) {
    setTab(t);
    try { localStorage.setItem("ideas_active_tab", t); } catch { /* ignore */ }
  }

  return (
    <div className="h-full overflow-y-auto overflow-x-hidden bg-surface-0">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 py-5 space-y-4">
        {/* Header + tab bar */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Target className="h-5 w-5 text-accent" />
            <div>
              <h1 className="text-lg font-bold text-text-primary">Trade Ideas</h1>
              <p className="text-[11px] text-text-muted">
                High-conviction, emerging, and long-term ideas — what to look at this session.
              </p>
            </div>
          </div>
          <div className="flex bg-surface-2 rounded-lg p-0.5">
            {IDEAS_TABS.map((t) => {
              const Icon = t.icon;
              return (
                <button
                  key={t.id}
                  onClick={() => pickTab(t.id)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                    tab === t.id
                      ? "bg-surface-4 text-text-primary shadow-sm"
                      : "text-text-muted hover:text-text-secondary"
                  }`}
                >
                  <Icon className="h-3 w-3" />
                  {t.label}
                </button>
              );
            })}
          </div>
        </div>

        {tab === "conviction" && <ConvictionTabView />}
        {tab === "emerging" && <EmergingTabView />}
        {tab === "long_term" && <GrowthLeadersTabView />}
      </div>
    </div>
  );
}
