/** Public Replay Page — shareable trade replay at /replay/:alertId.
 *
 *  No auth required for viewing. Uses StaticTradeChart for a clean
 *  quick-look chart with entry/stop/T1/T2 horizontal lines, alert/outcome
 *  markers, and the trade stats above the chart.
 *
 *  Previously used ChartReplay (cinematic candle-by-candle playback) —
 *  swapped 2026-05-14 for the static view which is faster to evaluate
 *  and better for sharing.
 */

import { useParams } from "react-router-dom";
import StaticTradeChart from "../components/StaticTradeChart";

export default function ReplayPage() {
  const { alertId } = useParams();
  const id = parseInt(alertId || "0", 10);

  if (!id) {
    return (
      <div className="min-h-screen bg-surface-0 flex items-center justify-center">
        <p className="text-text-muted">Invalid replay link</p>
      </div>
    );
  }

  return <StaticTradeChart alertId={id} />;
}
