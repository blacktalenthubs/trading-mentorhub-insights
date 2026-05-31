/** ScreenerTable — shared pro screener table used across Trade Ideas tabs (spec 62).
 *  Desktop: dense sortable table. Mobile: card rows via `mobileRow`. Handles
 *  sort state, loading skeleton, error, and empty states.
 */

import { useMemo, useState, type ReactNode } from "react";
import { ChevronRight, ChevronUp, ChevronDown } from "lucide-react";

export interface Column<T> {
  key: string;
  label: string;
  align?: "left" | "right";
  /** Provide to make the column sortable. */
  value?: (row: T) => number | string;
  render: (row: T) => ReactNode;
  /** Extra th/td classes (width, responsive hiding e.g. "hidden xl:table-cell"). */
  cls?: string;
}

interface Props<T> {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  defaultSort?: { key: string; dir: "asc" | "desc" };
  mobileRow: (row: T) => ReactNode;
  isLoading?: boolean;
  isError?: boolean;
  errorText?: string;
  empty?: ReactNode;
}

function SkeletonRows() {
  return (
    <div className="p-3 space-y-px">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="h-11 bg-surface-1/60 animate-pulse rounded" />
      ))}
    </div>
  );
}

export default function ScreenerTable<T>({
  rows, columns, rowKey, onRowClick, defaultSort, mobileRow,
  isLoading, isError, errorText, empty,
}: Props<T>) {
  const [sort, setSort] = useState<{ key: string; dir: "asc" | "desc" } | null>(defaultSort ?? null);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.value) return rows;
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const av = col.value!(a), bv = col.value!(b);
      if (typeof av === "string" || typeof bv === "string") return String(av).localeCompare(String(bv)) * dir;
      return ((av as number) - (bv as number)) * dir;
    });
  }, [rows, sort, columns]);

  function toggle(c: Column<T>) {
    if (!c.value) return;
    setSort((s) => (s && s.key === c.key ? { key: c.key, dir: s.dir === "asc" ? "desc" : "asc" } : { key: c.key, dir: "desc" }));
  }

  const shell = "bg-surface-1 border border-border-subtle rounded-xl overflow-hidden";

  if (isLoading) return <div className={shell}><SkeletonRows /></div>;
  if (isError) return <div className={shell}><p className="py-16 text-center text-sm text-bearish-text">{errorText ?? "Couldn't load this list."}</p></div>;
  if (sorted.length === 0) return <div className={shell}>{empty}</div>;

  return (
    <div className={shell}>
      {/* Desktop table */}
      <table className="hidden md:table w-full text-sm">
        <thead>
          <tr className="border-b border-border-subtle text-[11px] uppercase tracking-wider text-text-faint">
            {columns.map((c) => {
              const active = sort?.key === c.key;
              return (
                <th
                  key={c.key}
                  onClick={() => toggle(c)}
                  className={`py-2.5 px-3 font-semibold select-none ${c.value ? "cursor-pointer hover:text-text-secondary" : ""} ${c.align === "right" ? "text-right" : "text-left"} ${c.cls ?? ""}`}
                >
                  <span className={`inline-flex items-center gap-1 ${c.align === "right" ? "justify-end" : ""}`}>
                    {c.label}
                    {active && (sort!.dir === "asc" ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />)}
                  </span>
                </th>
              );
            })}
            <th className="w-8" />
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr
              key={rowKey(r)}
              onClick={() => onRowClick?.(r)}
              className={`border-b border-border-subtle/40 last:border-0 transition-colors ${onRowClick ? "hover:bg-surface-2/50 cursor-pointer" : ""}`}
            >
              {columns.map((c) => (
                <td key={c.key} className={`py-2.5 px-3 ${c.align === "right" ? "text-right" : "text-left"} ${c.cls ?? ""}`}>
                  {c.render(r)}
                </td>
              ))}
              <td className="py-2.5 px-2 text-right">{onRowClick && <ChevronRight className="h-4 w-4 text-text-faint" />}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Mobile cards */}
      <div className="md:hidden divide-y divide-border-subtle/40">
        {sorted.map((r) => (
          <button key={rowKey(r)} onClick={() => onRowClick?.(r)} className="w-full text-left px-4 py-3 hover:bg-surface-2/40 transition-colors">
            {mobileRow(r)}
          </button>
        ))}
      </div>
    </div>
  );
}
