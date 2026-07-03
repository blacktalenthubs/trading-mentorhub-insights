/** Market clock + status pill for the Trading top strip.
 *
 *  A live ET clock (market time) + a ● MARKET OPEN / PREMARKET / CLOSED pill,
 *  driven by the existing useMarketStatus() hook. The clock ticks in its own
 *  isolated component so the once-a-second re-render never touches the page.
 *  Labeled ET so it's not confused with the CT alert timestamps.
 */

import { useEffect, useState } from "react";
import { useMarketStatus } from "../api/hooks";

function etNow(): string {
  return new Date().toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "America/New_York",
  });
}

export default function MarketClock() {
  const { data } = useMarketStatus();
  const [now, setNow] = useState(etNow);

  useEffect(() => {
    const t = setInterval(() => setNow(etNow()), 1000);
    return () => clearInterval(t);
  }, []);

  const phase = data?.is_premarket ? "premarket" : data?.is_open ? "open" : "closed";
  const pill =
    phase === "premarket"
      ? { text: "Premarket", cls: "bg-warning/12 text-warning-text border-warning/30", dot: "bg-warning" }
      : phase === "open"
      ? { text: "Market Open", cls: "bg-bullish/12 text-bullish-text border-bullish/30", dot: "bg-bullish" }
      : { text: "Closed", cls: "bg-surface-3 text-text-muted border-border-subtle", dot: "bg-text-faint" };

  return (
    <div className="flex items-center gap-2 shrink-0">
      <span className="font-mono text-[13px] font-bold text-text-secondary tabular-nums tracking-wide">
        {now}
        <span className="ml-0.5 text-[9px] font-normal text-text-faint">ET</span>
      </span>
      <span
        className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[10px] font-semibold uppercase tracking-wide ${pill.cls}`}
      >
        <span className={`h-1.5 w-1.5 rounded-full ${pill.dot} ${phase === "open" ? "animate-pulse" : ""}`} />
        {pill.text}
      </span>
    </div>
  );
}
