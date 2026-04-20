/** Pure-SVG sparkline. Lightweight — no chart library. */

interface SparkProps {
  data: number[];
  up?: boolean;
  width?: number;
  height?: number;
  className?: string;
  strokeWidth?: number;
}

export default function Spark({
  data,
  up = true,
  width = 60,
  height = 20,
  className,
  strokeWidth = 1.2,
}: SparkProps) {
  if (!data || data.length < 2) {
    return (
      <svg
        className={className}
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        style={{ width, height }}
      />
    );
  }

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const pts = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * width;
      const y = height - ((v - min) / range) * (height - 2) - 1;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(' ');

  const color = up ? 'var(--color-bullish-text)' : 'var(--color-bearish-text)';

  return (
    <svg
      className={className}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      style={{ width, height }}
    >
      <polyline
        points={pts}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Deterministic pseudo-random sparkline data, seeded by a string.
 *  Useful when a real intraday series isn't available.
 */
export function seededSpark(seed: string, n = 20, bias = 0): number[] {
  let s = 0;
  for (let i = 0; i < seed.length; i++) {
    s = ((s * 31) + seed.charCodeAt(i)) | 0;
  }
  const rand = () => {
    s = (s * 9301 + 49297) & 0x7fffffff;
    return s / 0x7fffffff;
  };
  const out: number[] = [];
  let v = 50;
  for (let i = 0; i < n; i++) {
    v += (rand() - 0.5 + bias * 0.08) * 5;
    out.push(v);
  }
  return out;
}
