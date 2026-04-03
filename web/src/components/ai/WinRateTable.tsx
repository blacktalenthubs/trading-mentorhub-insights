/** Reusable win rate display table. */

interface Props {
  data: Record<string, unknown>;
  title: string;
}

export default function WinRateTable({ data, title }: Props) {
  const entries = Object.entries(data);

  if (entries.length === 0) {
    return <p className="text-sm text-text-faint">No {title.toLowerCase()} data</p>;
  }

  return (
    <div>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-muted">{title}</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-text-muted">
              <th className="pb-2">Key</th>
              <th className="pb-2">Value</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([key, val]) => (
              <tr key={key} className="border-t border-border-subtle">
                <td className="py-1.5 text-text-secondary">{key}</td>
                <td className="py-1.5 font-mono text-text-primary">
                  {typeof val === "number" ? val.toFixed(1) : JSON.stringify(val)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
