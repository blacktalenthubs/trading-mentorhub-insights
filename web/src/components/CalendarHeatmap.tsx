/** Calendar heatmap showing daily P&L (green/red intensity). */

import { useMemo } from "react";

interface DayData {
  date: string; // YYYY-MM-DD
  pnl: number;
}

interface Props {
  data: DayData[];
}

function getColor(pnl: number, maxAbs: number): string {
  if (pnl === 0) return "#1a2332";
  const intensity = Math.min(Math.abs(pnl) / maxAbs, 1);
  if (pnl > 0) {
    const g = Math.round(34 + intensity * 150);
    return `rgb(20, ${g}, 40)`;
  }
  const r = Math.round(60 + intensity * 150);
  return `rgb(${r}, 20, 20)`;
}

export default function CalendarHeatmap({ data }: Props) {
  const { months, maxAbs } = useMemo(() => {
    const byMonth: Record<string, DayData[]> = {};
    let max = 1;
    for (const d of data) {
      const m = d.date.slice(0, 7);
      if (!byMonth[m]) byMonth[m] = [];
      byMonth[m].push(d);
      max = Math.max(max, Math.abs(d.pnl));
    }
    const sorted = Object.entries(byMonth).sort(([a], [b]) => b.localeCompare(a));
    return { months: sorted, maxAbs: max };
  }, [data]);

  if (!data.length) {
    return <p className="text-sm text-text-faint">No trade data for heatmap</p>;
  }

  return (
    <div className="space-y-4">
      {months.slice(0, 6).map(([month, days]) => (
        <div key={month}>
          <p className="mb-1 text-xs font-medium text-text-muted">{month}</p>
          <div className="flex flex-wrap gap-1">
            {days.map((d) => (
              <div
                key={d.date}
                title={`${d.date}: $${d.pnl.toFixed(0)}`}
                className="h-4 w-4 rounded-sm"
                style={{ backgroundColor: getColor(d.pnl, maxAbs) }}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
