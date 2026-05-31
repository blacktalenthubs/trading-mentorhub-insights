/** Skeleton placeholder primitives.
 *
 *  Solves the "page flashes blank → data" jank that makes the app feel slow
 *  even when fetches are fast. Use these wherever a useQuery() is loading.
 *
 *  Patterns:
 *    <Skeleton h={20} />                    — single bar, full width
 *    <Skeleton w={60} h={14} />             — sized bar
 *    <SkeletonRow count={5} h={32} />       — repeated rows (lists/tables)
 *    <SkeletonCard rows={3} />              — a card-shaped block
 *
 *  Animation: subtle pulse via tailwind's `animate-pulse`. Same opacity
 *  range across all instances so a page-load looks uniform.
 */

interface SkeletonProps {
  /** Width — number = pixels, string = passes through (e.g. "100%", "12rem"). */
  w?: number | string;
  /** Height — number = pixels, string = passes through. */
  h?: number | string;
  /** Border-radius shorthand. "full" = pill. */
  rounded?: "none" | "sm" | "md" | "lg" | "full";
  /** Extra Tailwind classes. */
  className?: string;
}

const ROUNDED: Record<NonNullable<SkeletonProps["rounded"]>, string> = {
  none: "rounded-none",
  sm: "rounded-sm",
  md: "rounded-md",
  lg: "rounded-lg",
  full: "rounded-full",
};

export function Skeleton({ w = "100%", h = 16, rounded = "md", className = "" }: SkeletonProps) {
  const style: React.CSSProperties = {
    width: typeof w === "number" ? `${w}px` : w,
    height: typeof h === "number" ? `${h}px` : h,
  };
  return (
    <div
      style={style}
      className={`bg-surface-3/60 animate-pulse ${ROUNDED[rounded]} ${className}`}
      aria-hidden="true"
    />
  );
}

/** Repeated row skeleton — for table/list loading states. */
export function SkeletonRow({
  count = 4,
  h = 32,
  gap = 8,
  className = "",
}: {
  count?: number;
  h?: number;
  gap?: number;
  className?: string;
}) {
  return (
    <div
      className={`flex flex-col ${className}`}
      style={{ gap: `${gap}px` }}
      aria-hidden="true"
    >
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} h={h} />
      ))}
    </div>
  );
}

/** Card-shaped skeleton with a title bar + N content rows. */
export function SkeletonCard({ rows = 2, className = "" }: { rows?: number; className?: string }) {
  return (
    <div className={`bg-surface-1 border border-border-subtle rounded-xl p-4 space-y-2 ${className}`} aria-hidden="true">
      <Skeleton w="40%" h={16} />
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} h={12} />
      ))}
    </div>
  );
}

/** Centered "loading" presentation for full-section spinners.
 *  Uses the skeleton style instead of a spinning loader for visual consistency.
 */
export function SkeletonSection({ rows = 4, title }: { rows?: number; title?: string }) {
  return (
    <div className="space-y-3" aria-busy="true">
      {title && <Skeleton w="30%" h={14} />}
      <SkeletonRow count={rows} h={40} />
    </div>
  );
}
