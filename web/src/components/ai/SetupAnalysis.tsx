/** Setup analysis display (daily/weekly/MTF). */

import Card from "../ui/Card";

interface Props {
  symbol: string;
  timeframe: string;
  analysis: Record<string, unknown>;
}

export default function SetupAnalysisView({ symbol, timeframe, analysis }: Props) {
  const entries = Object.entries(analysis);

  if (entries.length === 0) {
    return (
      <Card title={`${symbol} — ${timeframe}`}>
        <p className="text-sm text-text-faint">No analysis data</p>
      </Card>
    );
  }

  return (
    <Card title={`${symbol} — ${timeframe}`}>
      <div className="space-y-2">
        {entries.map(([key, val]) => (
          <div key={key} className="flex justify-between text-sm">
            <span className="text-text-muted">{key.replace(/_/g, " ")}</span>
            <span className="font-mono text-text-primary">
              {typeof val === "number" ? val.toFixed(2) : typeof val === "object" ? JSON.stringify(val) : String(val ?? "—")}
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}
