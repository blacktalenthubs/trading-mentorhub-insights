/** GradeBadge — A/B/C conviction grade, same scale as the Signal Feed (TV alerts).
 *  A = high (vol + slope), B = one gate, C = baseline.
 */
export default function GradeBadge({ grade, title }: { grade?: string | null; title?: string }) {
  const g = (grade || "C").toUpperCase();
  const cls =
    g === "A"
      ? "text-bullish-text bg-bullish/10 border-bullish/20"
      : g === "B"
      ? "text-amber-400 bg-amber-400/10 border-amber-400/20"
      : "text-text-muted bg-surface-3 border-border-subtle";
  return (
    <span
      title={title}
      className={`inline-flex items-center justify-center w-5 h-5 text-[11px] font-bold rounded border ${cls} ${title ? "cursor-help" : ""}`}
    >
      {g}
    </span>
  );
}

export const GRADE_RANK: Record<string, number> = { A: 3, B: 2, C: 1 };
