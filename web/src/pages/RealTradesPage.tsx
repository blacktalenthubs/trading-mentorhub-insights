/** Performance — the EOD / strategy surface. Three tabs that each earn their keep:
 *  Today's EOD (close out positions + real outcomes), Strategy Analysis (per-pattern edge
 *  vs the full catalog), Declined (what you passed on). The old by-pattern / weekly / by-symbol
 *  / sessions tabs and their components were culled — they were unreachable (#64 Sub-spec E).
 */
import { useState } from "react";
import TodayEOD from "../components/TodayEOD";
import MyStrategy from "../components/MyStrategy";
import DeclinedTrades from "../components/DeclinedTrades";

type PerfTab = "today-eod" | "strategy" | "declined";

const PERF_TABS: { id: PerfTab; label: string }[] = [
  { id: "today-eod", label: "Today's EOD" },
  { id: "strategy",  label: "Strategy Analysis" },
  { id: "declined",  label: "Declined" },
];

export default function RealTradesPage() {
  const [activeTab, setActiveTab] = useState<PerfTab>(() => {
    if (typeof window === "undefined") return "today-eod";
    const saved = localStorage.getItem("perf_active_tab");
    return saved === "strategy" || saved === "declined" ? saved : "today-eod";
  });
  function pickTab(t: PerfTab) {
    setActiveTab(t);
    try { localStorage.setItem("perf_active_tab", t); } catch { /* ignore */ }
  }

  return (
    <div className="h-full overflow-y-auto p-5">
      <div className="max-w-[1400px] mx-auto flex flex-col gap-6">
        <div className="flex items-center gap-6 flex-wrap">
          <h1 className="text-xl font-bold text-text-primary">Performance</h1>
          <div className="flex bg-surface-2 rounded-lg p-0.5 flex-wrap">
            {PERF_TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => pickTab(t.id)}
                className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                  activeTab === t.id ? "bg-surface-4 text-text-primary shadow-sm" : "text-text-muted hover:text-text-secondary"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {activeTab === "today-eod" && <TodayEOD />}
        {activeTab === "strategy"  && <MyStrategy />}
        {activeTab === "declined"  && <DeclinedTrades />}
      </div>
    </div>
  );
}
