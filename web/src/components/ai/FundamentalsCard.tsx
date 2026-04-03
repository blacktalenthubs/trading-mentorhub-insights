/** Fundamentals display card. */

import Card from "../ui/Card";

interface Props {
  symbol: string;
  data: Record<string, unknown>;
}

export default function FundamentalsCard({ symbol, data }: Props) {
  const entries = Object.entries(data);

  if (entries.length === 0) {
    return (
      <Card title={`${symbol} Fundamentals`}>
        <p className="text-sm text-text-faint">No fundamentals data available</p>
      </Card>
    );
  }

  return (
    <Card title={`${symbol} Fundamentals`}>
      <div className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3">
        {entries.map(([key, val]) => (
          <div key={key}>
            <p className="text-xs text-text-muted">{key.replace(/_/g, " ")}</p>
            <p className="font-mono text-sm text-text-primary">
              {typeof val === "number"
                ? val > 1e9
                  ? `$${(val / 1e9).toFixed(1)}B`
                  : val > 1e6
                  ? `$${(val / 1e6).toFixed(1)}M`
                  : val.toFixed(2)
                : String(val ?? "—")}
            </p>
          </div>
        ))}
      </div>
    </Card>
  );
}
